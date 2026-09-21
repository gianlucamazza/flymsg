// Pure geometry helpers shared by the fragment worker and the tests.

/**
 * Turn a decoded Draco fragment into renderable arrays: dequantize positions with the
 * per-axis affine map from fragmentTransform, then compute area-weighted vertex normals
 * exactly as three.js BufferGeometry.computeVertexNormals does.
 */
export function finishFragment(q, index, scale, offset) {
  const n = q.length;
  const p = new Float32Array(n);
  for (let i = 0; i < n; i += 3) {
    p[i] = offset[0] + scale[0] * q[i];
    p[i + 1] = offset[1] + scale[1] * q[i + 1];
    p[i + 2] = offset[2] + scale[2] * q[i + 2];
  }
  const normals = new Float32Array(n);
  for (let t = 0; t < index.length; t += 3) {
    const a = 3 * index[t],
      b = 3 * index[t + 1],
      c = 3 * index[t + 2];
    // (C - B) x (A - B), as three.js does
    const cbx = p[c] - p[b],
      cby = p[c + 1] - p[b + 1],
      cbz = p[c + 2] - p[b + 2];
    const abx = p[a] - p[b],
      aby = p[a + 1] - p[b + 1],
      abz = p[a + 2] - p[b + 2];
    const nx = cby * abz - cbz * aby,
      ny = cbz * abx - cbx * abz,
      nz = cbx * aby - cby * abx;
    for (const v of [a, b, c]) {
      normals[v] += nx;
      normals[v + 1] += ny;
      normals[v + 2] += nz;
    }
  }
  for (let i = 0; i < n; i += 3) {
    const len = Math.hypot(normals[i], normals[i + 1], normals[i + 2]) || 1;
    normals[i] /= len;
    normals[i + 1] /= len;
    normals[i + 2] /= len;
  }
  return { positions: p, normals };
}

/**
 * Signed volume of a triangle mesh, measured from `origin`: positive when triangles wind
 * counter-clockwise seen from outside. For a surface with small gaps (e.g. seams between
 * chunked fragments) the result depends on the origin, so pass a point near the mesh.
 */
export function signedVolume(positions, index, origin = [0, 0, 0]) {
  const [ox, oy, oz] = origin;
  let v = 0;
  for (let t = 0; t < index.length; t += 3) {
    const a = 3 * index[t], b = 3 * index[t + 1], c = 3 * index[t + 2];
    const ax = positions[a] - ox, ay = positions[a + 1] - oy, az = positions[a + 2] - oz;
    const bx = positions[b] - ox, by = positions[b + 1] - oy, bz = positions[b + 2] - oz;
    const cx = positions[c] - ox, cy = positions[c + 1] - oy, cz = positions[c + 2] - oz;
    v += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx);
  }
  return v / 6;
}

/** Mean vertex position of a set of position arrays. */
export function centroid(arrays) {
  const sum = [0, 0, 0];
  let n = 0;
  for (const p of arrays) {
    for (let i = 0; i < p.length; i += 3) {
      sum[0] += p[i];
      sum[1] += p[i + 1];
      sum[2] += p[i + 2];
    }
    n += p.length / 3;
  }
  return sum.map((x) => x / n);
}
