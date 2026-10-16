// Managed ArrayBuffer accounting, not browser RSS or driver GPU allocation.
export function bufferBytes(arrays) {
  const buffers = new Set(
    arrays.filter(ArrayBuffer.isView).map((a) => a.buffer),
  );
  return [...buffers].reduce((bytes, b) => bytes + b.byteLength, 0);
}
export function geometryArrays(geometry) {
  return [
    ...Object.values(geometry.attributes).map((a) => a.array),
    geometry.index?.array,
  ].filter(Boolean);
}
