// Diagnostic experiment only: full source paths remain the independent reference.
export function* sourcePaths(vertexCount, edges) {
  if (edges.length % 2) throw new RangeError("Incomplete edge");
  const degree = new Uint32Array(vertexCount);
  for (const v of edges) {
    if (!Number.isInteger(v) || v < 0 || v >= vertexCount)
      throw new RangeError("Invalid source endpoint");
    degree[v]++;
  }
  const start = new Uint32Array(vertexCount + 1);
  for (let v = 0; v < vertexCount; v++) start[v + 1] = start[v] + degree[v];
  const next = start.slice(),
    adjacent = new Uint32Array(edges.length);
  for (let e = 0; e < edges.length / 2; e++) {
    adjacent[next[edges[2 * e]]++] = e;
    adjacent[next[edges[2 * e + 1]]++] = e;
  }
  const used = new Uint8Array(edges.length / 2);
  function walk(from, edge) {
    const vertices = [from],
      provenance = [];
    while (!used[edge]) {
      used[edge] = 1;
      provenance.push(edge);
      const to =
        edges[2 * edge] === from ? edges[2 * edge + 1] : edges[2 * edge];
      vertices.push(to);
      if (degree[to] !== 2 || to === vertices[0]) break;
      let following = -1;
      for (let s = start[to]; s < start[to + 1]; s++)
        if (!used[adjacent[s]]) {
          following = adjacent[s];
          break;
        }
      if (following < 0) break;
      from = to;
      edge = following;
    }
    return { vertices, edges: provenance };
  }
  for (let v = 0; v < vertexCount; v++)
    if (degree[v] !== 2)
      for (let s = start[v]; s < start[v + 1]; s++)
        if (!used[adjacent[s]]) yield walk(v, adjacent[s]);
  for (let e = 0; e < used.length; e++)
    if (!used[e]) yield walk(edges[2 * e], e);
}

export function projectSource(vertices, eyes) {
  if (!eyes.length) throw new RangeError("At least one eye required");
  return eyes.map(({ matrix: m, width, height }) => {
    if (
      m.length !== 16 ||
      !m.every(Number.isFinite) ||
      !(width > 0 && height > 0)
    )
      throw new RangeError("Finite clip transform and viewport required");
    const xy = new Float64Array((vertices.length / 3) * 2),
      valid = new Uint8Array(vertices.length / 3);
    for (let v = 0; v < valid.length; v++) {
      const x = vertices[3 * v],
        y = vertices[3 * v + 1],
        z = vertices[3 * v + 2];
      const w = m[3] * x + m[7] * y + m[11] * z + m[15];
      const depth = m[2] * x + m[6] * y + m[10] * z + m[14];
      const a = (((m[0] * x + m[4] * y + m[8] * z + m[12]) / w) * width) / 2;
      const b = (((m[1] * x + m[5] * y + m[9] * z + m[13]) / w) * height) / 2;
      // Full paths near either clip plane are retained; no unproved clipping bound.
      valid[v] =
        Number.isFinite(a) &&
        Number.isFinite(b) &&
        w > 1e-8 &&
        depth > -w + 1e-8 &&
        depth < w - 1e-8;
      xy[2 * v] = a;
      xy[2 * v + 1] = b;
    }
    return { xy, valid };
  });
}

function deviation(xy, p, a, b) {
  const dx = xy[2 * b] - xy[2 * a],
    dy = xy[2 * b + 1] - xy[2 * a + 1];
  const x = xy[2 * p] - xy[2 * a],
    y = xy[2 * p + 1] - xy[2 * a + 1];
  const length = dx * dx + dy * dy;
  const t = length ? Math.max(0, Math.min(1, (x * dx + y * dy) / length)) : 0;
  return Math.hypot(x - t * dx, y - t * dy);
}

export function simplifyPath(path, projections, tolerance = 0.5) {
  if (!(tolerance > 0 && tolerance <= 0.5) || !projections.length)
    throw new RangeError("A proven eye set and tolerance in (0, 0.5] required");
  const full = () => Array.from({ length: path.length }, (_, i) => i);
  if (
    path.length < 3 ||
    path[0] === path.at(-1) ||
    projections.some((p) => path.some((v) => !p.valid[v]))
  )
    return full();
  const keep = new Uint8Array(path.length);
  keep[0] = keep[path.length - 1] = 1;
  const pending = [[0, path.length - 1]];
  while (pending.length) {
    const [a, b] = pending.pop();
    let farthest = -1,
      error = tolerance * 0.999999;
    for (let k = a + 1; k < b; k++) {
      const d = Math.max(
        ...projections.map((p) => deviation(p.xy, path[k], path[a], path[b])),
      );
      if (d > error) {
        error = d;
        farthest = k;
      }
    }
    if (farthest >= 0) {
      keep[farthest] = 1;
      pending.push([a, farthest], [farthest, b]);
    }
  }
  return Array.from(keep.keys()).filter((i) => keep[i]);
}

// The original renderer retains source positions in its shared arena rather than
// each neuron. Slice only the referenced source span; never copy capacity padding.
export function sourceVertexView(positions, owners, base, edges, neuron) {
  let count = 0;
  for (const index of edges) {
    if (!Number.isInteger(index) || index < 0)
      throw Error("Invalid original source index");
    count = Math.max(count, index + 1);
  }
  if (
    !Number.isInteger(base) ||
    base < 0 ||
    3 * (base + count) > positions.length ||
    base + count > owners.length
  )
    throw Error("Original source arena bounds mismatch");
  for (const index of edges)
    if (owners[base + index] !== neuron)
      throw Error("Original source owner mismatch");
  return positions.subarray(3 * base, 3 * (base + count));
}
