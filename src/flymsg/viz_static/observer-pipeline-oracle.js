// Real viewer/materials, two explicitly declared source neurons. This fixture
// tests rendering equivalence; it cannot qualify a reduced scene for performance.
import {
  verifyRasterFootprint,
  bloomFootprint,
} from "./bounded-raster-oracle.js";
import { browserProbe } from "./browser-probe.js";
import { auditBoundedRuntime } from "./bounded-runtime-oracle.js";
import { serializedGpuProbe } from "./gpu-probe.js";

export async function observerPipelineOracle() {
  const started = performance.now();
  const stage = (name) =>
    console.info(
      "PIPELINE_ORACLE",
      JSON.stringify({ stage: name, elapsed_ms: performance.now() - started }),
    );
  stage("loading");
  const deadline = performance.now() + 60000;
  while (performance.now() < deadline) {
    const api = window.flymsg;
    if (api?.fidelity().status === "unsupported")
      throw new Error(JSON.stringify(api.fidelity()));
    if (api?.resources().gpu_resources.state === "unsupported")
      throw new Error(JSON.stringify(api.resources()));
    if (api?.fidelity().gpu_ready === true) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  const api = window.flymsg;
  if (api?.fidelity().gpu_ready !== true)
    throw new Error("Viewer preparation timed out");
  const bounded = api.fidelity().representation === "skeleton-bounded";
  const results = [];
  stage("resources-ready");
  const beforeReferenceResources = api.resources();
  for (const time of [0, 20, 350])
    for (const eye of [-1, 1]) {
      stage(`direct-${time}-${eye}`);
      const cameraWorld = api.camera.matrixWorld.toArray();
      cameraWorld[12] += eye * 0.015 * api.camera.position.length();
      const options = { width: 256, height: 256, time, cameraWorld };
      const original = await api.reference({
        ...options,
        pipeline: "original",
      });
      if (bounded) {
        const state = api.diagnosticState();
        try {
          api.diagnostic({ ...state, suspended: true });
          const projection = original.projection;
          await api.prepareBounded({ ...options, projection });
          const modelView = new api.THREE.Matrix4()
            .fromArray(cameraWorld)
            .invert()
            .multiply(new api.THREE.Matrix4().fromArray(original.data_world))
            .toArray();
          await auditBoundedRuntime(api, [
            { modelView, projection, width: 256, height: 256 },
          ]);
        } finally {
          api.diagnostic(state);
        }
      }
      const paged = await api.reference({
        ...options,
        pipeline: "paged",
        culling: true,
      });
      const footprint = bounded
        ? verifyRasterFootprint(
            original.images.colour,
            paged.images.colour,
            original.images.neuron_id,
            original.width,
            original.height,
          )
        : null;
      const comparisons = Object.fromEntries(
        Object.keys(original.images).map((pass) => [
          pass,
          original.images[pass].sha256 === paged.images[pass].sha256,
        ]),
      );
      const pixels = Uint8Array.from(
        atob(original.images.neuron_id.base64),
        (c) => c.charCodeAt(0),
      );
      const ids = new Set();
      for (let i = 0; i < pixels.length; i += 4) {
        const id = pixels[i] + 256 * pixels[i + 1] + 65536 * pixels[i + 2];
        if (id) ids.add(id);
      }
      const exactPasses = bounded
        ? ["neuron_id", "packed_depth"]
        : Object.keys(comparisons);
      if (!exactPasses.every((pass) => comparisons[pass]) || !ids.size)
        throw new Error(
          JSON.stringify({ time, eye, comparisons, ids: [...ids] }),
        );
      results.push({
        time,
        eye,
        comparisons,
        footprint,
        bounded_submission: bounded ? api.paged.bounded.report() : null,
        nonempty_ids: [...ids],
        scene_sha256: original.scene_sha256,
        activity_sha256: original.activity_sha256,
        source_geometry: original.geometry,
        width: original.width,
        height: original.height,
        reference_view: {
          projection: original.projection,
          camera_world: original.camera_world,
          data_world: original.data_world,
        },
        candidate_view: {
          projection: paged.projection,
          camera_world: paged.camera_world,
          data_world: paged.data_world,
        },
        reference_images: original.images,
        candidate_images: paged.images,
      });
    }
  let diagnosticRouting = null;
  if (api.fidelity().representation === "skeleton") {
    const beforeDiagnostics = api.diagnosticState();
    const gpu = serializedGpuProbe(api, { sizes: [64], warmup: 1, repeats: 1 });
    const direct = await browserProbe(api, {
      seconds: 2,
      size: 64,
      pipeline: "direct",
    });
    const desktop = await browserProbe(api, {
      seconds: 2,
      size: 64,
      pipeline: "desktop",
    });
    if (
      [gpu, direct, desktop].some(
        (r) => r.renderer_pipeline !== "immutable-pages",
      )
    )
      throw new Error("Diagnostic measured a different pipeline");
    if (
      JSON.stringify(api.diagnosticState()) !==
      JSON.stringify(beforeDiagnostics)
    )
      throw new Error("Diagnostic did not restore application state");
    diagnosticRouting = {
      gpu_variants: gpu.records.length,
      direct_frames: direct.records.length,
      desktop_frames: desktop.records.length,
      renderer_pipeline: "immutable-pages",
      application_state_restored: true,
      qualification: "software fixture routing only; no performance claim",
    };
  }
  const desktopCases = [],
    originalState = api.diagnosticState();
  try {
    api.diagnostic({
      ...originalState,
      suspended: true,
      playing: false,
      continuous: false,
    });
    for (const time of [0, 20, 350]) {
      stage(`desktop-original-${time}`);
      const reference = await api.desktopReference({
        time,
        pipeline: "original",
      });
      stage(`desktop-paged-${time}`);
      if (bounded) await api.prepareBounded();
      const candidate = await api.desktopReference({ time, pipeline: "paged" });
      if (
        (!bounded && reference.rgba.sha256 !== candidate.rgba.sha256) ||
        reference.samples !== 4 ||
        candidate.samples !== 4 ||
        JSON.stringify(reference.projection) !==
          JSON.stringify(candidate.projection) ||
        JSON.stringify(reference.camera_world) !==
          JSON.stringify(candidate.camera_world)
      )
        throw new Error(`Full-quality desktop mismatch at ${time} ms`);
      let footprint = null;
      if (bounded) {
        const source = await api.reference({
          time,
          width: reference.width,
          height: reference.height,
          projection: reference.projection,
          cameraWorld: reference.camera_world,
          pipeline: "original",
        });
        footprint = verifyRasterFootprint(
          reference.rgba,
          candidate.rgba,
          source.images.neuron_id,
          reference.width,
          reference.height,
          bloomFootprint(api, reference.width, reference.height),
        );
      }
      desktopCases.push({ time, reference, candidate, footprint });
    }
  } finally {
    api.diagnostic(originalState);
  }
  let contextRecovery = null;
  if (
    ["skeleton", "skeleton-bounded"].includes(api.fidelity().representation)
  ) {
    stage("context-loss");
    const canvas = api.renderer.domElement,
      extension = api.renderer.getContext().getExtension("WEBGL_lose_context");
    if (!extension)
      throw Error("Context recovery fixture requires WEBGL_lose_context");
    const generation = api.paged.generation;
    const lost = new Promise((resolve) =>
      canvas.addEventListener("webglcontextlost", resolve, { once: true }),
    );
    extension.loseContext();
    await lost;
    if (api.paged.state !== "context-lost" || api.paged.bounded?.current)
      throw Error("Lost context retained a bounded selection");
    const restored = new Promise((resolve) =>
      canvas.addEventListener("webglcontextrestored", resolve, { once: true }),
    );
    await new Promise((resolve) => setTimeout(resolve, 100));
    extension.restoreContext();
    await restored;
    const deadline = performance.now() + 30000;
    while (!api.fidelity().gpu_ready && performance.now() < deadline)
      await new Promise((resolve) => setTimeout(resolve, 50));
    if (!api.fidelity().gpu_ready || api.paged.generation <= generation)
      throw Error(
        "Context reconstruction failed: " +
          JSON.stringify(api.resources().gpu_resources),
      );
    contextRecovery = {
      generation_before: generation,
      generation_after: api.paged.generation,
      resources: api.resources().gpu_resources,
    };
    stage("context-restored");
  }
  stage("complete");
  return {
    status: "pass",
    before_reference_resources: beforeReferenceResources,
    diagnostic_routing: diagnosticRouting,
    context_recovery: contextRecovery,
    desktop_cases: desktopCases,
    qualification: bounded
      ? "bounded graph, auxiliary passes and colour-support fixture; no full-scene hardware or human qualification"
      : "correctness fixture only; not full-scene hardware performance",
    fidelity: api.fidelity(),
    resources: api.resources(),
    results,
    gpu: await api.gpuInventory(),
  };
}
