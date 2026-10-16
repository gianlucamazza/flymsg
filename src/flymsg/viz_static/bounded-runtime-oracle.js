// Diagnostic only. Read the submitted native indices and independently walk the
// original graph; no candidate paths, simplifier or error estimator is imported.
export function auditSelection(
  T,
  positions,
  original,
  selected,
  anchors,
  eyes,
) {
  const vertices = positions.length / 3;
  const adjacency = Array.from({ length: vertices }, () => []);
  const retained = new Uint8Array(vertices),
    seen = new Uint8Array(original.length / 2);
  const chords = new Map();
  const key = (a, b) => (a < b ? `${a}:${b}` : `${b}:${a}`);
  for (let e = 0; e < original.length / 2; e++) {
    const a = original[2 * e],
      b = original[2 * e + 1];
    if (a >= vertices || b >= vertices)
      throw Error("Invalid original endpoint");
    adjacency[a].push([b, e]);
    adjacency[b].push([a, e]);
  }
  for (let i = 0; i < selected.length; i += 2) {
    const a = selected[i],
      b = selected[i + 1];
    if (a >= vertices || b >= vertices)
      throw Error("Invented candidate endpoint");
    retained[a] = retained[b] = 1;
    const k = key(a, b);
    chords.set(k, (chords.get(k) ?? 0) + 1);
  }
  for (let v = 0; v < vertices; v++)
    if (
      adjacency[v].length &&
      (anchors[v] || adjacency[v].length !== 2) &&
      !retained[v]
    )
      throw Error("Lost source anchor");
  const projections = eyes.map((eye) => {
    const matrix = new T.Matrix4()
      .fromArray(eye.projection)
      .multiply(new T.Matrix4().fromArray(eye.modelView));
    return Array.from({ length: vertices }, (_, v) => {
      const p = new T.Vector4(
        ...positions.subarray(3 * v, 3 * v + 3),
        1,
      ).applyMatrix4(matrix);
      return {
        x: ((p.x / p.w) * eye.width) / 2,
        y: ((p.y / p.w) * eye.height) / 2,
        valid: p.w > 0 && p.z > -p.w && p.z < p.w,
      };
    });
  });
  let maximum = 0,
    paths = 0;
  for (let start = 0; start < vertices; start++)
    if (retained[start])
      for (const [next, first] of adjacency[start]) {
        if (seen[first]) continue;
        let previous = first,
          end = next;
        const path = [start, next];
        seen[first] = 1;
        while (!retained[end]) {
          if (adjacency[end].length !== 2) throw Error("Unretained branch");
          const [to, edge] = adjacency[end].find(([, e]) => e !== previous);
          if (seen[edge]) throw Error("Unretained source cycle");
          seen[edge] = 1;
          previous = edge;
          end = to;
          path.push(end);
        }
        const k = key(start, end),
          count = chords.get(k) ?? 0;
        if (count < 1) throw Error("Missing candidate path");
        chords.set(k, count - 1);
        paths++;
        if (path.length === 2) continue;
        for (const projected of projections) {
          if (path.some((v) => !projected[v].valid))
            throw Error("Approximated clipped source path");
          const a = projected[start],
            b = projected[end],
            dx = b.x - a.x,
            dy = b.y - a.y,
            den = dx * dx + dy * dy;
          for (const v of path) {
            const p = projected[v],
              t = den
                ? Math.max(
                    0,
                    Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / den),
                  )
                : 0;
            maximum = Math.max(
              maximum,
              Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy),
            );
          }
        }
      }
  if (seen.some((v) => v !== 1) || [...chords.values()].some((v) => v !== 0))
    throw Error("Incomplete or invented graph coverage");
  if (!(maximum <= 0.5))
    throw Error("Independent projected path exceeds half a pixel");
  return {
    maximum_error_px: maximum,
    source_edges: original.length / 2,
    submitted_edges: selected.length / 2,
    paths,
  };
}

