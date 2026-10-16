// Worker-only spatial preparation. Original float32 source arrays are never changed.
import { sourcePaths } from "./bounded-paths.js";
import { verifySpatialPaths } from "./spatial-path-oracle.js";

export function sourceAnchors(vertexCount, indices) {
  const degree = new Uint32Array(vertexCount);
  for (const v of indices) {
    if (v >= vertexCount) throw Error("Source endpoint outside vertices");
    degree[v]++;
  }
  const anchors = Uint8Array.from(degree, (d) => (d !== 2 ? 1 : 0));
  // Iterative bridge discovery handles parallel edges and self-loops by edge ID.
  // Every endpoint on a non-bridge edge is locked: cyclic source paths stay exact.
  const start = new Uint32Array(vertexCount + 1);
  for (let v = 0; v < vertexCount; v++) start[v + 1] = start[v] + degree[v];
  const cursor = start.slice(),
    adj = new Uint32Array(indices.length);
  for (let e = 0; e < indices.length / 2; e++) {
    adj[cursor[indices[2 * e]]++] = e;
    adj[cursor[indices[2 * e + 1]]++] = e;
  }
  cursor.set(start.subarray(0, vertexCount));
  const visited = new Uint32Array(vertexCount),
    low = new Uint32Array(vertexCount),
    parent = new Int32Array(vertexCount).fill(-1),
    bridge = new Uint8Array(indices.length / 2);
  let time = 0;
  for (let root = 0; root < vertexCount; root++)
    if (!visited[root]) {
      visited[root] = low[root] = ++time;
      const stack = [root];
      while (stack.length) {
        const v = stack.at(-1);
        if (cursor[v] < start[v + 1]) {
          const e = adj[cursor[v]++];
          if (e === parent[v]) continue;
          const to = indices[2 * e] === v ? indices[2 * e + 1] : indices[2 * e];
          if (!visited[to]) {
            parent[to] = e;
            visited[to] = low[to] = ++time;
            stack.push(to);
          } else low[v] = Math.min(low[v], visited[to]);
        } else {
          stack.pop();
          const e = parent[v];
          if (e < 0) continue;
          const from =
            indices[2 * e] === v ? indices[2 * e + 1] : indices[2 * e];
          if (low[v] > visited[from]) bridge[e] = 1;
          low[from] = Math.min(low[from], low[v]);
        }
      }
    }
  if (bridge.some((flag) => flag === 0)) anchors.fill(1); // A cyclic source remains entirely exact.
  return anchors;
}

