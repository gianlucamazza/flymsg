// Colour classes for the sex-related annotations of MaleCNS (see docs/result/dimorphism.md).
// "potentially ..." calls join their class: the field is the release's best current call.

export const DIMORPHISM_COLORS = {
  "male-specific": "#f72585",
  dimorphic: "#ffd166",
  "not annotated": "#5c6370",
};

export const FRU_DSX_COLORS = {
  fru: "#4cc9f0",
  dsx: "#ff7b00",
  "fru + dsx": "#b5e48c",
  "not annotated": "#5c6370",
};

export function dimorphismClass(value) {
  if (!value) return "not annotated";
  if (value.includes("male-specific")) return "male-specific";
  if (value.includes("dimorphic")) return "dimorphic";
  return "not annotated";
}

/** fru_high/fru_low -> fru, dsx_* -> dsx, coexpress_* -> fru + dsx. */
export function fruDsxClass(value) {
  if (!value) return "not annotated";
  if (value.startsWith("coexpress")) return "fru + dsx";
  if (value.startsWith("fru")) return "fru";
  if (value.startsWith("dsx")) return "dsx";
  return "not annotated";
}

export const PALETTE = [
  "#4cc9f0",
  "#f72585",
  "#b5e48c",
  "#ffd166",
  "#9b5de5",
  "#ff7b00",
  "#00f5d4",
  "#ef476f",
  "#8ecae6",
  "#e9c46a",
];

export const NT_COLORS = {
  acetylcholine: "#4cc9f0",
  gaba: "#f72585",
  glutamate: "#ffd166",
  histamine: "#9b5de5",
  dopamine: "#00f5d4",
  serotonin: "#ff7b00",
  octopamine: "#b5e48c",
  unclear: "#7b8494",
  unknown: "#7b8494",
};

// A selected neuron and its partners in the scene; every other neuron stays drawn as context.
export const FOCUS_COLORS = {
  selected: "#ffffff",
  upstream: "#ff9f1c",
  downstream: "#2ec4b6",
  "up and downstream": "#c77dff",
  context: "#2a2f38",
};

// Two runs compared: more or fewer spikes in B than in A, the same, or held by one export only.
export const COMPARE_COLORS = {
  more: "#ff4d6d",
  less: "#4cc9f0",
  same: "#5c6370",
  "not exported": "#2a2f38",
};

/** Stable small hash of a string, so a cell type always gets the same palette entry. */
export const hash = (s) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

/**
 * The colour of a neuron under the current view: by group, by transmitter, by cell type, or
 * by one of the two sex-related annotations. A selection (`view.focus`, row -> role) overrides
 * the mode until it is cleared.
 */
export function colourOf(n, view, groups) {
  if (view.focus) return FOCUS_COLORS[view.focus.get(n.k) ?? "context"];
  if (view.compare) return COMPARE_COLORS[view.compare[n.k]];
  switch (view.colorBy) {
    case "group":
      return PALETTE[groups.indexOf(n.group) % PALETTE.length];
    case "transmitter":
      return NT_COLORS[n.nt] ?? NT_COLORS.unknown;
    case "dimorphism":
      return DIMORPHISM_COLORS[dimorphismClass(n.dimorphism)];
    case "fru/dsx":
      return FRU_DSX_COLORS[fruDsxClass(n.fruDsx)];
    default:
      return PALETTE[hash(n.type) % PALETTE.length];
  }
}

/** Whether a neuron passes the current group toggles and type filter. */
export function isShown(n, view) {
  return (
    view.groupsOn[n.group] &&
    (!view.filter || n.type.toLowerCase().includes(view.filter))
  );
}

// Whole-CNS soma layer: region code -> name and colour, in the order of somata.json "regions"
// (scripts/build_somata.py).
export const REGION_COLORS = {
  "optic lobe": "#4f7fd0",
  "central brain": "#d09a4f",
  "ventral nerve cord": "#5fae66",
  descending: "#b866c4",
  ascending: "#c45f5f",
  other: "#8a8a8a",
};

// Labels for the difference view of two runs.
const COMPARE_LABELS = {
  more: "more spikes in B",
  less: "fewer spikes in B",
  same: "same",
  "not exported": "in one export only",
};

/** "LC4_R ×55, LC4_L ×53": a group's instances, largest first, at most `max`, then "+n more". */
export function groupMembers(neurons, group, max = 3) {
  const counts = new Map();
  for (const n of neurons)
    if (n.group === group) {
      const name = n.instance || n.type || String(n.bodyId);
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  const sorted = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const shown = sorted.slice(0, max).map(([name, c]) => `${name} ×${c}`);
  if (sorted.length > max) shown.push(`+${sorted.length - max} more`);
  return shown.join(", ");
}

/** [label, colour] pairs for what the neurons show now; the same precedence as colourOf. */
export function legendEntries(view, groups, neurons) {
  if (view.focus) return Object.entries(FOCUS_COLORS);
  if (view.compare)
    return Object.entries(COMPARE_COLORS).map(([k, c]) => [COMPARE_LABELS[k], c]);
  switch (view.colorBy) {
    case "group":
      return groups.map((g, i) => [
        `${g} (${neurons.filter((n) => n.group === g).length}): ${groupMembers(neurons, g)}`,
        PALETTE[i % PALETTE.length],
      ]);
    case "transmitter":
      return [...new Set(neurons.map((n) => n.nt))].map((t) => [
        t || "unknown",
        NT_COLORS[t] ?? NT_COLORS.unknown,
      ]);
    case "dimorphism":
      return Object.entries(DIMORPHISM_COLORS);
    case "fru/dsx":
      return Object.entries(FRU_DSX_COLORS);
    default:
      return [["one colour per cell type", "#d8dee9"]];
  }
}
