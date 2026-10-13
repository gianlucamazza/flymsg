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
