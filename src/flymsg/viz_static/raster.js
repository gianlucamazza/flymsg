/**
 * Spike raster beside the 3D replay. The replay stores spike counts per bin (activity.bin),
 * so a raster cell is "spikes in that bin", never an exact spike time. The bin of a replay
 * time comes from binAt, the same function the 3D glow uses, so the cursor and the glow
 * always show the same bin.
 */

/** The bin shown at replay time `t` (ms): clamped to the last bin. */
export function binAt(t, binMs, bins) {
  return Math.max(0, Math.min(Math.floor(t / binMs), bins - 1));
}

/**
 * One row per neuron row `k` in `ks`: its counts per bin and their total. A row whose total
 * is 0 had no spike in the replay; the page says so instead of drawing an empty line.
 *
 * @param {Uint8Array} spikes counts, bin-major: spikes[bin * n + k]
 */
export function rasterRows(spikes, { n, bins }, ks) {
  return ks.map((k) => {
    const counts = new Uint8Array(bins);
    let total = 0;
    for (let b = 0; b < bins; b++) {
      counts[b] = spikes[b * n + k];
      total += counts[b];
    }
    return { k, counts, total };
  });
}

/**
 * The rows to draw for a selection: the selected neuron, then its partners in the scene by
 * role and synapse count (as partners.json orders them), at most `limit`; `hidden` counts
 * the rest.
 */
export function selectionRows(k, entry, limit = 40) {
  const order = [k];
  const seen = new Set(order);
  for (const key of ["upstream", "downstream"])
    for (const [r] of entry?.[key]?.in_scene ?? [])
      if (!seen.has(r)) {
        seen.add(r);
        order.push(r);
      }
  return { rows: order.slice(0, limit), hidden: Math.max(0, order.length - limit) };
}

/** A small JSON record of what is on screen, with where it came from. */
export function selectionExport({ neurons, rows, activity, t, manifest }) {
  return {
    schema: "flymsg.selection/v1",
    note: "spike counts per bin from a model replay, not recordings",
    t_ms: t,
    bin_ms: activity.bin_ms,
    stim_ms: activity.stim_ms,
    neurons: rows.map(({ k, counts, total }) => ({
      bodyId: neurons[k].bodyId,
      type: neurons[k].type,
      counts: Array.from(counts),
      total,
    })),
    source: manifest
      ? {
          command: manifest.command,
          commit: manifest.git?.commit,
          dirty: manifest.git?.dirty,
          config: manifest.config,
          seeds: manifest.seeds,
          dataset: manifest.dataset?.name,
          release: manifest.dataset?.release,
        }
      : null,
  };
}
