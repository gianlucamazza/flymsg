"""Whole-CNS leaky integrate-and-fire model, after Shiu et al. (Nature 2024).

Each neuron is a LIF unit; a synaptic connection of n synapses adds sign * n * w_syn
to the postsynaptic conductance after a fixed delay. Stimulated neurons receive
Poisson input spikes. A spike-triggered threshold increase (see Params) keeps the
network from self-sustained runaway.

The update follows the published brian2 model step by step (github.com/philshiu/
Drosophila_brain_model, model.py): exact integration of v and g, frozen while refractory;
threshold; delivery of delayed spikes to g (lost while refractory) and of Poisson input to
v; reset of v and g.
Stimulated neurons have no refractory period. The adaptive threshold is the only addition.
"""

from dataclasses import dataclass

import numba
import numpy as np
import pandas as pd
from scipy import sparse

SHIU_W_SYN = 0.275  # mV per synapse, Shiu et al. 2024, tuned on FlyWire FAFB


@dataclass
class Params:
    v_rest: float = -52.0  # mV, also the reset potential
    v_th: float = -45.0  # mV
    tau_m: float = 20.0  # ms
    tau_syn: float = 5.0  # ms
    t_ref: float = 2.2  # ms
    delay: float = 1.8  # ms
    # MaleCNS counts more synapses per neuron than FAFB (median 1.81x over matched types,
    # compare.synapse_density_ratio); the default is Shiu's weight divided by 1.43, the lower
    # quartile of that ratio, chosen by the pre-registered model selection and replication
    # (docs/validation.md)
    w_syn: float = SHIU_W_SYN / 1.43  # mV per synapse
    poisson_scale: float = (
        250.0  # a Poisson input spike adds poisson_scale * w_syn to v
    )
    # Adaptive threshold: not in Shiu et al. It was needed while w_syn stayed at Shiu's FAFB
    # value (the whole CNS then ran away); at the density-scaled weight it is not, so it is
    # off by default and kept as an option. Stimulated neurons are exempt.
    th_jump: float = 0.0  # mV per spike; 0 = off (default since the B- replication)
    tau_th: float = 100.0  # ms, threshold relaxation back to v_th
    dt: float = 0.1  # ms


def weight_matrix(
    edges: pd.DataFrame, sign: np.ndarray, n: int, w_syn: float
) -> sparse.csc_matrix:
    """Signed (post x pre) matrix; CSC so that columns of spiking neurons slice fast."""
    w = edges["weight"].to_numpy() * sign[edges["pre"].to_numpy()] * w_syn
    keep = w != 0
    return sparse.csc_matrix(
        (
            w[keep].astype(np.float32),
            (edges["post"].to_numpy()[keep], edges["pre"].to_numpy()[keep]),
        ),
        shape=(n, n),
    )


@dataclass
class Result:
    counts: np.ndarray  # (bins, n) spikes per time bin
    first_spike_ms: np.ndarray  # (n,) latency of the first spike, NaN if silent
    bin_ms: float
    stim_ms: float

    @property
    def duration_ms(self) -> float:
        return self.counts.shape[0] * self.bin_ms

    def rate(self, t0: float = 0.0, t1: float | None = None) -> np.ndarray:
        """Mean firing rate in Hz per neuron over [t0, t1) ms, rounded to whole bins."""
        b0, b1 = round(t0 / self.bin_ms), round((t1 or self.duration_ms) / self.bin_ms)
        return self.counts[b0:b1].sum(axis=0) / ((b1 - b0) * self.bin_ms / 1000.0)

    def persistent(self, settle_ms: float = 100.0) -> np.ndarray:
        """Neurons still firing from stim end + `settle_ms` to the end of the run."""
        t0 = self.stim_ms + settle_ms
        if t0 >= self.duration_ms:
            raise ValueError("run must extend past stim_ms + settle_ms")
        return np.flatnonzero(self.rate(t0) > 0)


