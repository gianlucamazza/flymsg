import assert from "node:assert/strict";
import { test } from "node:test";

import {
  effectiveBudget,
  scaledRatio,
  trisPerByte,
  vertsPerTri,
} from "../../src/flymsg/viz_static/budget.js";

test("the learned ratios fall back to their defaults until enough geometry is decoded", () => {
  assert.equal(trisPerByte({ bytes: 1e4, tris: 1e6 }), 0.6);
  assert.equal(vertsPerTri({ tris: 1e4, verts: 1e6 }), 0.6);
  assert.equal(trisPerByte({ bytes: 2e5, tris: 1e5 }), 0.5);
  assert.equal(vertsPerTri({ tris: 2e5, verts: 1e5 }), 0.5);
});

test("the budget is the smallest of the request, the vertex buffer and the index buffer", () => {
  const stats = { bytes: 2e5, tris: 2e5, verts: 1e5 }; // 0.5 vertices per triangle
  const roomy = { vertices: 1e9, indices: 1e9 };
  assert.equal(effectiveBudget(stats, roomy, 1), 0.9e6); // the request, minus 10% slack
  assert.equal(effectiveBudget(stats, { vertices: 1e5, indices: 1e9 }, 1), 0.9 * 2e5);
  assert.equal(effectiveBudget(stats, { vertices: 1e9, indices: 3e5 }, 1), 0.9 * 1e5);
});

test("the pixel ratio scales with the square root of the frame time, in steps of 1/20", () => {
  assert.equal(scaledRatio(1, 16.7, 16.7), 1); // on target: unchanged
  assert.equal(scaledRatio(1, 66.8, 16.7), 0.5); // four times too slow: half the ratio
  assert.equal(scaledRatio(2, 16.7, 66.8), 4); // room to spare: twice the ratio
  assert.equal(scaledRatio(1, 19, 16.7), 0.95); // rounded to the nearest 0.05
});
