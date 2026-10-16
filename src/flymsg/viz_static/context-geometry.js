// Source preparation shared by workers and independent format tests. No renderer.
import { finishFragment } from "./geometry.js";

export function prepareNeuropil(parts) {
  const vertices = parts.reduce((n, p) => n + p.vertices.length / 3, 0);
  const positions = new Float32Array(3 * vertices);
  const index = new Uint32Array(
    parts.reduce((n, p) => n + p.indices.length, 0),
  );
  let vertex = 0,
    offset = 0;
  for (const part of parts) {
    positions.set(part.vertices, 3 * vertex);
    if (part.indices.length % 3)
      throw new Error("Incomplete neuropil triangle");
    for (let i = 0; i < part.indices.length; i++) {
      if (part.indices[i] >= part.vertices.length / 3)
        throw new Error("Neuropil index outside source");
      index[offset + i] = vertex + part.indices[i];
    }
    vertex += part.vertices.length / 3;
    offset += part.indices.length;
  }
  return { ...finishFragment(positions, index, [1, 1, 1], [0, 0, 0]), index };
}

export function prepareSomata(buffer, resolution, palette) {
  const count = buffer.byteLength / 13;
  if (!Number.isInteger(count) || !palette.length)
    throw new Error("Invalid soma context file");
  const voxels = new Float32Array(buffer, 0, 3 * count);
  const codes = new Uint8Array(buffer, 12 * count, count);
  const positions = new Float32Array(3 * count),
    colors = new Float32Array(3 * count);
  for (let i = 0; i < count; i++) {
    for (let axis = 0; axis < 3; axis++)
      positions[3 * i + axis] = voxels[3 * i + axis] * resolution[axis];
    colors.set(palette[Math.min(codes[i], palette.length - 1)], 3 * i);
  }
  return { positions, colors, count };
}
