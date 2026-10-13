import assert from "node:assert/strict";
import { test } from "node:test";

import {
  applyChrome,
  autoplay,
  clearHint,
  hint,
  isTap,
  showChrome,
} from "../../src/flymsg/viz_static/chrome.js";

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

test("a finger may move further than a mouse and still tap", () => {
  assert.equal(isTap("mouse", 3, 0), true);
  assert.equal(isTap("mouse", 5, 0), false);
  assert.equal(isTap("touch", 8, 8), true);
  assert.equal(isTap("touch", 10, 10), false);
  assert.equal(isTap("pen", 6, 0), true);
  assert.equal(isTap(undefined, 4, 0), true);
});

test("touch hints name taps and pinches", () => {
  assert.match(hint(true), /^tap .* pinch to zoom$/);
  assert.match(hint(false), /^click .* scroll to zoom$/);
});

test("a touch screen ends a selection with the clear button, not Esc", () => {
  assert.match(clearHint(true), /^clear /);
  assert.match(clearHint(false), /^Esc /);
});

test("a replay autoplays unless paused or the reader asked for reduced motion", () => {
  assert.equal(autoplay("", false), true);
  assert.equal(autoplay("?t=120", false), true);
  assert.equal(autoplay("?paused", false), false);
  assert.equal(autoplay("", true), false);
});
