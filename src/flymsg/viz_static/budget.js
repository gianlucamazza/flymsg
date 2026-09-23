/**
 * Triangle budget and adaptive resolution: the arithmetic of "how much geometry fits" and
 * "how large a frame we can afford", kept out of main.js so it can be tested.
 */

/** Triangles per compressed byte, learned from decoded fragments (0.6: GF's coarsest LOD). */
export function trisPerByte(stats) {
  return stats.bytes > 1e5 ? stats.tris / stats.bytes : 0.6;
}

/** Vertices per triangle, learned the same way. */
export function vertsPerTri(stats) {
  return stats.tris > 1e5 ? stats.verts / stats.tris : 0.6;
}

/**
 * Triangles the BatchedMesh can actually hold, with 10% slack for fragmentation: the
 * requested budget, the vertex buffer and the index buffer, whichever runs out first.
 */
export function effectiveBudget(stats, capacity, budgetM) {
  return (
    0.9 *
    Math.min(
      budgetM * 1e6,
      capacity.vertices / vertsPerTri(stats),
      capacity.indices / 3,
    )
  );
}

/**
 * The pixel ratio that should hit `targetFrameMs`, from the ratio a frame of `frameMs` was
 * drawn at. Rendering cost grows with the pixel count, so the ratio scales with the square
 * root; rounded to 1/20 to avoid thrashing between neighbouring values.
 */
export function scaledRatio(ratio, frameMs, targetFrameMs) {
  return Math.round(ratio * Math.sqrt(targetFrameMs / frameMs) * 20) / 20;
}
