// Module worker: dequantize and compute normals for decoded fragments off the main thread.
import { finishFragment } from "./geometry.js";

self.onmessage = ({ data: { id, q, index, scale, offset } }) => {
  const { positions, normals } = finishFragment(q, index, scale, offset);
  self.postMessage({ id, positions, normals, index }, [
    positions.buffer,
    normals.buffer,
    index.buffer,
  ]);
};
