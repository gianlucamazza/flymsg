import assert from "node:assert/strict";
import { test } from "node:test";

import { FULL, gradedAt, gradedMv } from "../../src/flymsg/viz_static/graded.js";

// scene rows 3 and 0 are graded; three 10 ms bins
const shape = { k: [3, 0], bins: 3, binMs: 10, scaleMv: [20, 50] };
const steps = new Int8Array([127, -127, 0, 64, -64, 0]);

test("a graded neuron glows by the signed potential of the current bin", () => {
  const out = new Float32Array(4).fill(0.25);
  gradedAt(steps, shape, 5, out);
  // full scale glows like one spike; spiking rows keep their glow
  assert.deepEqual([...out], [-FULL, 0.25, 0.25, FULL]);
  gradedAt(steps, shape, 25, out);
  assert.ok(Math.abs(out[3] + (FULL * 64) / 127) < 1e-6 && out[0] === 0);
});

test("the panel reads millivolts back from the steps", () => {
  assert.equal(gradedMv(steps, shape, 0, 1), -50);
  assert.ok(Math.abs(gradedMv(steps, shape, 1, 1) - (64 / 127) * 50) < 1e-9);
});
