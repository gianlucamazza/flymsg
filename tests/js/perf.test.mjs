import assert from "node:assert/strict";
import { test } from "node:test";

import { Perf, percentile } from "../../src/flymsg/viz_static/perf.js";

test("percentile picks a sample (0..100), never interpolating", () => {
  const v = [1, 2, 3, 4];
  assert.equal(percentile(v, 0), 1);
  assert.equal(percentile(v, 50), 3); // the sample at index floor(0.5 * 4)
  assert.equal(percentile(v, 100), 4); // clamped to the last sample
  assert.equal(percentile([5], 90), 5);
});

test("percentile sorts its input and reports nothing for no samples", () => {
  assert.equal(percentile([4, 1, 3, 2], 50), percentile([1, 2, 3, 4], 50));
  assert.equal(percentile([], 50), null);
});

test("slow continuous frames reach the adaptive fallback without a GPU timer", (t) => {
  let now = 0;
  t.mock.method(performance, "now", () => now);
  const p = new Perf({
    info: { reset() {}, render: { calls: 1, triangles: 10, lines: 20 } },
    getContext: () => ({ getExtension: () => null }),
  });
  const frame = (time, continuous) => {
    now = time;
    p.begin();
    p.end({ continuous });
  };
  frame(0, true);
  frame(250, true);
  frame(500, true);
  assert.equal(p.fps, 4);
  assert.deepEqual(p.intervals, [250, 250]);
  // A redraw after an idle interval is not a low-framerate sample.
  frame(10000, false);
  assert.equal(p.fps, 0);
  assert.match(p.line(1, 4), /^idle/);
  assert.equal(p.summary().fps.p50, null);
  frame(20000, true);
  frame(20250, true);
  assert.deepEqual(p.intervals, [250, 250, 250]);
  // After changing quality, tuneQuality waits 12 frames. Its no-GPU decision must
  // use those new samples, not the HUD window dominated by the prior slow tier.
  for (let i = 1; i <= 40; i++) frame(20250 + i * 250, true);
  for (let i = 1; i <= 12; i++) frame(30250 + i * 20, true);
  assert.equal(p.fps, 4);
  assert.equal(p.recentFrameMs(8), 20);
});
