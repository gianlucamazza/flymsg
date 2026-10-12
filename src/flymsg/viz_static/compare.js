/**
 * Two replays of the same neurons and time base (flymsg viz-compare): totals, first bins,
 * the class of each neuron, and the text that says what each run is. A neuron one export
 * does not hold is "not exported" there, never silent.
 */

/** Spikes per neuron over the whole replay. */
export function totals(spikes, { n, bins }) {
  const out = new Uint32Array(n);
  for (let b = 0; b < bins; b++)
    for (let k = 0; k < n; k++) out[k] += spikes[b * n + k];
  return out;
}

/** The first bin with a spike, or null. */
export function firstBin(spikes, { n, bins }, k) {
  for (let b = 0; b < bins; b++) if (spikes[b * n + k]) return b;
  return null;
}

/** |a - b| per bin and neuron: what the difference view glows with. */
export function difference(a, b) {
  const out = new Uint8Array(a.length);
  for (let i = 0; i < a.length; i++) out[i] = Math.abs(a[i] - b[i]);
  return out;
}

export function compareClass(inA, inB, totalA, totalB) {
  if (!inA || !inB) return "not exported";
  if (totalB > totalA) return "more";
  if (totalB < totalA) return "less";
  return "same";
}

/** One line per run: label and protocol status; a failed protocol says what it is not. */
export function runLines(comparison) {
  return comparison.runs.map((r, i) => {
    const tag = i === 0 ? "A" : "B";
    const status =
      r.status === "failed"
        ? "failed protocol: not evidence for a mechanism"
        : r.status === "validated"
          ? "validated protocol"
          : "exploratory, not scored";
    return `${tag} ${r.label} · ${status}${r.note ? ` · ${r.note}` : ""}`;
  });
}

/** What differs between the two run manifests, or that nothing does. */
export function differenceLines(comparison) {
  if (!comparison.differences.length) return ["the two run manifests match"];
  return comparison.differences.map(
    (d) => `${d.key}: ${JSON.stringify(d.a)} → ${JSON.stringify(d.b)}`,
  );
}

/** Panel lines for one neuron of a comparison. */
export function neuronLines(n, k, { spikesA, spikesB, shape, binMs, labels }) {
  const line = (label, present, spikes) => {
    if (!present) return `${label}: not exported in this run`;
    let total = 0;
    for (let b = 0; b < shape.bins; b++) total += spikes[b * shape.n + k];
    const first = firstBin(spikes, shape, k);
    return `${label}: ${total} spikes${first == null ? "" : `, first in the ${first * binMs}–${(first + 1) * binMs} ms bin`}`;
  };
  return [
    line(`A ${labels[0]}`, n.in[0], spikesA),
    line(`B ${labels[1]}`, n.in[1], spikesB),
  ];
}
