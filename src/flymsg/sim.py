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

Optional graded (non-spiking) neurons (`Graded`, issue #97) integrate like the others but
have no threshold, reset or refractory period; they release continuously instead.
Optional electrical synapses (`Gap`, issue #85) couple pairs of neurons through their
potentials. Without either, every array and every rounding step is the spiking model's.
"""

from dataclasses import dataclass
from itertools import pairwise

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


@dataclass(frozen=True)
class Graded:
    """Non-spiking neurons and their release curve. At every step a graded neuron releases
    f = clip((v - v_lo) / span, 0, 1) times `rate_hz * dt / 1000` of one spike's weight on
    each outgoing synapse, delivered after the synaptic delay: at saturation it acts on its
    targets like a neuron firing at `rate_hz`. It never spikes and is never refractory. The
    curve is threshold-linear between two voltages; no value has a default, so a lock states
    each one and its source. Silenced graded neurons release nothing."""

    idx: np.ndarray  # neuron indices
    v_lo: np.ndarray  # mV, no release at or below
    span: np.ndarray  # mV, release saturates at v_lo + span
    rate_hz: np.ndarray  # spike rate equivalent to saturated release


def graded_arrays(graded: Graded | None, n: int, dt: float) -> tuple:
    """Kernel arrays of `graded`, sorted by neuron index: indices (int64), v_lo, span and the
    per-step release at saturation (float32), and the (n,) mask. Empty without graded
    neurons. Shared with `runtime.CpuRuntime`."""
    mask = np.zeros(n, dtype=np.bool_)
    if graded is None:
        empty = np.empty(0, dtype=np.float32)
        return np.empty(0, dtype=np.int64), empty, empty, empty, mask
    idx = np.asarray(graded.idx)
    if idx.size and idx.dtype.kind not in "iu":
        raise ValueError("graded indices must be integers")
    idx = idx.astype(np.int64).reshape(-1)
    cols = [
        np.broadcast_to(np.asarray(x, dtype=np.float64), idx.shape)
        for x in (graded.v_lo, graded.span, graded.rate_hz)
    ]
    if np.unique(idx).size != idx.size or np.any(idx < 0) or np.any(idx >= n):
        raise ValueError("graded indices must be unique and inside the network")
    if not all(np.isfinite(c).all() for c in cols):
        raise ValueError("graded parameters must be finite")
    if np.any(cols[1] <= 0) or np.any(cols[2] < 0):
        raise ValueError("graded span must be positive and rate nonnegative")
    order = np.argsort(idx)
    mask[idx] = True
    return (
        idx[order],
        cols[0][order].astype(np.float32),
        cols[1][order].astype(np.float32),
        (cols[2][order] * dt / 1000.0).astype(np.float32),
        mask,
    )


@dataclass(frozen=True)
class Gap:
    """Electrical synapses: symmetric, non-rectifying couplings between neurons `i[k]` and
    `j[k]` of strength `coupling[k]`, the junction's conductance over the leak conductance
    (dimensionless; a coupling coefficient c between two equal cells gives c / (1 - c)).
    Coupled neurons follow tau_m dv/dt = v_rest - v + g + sum_j coupling (v_j - v), which is
    linear between spikes, so each connected group is integrated exactly over a step by a
    precomputed matrix exponential (Van Loan's block form for the decaying synaptic input).
    A refractory neuron is held at rest and its frozen conductance does not act, as in the
    uncoupled model; it enters its partners' step at rest. Spikes do not cross: a LIF spike
    is a reset, not a waveform, so spikelets are absent."""

    i: np.ndarray
    j: np.ndarray
    coupling: np.ndarray


def gap_arrays(gap: Gap | None, n: int, p: "Params") -> tuple:
    """Kernel arrays of `gap`: the coupled neurons grouped by connected component (indices,
    component offsets) and, per component of m neurons, the m x 2m float64 step matrix
    [P | Q] with v(t + dt) - v_rest = P (v - v_rest) + Q g for free neurons, row-major, with
    its offsets. Empty without electrical synapses."""
    from scipy.linalg import expm
    from scipy.sparse.csgraph import connected_components

    empty = (
        np.empty(0, dtype=np.int64),
        np.zeros(1, dtype=np.int64),
        np.empty(0, dtype=np.float64),
        np.zeros(1, dtype=np.int64),
    )
    if gap is None:
        return empty
    ends = []
    for x in (gap.i, gap.j):
        a = np.asarray(x)
        if a.size and a.dtype.kind not in "iu":
            raise ValueError("gap endpoints must be integers")
        ends.append(a.astype(np.int64).reshape(-1))
    i, j = ends
    if i.shape != j.shape or np.any(i == j):
        raise ValueError("gap endpoints must pair distinct neurons")
    if np.any(np.r_[i, j] < 0) or np.any(np.r_[i, j] >= n):
        raise ValueError("gap endpoints outside the network")
    c = np.broadcast_to(np.asarray(gap.coupling, dtype=np.float64), i.shape)
    if not np.isfinite(c).all() or np.any(c < 0):
        raise ValueError("gap couplings must be finite and nonnegative")
    keep = c > 0
    i, j, c = i[keep], j[keep], c[keep]
    if i.size == 0:
        return empty
    K = sparse.coo_matrix(
        (np.r_[c, c], (np.r_[i, j], np.r_[j, i])), shape=(n, n)
    ).tocsr()
    nodes = np.unique(np.r_[i, j])
    _, label = connected_components(K[nodes][:, nodes], directed=False)
    order = np.lexsort((nodes, label))
    nodes, label = nodes[order], label[order]
    off = np.r_[0, np.cumsum(np.bincount(label))].astype(np.int64)
    mats, moff = [], [0]
    for a, b in pairwise(off):
        members = nodes[a:b]
        m = members.size
        Kc = K[members][:, members].toarray()
        A = (Kc - np.diag(1.0 + Kc.sum(axis=1))) / p.tau_m
        block = np.zeros((2 * m, 2 * m))
        block[:m, :m] = A
        block[:m, m:] = np.eye(m) / p.tau_m
        block[m:, m:] = -np.eye(m) / p.tau_syn
        E = expm(block * p.dt)
        mats.append(np.hstack([E[:m, :m], E[:m, m:]]).ravel())
        moff.append(moff[-1] + 2 * m * m)
    return nodes, off, np.concatenate(mats), np.asarray(moff, dtype=np.int64)


def network(
    neurons: pd.DataFrame, edges: pd.DataFrame, p: "Params"
) -> sparse.csc_matrix:
    """The weight matrix of a dataset at these parameters: the usual way to build one, from
    the neurons' `sign` column. `weight_matrix` stays for the variants that need another
    sign column or a scaled weight (see `compare`)."""
    return weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)


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
    traced: np.ndarray | None = (
        None  # (steps, n_trace) spike bits; None if not requested
    )
    # (bins, n_graded) mean membrane potential of the graded neurons per bin, in the order
    # of their sorted indices; None without graded neurons
    graded_v: np.ndarray | None = None

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


def poisson_kicks(
    seed: int, rate_hz: float, dt_ms: float, n_steps: int, n_stim: int
) -> np.ndarray:
    """The open-loop Poisson draw. One Generator, one call, so a shorter slice is the prefix."""
    rng = np.random.default_rng(seed)
    return rng.poisson(rate_hz * dt_ms / 1000.0, (n_steps, n_stim))


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
    kicks: np.ndarray | None = None,
    trace: np.ndarray | None = None,
    graded: Graded | None = None,
    gap: Gap | None = None,
) -> Result:
    """Simulate; stimulation lasts `stim_ms` (default: the whole run). Neurons in `silence`
    never fire, so they transmit nothing: for the rest of the network this equals zeroing
    their outgoing synapses, as Shiu et al. silence neurons.

    `kicks` replaces the seeded draw: shape (steps, n_stim), applied in order. `trace` records
    every spike step of those neurons, in the order given. The recording is written after the
    spike bookkeeping and does not enter the state update. `graded` makes those neurons
    non-spiking (see `Graded`); their mean potential per bin is returned in `graded_v`.
    `gap` adds electrical synapses (see `Gap`).
    """
    p = p or Params()
    stim = np.unique(stim)  # duplicates would be dropped by fancy-index +=
    n = W.shape[0]
    steps = int(duration_ms / p.dt)
    if kicks is None:
        stim_steps = steps if stim_ms is None else int(stim_ms / p.dt)
        kicks = poisson_kicks(seed, rate_hz, p.dt, stim_steps, int(stim.size))
    else:
        kicks = np.asarray(kicks)
        if kicks.ndim != 2 or kicks.shape[1] != stim.size:
            raise ValueError("kicks must have one column per stimulated neuron")
        if kicks.shape[0] > steps:
            raise ValueError("kicks are longer than the run")
        stim_steps = kicks.shape[0]
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
    trace_col = np.full(n, -1, dtype=np.int32)
    if trace is None:
        traced = np.zeros((steps, 1), dtype=np.uint8)
        keep_trace = None
    else:
        requested = np.asarray(trace, dtype=np.int64).reshape(-1)
        _, first_at = np.unique(requested, return_index=True)
        trace = requested[np.sort(first_at)]
        if trace.size == 0 or np.any(trace < 0) or np.any(trace >= n):
            raise ValueError("trace indices are outside the network")
        trace_col[trace] = np.arange(trace.size, dtype=np.int32)
        traced = np.zeros((steps, trace.size), dtype=np.uint8)
        keep_trace = traced
    d, ref_steps = _delays(p)
    g_idx, g_lo, g_span, g_scale, is_graded = graded_arrays(graded, n, p.dt)
    gap_nodes, gap_off, gap_mat, gap_moff = gap_arrays(gap, n, p)
    counts, first, g_vsum = _kernel(
        W.indptr.astype(np.int64),
        W.indices.astype(np.int64),
        W.data.astype(np.float32),
        n,
        steps,
        per_bin,
        d,
        ref_steps,
        stim.astype(np.int64),
        kicks,
        is_stim,
        silent,
        jump,
        *_constants(p),
        trace_col,
        traced,
        g_idx,
        g_lo,
        g_span,
        g_scale,
        is_graded,
        gap_nodes,
        gap_off,
        gap_mat,
        gap_moff,
    )
    return Result(
        counts=counts,
        first_spike_ms=np.where(first >= 0, first * p.dt, np.nan),
        bin_ms=per_bin * p.dt,
        stim_ms=stim_steps * p.dt,
        traced=keep_trace,
        graded_v=_bin_means(g_vsum, steps, per_bin) if g_idx.size else None,
    )


def _bin_means(vsum: np.ndarray, steps: int, per_bin: int) -> np.ndarray:
    """Mean per bin from per-bin sums; the last bin may be shorter."""
    sizes = np.minimum(per_bin, steps - np.arange(vsum.shape[0]) * per_bin)
    return vsum / sizes[:, None]


def _delays(p: Params) -> tuple[int, int]:
    """Synaptic delay and refractory period in steps. Shared with `runtime.CpuRuntime`."""
    return max(1, round(p.delay / p.dt)), round(p.t_ref / p.dt)


def _constants(p: Params) -> tuple:
    """The kernel's float32 constants: membrane and synaptic decays, the synaptic gain (from
    the float64 decays), threshold decay, rest, threshold and Poisson kick. Shared with
    `runtime.CpuRuntime`, so both paths round the same way."""
    em, es = np.exp(-p.dt / p.tau_m), np.exp(-p.dt / p.tau_syn)
    gv = p.tau_syn / (p.tau_syn - p.tau_m) * (es - em)
    return tuple(
        np.float32(x)
        for x in (
            em,
            es,
            gv,
            np.exp(-p.dt / p.tau_th),
            p.v_rest,
            p.v_th,
            p.poisson_scale * p.w_syn,
        )
    )


@numba.njit(cache=True)
def _kernel(
    indptr,
    indices,
    data,
    n,
    steps,
    per_bin,
    d,
    ref_steps,
    stim,
    kicks,
    is_stim,
    silent,
    jump,
    em,
    es,
    gv,
    decay_th,
    v_rest,
    v_th,
    kick,
    trace_col,
    traced,
    g_idx,
    g_lo,
    g_span,
    g_scale,
    is_graded,
    gap_nodes,
    gap_off,
    gap_mat,
    gap_moff,
):
    """One simulation. Same operations, order and float32/float64 rounding as the NumPy
    reference (tests/reference_sim.py), so the spikes are identical:
    1. state update of non-refractory neurons (a neuron spiking at step s is refractory at
       s+1 .. s+ref_steps-1; stimulated neurons never are); threshold offset decays;
    2. threshold; silenced neurons never fire;
    3. delivery of the spikes emitted d steps ago, summed per target in float32 column by
       column (as scipy's CSC product), lost on refractory targets; Poisson input into v;
    4. reset of v and g, threshold jump.
    Graded neurons skip 2 and 4; their release, computed at 2 from v, is delivered d steps
    later at 3, after the spikes, summed per target column by column (as scipy's CSC
    matrix-vector product). Electrically coupled neurons replace the update of 1 by their
    component's exact step [P | Q] applied to the state before it (potentials relative to
    rest, then conductances, zero for refractory neurons), summed in float64 in that order."""
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
    g_ring = np.zeros((d, g_idx.size), dtype=np.float32)
    g_new = np.zeros(g_idx.size, dtype=np.float32)
    g_vsum = np.zeros((counts.shape[0], g_idx.size), dtype=np.float64)
    gap_buf = np.zeros(gap_nodes.size, dtype=np.float32)
    _advance(
        0,
        steps,
        indptr,
        indices,
        data,
        n,
        per_bin,
        d,
        ref_steps,
        stim,
        kicks,
        is_stim,
        silent,
        jump,
        em,
        es,
        gv,
        decay_th,
        v_rest,
        v_th,
        kick,
        trace_col,
        traced,
        v,
        g,
        th,
        ref_until,
        ring,
        ring_len,
        counts,
        first,
        c,
        touched,
        hit,
        spiking,
        g_idx,
        g_lo,
        g_span,
        g_scale,
        is_graded,
        g_ring,
        g_new,
        g_vsum,
        gap_nodes,
        gap_off,
        gap_mat,
        gap_moff,
        gap_buf,
    )
    return counts, first, g_vsum


@numba.njit(cache=True)
def _advance(
    start_step,
    stop_step,
    indptr,
    indices,
    data,
    n,
    per_bin,
    d,
    ref_steps,
    stim,
    kicks,
    is_stim,
    silent,
    jump,
    em,
    es,
    gv,
    decay_th,
    v_rest,
    v_th,
    kick,
    trace_col,
    traced,
    v,
    g,
    th,
    ref_until,
    ring,
    ring_len,
    counts,
    first,
    c,
    touched,
    hit,
    spiking,
    g_idx,
    g_lo,
    g_span,
    g_scale,
    is_graded,
    g_ring,
    g_new,
    g_vsum,
    gap_nodes,
    gap_off,
    gap_mat,
    gap_moff,
    gap_buf,
):
    stim_steps = kicks.shape[0]
    rest64 = np.float64(v_rest)
    zero, one = np.float32(0.0), np.float32(1.0)
    for t in range(start_step, stop_step):
        # exact step of each electrically coupled component, from the state before 1
        for comp in range(gap_off.size - 1):
            a, m = gap_off[comp], gap_off[comp + 1] - gap_off[comp]
            for r in range(m):
                row = gap_moff[comp] + r * 2 * m
                acc = 0.0
                for q in range(m):
                    acc += gap_mat[row + q] * (np.float64(v[gap_nodes[a + q]]) - rest64)
                for q in range(m):
                    j = gap_nodes[a + q]
                    if ref_until[j] <= t:
                        acc += gap_mat[row + m + q] * np.float64(g[j])
                gap_buf[a + r] = np.float32(rest64 + acc)
        # 1. state update (refractory: v stays at v_rest, g frozen), branch-free so that
        # it vectorises; the refractory lanes compute and discard
        for i in range(n):
            frozen = ref_until[i] > t
            vi = (v[i] - v_rest) * em + g[i] * gv + v_rest
            gi = g[i] * es
            v[i] = v_rest if frozen else vi
            g[i] = g[i] if frozen else gi
            th[i] = th[i] * decay_th
        for k in range(gap_nodes.size):
            if ref_until[gap_nodes[k]] <= t:
                v[gap_nodes[k]] = gap_buf[k]
        # 2. threshold
        ns = 0
        for i in range(n):
            if v[i] > v_th + th[i] and not silent[i] and not is_graded[i]:
                spiking[ns] = i
                ns += 1
        for k in range(g_idx.size):
            i = g_idx[k]
            f = (v[i] - g_lo[k]) / g_span[k]
            f = max(zero, min(f, one))
            g_new[k] = zero if silent[i] else f * g_scale[k]
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
        nt = 0
        for k in range(g_idx.size):
            a = g_ring[slot, k]
            if a == zero:
                continue
            j = g_idx[k]
            for q in range(indptr[j], indptr[j + 1]):
                r = indices[q]
                c[r] += data[q] * a
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
            col = trace_col[i]
            if col >= 0:
                traced[t, col] = 1
        ring_len[slot] = ns
        for k in range(g_idx.size):
            g_ring[slot, k] = g_new[k]
            g_vsum[b, k] += v[g_idx[k]]
