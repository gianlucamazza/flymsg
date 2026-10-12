import assert from "node:assert/strict";
import { test } from "node:test";

import { activityAt } from "../../src/flymsg/viz_static/activity.js";
import {
  binAt,
  rasterRows,
  selectionExport,
  selectionRows,
} from "../../src/flymsg/viz_static/raster.js";

// two neurons, six 10 ms bins; neuron 0 spikes in bin 2, neuron 1 never
const shape = { n: 2, bins: 6, binMs: 10 };
const spikes = new Uint8Array(12);
spikes[2 * 2 + 0] = 3;

test("the raster cursor and the 3D glow show the same bin at every time", () => {
  for (let t = 0; t < 60; t += 0.5) {
    // a one-bin history lights neuron 0 only while the glow is reading bin 2
    const glow = activityAt(spikes, shape, t, new Float32Array(2), 15, 1)[0];
    assert.equal(glow > 0, binAt(t, 10, 6) === 2, `t = ${t}`);
  }
  assert.equal(binAt(1e6, 10, 6), 5);
  assert.equal(binAt(-1, 10, 6), 0);
});

test("rows carry counts per bin, and a silent neuron is marked by its zero total", () => {
  const [a, b] = rasterRows(spikes, shape, [0, 1]);
  assert.deepEqual(Array.from(a.counts), [0, 0, 3, 0, 0, 0]);
  assert.equal(a.total, 3);
  assert.equal(b.total, 0);
});

test("selection rows: the neuron, then partners by role, capped", () => {
  const entry = {
    upstream: { in_scene: [[4, 9], [2, 5]] },
    downstream: { in_scene: [[2, 7], [6, 1]] },
  };
  assert.deepEqual(selectionRows(1, entry), { rows: [1, 4, 2, 6], hidden: 0 });
  assert.deepEqual(selectionRows(1, entry, 2), { rows: [1, 4], hidden: 2 });
  assert.deepEqual(selectionRows(3, undefined), { rows: [3], hidden: 0 });
});

test("the export names its source and says it is a model replay", () => {
  const neurons = [{ bodyId: 10, type: "A" }, { bodyId: 11, type: "B" }];
  const rows = rasterRows(spikes, shape, [0]);
  const out = selectionExport({
    neurons,
    rows,
    activity: { bin_ms: 10, stim_ms: 30 },
    t: 25,
    manifest: { command: "viz", git: { commit: "abc", dirty: false }, seeds: { seed: 0 } },
  });
  assert.equal(out.schema, "flymsg.selection/v1");
  assert.match(out.note, /not recordings/);
  assert.equal(out.neurons[0].bodyId, 10);
  assert.equal(out.source.commit, "abc");
  assert.equal(selectionExport({ neurons, rows, activity: {}, t: 0 }).source, null);
});
