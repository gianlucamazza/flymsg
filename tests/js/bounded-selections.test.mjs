import assert from "node:assert/strict";
import { test } from "node:test";
import * as T from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { BoundedSelections } from "../../src/flymsg/viz_static/bounded-selections.js";
const camera = new T.PerspectiveCamera(55, 1.5, 0.1, 100);
const eyes = [
  {
    modelView: new T.Matrix4().toArray(),
    projection: camera.projectionMatrix.toArray(),
    width: 1200,
    height: 800,
  },
];
function fixture() {
  const requests = [],
    owned = [],
    released = [];
  const uploads = {
    gl: { UNSIGNED_INT: 5125 },
    enqueue: (arrays) => {
      const r = {
        arrays,
        state: "preparing",
        buffers: [
          { buffer: { id: owned.length }, bytes: arrays[0].byteLength },
        ],
      };
      owned.push(r);
      return r;
    },
    release: (r) => {
      if (!released.includes(r)) {
        released.push(r);
        r.state = "released";
      }
    },
  };
  const controller = new BoundedSelections(
    T,
    uploads,
    (pages) =>
      new Promise((resolve, reject) =>
        requests.push({ pages, resolve, reject }),
      ),
    { float: 23, subpixel: 4 },
  );
  const geometry = new T.BufferGeometry().setIndex([0, 1, 1, 2, 2, 3]);
  const page = {
    object: { geometry, visible: true },
    boundedSource: { anchors: new Uint8Array(4), origins: new Uint32Array(4) },
  };
  controller.add(page, {
    page: 7,
    boxes: { 0: { min: [-0.1, -0.1, -3], max: [0.1, 0.1, -2] } },
    cpu_index_bytes: 40,
    levels: [
      { id: 0, ranges: [{ owner: 0, first: 0, count: 6 }], errors: { 0: 0 } },
      {
        id: 1,
        ranges: [{ owner: 0, first: 0, count: 4 }],
        errors: { 0: 0.0001 },
      },
    ],
  });
  return { controller, page, requests, owned, released, uploads };
}
const resolve = async (f, indices = new Uint32Array([0, 1, 1, 3])) => {
  f.requests.at(-1).resolve({ pages: [{ page: 7, indices }] });
  await Promise.resolve();
};
test("publish complete indices only; reject stale pose proofs immediately and restore the full index", async () => {
  const f = fixture();
  f.controller.update(eyes);
  await resolve(f);
  f.controller.apply(eyes);
  assert.equal(f.page.object.geometry.index.count, 6);
  f.owned[0].state = "ready";
  f.controller.update(eyes);
  f.controller.apply(eyes);
  assert.equal(f.page.object.geometry.index.count, 4);
  assert(f.controller.initialized);
  assert(f.controller.report().maximum_error_px <= 0.5);
  f.controller.restore();
  assert.equal(f.page.object.geometry.index.count, 6);
  const changed = [
    {
      ...eyes[0],
      modelView: new T.Matrix4().makeTranslation(0, 0, 4).toArray(),
    },
  ];
  f.controller.apply(changed);
  assert.equal(f.page.object.geometry.index.count, 6);
  assert.equal(f.controller.report().fallback_frames, 1);
});
test("camera changes coalesce obsolete composition; a context generation discards late replies", async () => {
  const f = fixture();
  f.controller.update(eyes);
  f.controller.update([
    {
      ...eyes[0],
      modelView: new T.Matrix4().makeTranslation(0, 0, 4).toArray(),
    },
  ]);
  await resolve(f);
  assert.equal(f.owned.length, 0);
  assert.equal(f.controller.discarded, 1);
  f.controller.update(eyes);
  f.controller.reset();
  await resolve(f);
  assert.equal(f.owned.length, 0);
  assert.equal(f.controller.current, null);
});
test("wrong index counts are refused and allocation failures remain an explicit full-source fallback", async () => {
  const f = fixture();
  f.controller.update(eyes);
  await resolve(f, new Uint32Array([0, 1]));
  assert.match(f.controller.error, /count/);
  f.controller.apply(eyes);
  assert.equal(f.page.object.geometry.index.count, 6);
  const g = fixture();
  g.controller.update(eyes);
  await resolve(g);
  g.uploads.error = "allocation failed";
  g.controller.update(eyes);
  g.controller.apply(eyes);
  assert.equal(g.page.object.geometry.index.count, 6);
  assert.equal(g.controller.report().state, "fallback-full");
  assert(g.released.length);
});

test("a stricter physical eye or missing pose forces original indices on the same draw", async () => {
  const f = fixture();
  f.controller.update(eyes);
  await resolve(f);
  f.owned[0].state = "ready";
  f.controller.update(eyes);
  f.controller.apply(eyes);
  assert.equal(f.page.object.geometry.index.count, 4);
  f.controller.apply([...eyes, { ...eyes[0], width: 120000, height: 80000 }]);
  assert.equal(f.page.object.geometry.index.count, 6);
  f.controller.apply([]);
  assert.equal(f.page.object.geometry.index.count, 6);
  f.controller.restore();
});
