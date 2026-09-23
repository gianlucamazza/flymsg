/**
 * Replay activity: turning binned spike counts into the 0..1 glow shown at a given time.
 */

/**
 * Activity of every neuron at `t` ms: each spike bin within `historyBins` before `t`
 * contributes its count decayed by exp(-age / tauMs), where the age is measured from the
 * middle of the bin. Scaled so that two spikes in the same bin saturate.
 *
 * @param {Uint16Array|Float32Array} spikes counts, bin-major: spikes[bin * n + k]
 * @param {{n: number, bins: number, binMs: number}} shape of that array
 * @param {Float32Array} out written in place, length n
 */
export function activityAt(
  spikes,
  { n, bins, binMs },
  t,
  out,
  tauMs = 15,
  historyBins = 5,
) {
  const b = Math.min(Math.floor(t / binMs), bins - 1);
  for (let k = 0; k < n; k++) {
    let s = 0;
    for (let j = Math.max(0, b - historyBins + 1); j <= b; j++) {
      const c = spikes[j * n + k];
      if (c) s += c * Math.exp(-Math.max(0, t - (j + 0.5) * binMs) / tauMs);
    }
    out[k] = Math.min(1, 0.5 * s);
  }
  return out;
}
