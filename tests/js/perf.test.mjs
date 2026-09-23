import assert from "node:assert/strict";
import { test } from "node:test";

import { percentile } from "../../src/flymsg/viz_static/perf.js";

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
