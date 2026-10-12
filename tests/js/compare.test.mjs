import assert from "node:assert/strict";
import { test } from "node:test";

import { COMPARE_COLORS, colourOf } from "../../src/flymsg/viz_static/colors.js";
import {
  compareClass,
  difference,
  differenceLines,
  firstBin,
  neuronLines,
  runLines,
  totals,
} from "../../src/flymsg/viz_static/compare.js";

const shape = { n: 2, bins: 3 };
const a = new Uint8Array([1, 0, 2, 0, 0, 0]); // bin-major: neuron 0 has 1 and 2 in bins 0, 1
const b = new Uint8Array([1, 0, 0, 0, 0, 0]); // neuron 0: bin 0 only

test("identical runs have zero difference everywhere", () => {
  assert.ok(difference(a, a).every((x) => x === 0));
  assert.deepEqual(Array.from(difference(a, b)), [0, 0, 2, 0, 0, 0]);
});

test("totals, first bins and classes", () => {
  assert.deepEqual(Array.from(totals(a, shape)), [3, 0]);
  assert.equal(firstBin(a, shape, 0), 0);
  assert.equal(firstBin(a, shape, 1), null);
  assert.equal(compareClass(true, true, 3, 1), "less");
  assert.equal(compareClass(true, true, 1, 3), "more");
  assert.equal(compareClass(true, true, 2, 2), "same");
  assert.equal(compareClass(true, false, 2, 0), "not exported");
});

test("a failed protocol is never shown as a mechanism", () => {
  const lines = runLines({
    runs: [
      { label: "baseline", status: "exploratory", note: "" },
      { label: "DNp01 silenced", status: "failed", note: "behavior v1 silence check" },
    ],
  });
  assert.match(lines[1], /failed protocol: not evidence for a mechanism/);
  assert.doesNotMatch(lines.join(" "), /validated/);
  assert.deepEqual(differenceLines({ differences: [] }), ["the two run manifests match"]);
  assert.deepEqual(
    differenceLines({ differences: [{ key: "config.silence", a: [], b: ["DNp01"] }] }),
    ['config.silence: [] → ["DNp01"]'],
  );
});

test("panel lines say when a neuron is not exported in a run", () => {
  const lines = neuronLines(
    { in: [true, false] },
    0,
    { spikesA: a, spikesB: b, shape, binMs: 10, labels: ["base", "silenced"] },
  );
  assert.deepEqual(lines, [
    "A base: 3 spikes, first in the 0–10 ms bin",
    "B silenced: not exported in this run",
  ]);
});

test("compare colours apply when no neuron is selected", () => {
  const view = { colorBy: "group", focus: null, compare: ["more", "less"] };
  assert.equal(colourOf({ k: 0, group: "g" }, view, ["g"]), COMPARE_COLORS.more);
  assert.equal(colourOf({ k: 1, group: "g" }, view, ["g"]), COMPARE_COLORS.less);
});
