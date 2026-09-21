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

/** Distance from point i to the segment a-b, all indices into a flat xyz array. */
function segmentDistance(p, i, a, b) {
  const ax = p[3 * a], ay = p[3 * a + 1], az = p[3 * a + 2];
  const dx = p[3 * b] - ax, dy = p[3 * b + 1] - ay, dz = p[3 * b + 2] - az;
  const px = p[3 * i] - ax, py = p[3 * i + 1] - ay, pz = p[3 * i + 2] - az;
  const len2 = dx * dx + dy * dy + dz * dz;
  const t = len2 > 0 ? Math.max(0, Math.min(1, (px * dx + py * dy + pz * dz) / len2)) : 0;
  return Math.hypot(px - t * dx, py - t * dy, pz - t * dz);
}

/**
 * Skeleton levels of detail, the line counterpart of the multi-resolution meshes. The graph is
 * split into unbranched paths between branch points and ends (which are always kept), and
 * every path is simplified with Douglas-Peucker. A vertex's error is the largest deviation its
 * removal would cause, capped by its DP ancestors', so the vertices kept at tolerance eps are
 * exactly those with error > eps and every level stays within eps of the full skeleton.
 *
 * Returns {eps: [0, base, 2 base, ...], levels: [Uint32Array segment pairs], bounds}; level 0
 * is the full skeleton, and a coarser level is only listed when it drops segments.
 */
export function skeletonLevels(vertices, edges, base, count) {
  const nv = vertices.length / 3;
  const degree = new Uint32Array(nv);
  for (let e = 0; e < edges.length; e++) degree[edges[e]]++;
  // adjacency in CSR form
  const start = new Uint32Array(nv + 1);
  for (let v = 0; v < nv; v++) start[v + 1] = start[v] + degree[v];
  const adj = new Uint32Array(edges.length);
  const fill = start.slice(0, nv);
  for (let e = 0; e < edges.length; e += 2) {
    const a = edges[e], b = edges[e + 1];
    adj[fill[a]++] = b;
    adj[fill[b]++] = a;
  }
  const used = new Uint8Array(edges.length); // per adjacency slot: edge already walked
  const markUsed = (a, b) => {
    for (let s = start[a]; s < start[a + 1]; s++) if (adj[s] === b && !used[s]) { used[s] = 1; break; }
    for (let s = start[b]; s < start[b + 1]; s++) if (adj[s] === a && !used[s]) { used[s] = 1; break; }
  };
  const paths = []; // arrays of vertex ids
  const walk = (from, slot) => {
    const path = [from];
    let prev = from, cur = adj[slot];
    markUsed(prev, cur);
    path.push(cur);
    while (degree[cur] === 2 && cur !== from) {
      let next = -1;
      for (let s = start[cur]; s < start[cur + 1]; s++) if (!used[s]) { next = adj[s]; break; }
      if (next < 0) break;
      markUsed(cur, next);
      prev = cur;
      cur = next;
      path.push(cur);
    }
    paths.push(path);
  };
  for (let v = 0; v < nv; v++)
    if (degree[v] !== 2) for (let s = start[v]; s < start[v + 1]; s++) if (!used[s]) walk(v, s);
  // what is left are cycles made only of degree-2 vertices
  for (let v = 0; v < nv; v++) for (let s = start[v]; s < start[v + 1]; s++) if (!used[s]) walk(v, s);

  const err = paths.map((path) => {
    const e = new Float64Array(path.length).fill(Infinity); // ends are always kept
    const stack = [[0, path.length - 1, Infinity]];
    while (stack.length) {
      const [i, j, cap] = stack.pop();
      let best = -1, d = -1;
      for (let k = i + 1; k < j; k++) {
        const dk = segmentDistance(vertices, path[k], path[i], path[j]);
        if (dk > d) [best, d] = [k, dk];
      }
      if (best < 0) continue;
      e[best] = Math.min(d, cap);
      stack.push([i, best, e[best]], [best, j, e[best]]);
    }
    return e;
  });

  const eps = [0], levels = [edges];
  for (let l = 0; l < count; l++) {
    const tol = base * 2 ** l;
    const out = [];
    paths.forEach((path, p) => {
      let last = path[0];
      for (let k = 1; k < path.length; k++)
        if (err[p][k] > tol) {
          out.push(last, path[k]);
          last = path[k];
        }
    });
    if (out.length < levels.at(-1).length) {
      eps.push(tol);
      levels.push(Uint32Array.from(out));
    }
  }
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < vertices.length; i += 3)
    for (let a = 0; a < 3; a++) {
      min[a] = Math.min(min[a], vertices[i + a]);
      max[a] = Math.max(max[a], vertices[i + a]);
    }
  return { eps, levels, bounds: { min, max } };
}
