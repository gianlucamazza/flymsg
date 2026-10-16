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
    encoding: "anchored-path-u32/v1",
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

const scaledEyes = (factor) =>
  eyes.map((eye) => ({
    ...eye,
    width: eye.width * factor,
    height: eye.height * factor,
  }));
test("retain a certified current selection between the preferred and fallback thresholds", async () => {
  const f = fixture();
  f.controller.update(eyes);
  await resolve(f);
  f.owned[0].state = "ready";
  f.controller.update(eyes);
  f.controller.update(scaledEyes(6));
  f.controller.apply(scaledEyes(6));
  assert.equal(f.page.object.geometry.index.count, 4);
  assert(f.controller.report().maximum_error_px > 0.4);
  assert(f.controller.report().maximum_error_px <= 0.5);
  assert.equal(f.requests.length, 1);
  assert.equal(f.released.length, 0);
  f.controller.restore();
  f.controller.update(scaledEyes(8));
  f.controller.apply(scaledEyes(8));
  assert.equal(f.page.object.geometry.index.count, 6);
});

test("an older preferred selection may finish while still certified for the actual pose", async () => {
  const f = fixture();
  f.controller.update(eyes);
  f.controller.update(scaledEyes(6));
  await resolve(f);
  assert.equal(f.owned.length, 1);
  f.controller.update(scaledEyes(6));
  assert.equal(f.released.length, 0);
  f.owned[0].state = "ready";
  f.controller.update(scaledEyes(6));
  f.controller.apply(scaledEyes(6));
  assert.equal(f.page.object.geometry.index.count, 4);
  assert(f.controller.report().maximum_error_px <= 0.5);
});

function twoPages() {
  const f = fixture();
  f.page.object.geometry.setIndex([0, 1, 1, 2, 2, 3, 3, 4]);
  f.page.fullIndex = f.page.object.geometry.index;
  f.page.bounded.levels[0].ranges[0].count = 8;
  f.page.bounded.levels.push({
    id: 2,
    ranges: [{ owner: 0, first: 0, count: 6 }],
    errors: { 0: 0.00001 },
  });
  const second = {
    object: {
      geometry: new T.BufferGeometry().setIndex([0, 1, 1, 2, 2, 3, 3, 4]),
      visible: true,
    },
  };
  const metadata = structuredClone(f.page.bounded);
  metadata.page = 8;
  metadata.levels[1].errors[0] = 0.00001;
  f.controller.add(second, metadata);
  const release = f.uploads.release;
  f.uploads.release = (record) => {
    assert(
      !f.released.includes(record),
      "a shared native record must be released exactly once",
    );
    release(record);
  };
  return { ...f, second };
}
async function resolvePages(f) {
  const request = f.requests.at(-1);
  request.resolve({
    pages: request.pages.map(({ page, selection }) => ({
      page,
      indices: new Uint32Array(
        selection[0] === 1 ? [0, 2, 2, 4] : [0, 1, 1, 2, 2, 4],
      ),
    })),
  });
  await Promise.resolve();
}
async function initializedPair() {
  const f = twoPages();
  f.controller.update(scaledEyes(8));
  await resolvePages(f);
  for (const r of f.owned) r.state = "ready";
  f.controller.update(scaledEyes(8));
  return f;
}
test("reuse unchanged native pages and publish a changed selection only when complete", async () => {
  const f = await initializedPair();
  const previous = f.controller.current,
    shared = previous.records.get(8);
  f.controller.update(eyes);
  await resolvePages(f);
  assert.equal(f.owned.length, 3);
  assert.equal(f.controller.pending.records.get(8), shared);
  f.controller.apply(eyes);
  assert.equal(f.page.object.geometry.index.count, 6);
  f.controller.restore();
  f.owned.at(-1).state = "ready";
  f.controller.update(eyes);
  f.controller.apply(eyes);
  assert.equal(f.page.object.geometry.index.count, 4);
  assert.equal(f.controller.current.records.get(8), shared);
  assert(!f.released.includes(shared));
  assert(f.released.includes(previous.records.get(7)));
  assert.equal(f.controller.report().composed_pages, 4);
  assert.equal(f.controller.report().reused_pages, 1);
  assert.equal(f.controller.report().installed_selections, 2);
  f.controller.restore();
  f.controller.reset();
  assert.equal(f.released.length, 3);
});
test("discard invalid pending proofs without releasing pages shared with the current selection", async () => {
  const f = await initializedPair();
  const previous = f.controller.current;
  f.controller.update(eyes);
  await resolvePages(f);
  const replacement = f.owned.at(-1);
  f.controller.update(scaledEyes(8));
  assert.equal(f.controller.current, previous);
  assert(f.released.includes(replacement));
  assert(!f.released.includes(previous.records.get(8)));
  f.controller.apply(scaledEyes(8));
  assert.equal(f.page.object.geometry.index.count, 6);
  f.controller.restore();
  f.controller.reset();
  assert.equal(f.released.length, 3);
});
test("context reset releases current and pending shared buffers once", async () => {
  const f = await initializedPair();
  f.controller.update(eyes);
  await resolvePages(f);
  assert.equal(f.owned.length, 3);
  f.controller.reset();
  assert.equal(f.released.length, 3);
  assert.equal(f.controller.current, null);
  assert.equal(f.controller.pending, null);
});

test("zero spatial error does not admit an unproved clipped pose on the same draw", async () => {
  const f = fixture();
  f.page.bounded.levels[1].errors[0] = 0;
  f.controller.update(eyes);
  await resolve(f);
  f.owned[0].state = "ready";
  f.controller.update(eyes);
  f.controller.apply(eyes);
  assert.equal(f.page.object.geometry.index.count, 4);
  f.controller.restore();
  f.controller.apply([
    {
      ...eyes[0],
      modelView: new T.Matrix4().makeTranslation(0, 0, 4).toArray(),
    },
  ]);
  assert.equal(f.page.object.geometry.index.count, 6);
  assert.equal(f.controller.report().maximum_error_px, 0);
});
