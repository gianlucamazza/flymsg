import assert from "node:assert/strict";
import { test } from "node:test";

import { activityAt } from "../../src/flymsg/viz_static/activity.js";

// two neurons, four 10 ms bins; neuron 0 spikes once in bin 0, neuron 1 twice in bin 2
const shape = { n: 2, bins: 4, binMs: 10 };
const spikes = new Uint16Array([1, 0, 0, 0, 0, 2, 0, 0]);
const at = (t, tau = 15, history = 5) =>
  [...activityAt(spikes, shape, t, new Float32Array(2), tau, history)];

test("a spike glows at half strength and fades with the time constant", () => {
  const [a] = at(5); // the middle of bin 0: no age yet
  assert.equal(a, 0.5);
  const [b] = at(20); // 15 ms later: one time constant
  assert.ok(Math.abs(b - 0.5 * Math.exp(-1)) < 1e-6);
});

test("two spikes in one bin saturate", () => {
  assert.equal(at(25)[1], 1);
});

test("bins older than the history window are dropped, and time is clamped to the last bin", () => {
  assert.equal(at(35, 15, 2)[0], 0); // at bin 3 a 2-bin window starts at bin 2
  assert.ok(at(35, 15, 2)[1] > 0); // the spikes in bin 2 are still in it
  assert.ok(at(35, 15, 5)[0] > 0); // a 5-bin window still reaches bin 0
  // past the end of the replay the bin is clamped but the age is not, so the glow has faded
  assert.deepEqual(at(1e6), [0, 0]);
});
