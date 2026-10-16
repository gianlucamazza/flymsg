// Audit recorded expectations with the unchanged pinned implementation, never
// with the candidate certificate function. Requires local Git history only.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..", import.meta.url));
const corpus = JSON.parse(
  readFileSync(
    new URL("../tests/fixtures/projection-bound-b4427da.json", import.meta.url),
    "utf8",
  ),
);
assert.equal(
  corpus.reference_commit,
  "b4427daa400fbe3ea723b7ec0eb569265c7539c3",
);
const source = execFileSync(
  "git",
  [
    "show",
    `${corpus.reference_commit}:src/flymsg/viz_static/projection-error-bound.js`,
  ],
  { cwd: root, encoding: "utf8" },
);
assert.equal(
  createHash("sha256").update(source).digest("hex"),
  corpus.reference_sha256,
);
const reference = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
let checked = 0;
for (const { eye, boxes } of corpus.cases)
  for (const { box, bound, unproved } of boxes) {
    const result = reference.projectionErrorBound(box, eye, corpus.precision);
    if (unproved)
      assert.deepEqual(result, { scale: Infinity, rounding: Infinity });
    else {
      assert(Object.is(result.scale, bound.scale));
      assert(Object.is(result.rounding, bound.rounding));
    }
    checked++;
  }
assert.equal(checked, 1120);
console.log(
  JSON.stringify({
    status: "pass",
    reference_commit: corpus.reference_commit,
    checked,
    qualification: "recorded numeric expectations only; not device admission",
  }),
);
