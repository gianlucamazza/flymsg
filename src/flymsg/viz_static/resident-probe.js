// Diagnostic only: executes the APPLICATION scheduler, then reads every pixel.
// Serialized wall time is not a GPU timer, frame rate or XR qualification.
export async function residentLineProbe(
  view,
  localEyePlanes,
  { size = 512, warmup = 3, repeats = 8, time = 20 } = {},
) {
  const { THREE: T, renderer: r, world, camera, data, skeletons } = view;
  if (
    r.xr.isPresenting ||
    view.fidelity().status !== "ready" ||
    view.fidelity().representation !== "skeleton" ||
    view.fidelity().selected < 1
  )
    throw new Error("Complete non-immersive original skeleton scene required");
  if (
    ![size, warmup, repeats].every(Number.isInteger) ||
    size < 32 ||
    size > 1024 ||
    warmup < 2 ||
    warmup > 5 ||
    repeats < 2 ||
    repeats > 16
  )
    throw new RangeError("Invalid bounded residency probe configuration");
  const gl = r.getContext(),
    saved = view.diagnostic({ continuous: false, playing: false, time });
  const target = r.getRenderTarget(),
    viewport = r.getViewport(new T.Vector4()),
    scissor = r.getScissor(new T.Vector4()),
    scissorTest = r.getScissorTest();
  const bufferData = gl.bufferData,
    bufferSubData = gl.bufferSubData;
  let bytes = 0,
    uploads = 0;
  const tally = (args, sub) => {
    if (args[0] !== gl.ELEMENT_ARRAY_BUFFER) return;
    const source = args[sub ? 2 : 1];
    bytes +=
      typeof source === "number"
        ? source
        : sub && args.length >= 4
          ? (args[4] ?? source.length - args[3]) * source.BYTES_PER_ELEMENT
          : source.byteLength;
    uploads++;
  };
  const rt = new T.WebGLRenderTarget(size, size, {
    samples: 0,
    depthBuffer: true,
  });
  const pixels = new Uint8Array(size * size * 4),
    records = [],
    references = [];
  try {
    const sourceReference = await view.reference({
      width: 32,
      height: 32,
      time,
      culling: false,
    });
    for (const [name, scale, moving, all] of [
      ["dense-all", 1, false, true],
      ["anatomical-motion", 1, true, false],
      ["close-motion", 0.35, true, false],
    ]) {
      const base = camera.clone();
      base.aspect = 1;
      base.position.multiplyScalar(scale);
      base.updateProjectionMatrix();
      base.updateMatrixWorld(true);
      view.diagnostic({ time, residentLines: true });
      const options = {
        width: size,
        height: size,
        time,
        projection: base.projectionMatrix.toArray(),
        cameraWorld: base.matrixWorld.toArray(),
      };
      const full = await view.reference({ ...options, culling: false });
      const candidate = await view.reference({ ...options, culling: true });
      const ids = atob(full.images.neuron_id.base64);
      let hasNeuron = false;
      for (let i = 0; i < ids.length; i += 4)
        if (
          ids.charCodeAt(i) ||
          ids.charCodeAt(i + 1) ||
          ids.charCodeAt(i + 2)
        ) {
          hasNeuron = true;
          break;
        }
      if (!hasNeuron)
        throw new Error(`${name}: reference has no neuron-ID witness`);
      const checks = Object.fromEntries(
        Object.keys(full.images).map((key) => {
          if (full.images[key].sha256 !== candidate.images[key].sha256)
            throw new Error(
              `${name}/${key}: resident image differs from full source`,
            );
          return [key, full.images[key].sha256];
        }),
      );
      references.push({ name, options, checks, nonempty_neuron_id: true });
      const expected = [];
      for (const [order, mode] of [
        "compact",
        "resident",
        "resident",
        "compact",
      ].entries()) {
        view.diagnostic({ time, residentLines: mode === "resident" });
        gl.bufferData = function (...args) {
          tally(args, false);
          return bufferData.apply(gl, args);
        };
        gl.bufferSubData = function (...args) {
          tally(args, true);
          return bufferSubData.apply(gl, args);
        };
        const samples = [];
        r.setRenderTarget(rt);
        r.setViewport(0, 0, size, size);
        r.setScissorTest(false);
        for (let i = 0; i < warmup + repeats; i++) {
          if (gl.isContextLost())
            throw new Error("Context lost during residency probe");
          const c = base.clone();
          if (moving) c.rotateY((i - warmup) * 0.01);
          c.updateMatrixWorld(true);
          const eyes = all
            ? [[]]
            : localEyePlanes(T, data.matrixWorld, [
                {
                  projection: c.projectionMatrix,
                  inverseWorld: c.matrixWorldInverse,
                  width: size,
                  height: size,
                },
              ]);
          bytes = uploads = 0;
          r.info.reset();
          const started = performance.now();
          const submission = view.scheduleLines(eyes);
          const selected = performance.now();
          r.clear();
          r.render(world, c);
          r.readRenderTargetPixels(rt, 0, 0, size, size, pixels);
          const wall = performance.now() - started;
          if (i < warmup) continue;
          if (!pixels.some((v, j) => v !== pixels[j % 4]))
            throw new Error(`${name}/${mode}: no rendered-content witness`);
          let different = 0;
          if (!order) expected.push(pixels.slice());
          else
            for (let j = 0; j < pixels.length; j++)
              if (pixels[j] !== expected[i - warmup][j]) different++;
          if (different)
            throw new Error(
              `${name}/${mode}: ${different} changed colour bytes`,
            );
          if (
            mode === "resident" &&
            (submission.mode !== "resident" || bytes !== 0 || uploads !== 0)
          )
            throw new Error(
              "Resident steady-state index residency invariant failed",
            );
          samples.push({
            selection_ms: selected - started,
            serialized_wall_ms: wall,
            index_upload_bytes: bytes,
            index_upload_calls: uploads,
            different_colour_bytes: different,
            submission,
            draws: { ...r.info.render },
          });
        }
        gl.bufferData = bufferData;
        gl.bufferSubData = bufferSubData;
        records.push({ name, mode, order, samples });
      }
    }
    return {
      schema: "flymsg.resident-line-probe/v1",
      size,
      warmup,
      repeats,
      time,
      source_reference: sourceReference,
      references,
      records,
      metric:
        "CPU selection and serialized render/readback wall time; not GPU timer or XR cadence",
      pipeline:
        "original geometry, original shaders, one view, zero MSAA, no composer",
      qualification:
        "diagnostic only; no immersive frame-clock or motion-to-photon qualification",
    };
  } finally {
    gl.bufferData = bufferData;
    gl.bufferSubData = bufferSubData;
    view.diagnostic(saved);
    const eyes = saved.pageCulling
      ? localEyePlanes(T, data.matrixWorld, [
          {
            projection: camera.projectionMatrix,
            inverseWorld: camera.matrixWorldInverse,
            width: r.domElement.width,
            height: r.domElement.height,
          },
        ])
      : null;
    view.scheduleLines(eyes);
    r.setRenderTarget(target);
    r.setViewport(viewport);
    r.setScissor(scissor);
    r.setScissorTest(scissorTest);
    rt.dispose();
  }
}
