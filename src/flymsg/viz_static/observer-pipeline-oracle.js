// Real viewer/materials, two explicitly declared source neurons. This fixture
// tests rendering equivalence; it cannot qualify a reduced scene for performance.
import { browserProbe } from "./browser-probe.js";
import { serializedGpuProbe } from "./gpu-probe.js";

export async function observerPipelineOracle() {
  const deadline = performance.now() + 60000;
  while (performance.now() < deadline) {
    const api = window.flymsg;
    if (api?.fidelity().status === "unsupported")
      throw new Error(JSON.stringify(api.fidelity()));
    if (api?.resources().gpu_resources.state === "unsupported")
      throw new Error(JSON.stringify(api.resources()));
    if (api?.resources().gpu_resources.state === "ready") break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  const api = window.flymsg;
  if (api?.resources().gpu_resources.state !== "ready")
    throw new Error("Viewer preparation timed out");
  const results = [];
  const beforeReferenceResources = api.resources();
  for (const time of [0, 20, 350])
    for (const eye of [-1, 1]) {
      const cameraWorld = api.camera.matrixWorld.toArray();
      cameraWorld[12] += eye * 0.015 * api.camera.position.length();
      const options = { width: 256, height: 256, time, cameraWorld };
      const original = await api.reference({
        ...options,
        pipeline: "original",
      });
      const paged = await api.reference({
        ...options,
        pipeline: "paged",
        culling: true,
      });
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
      if (!Object.values(comparisons).every(Boolean) || !ids.size)
        throw new Error(
          JSON.stringify({ time, eye, comparisons, ids: [...ids] }),
        );
      results.push({
        time,
        eye,
        comparisons,
        nonempty_ids: [...ids],
        scene_sha256: original.scene_sha256,
        activity_sha256: original.activity_sha256,
        source_geometry: original.geometry,
      });
    }
  let diagnosticRouting = null;
  if (api.fidelity().representation === "skeleton") {
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
    diagnosticRouting = {
      gpu_variants: gpu.records.length,
      direct_frames: direct.records.length,
      desktop_frames: desktop.records.length,
      renderer_pipeline: "immutable-pages",
      qualification: "software fixture routing only; no performance claim",
    };
  }
  return {
    status: "pass",
    before_reference_resources: beforeReferenceResources,
    diagnostic_routing: diagnosticRouting,
    qualification:
      "correctness fixture only; not full-scene hardware performance",
    fidelity: api.fidelity(),
    resources: api.resources(),
    results,
    gpu: await api.gpuInventory(),
  };
}
