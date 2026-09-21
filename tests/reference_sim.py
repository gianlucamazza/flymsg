"""Reference implementation of `sim.run`: the vectorised NumPy loop that the compiled kernel
replaced (flymsg v0.4.0). The kernel must reproduce its spikes exactly (tests/test_core.py)."""

import numpy as np
from scipy import sparse

from flymsg.sim import Params, Result


def run_reference(
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
    silent = np.zeros(n, dtype=bool)
    if silence is not None:
        silent[silence] = True
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
        if silence is not None:
            spiking = spiking[~silent[spiking]]
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
