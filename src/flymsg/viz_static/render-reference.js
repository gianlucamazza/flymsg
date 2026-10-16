// Opt-in diagnostic captures. No simulation state or renderer is created here.
export async function sha256(array) {
  const bytes = new Uint8Array(
    array.buffer,
    array.byteOffset,
    array.byteLength,
  );
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}

export function base64(bytes) {
  let text = "";
  for (let i = 0; i < bytes.length; i += 8192)
    text += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(text);
}

/** Hash before the asynchronous digest, so later buffer updates cannot alter the reference. */
export async function geometryInventory(objects) {
  const rows = [];
  for (const o of objects) {
    if (!o.geometry) continue;
    const g = o.geometry;
    const attrs = Object.fromEntries(
      Object.entries(g.attributes).map(([k, a]) => [
        k,
        {
          type: a.array.constructor.name,
          itemSize: a.itemSize,
          bytes: a.array.slice(),
        },
      ]),
    );
    const index = g.index?.array.slice();
    rows.push({
      name: o.name,
      type: o.type,
      matrix: o.matrixWorld.toArray(),
      visible: o.visible,
      range: { ...g.drawRange },
      attrs,
      index,
    });
  }
  for (const row of rows) {
    for (const a of Object.values(row.attrs)) {
      a.sha256 = await sha256(a.bytes);
      a.byteLength = a.bytes.byteLength;
      delete a.bytes;
    }
    row.index = row.index
      ? { sha256: await sha256(row.index), byteLength: row.index.byteLength }
      : null;
  }
  return rows;
}

/** Raw RGBA8, bottom-left origin. Caller freezes replay and supplies colour/id/depth passes. */
export function capturePasses(
  THREE,
  renderer,
  world,
  camera,
  passes,
  width,
  height,
  render = () => renderer.render(world, camera),
) {
  if (renderer.xr.isPresenting)
    throw new Error(
      "Capture explicit eye cameras outside an active XR session",
    );
  if (![width, height].every((v) => Number.isInteger(v) && v > 0 && v <= 4096))
    throw new RangeError("Reference dimensions must be integers in 1..4096");
  const target = new THREE.WebGLRenderTarget(width, height, {
    depthBuffer: true,
  });
  const saved = {
    target: renderer.getRenderTarget(),
    clear: renderer.getClearColor(new THREE.Color()),
    alpha: renderer.getClearAlpha(),
    viewport: renderer.getViewport(new THREE.Vector4()),
    scissor: renderer.getScissor(new THREE.Vector4()),
    scissorTest: renderer.getScissorTest(),
    background: world.background,
    override: world.overrideMaterial,
    shaderError: renderer.debug.onShaderError,
  };
  const out = {};
  try {
    renderer.debug.onShaderError = () => {
      throw new Error("Reference shader compilation failed");
    };
    for (const [name, install] of Object.entries(passes)) {
      let restore;
      try {
        restore = install();
        renderer.setRenderTarget(target);
        renderer.setViewport(0, 0, width, height);
        renderer.setScissorTest(false);
        renderer.clear();
        render(name);
        const pixels = new Uint8Array(4 * width * height);
        renderer.readRenderTargetPixels(target, 0, 0, width, height, pixels);
        out[name] = pixels;
      } finally {
        restore?.();
      }
    }
  } finally {
    world.background = saved.background;
    world.overrideMaterial = saved.override;
    renderer.debug.onShaderError = saved.shaderError;
    renderer.setRenderTarget(saved.target);
    renderer.setViewport(saved.viewport);
    renderer.setScissor(saved.scissor);
    renderer.setScissorTest(saved.scissorTest);
    renderer.setClearColor(saved.clear, saved.alpha);
    target.dispose();
  }
  return out;
}

/** Read the actual full-quality desktop framebuffer; do not resize or tune it. */
export function captureDesktopPixels(THREE, renderer, draw) {
  const gl = renderer.getContext();
  if (renderer.xr.isPresenting || gl.isContextLost())
    throw new Error("Desktop context required");
  const width = renderer.domElement.width,
    height = renderer.domElement.height;
  const saved = {
    target: renderer.getRenderTarget(),
    viewport: renderer.getViewport(new THREE.Vector4()),
    scissor: renderer.getScissor(new THREE.Vector4()),
    scissorTest: renderer.getScissorTest(),
    clear: renderer.getClearColor(new THREE.Color()),
    alpha: renderer.getClearAlpha(),
    shaderError: renderer.debug.onShaderError,
  };
  try {
    renderer.debug.onShaderError = () => {
      throw new Error("Desktop reference shader compilation failed");
    };
    renderer.setRenderTarget(null);
    renderer.setViewport(0, 0, width, height);
    renderer.setScissorTest(false);
    draw();
    renderer.setRenderTarget(null);
    const pixels = new Uint8Array(4 * width * height);
    gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    if (gl.isContextLost() || gl.getError() !== gl.NO_ERROR)
      throw new Error("Desktop reference readback failed");
    return { width, height, pixels };
  } finally {
    renderer.debug.onShaderError = saved.shaderError;
    renderer.setRenderTarget(saved.target);
    renderer.setViewport(saved.viewport);
    renderer.setScissor(saved.scissor);
    renderer.setScissorTest(saved.scissorTest);
    renderer.setClearColor(saved.clear, saved.alpha);
  }
}
