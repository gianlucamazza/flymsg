import assert from "node:assert/strict";
import { test } from "node:test";
import { RasterPainter } from "../../src/flymsg/viz_static/raster-painter.js";

function fixture() {
  let resets = 0;
  const calls = [];
  const ctx = new Proxy(
    {},
    {
      get:
        (_, name) =>
        (...args) =>
          calls.push([name, ...args]),
      set: () => true,
    },
  );
  const canvas = {
    style: {},
    getContext: () => ctx,
    set width(value) {
      resets++;
    },
    set height(value) {
      resets++;
    },
  };
  const state = {
    rows: [
      {
        counts: new Uint8Array([0, 2, 0]),
        total: 2,
        label: "neuron",
        colour: "#4cc9f0",
      },
    ],
    bins: 3,
    binMs: 10,
    stimMs: 10,
  };
  return {
    painter: new RasterPainter(canvas),
    state,
    calls,
    resets: () => resets,
  };
}

test("unchanged bins do no canvas work; bin transitions and scrub backwards redraw", () => {
  const { painter, state, calls, resets } = fixture();
  const frame = (time) => painter.draw(state, { width: 560, ratio: 2, time });
  assert.equal(frame(0), true);
  const work = calls.length;
  for (const t of [0.1, 0.9, 1, 9.99]) assert.equal(frame(t), false);
  assert.equal(calls.length, work);
  assert.equal(resets(), 2);
  assert.equal(frame(10), true);
  assert.equal(frame(0), true);
  assert.deepEqual(painter.report(), { draws: 3, skips: 4, cache_bytes: 0 });
});

test("selection/run changes, resize, DPR and reopened rasters invalidate the frame", () => {
  const { painter, state } = fixture();
  const opts = { width: 560, ratio: 2, time: 0 };
  assert.equal(painter.draw(state, opts), true);
  assert.equal(painter.draw({ ...state }, opts), true);
  assert.equal(painter.draw(state, opts), true);
  assert.equal(painter.draw(state, { ...opts, width: 272 }), true);
  assert.equal(painter.draw(state, { ...opts, width: 272, ratio: 1.25 }), true);
  painter.clear();
  assert.equal(painter.draw(state, { ...opts, width: 272, ratio: 1.25 }), true);
  assert.equal(painter.report().cache_bytes, 0);
});
