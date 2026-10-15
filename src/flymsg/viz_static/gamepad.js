// A game controller drives the view on a TV (an Xbox's Edge, or any browser with the
// Gamepad API and the "standard" mapping). Pure functions: main.js polls the pad each
// frame, turns its state into one step of camera motion and the buttons pressed since
// the last frame, and applies them.

// Standard-mapping button indices (https://w3c.github.io/gamepad/#remapping).
export const BUTTON = {
  A: 0,
  X: 2, // not B: on an Xbox, Edge keeps B for going back a page
  Y: 3,
  LB: 4,
  RB: 5,
  LT: 6,
  RT: 7,
  VIEW: 8,
};
export const DEADZONE = 0.15; // a resting stick reads up to about this much
export const ORBIT_RAD_PER_S = 2.0; // full deflection turns the view this fast
export const ZOOM_PER_S = 1.5; // full deflection scales the distance by e^this per second

// A stick axis with its dead zone removed and the rest rescaled to [-1, 1].
export function axis(value, deadzone = DEADZONE) {
  const v = Number(value) || 0;
  if (Math.abs(v) <= deadzone) return 0;
  return (Math.sign(v) * (Math.abs(v) - deadzone)) / (1 - deadzone);
}

// The motion of one frame of `dt` seconds:
// - the left stick orbits: `theta` is the azimuth and `phi` the polar angle, in radians;
// - the right stick's vertical and the triggers zoom: `zoom` multiplies the camera's
//   distance to its target (> 1 moves away).
export function motion(pad, dt) {
  if (!pad) return { theta: 0, phi: 0, zoom: 1 };
  const ax = pad.axes ?? [];
  const pressed = (i) => Number(pad.buttons?.[i]?.value ?? 0);
  const theta = -axis(ax[0]) * ORBIT_RAD_PER_S * dt;
  const phi = -axis(ax[1]) * ORBIT_RAD_PER_S * dt;
  const push = axis(ax[3]) + pressed(BUTTON.LT) - pressed(BUTTON.RT);
  return { theta, phi, zoom: Math.exp(push * ZOOM_PER_S * dt) };
}

// The buttons that went down since `before` (an array of booleans, or null at start).
export function pressedSince(pad, before) {
  const now = (pad?.buttons ?? []).map((b) => Boolean(b?.pressed));
  const fresh = new Set();
  now.forEach((down, i) => {
    if (down && !before?.[i]) fresh.add(i);
  });
  return { now, fresh };
}

// A console's browser: a TV layout by default (?tv=0 or ?tv=1 overrides).
export function tvMode(search, userAgent) {
  const flag = new URLSearchParams(search).get("tv");
  if (flag !== null) return flag !== "0";
  return /\bXbox\b/i.test(userAgent ?? "");
}

export function padHint() {
  return "left stick rotate · right stick or triggers zoom · A play/pause · LB/RB step one bin · Y reset view · X clear selection · View panel";
}
