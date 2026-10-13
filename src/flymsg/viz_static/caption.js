// One line under the clock that says what the scene is, from the run manifest written by
// `flymsg viz`: the stimulated types with their input rate and window, silenced types and
// seed, or the cell types of an anatomy scene. A scene without a manifest gets no line.

const list = (xs) => xs.join(", ");

export function sceneCaption(manifest) {
  const c = manifest?.config;
  if (!c) return "";
  if (!c.sim?.length)
    return c.types?.length ? `anatomy: ${list(c.types)} (no simulation)` : "";
  const parts = [
    `input: ${list(c.sim)} at ${c.rate} Hz for ${c.stim_ms} of ${c.duration} ms`,
  ];
  if (c.silence?.length) parts.push(`silenced: ${list(c.silence)}`);
  const seed = manifest.seeds?.seed ?? manifest.seeds?.all?.[0];
  if (seed !== undefined) parts.push(`seed ${seed}`);
  parts.push("model replay");
  return parts.join(" · ");
}
