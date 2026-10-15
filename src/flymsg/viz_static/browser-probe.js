// Bounded direct-render diagnostic. This is not an XR or requestAnimationFrame trial.
export async function browserProbe(
  view,
  { seconds = 8, size = 512, pipeline = "direct" } = {},
) {
  if (
    !Number.isInteger(seconds) ||
    seconds < 2 ||
    seconds > 20 ||
    !Number.isInteger(size) ||
    size < 32 ||
    size > 1024
  )
    throw new RangeError("Invalid bounded browser diagnostic");
  if (!["direct", "desktop"].includes(pipeline))
    throw new RangeError("Unknown browser pipeline");
  const { renderer: r, THREE: T, world, camera } = view;
  if (r.xr.isPresenting || view.fidelity().status !== "ready")
    throw Error("Complete non-immersive observer required");
  const gl = r.getContext(),
    ext = gl.getExtension("WEBGL_debug_renderer_info");
  const capabilities = {
    user_agent: navigator.userAgent,
    renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null,
    vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null,
    context: gl.getContextAttributes(),
    extensions: gl.getSupportedExtensions(),
    hardware_concurrency: navigator.hardwareConcurrency,
    device_pixel_ratio: devicePixelRatio,
    document_visibility: document.visibilityState,
  };
  const target = r.getRenderTarget(),
    viewport = r.getViewport(new T.Vector4()),
    scissor = r.getScissor(new T.Vector4()),
    scissorTest = r.getScissorTest();
  const originalSize = r.getSize(new T.Vector2()),
    pixelRatio = r.getPixelRatio();
  const originalProjection = camera.projectionMatrix.clone(),
    originalInverse = camera.projectionMatrixInverse.clone(),
    originalAspect = camera.aspect;
  if (
    pipeline === "desktop" &&
    (view.composer.readBuffer.width !==
      Math.floor(originalSize.x * pixelRatio) ||
      view.composer.readBuffer.height !==
        Math.floor(originalSize.y * pixelRatio))
  )
    throw Error("Composer and renderer dimensions differ");
  const saved = view.diagnostic({
    time: 20,
    playing: false,
    continuous: false,
    pageCulling: false,
  });
  const rt = new T.WebGLRenderTarget(size, size, {
    samples: 0,
    depthBuffer: true,
  });
  const pixels = new Uint8Array(size * size * 4),
    records = [];
  const c = camera.clone();
  c.aspect = 1;
  c.updateProjectionMatrix();
  c.updateMatrixWorld(true);
  const uploads = [];
  const originals = {
    bufferData: gl.bufferData,
    bufferSubData: gl.bufferSubData,
  };
  let phase = "reference-before";
  for (const [name, original] of Object.entries(originals))
    gl[name] = function (...args) {
      const source = args[name === "bufferData" ? 1 : 2];
      const bytes =
        typeof source === "number"
          ? source
          : args.length >= 4 && name === "bufferSubData"
            ? (args[4] ?? source.length - args[3]) * source.BYTES_PER_ELEMENT
            : (source?.byteLength ?? 0);
      const started = performance.now();
      const result = original.apply(this, args);
      uploads.push({
        phase,
        operation: name,
        target: args[0],
        bytes,
        submission_ms: performance.now() - started,
      });
      return result;
    };
  const tasks = [];
  let observer;
  try {
    observer = new PerformanceObserver((list) =>
      tasks.push(
        ...list
          .getEntries()
          .map((e) => ({ start: e.startTime, duration: e.duration })),
      ),
    );
    observer.observe({ type: "longtask", buffered: false });
  } catch {
    /* Unavailable counters stay unavailable. */
  }
  let completed = false;
  try {
    // The reference updates real activity and independently witnesses all anatomy.
    const before = await view.reference({
      width: 32,
      height: 32,
      time: 20,
      culling: false,
    });
    view.scheduleLines(null);
    if (pipeline === "desktop") {
      camera.aspect = 1;
      camera.updateProjectionMatrix();
      r.setPixelRatio(1);
      r.setSize(size, size, false);
      view.composer.setPixelRatio(1);
      view.composer.setSize(size, size);
    }
    phase = "dense-steady";
    const workloadStartedAt = new Date().toISOString();
    const started = performance.now();
    while (performance.now() - started < seconds * 1000) {
      const begin = performance.now();
      r.info.reset();
      r.setRenderTarget(rt);
      r.setViewport(0, 0, size, size);
      r.setScissorTest(false);
      if (pipeline === "direct") {
        r.render(world, c);
        r.readRenderTargetPixels(rt, 0, 0, size, size, pixels);
      } else {
        r.setRenderTarget(null);
        view.composer.render();
        gl.readPixels(0, 0, size, size, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      }
      records.push({
        start_ms: begin - started,
        serialized_wall_ms: performance.now() - begin,
        calls: r.info.render.calls,
        lines: r.info.render.lines,
        triangles: r.info.render.triangles,
      });
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    const workloadEndedAt = new Date().toISOString();
    const nonuniform = pixels.some((v, i) => v !== pixels[i % 4]);
    if (!nonuniform) throw Error("Diagnostic has no nonuniform colour witness");
    camera.aspect = originalAspect;
    camera.projectionMatrix.copy(originalProjection);
    camera.projectionMatrixInverse.copy(originalInverse);
    phase = "reference-after";
    const after = await view.reference({
      width: 32,
      height: 32,
      time: 20,
      culling: false,
    });
    if (JSON.stringify(before) !== JSON.stringify(after))
      throw Error("Source reference changed during trial");
    completed = true;
    return {
      schema: "flymsg.browser-probe/v1",
      capabilities,
      pipeline,
      workload_started_at: workloadStartedAt,
      workload_ended_at: workloadEndedAt,
      records,
      long_tasks: tasks,
      uploads,
      fidelity: view.fidelity(),
      resources: view.resources(),
      reference: before,
      nonuniform_colour: true,
      source_reference_unchanged: true,
      qualification:
        "not-scored; artificial single-view serialized workload, system GPU counters include other processes",
    };
  } finally {
    for (const [name, original] of Object.entries(originals))
      gl[name] = original;
    observer?.disconnect();
    rt.dispose();
    if (pipeline === "desktop") {
      r.setPixelRatio(pixelRatio);
      r.setSize(originalSize.x, originalSize.y, false);
      view.composer.setPixelRatio(pixelRatio);
      view.composer.setSize(originalSize.x, originalSize.y);
      camera.aspect = originalAspect;
      camera.projectionMatrix.copy(originalProjection);
      camera.projectionMatrixInverse.copy(originalInverse);
    }
    r.setRenderTarget(target);
    r.setViewport(viewport);
    r.setScissor(scissor);
    r.setScissorTest(scissorTest);
    view.diagnostic(saved);
    if (completed) {
      // Restore actual activity/textures as well as the logical replay clock.
      await view.reference({
        width: 32,
        height: 32,
        time: saved.time,
        culling: saved.pageCulling,
      });
      if (pipeline === "desktop") view.composer.render();
    }
  }
}
