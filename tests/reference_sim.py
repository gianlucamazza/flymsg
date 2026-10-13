"""Reference implementation of `sim.run`: the vectorised NumPy loop that the compiled kernel
replaced (flymsg v0.4.0). The kernel must reproduce its spikes exactly (tests/test_core.py).
With `record`, it also returns v, g and th of those neurons after every step, the oracle for
flymsg.tracing (tests/test_tracing.py)."""

import numpy as np
from scipy import sparse

from flymsg.sim import Gap, Graded, Membrane, Params, Result, graded_arrays


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
    record: np.ndarray | None = None,
    graded: Graded | None = None,
    gap: Gap | None = None,
    membrane: Membrane | None = None,
):
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
    # per-neuron membrane: Params everywhere, then the listed neurons' own values
    tau_m, tau_syn = np.full(n, p.tau_m), np.full(n, p.tau_syn)
    rest, v_th = np.full(n, p.v_rest), np.full(n, p.v_th)
    if membrane is not None:
        idx = np.asarray(membrane.idx, dtype=np.int64)
        tau_m[idx], tau_syn[idx] = membrane.tau_m, membrane.tau_syn
        rest[idx], v_th[idx] = membrane.v_rest, membrane.v_th
    rest, v_th = rest.astype(np.float32), v_th.astype(np.float32)
    v = rest.copy()
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
    gi, g_lo, g_span, g_scale, is_graded = graded_arrays(graded, n, p.dt)
    from scipy.linalg import expm
    from scipy.sparse.csgraph import connected_components

    coupled, operators = [], {}
    pulse = np.zeros(n, dtype=np.int32)
    width = (
        round(gap.spike_ms / p.dt)
        if gap is not None and gap.spike_ms is not None
        else 0
    )
    amplitude = np.broadcast_to(
        np.asarray(
            gap.spike_mv if gap is not None and gap.spike_mv is not None else 0.0,
            dtype=np.float64,
        ),
        (n,),
    )
    if gap is not None:
        forward = np.broadcast_to(
            np.asarray(gap.coupling, dtype=float), np.asarray(gap.i).shape
        )
        back = (
            forward
            if gap.coupling_back is None
            else np.broadcast_to(
                np.asarray(gap.coupling_back, dtype=float), forward.shape
            )
        )
        C = sparse.coo_matrix(
            (np.r_[forward, back], (np.r_[gap.i, gap.j], np.r_[gap.j, gap.i])),
            shape=(n, n),
        ).tocsr()
        active = np.flatnonzero(np.asarray(C.sum(axis=1)).ravel() > 0)
        _, labels = connected_components(C[active][:, active], directed=False)
        for label in np.unique(labels):
            nodes = active[labels == label]
            K = C[nodes][:, nodes].toarray()
            generator = (K - np.diag(1 + K.sum(axis=1))) / p.tau_m
            coupled.append((nodes, generator, K))
    rest64 = np.float64(np.float32(p.v_rest))
    g_flight = [np.zeros(gi.size, dtype=np.float32)] * d  # release in flight
    g_vsum = np.zeros((-(-steps // per_bin), gi.size))
    recent: list[np.ndarray] = [np.empty(0, dtype=np.int64)] * max(ref_steps - 1, 0)
    in_flight: list[np.ndarray] = [
        np.empty(0, dtype=np.int64)
    ] * d  # ring buffer of delayed spikes
    counts = np.zeros((-(-steps // per_bin), n), dtype=np.uint16)
    first = np.full(n, -1, dtype=np.int64)
    # exact solution of dv/dt = (v_rest - v + g) / tau_m, dg/dt = -g / tau_syn over dt
    em, es = np.exp(-p.dt / tau_m), np.exp(-p.dt / tau_syn)
    em, es, gv = (
        em.astype(np.float32),
        es.astype(np.float32),
        (tau_syn / (tau_syn - tau_m) * (es - em)).astype(np.float32),
    )
    decay_th = np.float32(np.exp(-p.dt / p.tau_th))
    lam, kick = rate_hz * p.dt / 1000.0, np.float32(p.poisson_scale * p.w_syn)

    rec = None if record is None else {"v": [], "g": [], "th": []}
    for t in range(steps):
        ref = np.concatenate(recent) if recent else np.empty(0, dtype=np.int64)
        # state update, skipped while refractory (v stays at v_rest, g is frozen)
        g_ref = g[ref]
        frozen = np.zeros(n, dtype=bool)
        frozen[ref] = True
        exact = []
        for comp, (nodes, generator, K) in enumerate(coupled):
            mask = (
                frozen[nodes]
                if gap.refractory_mode == "continuous"
                else np.zeros(len(nodes), dtype=bool)
            )
            key = (comp, mask.tobytes())
            m = len(nodes)
            if key not in operators:
                free = np.flatnonzero(~mask)
                f = len(free)
                block = np.zeros((2 * f + m, 2 * f + m))
                block[:f, :f] = generator[np.ix_(free, free)]
                block[:f, f : 2 * f] = np.eye(f) / p.tau_m
                block[:f, 2 * f :] = K[free] / p.tau_m
                block[f : 2 * f, f : 2 * f] = -np.eye(f) / p.tau_syn
                M = np.zeros((m, 3 * m))
                if f:
                    E = expm(block * p.dt)
                    M[np.ix_(free, free)] = E[:f, :f]
                    M[np.ix_(free, m + free)] = E[:f, f : 2 * f]
                    M[np.ix_(free, 2 * m + np.arange(m))] = E[:f, 2 * f :]
                operators[key] = M
            x = np.r_[
                v[nodes].astype(np.float64) - rest64,
                np.where(frozen[nodes], 0.0, g[nodes].astype(np.float64)),
                np.where(pulse[nodes] > 0, amplitude[nodes], 0.0),
            ]
            exact.append((nodes, (operators[key] * x).cumsum(axis=1)[:, -1]))
        pulse[pulse > 0] -= 1
        v -= rest
        v *= em
        v += g * gv
        v += rest
        for nodes, values in exact:
            v[nodes] = (rest64 + values).astype(np.float32)
        g *= es
        v[ref] = rest[ref]
        g[ref] = g_ref
        th *= decay_th
        # threshold (a refractory neuron sits at v_rest, below any threshold)
        spiking = np.flatnonzero(v > v_th + th)
        if silence is not None:
            spiking = spiking[~silent[spiking]]
        spiking = spiking[~is_graded[spiking]]
        release = np.clip((v[gi] - g_lo) / g_span, 0, 1) * g_scale
        release[silent[gi]] = 0
        # synaptic delivery: spikes from `delay` ago into g, Poisson input into v;
        # like brian2, input reaching a refractory neuron is lost
        arriving = in_flight[t % d]
        if arriving.size:
            g += np.asarray(W[:, arriving].sum(axis=1)).ravel()
            g[ref] = g_ref
        if np.any(g_flight[t % d]):
            g += W[:, gi] @ g_flight[t % d]
            g[ref] = g_ref
        g_flight[t % d] = release
        if t < stim_steps:
            v[stim] += kick * rng.poisson(lam, stim.size)
        # reset
        v[spiking] = rest[spiking]
        g[spiking] = 0.0
        th[spiking] += jump[spiking]
        if recent:
            recent[t % len(recent)] = spiking[~is_stim[spiking]]
        counts[t // per_bin, spiking] += 1
        first[spiking[first[spiking] < 0]] = t
        in_flight[t % d] = spiking
        if width:
            pulse[spiking] = width
        g_vsum[t // per_bin] += v[gi]
        if rec is not None:
            for k, x in (("v", v), ("g", g), ("th", th)):
                rec[k].append(x[record].copy())
    result = Result(
        counts=counts,
        first_spike_ms=np.where(first >= 0, first * p.dt, np.nan),
        bin_ms=per_bin * p.dt,
        stim_ms=stim_steps * p.dt,
        graded_v=g_vsum
        / np.minimum(per_bin, steps - np.arange(len(g_vsum)) * per_bin)[:, None]
        if gi.size
        else None,
    )
    if rec is None:
        return result
    return result, {k: np.stack(x) for k, x in rec.items()}
