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