function distance(p, v, a, b) {
  const dx = p[3 * b] - p[3 * a],
    dy = p[3 * b + 1] - p[3 * a + 1],
    dz = p[3 * b + 2] - p[3 * a + 2];
  const x = p[3 * v] - p[3 * a],
    y = p[3 * v + 1] - p[3 * a + 1],
    z = p[3 * v + 2] - p[3 * a + 2];
  const d = dx * dx + dy * dy + dz * dz,
    t = d ? Math.max(0, Math.min(1, (x * dx + y * dy + z * dz) / d)) : 0;
  return Math.hypot(x - t * dx, y - t * dy, z - t * dz);
}
function hierarchy(p, vertices) {
  const error = new Float64Array(vertices.length).fill(Infinity);
  if (vertices[0] === vertices.at(-1)) return error;
  const pending = [[0, vertices.length - 1, Infinity]];
  while (pending.length) {
    const [a, b, cap] = pending.pop();
    let best = -1,
      maximum = -1;
    for (let k = a + 1; k < b; k++) {
      const d = distance(p, vertices[k], vertices[a], vertices[b]);
      if (d > maximum) {
        best = k;
        maximum = d;
      }
    }
    if (best < 0) continue;
    error[best] = Math.min(cap, maximum);
    pending.push([a, best, error[best]], [best, b, error[best]]);
  }
  return error;
}
function ranges(index, owner) {
  const result = [];
  for (let at = 0; at < index.length; at += 2) {
    const id = owner[index[at]];
    if (id !== owner[index[at + 1]]) throw Error("Cross-neuron edge");
    const last = result.at(-1);
    if (last?.owner === id) last.count += 2;
    else result.push({ owner: id, first: at, count: 2 });
  }
  return result;
}
export function compilePageLods(page, { base = 1, count = 10 } = {}) {
  const started = performance.now();
  const preparation = {
    paths_ms: 0,
    hierarchy_ms: 0,
    boxes_ms: 0,
    cuts_ms: 0,
    verification_ms: 0,
    assembly_ms: 0,
  };
  const positions = page.attributes.position.array,
    owner = page.attributes.aNeuron.array;
  const anchors = page.boundedSource.anchors,
    records = [];
  for (const path of sourcePaths(positions.length / 3, page.index)) {
    if (path.vertices[0] === path.vertices.at(-1))
      records.push({ ...path, owner: owner[path.vertices[0]] });
    else {
      let start = 0;
      for (let k = 1; k < path.vertices.length; k++)
        if (k === path.vertices.length - 1 || anchors[path.vertices[k]]) {
          records.push({
            vertices: path.vertices.slice(start, k + 1),
            edges: path.edges.slice(start, k),
            owner: owner[path.vertices[start]],
          });
          start = k;
        }
    }
  }
  records.sort(
    (a, b) =>
      a.edges.reduce((x, y) => Math.min(x, y), Infinity) -
      b.edges.reduce((x, y) => Math.min(x, y), Infinity),
  );
  preparation.paths_ms = performance.now() - started;
  let stage = performance.now();
  const errors = records.map((path) => hierarchy(positions, path.vertices));
  preparation.hierarchy_ms = performance.now() - stage;
  stage = performance.now();
  const boxes = {};
  let magnitude = 1;
  for (let v = 0; v < owner.length; v++) {
    const box = (boxes[owner[v]] ??= {
      min: [Infinity, Infinity, Infinity],
      max: [-Infinity, -Infinity, -Infinity],
    });
    for (let a = 0; a < 3; a++) {
      const x = positions[3 * v + a];
      if (!Number.isFinite(x)) throw Error("Nonfinite source position");
      box.min[a] = Math.min(box.min[a], x);
      box.max[a] = Math.max(box.max[a], x);
      magnitude = Math.max(magnitude, Math.abs(x));
    }
  }
  const full = {
    index: page.index.slice(),
    ranges: ranges(page.index, owner),
    errors: Object.fromEntries(Object.keys(boxes).map((k) => [k, 0])),
  };
  preparation.boxes_ms = performance.now() - stage;
  const variants = new Map([[0, full]]);
  let bytes = 0;
  for (let level = count; level >= 1; level--) {
    stage = performance.now();
    const tolerance = base * 2 ** (level - 1);
    const cuts = records.map((p, r) =>
      Array.from(errors[r].keys()).filter((i) => errors[r][i] > tolerance),
    );
    preparation.cuts_ms += performance.now() - stage;
    stage = performance.now();
    const proof = verifySpatialPaths(
      positions,
      page.index,
      anchors,
      records,
      cuts,
    );
    preparation.verification_ms += performance.now() - stage;
    stage = performance.now();
    const length = cuts.reduce((sum, k) => sum + 2 * (k.length - 1), 0);
    if (
      length >= page.index.length ||
      bytes + length * 4 > page.index.byteLength
    )
      continue;
    const index = new Uint32Array(length);
    let at = 0;
    records.forEach((path, r) => {
      for (let k = 1; k < cuts[r].length; k++) {
        index[at++] = path.vertices[cuts[r][k - 1]];
        index[at++] = path.vertices[cuts[r][k]];
      }
    });
    if (
      [...variants.values()].some(
        (v) =>
          v.index.length === index.length &&
          v.index.every((x, i) => x === index[i]),
      )
    )
      continue;
    const record = {
      index,
      ranges: ranges(index, owner),
      errors: Object.fromEntries(
        [...proof].map(([k, error]) => [
          k,
          error === 0 ? 0 : error + 128 * Number.EPSILON * magnitude,
        ]),
      ),
    };
    variants.set(level, record);
    bytes += index.byteLength;
    preparation.assembly_ms += performance.now() - stage;
  }
  return {
    variants,
    metadata: {
      boxes,
      preparation,
      levels: [...variants].map(([id, v]) => ({
        id,
        ranges: v.ranges,
        errors: v.errors,
      })),
      cpu_index_bytes: page.index.byteLength + bytes,
      source_indices: page.index.length,
    },
  };
}
export function composePageLod(catalogue, selection) {
  const full = catalogue.variants.get(0),
    pieces = [];
  let length = 0;
  for (const range of full.ranges) {
    const level = selection[range.owner] ?? 0,
      variant = catalogue.variants.get(level);
    if (!variant) throw Error("Unknown certified level");
    const source = variant.ranges.filter((r) => r.owner === range.owner);
    // Canonical pages contain each source neuron in one contiguous source-order run.
    if (full.ranges.filter((r) => r.owner === range.owner).length !== 1)
      throw Error("Noncontiguous neuron source run");
    for (const span of source) {
      pieces.push(variant.index.subarray(span.first, span.first + span.count));
      length += span.count;
    }
  }
  const indices = new Uint32Array(length);
  let at = 0;
  for (const piece of pieces) {
    indices.set(piece, at);
    at += piece.length;
  }
  return indices;
}
