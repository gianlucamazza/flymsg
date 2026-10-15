import assert from "node:assert/strict";
import { test } from "node:test";

import {
  BUTTON,
  DEADZONE,
  ORBIT_RAD_PER_S,
  axis,
  motion,
  padHint,
  pressedSince,
  tvMode,
} from "../../src/flymsg/viz_static/gamepad.js";

function pad(axes = [0, 0, 0, 0], down = {}, values = {}) {
  const buttons = Array.from({ length: 17 }, (_, i) => ({
    pressed: Boolean(down[i]),
    value: values[i] ?? (down[i] ? 1 : 0),
  }));
  return { axes, buttons, mapping: "standard" };
}

test("a resting stick does nothing, a full one is rescaled to one", () => {
  assert.equal(axis(DEADZONE * 0.9), 0);
  assert.equal(axis(-DEADZONE), 0);
  assert.equal(axis(1), 1);
  assert.equal(axis(-1), -1);
  assert.ok(axis(0.5) > 0 && axis(0.5) < 0.5);
  assert.equal(axis(undefined), 0);
});

test("the left stick orbits at its rate, the right stick and triggers zoom", () => {
  const still = motion(pad(), 0.016);
  assert.deepEqual(still, { theta: -0, phi: -0, zoom: 1 });
  const turn = motion(pad([1, 0, 0, 0]), 0.5);
  assert.equal(turn.theta, -ORBIT_RAD_PER_S * 0.5);
  assert.equal(turn.zoom, 1);
  assert.ok(motion(pad([0, 0, 0, 1]), 0.1).zoom > 1); // stick down: away
  assert.ok(motion(pad([0, 0, 0, 0], { [BUTTON.RT]: true }), 0.1).zoom < 1); // closer
  assert.ok(motion(pad([0, 0, 0, 0], { [BUTTON.LT]: true }), 0.1).zoom > 1);
  assert.deepEqual(motion(null, 0.1), { theta: 0, phi: 0, zoom: 1 });
});

test("a button counts once, on its press", () => {
  const first = pressedSince(pad([], { [BUTTON.A]: true }), null);
  assert.ok(first.fresh.has(BUTTON.A));
  const held = pressedSince(pad([], { [BUTTON.A]: true }), first.now);
  assert.equal(held.fresh.size, 0);
  const released = pressedSince(pad(), held.now);
  const again = pressedSince(pad([], { [BUTTON.A]: true }), released.now);
  assert.ok(again.fresh.has(BUTTON.A));
});

test("a console's browser gets the TV layout unless the page says otherwise", () => {
  const xbox =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Xbox; Xbox Series S) AppleWebKit/537.36 Edg/120";
  assert.equal(tvMode("", xbox), true);
  assert.equal(tvMode("?tv=0", xbox), false);
  assert.equal(tvMode("?tv=1", "Mozilla/5.0 (X11; Linux x86_64)"), true);
  assert.equal(tvMode("", "Mozilla/5.0 (X11; Linux x86_64)"), false);
  assert.match(padHint(), /X clear selection/);
  assert.doesNotMatch(padHint(), /\bB\b/);
});
