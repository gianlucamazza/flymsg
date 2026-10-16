import assert from "node:assert/strict";
import { test } from "node:test";
import { contextReadiness } from "../../src/flymsg/viz_static/context-readiness.js";

const state = (changes = {}) => ({ catalogs: { brain: "loading", vnc: "loading" }, catalogErrors: {}, shells: [], allNeuropils: false,
  somata: { visible: false, state: "hidden", requested: false, points: null }, ...changes });

test("all requested neuropils wait for their catalogs before any mesh exists", () => {
  assert.equal(contextReadiness(state({ allNeuropils: true })).ready, false);
  assert.equal(contextReadiness(state()).ready, true);
});

test("default soma discovery must finish before GPU/VR admission", () => {
  assert.equal(contextReadiness(state({ somata: { visible: true, state: "loading" } })).ready, false);
  assert.equal(contextReadiness(state({ somata: { visible: true, state: "ready" } })).ready, true);
});

test("optional absent export and explicit missing soma request are distinct", () => {
  assert.equal(contextReadiness(state({ somata: { visible: true, state: "absent", requested: false } })).ready, true);
  const missing = contextReadiness(state({ somata: { visible: true, state: "absent", requested: true } }));
  assert.equal(missing.ready, false);
  assert.match(missing.error, /unavailable/);
});

test("unused failed catalogs do not block explicitly selected valid anatomy", () => {
  const s = state({ catalogs: { brain: "ready", vnc: "error" }, catalogErrors: { vnc: "VNC unavailable" }, shells: [{ region: "brain", visible: true, state: "ready" }] });
  assert.equal(contextReadiness(s).ready, true);
  assert.equal(contextReadiness({ ...s, allNeuropils: true }).error, "VNC unavailable");
});

test("selected meshes wait for full preparation and surface source errors", () => {
  const s = state({ catalogs: { brain: "ready" }, shells: [{ region: "brain", visible: true, state: "loading" }] });
  assert.equal(contextReadiness(s).ready, false);
  s.shells[0] = { ...s.shells[0], state: "error", error: "ROI source missing" };
  assert.equal(contextReadiness(s).error, "ROI source missing");
});

test("explicitly hidden contextual layers do not prevent a complete selection", () => {
  const s = state({ somata: { visible: true, state: "error", error: "Unavailable", points: { visible: false } } });
  assert.equal(contextReadiness(s).ready, true);
});
