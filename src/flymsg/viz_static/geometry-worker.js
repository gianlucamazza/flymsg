// Module worker: geometry work off the main thread. "fragment" dequantizes a decoded Draco
// fragment and computes its normals; "skeleton" builds a skeleton's levels of detail.
import { finishFragment, skeletonLevels } from "./geometry.js";
import { linePages } from "./geometry-pages.js";
import { parseLegacyMesh, parseSkeleton } from "./precomputed.js";
import { prepareNeuropil, prepareSomata } from "./context-geometry.js";

function process(data) {
  if (data.kind === "somata") {
    const result = prepareSomata(data.buffer, data.resolution, data.palette);
    self.postMessage({ id: data.id, ...result }, [
      result.positions.buffer,
      result.colors.buffer,
    ]);
    return;
  }
  if (data.kind === "neuropil") {
    const result = prepareNeuropil(
      data.parts.map((buffer) => parseLegacyMesh(buffer, { copy: false })),
    );
    self.postMessage({ id: data.id, ...result }, [
      result.positions.buffer,
      result.normals.buffer,
      result.index.buffer,
    ]);
    return;
  }
  if (data.kind === "skeleton" || data.kind === "skeleton-source") {
    const source = data.kind === "skeleton-source";
    const { vertices, edges } = source ? parseSkeleton(data.buffer) : data;
    const { eps, levels, bounds } = skeletonLevels(
      vertices,
      edges,
      data.base,
      data.count,
    );
    const coarser = levels.slice(1); // the caller keeps level 0, its own edges
    const pages = levels.map((edges) => linePages(vertices, edges));
    const transfers = [
      ...(source ? [vertices.buffer, edges.buffer] : []),
      ...coarser.map((l) => l.buffer),
      ...pages.flatMap((p) => [
        p.edgePage.buffer,
        p.bounds.buffer,
        p.sizes.buffer,
        p.runs.buffer,
      ]),
    ];
    self.postMessage(
      {
        id: data.id,
        eps,
        coarser,
        bounds,
        pages,
        ...(source ? { vertices, edges } : {}),
      },
      [...new Set(transfers)],
    );
    return;
  }
  const { id, q, index, scale, offset } = data;
  const { positions, normals } = finishFragment(q, index, scale, offset);
  self.postMessage({ id, positions, normals, index }, [
    positions.buffer,
    normals.buffer,
    index.buffer,
  ]);
}
self.onmessage = ({ data }) => {
  try {
    process(data);
  } catch (error) {
    self.postMessage({ id: data.id, error: String(error) });
  }
};
