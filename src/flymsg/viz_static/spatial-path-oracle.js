// Independent graph and spatial-error verifier. No candidate walker or simplifier.
export function verifySpatialPaths(positions, indices, anchors, records, cuts) {
  const count = positions.length / 3,
    degree = new Uint32Array(count),
    seen = new Uint8Array(indices.length / 2);
  for (const v of indices) {
    if (v >= count) throw Error("Source vertex outside bounds");
    degree[v]++;
  }
  const owners = new Map();
  for (let r = 0; r < records.length; r++) {
    const path = records[r],
      kept = cuts[r],
      vertices = path.vertices,
      retained = new Set(kept);
    if (
      vertices.length !== path.edges.length + 1 ||
      kept[0] !== 0 ||
      kept.at(-1) !== vertices.length - 1
    )
      throw Error("Incomplete source path partition");
    for (let k = 0; k < path.edges.length; k++) {
      const edge = path.edges[k],
        a = indices[edge * 2],
        b = indices[edge * 2 + 1];
      if (
        !Number.isInteger(edge) ||
        edge < 0 ||
        edge >= seen.length ||
        seen[edge]++ ||
        !(
          (a === vertices[k] && b === vertices[k + 1]) ||
          (b === vertices[k] && a === vertices[k + 1])
        )
      )
        throw Error("Invalid source edge provenance");
    }
    for (let k = 1; k < vertices.length - 1; k++)
      if (
        (degree[vertices[k]] !== 2 || anchors[vertices[k]]) &&
        !retained.has(k)
      )
        throw Error("Source branch or anchor crossed");
    const closed = vertices[0] === vertices.at(-1);
    if (
      closed &&
      (kept.length !== vertices.length || kept.some((v, i) => v !== i))
    )
      throw Error("Cycle changed");
    for (const endpoint of [vertices[0], vertices.at(-1)])
      if (!closed && degree[endpoint] === 2 && !anchors[endpoint])
        throw Error("Unanchored path endpoint");
    let maximum = 0;
    for (let c = 1; c < kept.length; c++) {
      const lo = kept[c - 1],
        hi = kept[c];
      if (!Number.isInteger(hi) || hi <= lo || hi >= vertices.length)
        throw Error("Invalid retained vertices");
      const a = vertices[lo] * 3,
        b = vertices[hi] * 3;
      const dx = positions[b] - positions[a],
        dy = positions[b + 1] - positions[a + 1],
        dz = positions[b + 2] - positions[a + 2];
      const denominator = dx * dx + dy * dy + dz * dz;
      for (let k = lo + 1; k < hi; k++) {
        const p = vertices[k] * 3,
          x = positions[p] - positions[a],
          y = positions[p + 1] - positions[a + 1],
          z = positions[p + 2] - positions[a + 2];
        const t = denominator
          ? Math.min(1, Math.max(0, (x * dx + y * dy + z * dz) / denominator))
          : 0;
        const distance = Math.sqrt(
          (x - t * dx) ** 2 + (y - t * dy) ** 2 + (z - t * dz) ** 2,
        );
        if (!Number.isFinite(distance)) throw Error("Nonfinite spatial proof");
        maximum = Math.max(maximum, distance);
      }
    }
    owners.set(path.owner, Math.max(owners.get(path.owner) ?? 0, maximum));
  }
  if (seen.some((n) => n !== 1))
    throw Error("Source graph not completely covered");
  return owners;
}