def run(
    W: sparse.csc_matrix,
    stim: np.ndarray,
    rate_hz: float = 150.0,
    duration_ms: float = 1000.0,
    stim_ms: float | None = None,
    p: Params | None = None,
    seed: int = 0,
    bin_ms: float = 10.0,
    silence: np.ndarray | None = None,
) -> Result:
    """Simulate; stimulation lasts `stim_ms` (default: the whole run). Neurons in `silence`
    never fire, so they transmit nothing: for the rest of the network this equals zeroing
    their outgoing synapses, as Shiu et al. silence neurons."""
    p = p or Params()
    stim = np.unique(stim)  # duplicates would be dropped by fancy-index +=
    rng = np.random.default_rng(seed)
    n = W.shape[0]
    steps = int(duration_ms / p.dt)
    stim_steps = steps if stim_ms is None else int(stim_ms / p.dt)
    per_bin = max(1, round(bin_ms / p.dt))
    if steps % per_bin:
        raise ValueError(f"duration_ms must be a multiple of bin_ms ({bin_ms})")
    jump = np.full(n, p.th_jump, dtype=np.float32)
    jump[stim] = 0.0
    is_stim = np.zeros(n, dtype=np.bool_)
    is_stim[stim] = True
    silent = np.zeros(n, dtype=np.bool_)
    if silence is not None:
        silent[silence] = True
    # all Poisson input up front: the same draws, in the same order, as one call per step
    kicks = rng.poisson(rate_hz * p.dt / 1000.0, (stim_steps, stim.size))
    em, es = np.exp(-p.dt / p.tau_m), np.exp(-p.dt / p.tau_syn)
    gv = p.tau_syn / (p.tau_syn - p.tau_m) * (es - em)  # from the float64 decays
    counts, first = _kernel(
        W.indptr.astype(np.int64),
        W.indices.astype(np.int64),
        W.data.astype(np.float32),
        n,
        steps,
        per_bin,
        max(1, round(p.delay / p.dt)),
        round(p.t_ref / p.dt),
        stim.astype(np.int64),
        kicks,
        is_stim,
        silent,
        jump,
        np.float32(em),
        np.float32(es),
        np.float32(gv),
        np.float32(np.exp(-p.dt / p.tau_th)),
        np.float32(p.v_rest),
        np.float32(p.v_th),
        np.float32(p.poisson_scale * p.w_syn),
    )
    return Result(
        counts=counts,
        first_spike_ms=np.where(first >= 0, first * p.dt, np.nan),
        bin_ms=per_bin * p.dt,
        stim_ms=stim_steps * p.dt,
    )


@numba.njit(cache=True)
def _kernel(
    indptr, indices, data, n, steps, per_bin, d, ref_steps, stim, kicks, is_stim, silent,
    jump, em, es, gv, decay_th, v_rest, v_th, kick,
):  # fmt: skip
    """One simulation. Same operations, order and float32/float64 rounding as the NumPy
    reference (tests/reference_sim.py), so the spikes are identical:
    1. state update of non-refractory neurons (a neuron spiking at step s is refractory at
       s+1 .. s+ref_steps-1; stimulated neurons never are); threshold offset decays;
    2. threshold; silenced neurons never fire;
    3. delivery of the spikes emitted d steps ago, summed per target in float32 column by
       column (as scipy's CSC product), lost on refractory targets; Poisson input into v;
    4. reset of v and g, threshold jump."""
    v = np.full(n, v_rest, dtype=np.float32)
    g = np.zeros(n, dtype=np.float32)
    th = np.zeros(n, dtype=np.float32)
    ref_until = np.zeros(n, dtype=np.int32)
    ring = np.empty((d, n), dtype=np.int32)  # spikes in flight, one row per step slot
    ring_len = np.zeros(d, dtype=np.int64)
    counts = np.zeros(((steps + per_bin - 1) // per_bin, n), dtype=np.uint16)
    first = np.full(n, -1, dtype=np.int64)
    c = np.zeros(n, dtype=np.float32)  # delivered input per target, reset after use
    touched = np.empty(n, dtype=np.int32)  # targets with delivered input this step
    hit = np.zeros(n, dtype=np.bool_)
    spiking = np.empty(n, dtype=np.int32)
    stim_steps = kicks.shape[0]
    for t in range(steps):
        # 1. state update (refractory: v stays at v_rest, g frozen), branch-free so that
        # it vectorises; the refractory lanes compute and discard
        for i in range(n):
            frozen = ref_until[i] > t
            vi = (v[i] - v_rest) * em + g[i] * gv + v_rest
            gi = g[i] * es
            v[i] = v_rest if frozen else vi
            g[i] = g[i] if frozen else gi
            th[i] = th[i] * decay_th
        # 2. threshold
        ns = 0
        for i in range(n):
            if v[i] > v_th + th[i] and not silent[i]:
                spiking[ns] = i
                ns += 1
        # 3. delivery: per-target sums in column order, then applied to the touched targets
        slot = t % d
        nt = 0
        for k in range(ring_len[slot]):
            j = ring[slot, k]
            for q in range(indptr[j], indptr[j + 1]):
                r = indices[q]
                c[r] += data[q]
                if not hit[r]:
                    hit[r] = True
                    touched[nt] = r
                    nt += 1
        for k in range(nt):
            r = touched[k]
            if ref_until[r] <= t:
                g[r] = g[r] + c[r]
            c[r] = 0.0
            hit[r] = False
        if t < stim_steps:
            for s in range(stim.size):
                i = stim[s]
                v[i] = np.float32(np.float64(v[i]) + np.float64(kick) * kicks[t, s])
        # 4. reset
        b = t // per_bin
        for k in range(ns):
            i = spiking[k]
            v[i] = v_rest
            g[i] = 0.0
            th[i] = th[i] + jump[i]
            if not is_stim[i]:
                ref_until[i] = t + ref_steps
            counts[b, i] += 1
            if first[i] < 0:
                first[i] = t
            ring[slot, k] = i
        ring_len[slot] = ns
    return counts, first
