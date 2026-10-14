import { binAt } from "./raster.js";

/**
 * Graded (non-spiking) neurons glow by their potential, not by spikes: graded.bin holds, per
 * 10 ms bin, each one's potential relative to its reference as a signed step of
 * scale_mv / 127. The glow is that bin's value, signed: positive depolarized, negative
 * hyperpolarized, |value| = 1 at the neuron's scale.
 *
 * @param {Int8Array} steps bin-major: steps[bin * g + j]
 * @param {{k: number[], bins: number, binMs: number}} shape scene rows of the graded neurons
 * @param {number} t replay time, ms
 * @param {Float32Array} out activity of every scene row; graded rows are overwritten
 */
export function gradedAt(steps, { k, bins, binMs }, t, out) {
  const g = k.length;
  const b = binAt(t, binMs, bins);
  for (let j = 0; j < g; j++) out[k[j]] = steps[b * g + j] / 127;
  return out;
}

/** The potential in mV that row `j` shows at bin `b`, for the panel. */
export function gradedMv(steps, { k, scaleMv }, b, j) {
  return (steps[b * k.length + j] / 127) * scaleMv[j];
}
