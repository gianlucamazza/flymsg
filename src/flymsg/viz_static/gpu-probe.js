// Diagnostic only. Serialized wall time includes CPU submission, browser/driver
// IPC and full framebuffer readback. NOT a GPU timer, frame cadence or XR qualification.
// The reference geometry, camera and activity stay fixed across all variants.
export function serializedGpuProbe(
  view,
  { sizes = [256, 512, 1024], warmup = 2, repeats = 5 } = {},
) {
  const { THREE, renderer, world, camera, skeletons } = view;
  const material = Array.isArray(skeletons.material)
    ? skeletons.material[0]
    : skeletons.material;
  if (
    !material ||
    (Array.isArray(skeletons.material) && skeletons.material.length !== 1)
  )
    throw new Error("Probe requires one shared line material");
  if (renderer.xr.isPresenting)
    throw new Error("Probe requires a non-immersive context");
  if (
    !sizes.length ||
    !sizes.every((s) => Number.isInteger(s) && s > 0 && s <= 2048) ||
    !Number.isInteger(warmup) ||
    warmup < 1 ||
    warmup > 5 ||
    !Number.isInteger(repeats) ||
    repeats < 1 ||
    repeats > 10
  )
    throw new RangeError("Invalid bounded probe configuration");
  const gl = renderer.getContext();
  if (gl.isContextLost()) throw new Error("Context lost before probe");
  const saved = {
    target: renderer.getRenderTarget(),
    viewport: renderer.getViewport(new THREE.Vector4()),
    scissor: renderer.getScissor(new THREE.Vector4()),
    scissorTest: renderer.getScissorTest(),
    discard: gl.isEnabled(gl.RASTERIZER_DISCARD),
    shader: material.vertexShader,
    shaderError: renderer.debug.onShaderError,
  };
  const minimalVertex = `varying vec3 vColor; varying float vOn;
    void main(){vColor=vec3(1.0);vOn=1.0;
      gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
  const records = [];
  const observerState = view.diagnosticState?.();
  if (observerState)
    view.diagnostic({
      ...observerState,
      suspended: true,
      playing: false,
      continuous: false,
    });
  try {
    renderer.debug.onShaderError = () => {
      throw new Error("Probe shader compilation failed");
    };
    world.updateMatrixWorld(true);
    camera.updateMatrixWorld(true);
    for (const size of sizes) {
      const target = new THREE.WebGLRenderTarget(size, size, {
        depthBuffer: true,
        samples: 0,
      });
      const pixels = new Uint8Array(4 * size * size);
      try {
        renderer.setRenderTarget(target);
        renderer.setViewport(0, 0, size, size);
        renderer.setScissorTest(false);
        // A/B/C/A order retains a post-probe full-render reference for drift.
        for (const mode of [
          "clear-readback",
          "full",
          "raster-discard",
          "raster-discard-minimal-line-vertex",
          "full-repeat",
        ]) {
          const discard = mode.startsWith("raster-discard");
          gl[discard ? "enable" : "disable"](gl.RASTERIZER_DISCARD);
          material.vertexShader =
            mode === "raster-discard-minimal-line-vertex"
              ? minimalVertex
              : saved.shader;
          material.needsUpdate = true;
          const wall = [];
          let draws;
          for (let i = 0; i < warmup + repeats; i++) {
            if (gl.isContextLost())
              throw new Error("Context lost during probe");
            // Best effort only: the previous iteration's readback, not finish,
            // establishes completion before measured iterations.
            gl.finish();
            renderer.info.reset();
            const started = performance.now();
            // Clear is ignored with rasterizer discard enabled. Always clear
            // first, so discarded draws cannot read the previous full image.
            gl.disable(gl.RASTERIZER_DISCARD);
            renderer.clear();
            gl[discard ? "enable" : "disable"](gl.RASTERIZER_DISCARD);
            if (mode !== "clear-readback") {
              if (view.renderScene) view.renderScene(camera);
              else if (view.paged)
                throw new Error(
                  "Paged diagnostic render entrypoint unavailable",
                );
              else renderer.render(world, camera);
            }
            // A finish call alone did not demonstrate GPU completion on Quest.
            // Read EVERY pixel to require fresh results from the whole target.
            renderer.readRenderTargetPixels(target, 0, 0, size, size, pixels);
            if (gl.isEnabled(gl.RASTERIZER_DISCARD) !== discard)
              throw new Error(
                "Unexpected rasterizer state change; probe invalid",
              );
            const elapsed = performance.now() - started;
            if (i >= warmup) wall.push(elapsed);
            draws = { ...renderer.info.render };
          }
          const nonUniform = pixels.some((v, i) => v !== pixels[i % 4]);
          if ((mode === "full" || mode === "full-repeat") && !nonUniform)
            throw new Error(
              "No non-uniform rendered-content witness; probe invalid",
            );
          if (mode.startsWith("raster-discard") && nonUniform)
            throw new Error(
              "Raster discard did not produce the expected clear image",
            );
          records.push({
            size,
            mode,
            serialized_wall_ms: wall,
            draws,
            non_uniform_readback: nonUniform,
            readback_bytes: pixels.byteLength,
          });
        }
      } finally {
        target.dispose();
      }
    }
    return {
      schema: "flymsg.serialized-render-probe/v2",
      renderer_pipeline: view.paged ? "immutable-pages" : "original",
      application_loop_suspended: !!observerState,
      records,
      warmup,
      repeats,
      metric:
        "CPU wall including submission, driver IPC and full RGBA8 readback; not GPU timer",
      pipeline:
        "offscreen direct render, zero MSAA, no composer, fixed projection",
      qualification: "not-scored; altered shaders/discard are diagnostic only",
      camera_world: camera.matrixWorld.toArray(),
      projection: camera.projectionMatrix.toArray(),
    };
  } finally {
    material.vertexShader = saved.shader;
    material.needsUpdate = true;
    renderer.debug.onShaderError = saved.shaderError;
    gl[saved.discard ? "enable" : "disable"](gl.RASTERIZER_DISCARD);
    renderer.setRenderTarget(saved.target);
    renderer.setViewport(saved.viewport);
    renderer.setScissor(saved.scissor);
    renderer.setScissorTest(saved.scissorTest);
    if (observerState) view.diagnostic(observerState);
  }
}
