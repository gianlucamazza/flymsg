"""Whole-CNS leaky integrate-and-fire model, after Shiu et al. (Nature 2024).

Each neuron is a LIF unit; a synaptic connection of n synapses adds sign * n * w_syn
to the postsynaptic conductance after a fixed delay. Stimulated neurons receive
Poisson input spikes. A spike-triggered threshold increase (see Params) keeps the
network from self-sustained runaway.
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
    poisson_scale: float = 250.0  # a Poisson input spike weighs poisson_scale * w_syn
    # Adaptive threshold: not in Shiu et al. Without it the whole CNS (brain + VNC)
    # falls into self-sustained activity (e.g. all Kenyon cells). 0 = plain Shiu model.
    # Stimulated neurons are exempt, so they follow the requested input rate.
    th_jump: float = 4.0  # mV added to the threshold per spike
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


def run(
    W: sparse.csc_matrix,
    stim: np.ndarray,
    rate_hz: float = 150.0,
    duration_ms: float = 1000.0,
    stim_ms: float | None = None,
    p: Params | None = None,
    seed: int = 0,
) -> np.ndarray:
    """Simulate and return each neuron's firing rate in Hz.

    Stimulation lasts `stim_ms` (default: the whole run).
    """
    p = p or Params()
    stim = np.unique(stim)  # duplicates would be dropped by fancy-index +=
    rng = np.random.default_rng(seed)
    n = W.shape[0]
    steps = int(duration_ms / p.dt)
    stim_steps = steps if stim_ms is None else int(stim_ms / p.dt)
    d = max(1, round(p.delay / p.dt))
    v = np.full(n, p.v_rest, dtype=np.float32)
    g = np.zeros(n, dtype=np.float32)
    th = np.zeros(n, dtype=np.float32)  # adaptive threshold offset
    jump = np.full(n, p.th_jump, dtype=np.float32)
    jump[stim] = 0.0
    ref_until = np.zeros(n, dtype=np.int64)
    in_flight: list[np.ndarray] = [
        np.empty(0, dtype=np.int64)
    ] * d  # ring buffer of delayed spikes
    counts = np.zeros(n, dtype=np.int64)
    decay_m, decay_s = np.float32(p.dt / p.tau_m), np.float32(np.exp(-p.dt / p.tau_syn))
    decay_th = np.float32(np.exp(-p.dt / p.tau_th))
    ref_steps, lam = round(p.t_ref / p.dt), rate_hz * p.dt / 1000.0

    for t in range(steps):
        arriving = in_flight[t % d]
        if arriving.size:
            g += np.asarray(W[:, arriving].sum(axis=1)).ravel()
        if t < stim_steps:
            g[stim] += p.poisson_scale * p.w_syn * rng.poisson(lam, stim.size)
        active = ref_until <= t
        v[active] += (g[active] - (v[active] - p.v_rest)) * decay_m
        g *= decay_s
        th *= decay_th
        spiking = np.flatnonzero(v >= p.v_th + th)
        th[spiking] += jump[spiking]
        v[spiking] = p.v_rest
        ref_until[spiking] = t + ref_steps
        counts[spiking] += 1
        in_flight[t % d] = spiking
    return counts / (duration_ms / 1000.0)
