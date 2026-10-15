import assert from "node:assert/strict";
import { test } from "node:test";
import * as T from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { PagedScene } from "../../src/flymsg/viz_static/paged-scene.js";

test("admission errors can arrive after an incomplete source set without changing its arrays", () => {
  const renderer = { getContext: () => ({}) };
  const scene = new PagedScene(T, renderer, new T.Group());
  scene.sync([], false);
  assert.equal(scene.state, "preparing");
  scene.sync([], false, "Visible context source is missing");
  assert.equal(scene.state, "unsupported");
  const generation = scene.generation;
  scene.sync([], false, "Visible context source is missing");
  assert.equal(scene.generation, generation);
  scene.sync([], false);
  assert.equal(scene.state, "preparing");
  scene.dispose();
});

test("failed first draw cannot advertise GPU readiness and restores source visibility/debug hooks", () => {
  const originalHook = () => {};
  const renderer = { getContext: () => ({}), debug: { onShaderError: originalHook } };
  const scene = new PagedScene(T, renderer, new T.Group());
  scene.state = "warming"; scene.complete = true;
  const original = new T.Mesh();
  assert.throws(() => scene.render([original], () => { throw new Error("Injected draw failure"); }), /Injected/);
  assert.equal(scene.state, "unsupported");
  assert.equal(scene.group.visible, false);
  assert.equal(original.visible, true);
  assert.equal(renderer.debug.onShaderError, originalHook);
  scene.dispose();
});
