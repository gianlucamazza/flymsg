import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { browserProbe } from "../../src/flymsg/viz_static/browser-probe.js";

test("browser diagnostics restore renderer, observer and GL methods on reference failure", async () => {
  const previous = { time: 7, playing: true, pageCulling: true };
  let state = previous,
    target = { original: true },
    scissorTest = true;
  const viewport = new THREE.Vector4(1, 2, 3, 4),
    scissor = new THREE.Vector4(5, 6, 7, 8);
  const originalBufferData = () => {},
    originalSubData = () => {};
  const gl = {
    getExtension: () => null,
    getContextAttributes: () => ({}),
    getSupportedExtensions: () => [],
    bufferData: originalBufferData,
    bufferSubData: originalSubData,
  };
  const renderer = {
    xr: { isPresenting: false },
    getContext: () => gl,
    getSize: (v) => v.set(512, 512),
    getPixelRatio: () => 1,
    getRenderTarget: () => target,
    setRenderTarget: (t) => (target = t),
    getViewport: (v) => v.copy(viewport),
    setViewport: (v) => viewport.copy(v),
    getScissor: (v) => v.copy(scissor),
    setScissor: (v) => scissor.copy(v),
    getScissorTest: () => scissorTest,
    setScissorTest: (v) => (scissorTest = v),
  };
  const oldDocument = globalThis.document,
    oldDpr = globalThis.devicePixelRatio;
  globalThis.document = { visibilityState: "visible" };
  globalThis.devicePixelRatio = 2;
  try {
    await assert.rejects(
      browserProbe({
        THREE,
        renderer,
        camera: new THREE.PerspectiveCamera(),
        fidelity: () => ({ status: "ready" }),
        diagnostic: (next) => {
          const old = state;
          state = next;
          return old;
        },
        reference: async () => {
          throw Error("injected failure");
        },
      }),
      /injected failure/,
    );
    assert.deepEqual(state, previous);
    assert(target.original);
    assert(scissorTest);
    assert.equal(gl.bufferData, originalBufferData);
    assert.equal(gl.bufferSubData, originalSubData);
    assert.deepEqual(viewport.toArray(), [1, 2, 3, 4]);
    assert.deepEqual(scissor.toArray(), [5, 6, 7, 8]);
  } finally {
    globalThis.document = oldDocument;
    globalThis.devicePixelRatio = oldDpr;
  }
});
