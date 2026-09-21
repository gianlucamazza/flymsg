import assert from "node:assert/strict";
import { test } from "node:test";

import { projectedPx, refine, select } from "../../src/flymsg/viz_static/lod.js";

const T = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]; // identity: model units = output units

// Two LODs over a 2x1x1 region of 10-unit chunks: one coarse fragment (20 units) above two
// fine ones. Sizes are bytes.
const manifest = () => ({
  chunkShape: [10, 10, 10],
  gridOrigin: [0, 0, 0],
  vertexOffsets: [[0, 0, 0], [0, 0, 0]],
  lods: [
    [{ pos: [0, 0, 0], size: 400 }, { pos: [1, 0, 0], size: 400 }],
    [{ pos: [0, 0, 0], size: 100 }],
  ],
});

const view = (x, px = 1000) => ({ eye: [x, 5, 5], pxPerUnit: px });

test("projected size grows as the eye approaches, infinite inside", () => {
  const box = { min: [0, 0, 0], max: [10, 10, 10] };
  assert.ok(projectedPx(box, view(-10)) > projectedPx(box, view(-100)));
  assert.equal(projectedPx(box, view(5)), Infinity);
});

test("far away keeps the coarse fragment, close up refines", () => {
  assert.deepEqual(refine(manifest(), view(-100000), 50, T), [{ lod: 1, i: 0 }]);
  assert.deepEqual(refine(manifest(), view(-1), 50, T), [{ lod: 0, i: 0 }, { lod: 0, i: 1 }]);
});

test("a parent and its children are never drawn together", () => {
  for (const x of [-1e6, -1e3, -100, -10, -1, 5]) {
    const lods = refine(manifest(), view(x), 50, T).map((f) => f.lod);
    assert.ok(!(lods.includes(0) && lods.includes(1)), `eye x=${x}`);
  }
});

test("a coarse fragment without children stays even when large on screen", () => {
  const m = manifest();
  m.lods[0] = [];
  assert.deepEqual(refine(m, view(-1), 50, T), [{ lod: 1, i: 0 }]);
});

test("budget: coarsen first, then fall back to skeleton, by priority", () => {
  const opts = { detailPx: 50, trisPerByte: 1, transform: T };
  const neurons = [
    { key: "low", priority: 1, manifest: manifest() },
    { key: "high", priority: 9, manifest: manifest() },
    { key: "pending", priority: 5, manifest: null },
  ];
  // close view: fine = 800 tris, coarse = 100 tris each
  const roomy = select(neurons, view(-1), { ...opts, budgetTris: 2000 });
  assert.equal(roomy.meshes.get("high").length, 2);
  assert.equal(roomy.meshes.get("low").length, 2);
  assert.deepEqual(roomy.skeletons, ["pending"]); // no manifest yet

  const tight = select(neurons, view(-1), { ...opts, budgetTris: 900 });
  assert.equal(tight.meshes.get("high").length, 2); // 800, full detail
  assert.deepEqual(tight.meshes.get("low"), [{ lod: 1, i: 0 }]); // 100, coarsened
  assert.equal(tight.tris, 900);

  const broke = select(neurons, view(-1), { ...opts, budgetTris: 150 });
  assert.deepEqual(broke.meshes.get("high"), [{ lod: 1, i: 0 }]);
  assert.deepEqual(broke.skeletons.sort(), ["low", "pending"]);
});
