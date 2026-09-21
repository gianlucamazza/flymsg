import assert from "node:assert/strict";
import { test } from "node:test";

import { BufferAttribute, BufferGeometry } from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { centroid, finishFragment, signedVolume, skeletonLevels } from "../../src/flymsg/viz_static/geometry.js";

// unit tetrahedron, triangles wound counter-clockwise seen from outside
const TET_Q = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]);
const TET_I = new Uint32Array([0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3]);

test("dequantization applies the per-axis affine map", () => {
  const { positions } = finishFragment(TET_Q, TET_I, [2, 3, 4], [10, 20, 30]);
  assert.deepEqual([...positions.slice(3, 6)], [12, 20, 30]);
  assert.deepEqual([...positions.slice(9, 12)], [10, 20, 34]);
});

test("normals equal three.js computeVertexNormals", () => {
  const scale = [0.5, 1.5, 2], offset = [1, -2, 3];
  const { positions, normals } = finishFragment(TET_Q, TET_I, scale, offset);
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(positions.slice(), 3));
  g.setIndex(new BufferAttribute(TET_I.slice(), 1));
  g.computeVertexNormals();
  const ref = g.getAttribute("normal").array;
  for (let i = 0; i < normals.length; i++) assert.ok(Math.abs(normals[i] - ref[i]) < 1e-6, `component ${i}`);
});

test("signed volume: positive outward, negative when flipped", () => {
  assert.ok(Math.abs(signedVolume(TET_Q, TET_I) - 1 / 6) < 1e-9);
  const flipped = TET_I.slice();
  for (let t = 0; t < flipped.length; t += 3) [flipped[t + 1], flipped[t + 2]] = [flipped[t + 2], flipped[t + 1]];
  assert.ok(signedVolume(TET_Q, flipped) < 0);
});

test("signed volume of a closed mesh does not depend on the origin", () => {
  const far = [1e5, -3e4, 7e4];
  assert.ok(Math.abs(signedVolume(TET_Q, TET_I, far) - 1 / 6) < 1e-6);
  assert.deepEqual(centroid([TET_Q]), [0.25, 0.25, 0.25]);
});

// a Y: a wavy stem 0..8 along x (amplitude 1 in y), branching at 8 into two straight arms
function yTree() {
  const v = [];
  for (let i = 0; i <= 8; i++) v.push(i * 10, i % 2 ? 1 : 0, 0);
  for (let i = 1; i <= 4; i++) v.push(80 + i * 10, i * 10, 0); // arm 1: vertices 9..12
  for (let i = 1; i <= 4; i++) v.push(80 + i * 10, -i * 10, 0); // arm 2: vertices 13..16
  const e = [];
  for (let i = 0; i < 8; i++) e.push(i, i + 1);
  e.push(8, 9, 9, 10, 10, 11, 11, 12, 8, 13, 13, 14, 14, 15, 15, 16);
  return { vertices: new Float32Array(v), edges: new Uint32Array(e) };
}
const degrees = (edges) => {
  const d = new Map();
  for (const v of edges) d.set(v, (d.get(v) ?? 0) + 1);
  return d;
};
function distToPolyline(p, i, pairs) {
  let best = Infinity;
  for (let s = 0; s < pairs.length; s += 2) {
    const [a, b] = [pairs[s], pairs[s + 1]];
    const d = [0, 1, 2].map((k) => p[3 * b + k] - p[3 * a + k]);
    const q = [0, 1, 2].map((k) => p[3 * i + k] - p[3 * a + k]);
    const l2 = d[0] ** 2 + d[1] ** 2 + d[2] ** 2;
    const t = l2 ? Math.max(0, Math.min(1, (q[0] * d[0] + q[1] * d[1] + q[2] * d[2]) / l2)) : 0;
    best = Math.min(best, Math.hypot(q[0] - t * d[0], q[1] - t * d[1], q[2] - t * d[2]));
  }
  return best;
}

test("skeleton levels: level 0 is the full skeleton, coarser levels drop segments", () => {
  const { vertices, edges } = yTree();
  const { eps, levels, bounds } = skeletonLevels(vertices, edges, 0.5, 4);
  assert.equal(levels[0], edges);
  assert.equal(eps[0], 0);
  for (let l = 1; l < levels.length; l++) assert.ok(levels[l].length < levels[l - 1].length);
  // straight arms collapse to one segment each, the wavy stem to one once eps >= 1
  assert.equal(levels.at(-1).length / 2, 3);
  assert.deepEqual(bounds, { min: [0, -40, 0], max: [120, 40, 0] });
});

test("skeleton levels: ends and branch points survive, every vertex stays within eps", () => {
  const { vertices, edges } = yTree();
  const { eps, levels } = skeletonLevels(vertices, edges, 0.5, 4);
  const anchors = [...degrees(edges)].filter(([, d]) => d !== 2).map(([v]) => v);
  for (let l = 1; l < levels.length; l++) {
    const kept = new Set(levels[l]);
    for (const a of anchors) assert.ok(kept.has(a), `anchor ${a} at level ${l}`);
    for (let i = 0; i < vertices.length / 3; i++)
      assert.ok(distToPolyline(vertices, i, levels[l]) <= eps[l] + 1e-9, `vertex ${i} at level ${l}`);
  }
});

test("skeleton levels: a closed loop of degree-2 vertices is kept", () => {
  const vertices = new Float32Array([0, 0, 0, 10, 0, 0, 10, 10, 0, 0, 10, 0]);
  const edges = new Uint32Array([0, 1, 1, 2, 2, 3, 3, 0]);
  const { levels } = skeletonLevels(vertices, edges, 1, 2);
  assert.equal(levels.length, 1); // every corner matters at these tolerances
});
