// ?chrome=0 is a gallery frame. The caller does not build the lil-gui panel.
// The performance readout (#stats, #perf) is hidden. The colour legend stays,
// because the caption depends on it. Any other value, including a missing
// flag, leaves the page unchanged.

const READOUT = ["stats", "perf"];

export function showChrome(search) {
  return new URLSearchParams(search).get("chrome") !== "0";
}

export function applyChrome(nodes, search) {
  if (showChrome(search)) return;
  for (const key of READOUT) {
    const node = nodes[key];
    if (node) node.hidden = true;
  }
}

// A phone or tablet: a coarse pointer gets touch hints and a wider tap slop, and a
// narrow screen starts with the lil-gui panel closed so the scene is not covered.
export const NARROW = "(max-width: 600px)";
export const COARSE = "(pointer: coarse)";

const SLOP_PX = { touch: 12, pen: 6 };

// A pointer that moved more than this between down and up was a drag, not a tap.
export function isTap(pointerType, dx, dy) {
  return Math.hypot(dx, dy) <= (SLOP_PX[pointerType] ?? 4);
}

export function hint(coarse) {
  return coarse
    ? "tap a neuron for details · drag to rotate · pinch to zoom"
    : "click a neuron for details · drag to rotate · scroll to zoom";
}

// What ends a selection: Esc on a keyboard, the panel's clear button on a touch screen.
export function clearHint(coarse) {
  return coarse ? "clear ends the selection" : "Esc clears the selection";
}

// A replay starts playing unless ?paused is set or the reader asked for reduced motion.
export function autoplay(search, reducedMotion) {
  return !new URLSearchParams(search).has("paused") && !reducedMotion;
}
