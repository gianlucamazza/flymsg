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
