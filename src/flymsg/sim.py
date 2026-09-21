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

import numpy as np
import pandas as pd
from scipy import sparse


@dataclass
class Params:
    v_rest: float = -52.0  # mV, also the reset potential
    v_th: float = -45.0  # mV
    tau_m: float = 20.0  # ms
    tau_syn: float = 5.0  # ms
    t_ref: float = 2.2  # ms
    delay: float = 1.8  # ms
    w_syn: float = 0.275  # mV per synapse
    poisson_scale: float = (
        250.0  # a Poisson input spike adds poisson_scale * w_syn to v
    )
    # Adaptive threshold: not in Shiu et al. Without it the whole CNS (brain + VNC)
    # falls into self-sustained activity (e.g. all Kenyon cells). 0 = plain Shiu model.
    # Stimulated neurons are exempt, so they follow the requested input rate.
    th_jump: float = 2.0  # mV added to the threshold per spike (calibrate-v3)
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
) -> Result:
    """Simulate; stimulation lasts `stim_ms` (default: the whole run)."""
    p = p or Params()
    stim = np.unique(stim)  # duplicates would be dropped by fancy-index +=
    rng = np.random.default_rng(seed)
    n = W.shape[0]
    steps = int(duration_ms / p.dt)
    stim_steps = steps if stim_ms is None else int(stim_ms / p.dt)
    per_bin = max(1, round(bin_ms / p.dt))
    if steps % per_bin:
        raise ValueError(f"duration_ms must be a multiple of bin_ms ({bin_ms})")
    d = max(1, round(p.delay / p.dt))
    v = np.full(n, p.v_rest, dtype=np.float32)
    g = np.zeros(n, dtype=np.float32)
    th = np.zeros(n, dtype=np.float32)  # adaptive threshold offset
    jump = np.full(n, p.th_jump, dtype=np.float32)
    jump[stim] = 0.0
    # A neuron spiking at step s is refractory at steps s+1 .. s+ref_steps-1 (brian2 integrates
    # it again at s + t_ref); stimulated neurons, Poisson targets, never are. The refractory
    # set is the non-stimulated spikers of the last ref_steps-1 steps, kept in a ring.
    ref_steps = round(p.t_ref / p.dt)
    is_stim = np.zeros(n, dtype=bool)
    is_stim[stim] = True
    recent: list[np.ndarray] = [np.empty(0, dtype=np.int64)] * max(ref_steps - 1, 0)
    in_flight: list[np.ndarray] = [
        np.empty(0, dtype=np.int64)
    ] * d  # ring buffer of delayed spikes
    counts = np.zeros((-(-steps // per_bin), n), dtype=np.uint16)
    first = np.full(n, -1, dtype=np.int64)
    # exact solution of dv/dt = (v_rest - v + g) / tau_m, dg/dt = -g / tau_syn over dt
    em, es = np.exp(-p.dt / p.tau_m), np.exp(-p.dt / p.tau_syn)
    em, es, gv = (
        np.float32(em),
        np.float32(es),
        np.float32(p.tau_syn / (p.tau_syn - p.tau_m) * (es - em)),
    )
    decay_th = np.float32(np.exp(-p.dt / p.tau_th))
    lam, kick = rate_hz * p.dt / 1000.0, np.float32(p.poisson_scale * p.w_syn)

    for t in range(steps):
        ref = np.concatenate(recent) if recent else np.empty(0, dtype=np.int64)
        # state update, skipped while refractory (v stays at v_rest, g is frozen)
        g_ref = g[ref]
        v -= p.v_rest
        v *= em
        v += g * gv
        v += p.v_rest
        g *= es
        v[ref] = p.v_rest
        g[ref] = g_ref
        th *= decay_th
        # threshold (a refractory neuron sits at v_rest, below any threshold)
        spiking = np.flatnonzero(v > p.v_th + th)
        # synaptic delivery: spikes from `delay` ago into g, Poisson input into v;
        # like brian2, input reaching a refractory neuron is lost
        arriving = in_flight[t % d]
        if arriving.size:
            g += np.asarray(W[:, arriving].sum(axis=1)).ravel()
            g[ref] = g_ref
        if t < stim_steps:
            v[stim] += kick * rng.poisson(lam, stim.size)
        # reset
        v[spiking] = p.v_rest
        g[spiking] = 0.0
        th[spiking] += jump[spiking]
        if recent:
            recent[t % len(recent)] = spiking[~is_stim[spiking]]
        counts[t // per_bin, spiking] += 1
        first[spiking[first[spiking] < 0]] = t
        in_flight[t % d] = spiking
    return Result(
        counts=counts,
        first_spike_ms=np.where(first >= 0, first * p.dt, np.nan),
        bin_ms=per_bin * p.dt,
        stim_ms=stim_steps * p.dt,
    )
