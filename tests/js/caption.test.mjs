import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { sceneCaption } from "../../src/flymsg/viz_static/caption.js";

const live = (name) =>
  JSON.parse(readFileSync(new URL(`../../docs/live/${name}/manifest.json`, import.meta.url)));

test("a replay names its input, window, silenced types and seed", () => {
  assert.equal(
    sceneCaption(live("looming")),
    "input: LC4_R at 100 Hz for 300 of 600 ms · seed 0 · model replay",
  );
  assert.match(sceneCaption(live("looming-dnp01-silenced")), / · silenced: DNp01 · /);
  assert.match(sceneCaption(live("looming-bilateral")), /^input: LC4 at /);
});

test("an anatomy scene lists its types; no manifest gives no line", () => {
  assert.equal(sceneCaption(live("anatomy")), "anatomy: pIP10, dPR1, dMS9 (no simulation)");
  assert.equal(sceneCaption(null), "");
  assert.equal(sceneCaption({}), "");
});

test("an eye replay names its edge and locked configuration", () => {
  const manifest = {
    config: {
      eye: {
        edge: ["on", "front_to_back"],
        t4t5_version: 4,
        configuration: 2,
        lmc_rate_hz: 50,
        medulla_rate_hz: 200,
        lamina_medulla_gain: 4,
      },
    },
  };
  assert.equal(
    sceneCaption(manifest),
    "input: ON edge front to back through the eye · t4t5 v4 configuration 2 " +
      "(LMC 50 Hz, medulla 200 Hz, lamina gain 4) · model replay",
  );
});
