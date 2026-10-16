import { test } from "node:test";
import assert from "node:assert/strict";
import { verifyCoverage } from "../../scripts/observer_oracle.mjs";
test("full original counts require each original primitive exactly once", () => {
  const expected = { "skeleton:3": 5, "skeleton:9": 2 };
  const a = { source: "skeleton:3", first: 0, count: 3 },
    b = { source: "skeleton:3", first: 3, count: 2 },
    c = { source: "skeleton:9", first: 0, count: 2 };
  verifyCoverage(expected, [{ spans: [a] }, { spans: [b, c] }]);
  for (const spans of [
    [a, c],
    [a, { ...b, first: 4 }, c],
    [a, a, b, c],
    [a, b, { ...c, count: 3 }],
  ])
    assert.throws(() => verifyCoverage(expected, [{ spans }]), /coverage/);
});
