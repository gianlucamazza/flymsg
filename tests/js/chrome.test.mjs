import assert from "node:assert/strict";
import { test } from "node:test";

import { applyChrome, showChrome } from "../../src/flymsg/viz_static/chrome.js";

function nodes() {
  return {
    stats: { hidden: false },
    perf: { hidden: false },
    legend: { hidden: false },
    clock: { hidden: false },
    info: { hidden: false },
  };
}

test("chrome=0 hides the readout, leaves the legend, and builds no panel", () => {
  const ui = nodes();
  const search = "?chrome=0&t=120&paused";
  assert.equal(showChrome(search), false);
  applyChrome(ui, search);
  assert.equal(ui.stats.hidden, true);
  assert.equal(ui.perf.hidden, true);
  assert.equal(ui.legend.hidden, false);
  assert.equal(ui.clock.hidden, false);
  assert.equal(ui.info.hidden, false);
});

test("a page without chrome=0 keeps the readout and builds the panel", () => {
  for (const search of ["", "?t=120&paused", "?chrome=1", "?chrome="]) {
    const ui = nodes();
    assert.equal(showChrome(search), true, search);
    applyChrome(ui, search);
    assert.equal(ui.stats.hidden, false, search);
    assert.equal(ui.perf.hidden, false, search);
    assert.equal(ui.legend.hidden, false, search);
  }
});
