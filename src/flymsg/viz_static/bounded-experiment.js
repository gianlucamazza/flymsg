// Disposable fixed-camera experiment. Never imported by the production entrypoint.
import { sourcePaths, projectSource, simplifyPath } from "./bounded-paths.js";
import { verifyBoundedPaths } from "./bounded-path-oracle.js";

export async function boundedExperiment(
  view,
  { close = false, iterations = 8, warmup = 5 } = {},
) {
  if (
    view.paged ||
    view.renderer.xr.isPresenting ||
    document.hidden ||
    view.fidelity().representation !== "skeleton" ||
    view.fidelity().status !== "ready"
  )
    throw Error("Complete visible original skeleton diagnostic required");
  const { THREE: T, renderer: r, camera, skeletons, world, data } = view;
  const saved = view.diagnosticState(),
    originalCamera = camera.position.clone();
  const originalGeometry = skeletons.geometry;
  const originalProjection = camera.projectionMatrix.clone(),
    originalInverse = camera.projectionMatrixInverse.clone();
  const originalNear = camera.near,
    originalFar = camera.far;
  let candidate;
  const digest = async (array) =>
    Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", array)))
      .map((x) => x.toString(16).padStart(2, "0"))
      .join("");
  try {
    view.diagnostic({
      suspended: true,
      continuous: false,
      playing: false,
      time: 20,
      pageCulling: false,
    });
    if (close) {
      const radius = camera.far - camera.position.length();
      camera.position.multiplyScalar(0.35);
      camera.near = Math.max(0.05, camera.position.length() - radius);
      camera.far = Math.max(camera.position.length() + radius, camera.near + 1);
      camera.updateProjectionMatrix();
    }
    camera.updateMatrixWorld(true);
    world.updateMatrixWorld(true);
    const before = await view.reference({
      width: 32,
      height: 32,
      time: 20,
      culling: false,
    });
    view.scheduleLines(null);
    const sourceGeometry = skeletons.geometry;
    const width = r.domElement.width,
      height = r.domElement.height;
    const eyes = [-1, 0, 1].map((offset) => {
      const c = camera.clone();
      c.position.x += offset * 0.015 * camera.position.length();
      c.updateMatrixWorld(true);
      return {
        matrix: c.projectionMatrix
          .clone()
          .multiply(c.matrixWorldInverse)
          .multiply(data.matrixWorld)
          .toArray(),
        width,
        height,
      };
    });
    const selected = new Set(before.neurons.map((n) => n.k)),
      chunks = [],
      neurons = [];
    let count = 0;
    const preparationStart = performance.now();
    for (const n of view.neurons)
      if (selected.has(n.k)) {
        const vertices = n.skelLod.vertices,
          edges = n.skelLod.levels[0];
        const projections = projectSource(vertices, eyes);
        const records = [...sourcePaths(vertices.length / 3, edges)].map(
          (path) => ({
            ...path,
            cuts: simplifyPath(path.vertices, projections),
          }),
        );
        const report = verifyBoundedPaths(T, vertices, edges, records, eyes);
        const indices = new Uint32Array(report.candidate_edges * 2);
        let at = 0;
        for (const path of records)
          for (let c = 1; c < path.cuts.length; c++) {
            indices[at++] = n.skelBase + path.vertices[path.cuts[c - 1]];
            indices[at++] = n.skelBase + path.vertices[path.cuts[c]];
          }
        if (at !== indices.length)
          throw Error("Candidate index/provenance mismatch");
        neurons.push({
          k: n.k,
          ...report,
          source_vertices_sha256: await digest(vertices),
          source_edges_sha256: await digest(edges),
          candidate_indices_sha256: await digest(indices),
        });
        chunks.push(indices);
        count += indices.length;
        // Preparation is explicitly outside measurement and yields between neurons.
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    if (neurons.length !== selected.size)
      throw Error("Selected neuron missing");
    if (
      neurons.reduce((sum, n) => sum + 2 * n.original_edges, 0) !==
      sourceGeometry.drawRange.count
    )
      throw Error(
        "Complete original primitive count differs from source geometry",
      );
    const index = new Uint32Array(count);
    let offset = 0;
    for (const chunk of chunks) {
      index.set(chunk, offset);
      offset += chunk.length;
    }
    candidate = new T.BufferGeometry();
    for (const [name, attribute] of Object.entries(sourceGeometry.attributes))
      candidate.setAttribute(name, attribute);
    candidate.setIndex(new T.BufferAttribute(index, 1));
    candidate.addGroup(0, index.length, 0);
    const preparationMs = performance.now() - preparationStart;
    const gl = r.getContext(),
      pixels = new Uint8Array(width * height * 4),
      blocks = [],
      images = {};
    const draw = () => {
      view.composer.render();
      gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    };
    for (let repeat = 0; repeat < 3; repeat++) {
      const arms = [];
      for (const mode of ["original", "bounded", "bounded", "original"]) {
        skeletons.geometry = mode === "bounded" ? candidate : sourceGeometry;
        for (let i = 0; i < warmup; i++) {
          draw();
          await new Promise((resolve) => setTimeout(resolve, 0));
        }
        const samples = [];
        for (let i = 0; i < iterations; i++) {
          const start = performance.now();
          draw();
          samples.push(performance.now() - start);
          await new Promise((resolve) => setTimeout(resolve, 0));
        }
        if (!pixels.some((v, i) => v !== pixels[i % 4]))
          throw Error("Empty image witness");
        if (!images[mode])
          images[mode] = {
            sha256: await digest(pixels),
            pixels: pixels.slice(),
          };
        arms.push({ mode, serialized_wall_ms: samples });
      }
      blocks.push({ repeat, arms });
    }
    let changedPixels = 0;
    for (let i = 0; i < pixels.length; i += 4)
      if (
        images.original.pixels
          .subarray(i, i + 4)
          .some((v, k) => v !== images.bounded.pixels[i + k])
      )
        changedPixels++;
    skeletons.geometry = sourceGeometry;
    const after = await view.reference({
      width: 32,
      height: 32,
      time: 20,
      culling: false,
    });
    if (JSON.stringify(before) !== JSON.stringify(after))
      throw Error("Original reference restoration mismatch");
    return {
      schema: "flymsg.bounded-skeleton-experiment/v1",
      normal_xr_qualification: false,
      qualification:
        "not-scored; artificial serialized fixed-camera diagnostic, no moving-view or visual acceptance",
      error_contract_px: 0.5,
      eyes,
      close,
      width,
      height,
      preparation_ms: preparationMs,
      neurons,
      blocks,
      images: {
        original_sha256: images.original.sha256,
        bounded_sha256: images.bounded.sha256,
        changed_pixels: changedPixels,
        total_pixels: width * height,
      },
      original_reference: before,
      original_reference_unchanged: true,
      render_settings: {
        pixel_ratio: r.getPixelRatio(),
        samples: view.observerStatus().identity.samples,
        bloom: view.bloom.enabled,
      },
    };
  } finally {
    skeletons.geometry = originalGeometry;
    if (candidate) {
      for (const name of Object.keys(candidate.attributes))
        candidate.deleteAttribute(name);
      candidate.dispose();
    }
    camera.near = originalNear;
    camera.far = originalFar;
    camera.projectionMatrix.copy(originalProjection);
    camera.projectionMatrixInverse.copy(originalInverse);
    camera.position.copy(originalCamera);
    camera.updateMatrixWorld(true);
    view.diagnostic(saved);
  }
}
