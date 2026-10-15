// Camera adapters are shared by live culling and diagnostic reference captures.
// THREE is injected so tests use the pinned vendor without a browser import map.
export function localEyePlanes(THREE, dataWorld, cameras) {
  if (!cameras.length) return null; // no pose yet: retain all geometry conservatively
  return cameras.map(({ projection, inverseWorld, width, height }) => {
    if (!(width > 0 && height > 0))
      throw new RangeError("Positive eye viewport required");
    const expanded = projection.clone();
    // Expand by two device pixels on each side, conservatively covering 1px lines
    // and raster edge rounding. This changes culling planes only, never projection.
    for (const i of [0, 4, 8, 12]) expanded.elements[i] /= 1 + 4 / width;
    for (const i of [1, 5, 9, 13]) expanded.elements[i] /= 1 + 4 / height;
    const clip = expanded.multiply(inverseWorld).multiply(dataWorld);
    return new THREE.Frustum()
      .setFromProjectionMatrix(clip)
      .planes.map((p) => [p.normal.x, p.normal.y, p.normal.z, p.constant]);
  });
}
