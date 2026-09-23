// Colour classes for the sex-related annotations of MaleCNS (see docs/dimorphism.md).
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

/** Stable small hash of a string, so a cell type always gets the same palette entry. */
export const hash = (s) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

/**
 * The colour of a neuron under the current view: by group, by transmitter, by cell type, or
 * by one of the two sex-related annotations.
 */
export function colourOf(n, view, groups) {
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
