// Independent verifier: original edges, pinned vector projection and direct distances.
// No candidate path walker, simplifier, projection or error estimator is imported.
export function verifyBoundedPaths(
  T,
  vertices,
  edges,
  records,
  eyes,
  limit = 0.5,
) {
  if (!(limit > 0 && limit <= 0.5) || !eyes.length)
    throw Error("Invalid error contract");
  const degree = new Uint32Array(vertices.length / 3),
    covered = new Uint8Array(edges.length / 2);
  for (const v of edges) degree[v]++;
  let maximum = 0,
    candidateEdges = 0;
  const projected = eyes.map((eye) => {
    const matrix = new T.Matrix4().fromArray(eye.matrix);
    const xy = new Float64Array(degree.length * 2),
      valid = new Uint8Array(degree.length);
    for (let v = 0; v < degree.length; v++) {
      const q = new T.Vector4(
        vertices[3 * v],
        vertices[3 * v + 1],
        vertices[3 * v + 2],
        1,
      ).applyMatrix4(matrix);
      xy[2 * v] = ((q.x / q.w) * eye.width) / 2;
      xy[2 * v + 1] = ((q.y / q.w) * eye.height) / 2;
      valid[v] =
        q.w > 1e-8 &&
        q.z > -q.w + 1e-8 &&
        q.z < q.w - 1e-8 &&
        Number.isFinite(xy[2 * v]) &&
        Number.isFinite(xy[2 * v + 1]);
    }
    return { xy, valid };
  });
  for (const { vertices: path, edges: provenance, cuts } of records) {
    if (
      path.length !== provenance.length + 1 ||
      cuts[0] !== 0 ||
      cuts.at(-1) !== path.length - 1
    )
      throw Error("Path endpoint or provenance mismatch");
    for (let k = 0; k < provenance.length; k++) {
      const e = provenance[k],
        a = edges[2 * e],
        b = edges[2 * e + 1];
      if (
        !Number.isInteger(e) ||
        e < 0 ||
        e >= covered.length ||
        covered[e]++ ||
        !(
          (a === path[k] && b === path[k + 1]) ||
          (b === path[k] && a === path[k + 1])
        )
      )
        throw Error("Missing, duplicated or invented source edge");
    }
    for (let k = 1; k < path.length - 1; k++)
      if (degree[path[k]] !== 2)
        throw Error("Simplification crosses a source branch");
    const closed = path[0] === path.at(-1);
    if (!closed && (degree[path[0]] === 2 || degree[path.at(-1)] === 2))
      throw Error("Path terminates inside an unbranched source path");
    if (
      (closed || projected.some((p) => path.some((v) => !p.valid[v]))) &&
      (cuts.length !== path.length || cuts.some((v, i) => v !== i))
    )
      throw Error("Cycle or clipped path was approximated");
    for (let c = 1; c < cuts.length; c++) {
      const first = cuts[c - 1],
        last = cuts[c];
      if (!Number.isInteger(last) || last <= first || last >= path.length)
        throw Error("Invalid path partition");
      candidateEdges++;
      if (last === first + 1) continue;
      for (const { xy } of projected) {
        const a = path[first],
          b = path[last];
        const ax = xy[2 * a],
          ay = xy[2 * a + 1],
          bx = xy[2 * b],
          by = xy[2 * b + 1];
        for (let k = first + 1; k < last; k++) {
          const px = xy[2 * path[k]],
            py = xy[2 * path[k] + 1];
          const denom = (bx - ax) ** 2 + (by - ay) ** 2;
          const t =
            denom === 0
              ? 0
              : Math.min(
                  1,
                  Math.max(
                    0,
                    ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / denom,
                  ),
                );
          const distance = Math.sqrt(
            (px - (ax + t * (bx - ax))) ** 2 + (py - (ay + t * (by - ay))) ** 2,
          );
          maximum = Math.max(maximum, distance);
          if (!(distance <= limit))
            throw Error("Projected original path exceeds error contract");
        }
      }
    }
  }
  if (covered.some((n) => n !== 1))
    throw Error("Original graph not completely covered");
  return {
    maximum_error_px: maximum,
    original_edges: covered.length,
    candidate_edges: candidateEdges,
    paths: records.length,
  };
}
