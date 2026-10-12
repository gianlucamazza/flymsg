import assert from "node:assert/strict";
import { test } from "node:test";

import {
  findNeuron,
  focusRoles,
  panelLines,
  selectParam,
} from "../../src/flymsg/viz_static/partners.js";

const neurons = [
  { k: 0, bodyId: 100, type: "pIP10", instance: "pIP10_R", nt: "acetylcholine", superclass: "descending_neuron", dimorphism: "male-specific", fruDsx: "fru_high", rate: 50 },
  { k: 1, bodyId: 101, type: "untyped", instance: "", nt: "unknown", superclass: "", dimorphism: "", fruDsx: "", rate: null },
  { k: 2, bodyId: 102, type: "dPR1", instance: "", nt: "acetylcholine", superclass: "vnc_intrinsic", dimorphism: "", fruDsx: "coexpress_low", rate: 0 },
];

test("a bodyId, an instance or a type selects the first matching neuron", () => {
  assert.equal(findNeuron(neurons, "101").k, 1);
  assert.equal(findNeuron(neurons, "pip10_r").k, 0);
  assert.equal(findNeuron(neurons, "DPR1").k, 2);
  assert.equal(findNeuron(neurons, " 999 "), null);
  assert.equal(findNeuron(neurons, ""), null);
});

test("partners in the scene get their role; one both ways is marked so", () => {
  const entry = {
    upstream: { in_scene: [[1, 5], [2, 3]] },
    downstream: { in_scene: [[2, 7]] },
  };
  const roles = focusRoles(0, entry);
  assert.deepEqual([...roles].sort(), [
    [0, "selected"],
    [1, "upstream"],
    [2, "up and downstream"],
  ]);
  assert.deepEqual([...focusRoles(1, undefined)], [[1, "selected"]]);
});

test("the panel labels missing annotations and keeps anatomy apart from simulation", () => {
  const entry = {
    upstream: { types: [["A", 9, 2]], total_types: 3, total_synapses: 12, in_scene: [[0, 9]] },
    downstream: { types: [], total_types: 0, total_synapses: 0, in_scene: [] },
  };
  const lines = panelLines(neurons[1], entry, "chemical synapse counts");
  assert.ok(lines.includes("type unknown · transmitter unknown · superclass unknown"));
  assert.ok(lines.includes("dimorphism not annotated · fru/dsx not annotated"));
  assert.ok(lines.includes("simulation: no replay in this scene"));
  assert.ok(lines.includes("inputs: 12 synapses from 3 cell types (top 1 shown, 2 more)"));
  assert.ok(lines.includes("  A — 9 synapses, 2 neurons"));
  assert.ok(lines.includes("outputs: none in the dataset"));
  assert.equal(lines.at(-1), "same numbers: flymsg info 101");
  const replay = panelLines(neurons[0], undefined, undefined);
  assert.ok(replay.includes("simulation: 50 Hz during the stimulus (model, not a recording)"));
  assert.ok(replay.includes("inputs: unknown (no partner table)"));
});

test("?select= is read from the URL", () => {
  assert.equal(selectParam("?t=120&select=12345"), "12345");
  assert.equal(selectParam("?select="), null);
  assert.equal(selectParam(""), null);
});
