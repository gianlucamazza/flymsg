import assert from "node:assert/strict";
import { test } from "node:test";

import { BufferAttribute, BufferGeometry } from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { centroid, finishFragment, signedVolume } from "../../src/flymsg/viz_static/geometry.js";

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
