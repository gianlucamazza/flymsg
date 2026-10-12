/**
 * Neuron selection: finding a neuron, the roles of its partners in the scene, and the panel
 * text. Anatomy (synapse counts from partners.json) and simulation (the replay rate) stay
 * labelled apart.
 */

const UNKNOWN = "unknown";
const known = (v) => (v && v !== "unknown" ? v : UNKNOWN);

/**
 * The first neuron matching `query`: a bodyId, then an instance, then a cell type (case
 * insensitive). Null when nothing matches.
 */
export function findNeuron(neurons, query) {
  const q = String(query ?? "").trim();
  if (!q) return null;
  if (/^\d+$/.test(q)) {
    const hit = neurons.find((n) => String(n.bodyId) === q);
    if (hit) return hit;
  }
  const lower = q.toLowerCase();
  return (
    neurons.find((n) => (n.instance || "").toLowerCase() === lower) ??
    neurons.find((n) => (n.type || "").toLowerCase() === lower) ??
    null
  );
}

/** Row index -> role, for the selected neuron and its partners inside the scene. */
export function focusRoles(k, entry) {
  const roles = new Map();
  const up = new Set((entry?.upstream?.in_scene ?? []).map(([r]) => r));
  const down = new Set((entry?.downstream?.in_scene ?? []).map(([r]) => r));
  for (const r of up)
    roles.set(r, down.has(r) ? "up and downstream" : "upstream");
  for (const r of down) if (!up.has(r)) roles.set(r, "downstream");
  roles.set(k, "selected");
  return roles;
}

function direction(label, prep, d) {
  if (!d) return [`${label}: ${UNKNOWN} (no partner table)`];
  if (!d.total_types) return [`${label}: none in the dataset`];
  const rows = d.types.map(
    ([type, syn, conn]) =>
      `  ${type} — ${syn} synapses, ${conn} neuron${conn === 1 ? "" : "s"}`,
  );
  const more = d.total_types - d.types.length;
  return [
    `${label}: ${d.total_synapses} synapses ${prep} ${d.total_types} cell types` +
      (more > 0 ? ` (top ${d.types.length} shown, ${more} more)` : ""),
    ...rows,
    `  ${d.in_scene.length} of these partner neurons are in this scene`,
  ];
}

/**
 * Panel lines for neuron `n`. `entry` is its partners.json record (undefined while the table
 * loads or when the scene has none); `source` names where the counts come from.
 */
export function panelLines(n, entry, source) {
  return [
    `${n.instance || n.type} · bodyId ${n.bodyId}`,
    `type ${known(n.type === "untyped" ? "" : n.type)} · transmitter ${known(n.nt)} · superclass ${known(n.superclass)}`,
    `dimorphism ${n.dimorphism || "not annotated"} · fru/dsx ${n.fruDsx || "not annotated"}`,
    n.rate == null
      ? "simulation: no replay in this scene"
      : `simulation: ${n.rate} Hz during the stimulus (model, not a recording)`,
    `anatomy: ${source ?? "partner table not exported for this scene"}`,
    ...direction("inputs", "from", entry?.upstream),
    ...direction("outputs", "onto", entry?.downstream),
    `same numbers: flymsg info ${n.bodyId}`,
  ];
}

/** The bodyId to select from the page URL (`?select=`), or null. */
export function selectParam(search) {
  const v = new URLSearchParams(search).get("select");
  return v && v.trim() ? v.trim() : null;
}
