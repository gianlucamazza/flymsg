// Module worker: geometry work off the main thread. "fragment" dequantizes a decoded Draco
// fragment and computes its normals; "skeleton" builds a skeleton's levels of detail.
import { finishFragment, skeletonLevels } from "./geometry.js";
import { linePages } from "./geometry-pages.js";

function process(data) {
  if (data.kind === "skeleton") {
    const { eps, levels, bounds } = skeletonLevels(
      data.vertices,
      data.edges,
      data.base,
      data.count,
    );
    const coarser = levels.slice(1); // the caller keeps level 0, its own edges
    const pages = levels.map((edges) => linePages(data.vertices, edges));
    self.postMessage({ id: data.id, eps, coarser, bounds, pages }, [
      ...coarser.map((l) => l.buffer),
      ...pages.flatMap((p) => [
        p.edgePage.buffer,
        p.bounds.buffer,
        p.sizes.buffer,
        p.runs.buffer,
      ]),
    ]);
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
