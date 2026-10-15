// Immutable spatial ownership of original line segments. Endpoints are never split,
// quantized or moved. edgePage maps original edge order to conservative leaf bounds.
export function linePages(vertices, edges, maxEdges = 2048) {
  if (
    vertices.length % 3 ||
    edges.length % 2 ||
    !Number.isInteger(maxEdges) ||
    maxEdges < 1
  )
    throw new RangeError("Invalid line page input");
  const count = edges.length / 2;
  const edgePage = new Uint32Array(count);
  const order = Uint32Array.from({ length: count }, (_, i) => i);
  const centers = new Float64Array(count * 3);
  for (let e = 0; e < count; e++) {
    const a = edges[2 * e],
      b = edges[2 * e + 1];
    if (a >= vertices.length / 3 || b >= vertices.length / 3)
      throw new RangeError("Line index outside source vertices");
    for (let axis = 0; axis < 3; axis++) {
      const va = vertices[3 * a + axis],
        vb = vertices[3 * b + axis];
      if (!Number.isFinite(va) || !Number.isFinite(vb))
        throw new RangeError("Non-finite endpoint");
      centers[3 * e + axis] = (va + vb) / 2;
    }
  }
  const boxes = [],
    sizes = [];
  function split(start, end) {
    if (end - start <= maxEdges) {
      const min = [Infinity, Infinity, Infinity],
        max = [-Infinity, -Infinity, -Infinity];
      const page = sizes.length;
      for (let i = start; i < end; i++) {
        const e = order[i];
        edgePage[e] = page;
        for (let endpoint = 0; endpoint < 2; endpoint++) {
          const v = edges[2 * e + endpoint];
          for (let axis = 0; axis < 3; axis++) {
            min[axis] = Math.min(min[axis], vertices[3 * v + axis]);
            max[axis] = Math.max(max[axis], vertices[3 * v + axis]);
          }
        }
      }
      boxes.push(...min, ...max);
      sizes.push(end - start);
      return;
    }
    const min = [Infinity, Infinity, Infinity],
      max = [-Infinity, -Infinity, -Infinity];
    for (let i = start; i < end; i++)
      for (let a = 0; a < 3; a++) {
        const c = centers[3 * order[i] + a];
        min[a] = Math.min(min[a], c);
        max[a] = Math.max(max[a], c);
      }
    const axis = [0, 1, 2].reduce(
      (best, a) => (max[a] - min[a] > max[best] - min[best] ? a : best),
      0,
    );
    order
      .subarray(start, end)
      .sort((a, b) => centers[3 * a + axis] - centers[3 * b + axis] || a - b);
    const middle = (start + end) >>> 1;
    split(start, middle);
    split(middle, end);
  }
  if (count) split(0, count);
  return {
    edgePage,
    bounds: new Float64Array(boxes),
    sizes: new Uint32Array(sizes),
  };
}

/** Planes are inward [x,y,z,d], in the same coordinates as source vertices.
 * A union of eyes is required: reject only if every eye excludes the whole box.
 * null disables culling for independent full-geometry reference captures.
 */
export function visibleLinePages(pages, eyePlanes) {
  const visible = new Uint8Array(pages.sizes.length);
  let edges = 0;
  for (let page = 0; page < visible.length; page++) {
    const o = 6 * page,
      b = pages.bounds;
    const shown =
      eyePlanes === null ||
      eyePlanes.some((planes) =>
        planes.every(([x, y, z, d]) => {
          const ax = x * b[o + (x >= 0 ? 3 : 0)];
          const ay = y * b[o + (y >= 0 ? 4 : 1)];
          const az = z * b[o + (z >= 0 ? 5 : 2)];
          const margin =
            1e-12 *
            (Math.abs(ax) + Math.abs(ay) + Math.abs(az) + Math.abs(d) + 1);
          return ax + ay + az + d >= -margin;
        }),
      );
    if (shown) {
      visible[page] = 1;
      edges += pages.sizes[page];
    }
  }
  return { visible, edges };
}

/** Copy in ORIGINAL edge order, retaining deterministic depth ties and neuron ownership. */
export function writeVisibleEdges(
  target,
  offset,
  edges,
  pages,
  visible,
  vertexBase = 0,
) {
  for (let e = 0; e < pages.edgePage.length; e++) {
    if (!visible[pages.edgePage[e]]) continue;
    target[offset++] = vertexBase + edges[2 * e];
    target[offset++] = vertexBase + edges[2 * e + 1];
  }
  return offset;
}
