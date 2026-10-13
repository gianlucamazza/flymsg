import assert from "node:assert/strict";
import { test } from "node:test";

import { DIMORPHISM_COLORS, FRU_DSX_COLORS, dimorphismClass, fruDsxClass } from "../../src/flymsg/viz_static/colors.js";

test("dimorphism classes fold the 'potentially' calls into their class", () => {
  assert.equal(dimorphismClass("male-specific"), "male-specific");
  assert.equal(dimorphismClass("potentially male-specific"), "male-specific");
  assert.equal(dimorphismClass("sexually dimorphic"), "dimorphic");
  assert.equal(dimorphismClass("potentially dimorphic"), "dimorphic");
  assert.equal(dimorphismClass(""), "not annotated");
  for (const v of ["male-specific", "dimorphic", ""]) assert.ok(DIMORPHISM_COLORS[dimorphismClass(v)]);
});

test("fru/dsx classes follow the expression annotation", () => {
  assert.equal(fruDsxClass("fru_high"), "fru");
  assert.equal(fruDsxClass("fru_low"), "fru");
  assert.equal(fruDsxClass("dsx_high"), "dsx");
  assert.equal(fruDsxClass("coexpress_low"), "fru + dsx");
  assert.equal(fruDsxClass(""), "not annotated");
  for (const v of ["fru_high", "dsx_low", "coexpress_high", ""]) assert.ok(FRU_DSX_COLORS[fruDsxClass(v)]);
});

test("a selection overrides the colour mode and keeps other neurons as context", async () => {
  const { FOCUS_COLORS, colourOf } = await import("../../src/flymsg/viz_static/colors.js");
  const view = { colorBy: "group", focus: new Map([[0, "selected"], [2, "upstream"]]) };
  assert.equal(colourOf({ k: 0, group: "g" }, view, ["g"]), FOCUS_COLORS.selected);
  assert.equal(colourOf({ k: 2, group: "g" }, view, ["g"]), FOCUS_COLORS.upstream);
  assert.equal(colourOf({ k: 1, group: "g" }, view, ["g"]), FOCUS_COLORS.context);
  assert.notEqual(colourOf({ k: 1, group: "g" }, { ...view, focus: null }, ["g"]), FOCUS_COLORS.context);
});

test("a group is described by its instances, largest first", async () => {
  const { groupMembers } = await import("../../src/flymsg/viz_static/colors.js");
  const neurons = [
    ...Array(3).fill({ group: "stimulus", instance: "LC4_R" }),
    ...Array(2).fill({ group: "stimulus", instance: "LC4_L" }),
    { group: "kept", instance: "DNp01_R" },
    { group: "stimulus", type: "X" },
  ];
  assert.equal(groupMembers(neurons, "stimulus"), "LC4_R ×3, LC4_L ×2, X ×1");
  assert.equal(groupMembers(neurons, "stimulus", 1), "LC4_R ×3, +2 more");
  assert.equal(groupMembers(neurons, "kept"), "DNp01_R ×1");
});

test("the legend follows the colouring: selection, then comparison, then the mode", async () => {
  const { legendEntries, colourOf, COMPARE_COLORS, FOCUS_COLORS, PALETTE } = await import(
    "../../src/flymsg/viz_static/colors.js"
  );
  const neurons = [{ k: 0, group: "stimulus", instance: "LC4_R", nt: "acetylcholine" }];
  const groups = ["stimulus"];
  const byGroup = legendEntries({ colorBy: "group" }, groups, neurons);
  assert.deepEqual(byGroup, [["stimulus (1): LC4_R ×1", PALETTE[0]]]);
  assert.equal(colourOf(neurons[0], { colorBy: "group" }, groups), byGroup[0][1]);
  const compare = { colorBy: "group", compare: ["more"] };
  const entries = legendEntries(compare, groups, neurons);
  assert.deepEqual(entries.map(([, c]) => c), Object.values(COMPARE_COLORS));
  assert.ok(entries.some(([, c]) => c === colourOf(neurons[0], compare, groups)));
  const focus = { ...compare, focus: new Map([[0, "selected"]]) };
  assert.deepEqual(legendEntries(focus, groups, neurons), Object.entries(FOCUS_COLORS));
});

test("soma region colours follow the regions of somata.json", async () => {
  const { REGION_COLORS } = await import("../../src/flymsg/viz_static/colors.js");
  const { readFileSync } = await import("node:fs");
  const meta = JSON.parse(readFileSync(new URL("../../docs/live/cns/somata.json", import.meta.url)));
  assert.deepEqual(Object.keys(REGION_COLORS), meta.regions);
});
