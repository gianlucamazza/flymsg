// Module worker: geometry work off the main thread. "fragment" dequantizes a decoded Draco
// fragment and computes its normals; "skeleton" builds a skeleton's levels of detail.
import { finishFragment, skeletonLevels } from "./geometry.js";

self.onmessage = ({ data }) => {
  if (data.kind === "skeleton") {
    const { eps, levels, bounds } = skeletonLevels(data.vertices, data.edges, data.base, data.count);
    const coarser = levels.slice(1); // the caller keeps level 0, its own edges
    self.postMessage({ id: data.id, eps, coarser, bounds }, coarser.map((l) => l.buffer));
    return;
  }
  const { id, q, index, scale, offset } = data;
  const { positions, normals } = finishFragment(q, index, scale, offset);
  self.postMessage({ id, positions, normals, index }, [
    positions.buffer,
    normals.buffer,
    index.buffer,
  ]);
};