export async function auditBoundedRuntime(api, eyes) {
  const candidate = api.paged,
    gl = api.renderer.getContext(),
    results = [];
  if (!candidate?.bounded || !api.diagnosticState().suspended)
    throw Error("Idle bounded diagnostic required");
  const read = (buffer, Type, bytes) => {
    const previous = gl.getParameter(gl.COPY_READ_BUFFER_BINDING),
      array = new Type(bytes / Type.BYTES_PER_ELEMENT);
    try {
      gl.bindBuffer(gl.COPY_READ_BUFFER, buffer);
      gl.getBufferSubData(gl.COPY_READ_BUFFER, 0, array);
    } finally {
      gl.bindBuffer(gl.COPY_READ_BUFFER, previous);
    }
    return array;
  };
  // Independent union-find detects cycles in the complete original neuron,
  // before paging can hide a global branch or turn a cycle into an open path.
  const sourceInfo = new Map();
  for (const source of candidate.sources.filter((s) =>
    s.key.startsWith("skeleton:"),
  )) {
    const p = source.attributes.position.array,
      index = source.index,
      degree = new Uint32Array(p.length / 3),
      parent = Int32Array.from({ length: degree.length }, (_, i) => i);
    const root = (v) => {
      while (parent[v] !== v) {
        parent[v] = parent[parent[v]];
        v = parent[v];
      }
      return v;
    };
    let cyclic = false;
    for (let e = 0; e < index.length; e += 2) {
      const a = index[e],
        b = index[e + 1];
      degree[a]++;
      degree[b]++;
      const x = root(a),
        y = root(b);
      if (x === y) cyclic = true;
      else parent[x] = y;
    }
    sourceInfo.set(source.attributes.aNeuron.constant, {
      positions: p,
      index,
      degree,
      cyclic,
    });
  }
  candidate.bounded.apply(eyes);
  try {
    for (const page of candidate.pages.filter((p) => p.bounded)) {
      const buffers = page.record.buffers;
      const position = read(
        buffers[page.names.indexOf("position")].buffer,
        Float32Array,
        buffers[page.names.indexOf("position")].bytes,
      );
      const owner = read(
        buffers[page.names.indexOf("aNeuron")].buffer,
        Float32Array,
        buffers[page.names.indexOf("aNeuron")].bytes,
      );
      const original = read(
          buffers.at(-1).buffer,
          Uint32Array,
          buffers.at(-1).bytes,
        ),
        index = page.object.geometry.index;
      const selected = read(index.buffer, Uint32Array, index.count * 4);
      for (let v = 0; v < owner.length; v++) {
        const source = sourceInfo.get(owner[v]),
          origin = page.boundedSource.origins[v];
        if (
          !source ||
          origin >= source.degree.length ||
          position
            .subarray(v * 3, v * 3 + 3)
            .some((x, a) => x !== source.positions[origin * 3 + a])
        )
          throw Error("GPU vertex differs from original source");
        if (
          (source.cyclic || source.degree[origin] !== 2) &&
          !page.boundedSource.anchors[v]
        )
          throw Error("Missing global source anchor");
      }
      let offset = 0;
      for (const span of page.spans) {
        const neuron = Number(span.source.slice("skeleton:".length)),
          source = sourceInfo.get(neuron);
        if (!source) throw Error("Unknown source span");
        for (let k = 0; k < span.count * 2; k++) {
          const v = original[offset + k];
          if (
            owner[v] !== neuron ||
            page.boundedSource.origins[v] !== source.index[span.first * 2 + k]
          )
            throw Error("GPU full index differs from original source order");
        }
        offset += span.count * 2;
      }
      if (offset !== original.length)
        throw Error("Uncovered GPU source indices");
      results.push(
        auditSelection(
          api.THREE,
          position,
          original,
          selected,
          page.boundedSource.anchors,
          eyes,
        ),
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  } finally {
    candidate.bounded.restore();
  }
  return {
    status: "pass",
    pages: results,
    qualification:
      "independent graph and projected geometry only; not raster or hardware acceptance",
  };
}
