import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { residentLineProbe } from "../../src/flymsg/viz_static/resident-probe.js";

test("legacy index probe rejects immutable GPU pages before touching renderer state", async () => {
  await assert.rejects(residentLineProbe({ paged: {} }, () => {}), /cannot measure/);
});

test("failed reference preparation restores diagnostic and renderer state", async () => {
  const original = {
    time: 7,
    playing: true,
    pageCulling: false,
    residentLines: true,
  };
  let state = { ...original },
    target = { name: "original" };
  const viewport = new THREE.Vector4(1, 2, 3, 4),
    scissor = new THREE.Vector4(5, 6, 7, 8);
  let scissorTest = true,
    restoredLines = false;
  const gl = { bufferData: () => {}, bufferSubData: () => {} };
  const renderer = {
    xr: { isPresenting: false },
    getContext: () => gl,
    getRenderTarget: () => target,
    setRenderTarget: (t) => {
      target = t;
    },
    getViewport: (v) => v.copy(viewport),
    setViewport: (v) => viewport.copy(v),
    getScissor: (v) => v.copy(scissor),
    setScissor: (v) => scissor.copy(v),
    getScissorTest: () => scissorTest,
    setScissorTest: (v) => {
      scissorTest = v;
    },
  };
  const view = {
    THREE,
    renderer,
    world: {},
    camera: {},
    data: {},
    skeletons: {},
    fidelity: () => ({ status: "ready", representation: "skeleton" }),
    diagnostic: (next) => {
      const old = state;
      state = { ...next };
      return old;
    },
    reference: async () => {
      throw Error("injected reference failure");
    },
    scheduleLines: (eyes) => {
      assert.equal(eyes, null);
      restoredLines = true;
    },
  };
  await assert.rejects(
    residentLineProbe(view, () => {}),
    /injected reference failure/,
  );
  assert.deepEqual(state, original);
  assert.equal(target.name, "original");
  assert.equal(restoredLines, true);
  assert.deepEqual(viewport.toArray(), [1, 2, 3, 4]);
  assert.deepEqual(scissor.toArray(), [5, 6, 7, 8]);
  assert(scissorTest);
});
