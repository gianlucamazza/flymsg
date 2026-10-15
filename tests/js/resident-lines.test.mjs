import assert from "node:assert/strict";
import { test } from "node:test";
import { ResidentLineIndex } from "../../src/flymsg/viz_static/resident-lines.js";
import {
  linePages,
  visibleLinePages,
} from "../../src/flymsg/viz_static/geometry-pages.js";

function neuron(k, count = 12) {
  const vertices = Float32Array.from({ length: count * 6 }, (_, i) => i);
  const edges = Uint32Array.from({ length: count * 2 }, (_, i) => i);
  return {
    k,
    skelBase: k * 100,
    skelLod: { levels: [edges], pages: [linePages(vertices, edges, 1)] },
  };
}
function maskVisibility(masks) {
  return (pages, _eyes, out) => {
    out.set(masks.get(pages));
    return {
      visible: out,
      edges: pages.sizes.reduce((n, s, i) => n + s * out[i], 0),
    };
  };
}

test("resident source order and shared arena stay unchanged across camera selection", () => {
  const ns = [neuron(0), neuron(1)],
    planner = new ResidentLineIndex(3);
  const arena = new Uint32Array(100);
  assert.equal(planner.sync(ns, arena), true);
  const expected = Uint32Array.from(
    ns.flatMap((n) => [...n.skelLod.levels[0]].map((i) => i + n.skelBase)),
  );
  assert.deepEqual(arena.subarray(0, planner.count), expected);
  const mask = new Map(
    ns.map((n) => [n.skelLod.pages[0], new Uint8Array(12).fill(1)]),
  );
  const full = planner.plan(null, () => true, maskVisibility(mask));
  assert.deepEqual(full.ranges, [{ start: 0, count: 48 }]);
  for (const m of mask.values()) m.set([1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0]);
  const partial = planner.plan(null, () => true, maskVisibility(mask));
  assert.equal(partial.fallback, null);
  assert.equal(partial.ranges.length, 3);
  assert.equal(partial.visibleIndices, 24);
  assert(partial.submittedIndices >= partial.visibleIndices);
  assert.deepEqual(arena.subarray(0, planner.count), expected);
  assert.equal(planner.sync(ns, arena), false);
  assert.equal(planner.builds, 1);
  assert.equal(planner.index, arena);
});

test("hidden neurons are hard barriers even when the draw limit would be exceeded", () => {
  const ns = [neuron(0), neuron(1), neuron(2)];
  const p = new ResidentLineIndex(1);
  p.sync(ns);
  const result = p.plan(null, (n) => n.k !== 1, visibleLinePages);
  assert.equal(result.fallback, "hidden-neuron draw limit");
  assert.deepEqual(result.ranges, []);
  assert.equal(result.visibleIndices, 48);
  p.maxDraws = 2;
  assert.deepEqual(p.plan(null, (n) => n.k !== 1, visibleLinePages).ranges, [
    { start: 0, count: 24 },
    { start: 48, count: 24 },
  ]);
});

test("randomized coalescing preserves every eligible edge, order and hidden identity", () => {
  const ns = Array.from({ length: 7 }, (_, i) => neuron(i));
  const p = new ResidentLineIndex(4);
  p.sync(ns);
  let seed = 72;
  const rand = () => (seed = (1664525 * seed + 1013904223) >>> 0) / 2 ** 32;
  for (let trial = 0; trial < 100; trial++) {
    const wanted = ns.map(() => rand() > 0.3);
    const masks = new Map(
      ns.map((n) => [
        n.skelLod.pages[0],
        Uint8Array.from({ length: 12 }, () => +(rand() > 0.5)),
      ]),
    );
    const plan = p.plan(null, (n) => wanted[n.k], maskVisibility(masks));
    if (plan.fallback) continue;
    assert(plan.ranges.length <= 4);
    const drawn = new Set();
    let end = 0;
    for (const r of plan.ranges) {
      assert(r.start >= end);
      assert.equal(r.start % 2, 0);
      assert.equal(r.count % 2, 0);
      for (let i = r.start; i < r.start + r.count; i += 2) drawn.add(i / 2);
      end = r.start + r.count;
    }
    ns.forEach((n, k) => {
      const pages = n.skelLod.pages[0];
      for (let edge = 0; edge < 12; edge++) {
        if (!wanted[k]) assert(!drawn.has(12 * k + edge));
        else if (masks.get(pages)[pages.edgePage[edge]])
          assert(drawn.has(12 * k + edge));
      }
    });
  }
});

test("shared arena restoration, appended data, zero edges and empty selection", () => {
  const p = new ResidentLineIndex(),
    ns = [neuron(0, 0)];
  p.sync(ns);
  assert.deepEqual(p.plan(null, () => true, visibleLinePages).ranges, []);
  ns.push(neuron(1));
  assert(p.sync(ns));
  const expected = p.index.slice();
  p.index.fill(0);
  p.writeIndex(p.index);
  assert.deepEqual(p.index, expected);
  assert.throws(() => p.writeIndex(new Uint32Array(1)), /capacity/);
  assert.deepEqual(p.plan(null, () => false, visibleLinePages).ranges, []);
  assert.throws(() => new ResidentLineIndex(0), /limit/);
});

test("reused visibility masks clear stale bits instead of retaining old pages", () => {
  const n = neuron(0),
    pages = n.skelLod.pages[0],
    mask = new Uint8Array(12);
  assert.equal(visibleLinePages(pages, null, mask).edges, 12);
  assert.equal(visibleLinePages(pages, [], mask).edges, 0);
  assert(mask.every((x) => x === 0));
  assert.throws(() => visibleLinePages(pages, null, new Uint8Array(1)), /size/);
});

test("native ranges retain exactly eligible source edges, byte offsets and hidden ownership", () => {
  const ns = [neuron(0), neuron(1), neuron(2)], p = new ResidentLineIndex();
  p.sync(ns);
  const masks = new Map(ns.map(n => [n.skelLod.pages[0],
    Uint8Array.from({length: 12}, (_, i) => +(i % 2 === 0))]));
  const result = p.plan(null, n => n.k !== 1, maskVisibility(masks), true);
  assert.equal(result.native, true);
  assert.equal(result.submittedIndices, result.visibleIndices);
  const actual = [];
  for (let i = 0; i < result.rangeCount; i++) {
    assert.equal(p.drawStarts[i] % 8, 0);
    const start = p.drawStarts[i] / 4;
    actual.push(...p.index.subarray(start, start + p.drawCounts[i]));
  }
  const expected = ns.filter(n => n.k !== 1).flatMap(n =>
    [...n.skelLod.levels[0]].filter((_, i) => masks.get(n.skelLod.pages[0])[Math.floor(i/2)])
      .map(v => v + n.skelBase));
  assert.deepEqual(actual, expected);
  assert.equal(p.plan(null, n => n.k !== 1, maskVisibility(masks), true).changed, false);
  p.maxRanges = 1;
  assert.equal(p.plan(null, () => true, maskVisibility(masks), true).fallback, "resident range capacity");
  const oldArena = p.index;
  p.releaseArena();
  assert(!p.arrays().includes(oldArena));
});
