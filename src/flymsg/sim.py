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
from typing import NamedTuple

import numba
import numpy as np
import pandas as pd
from scipy import sparse

from flymsg import electrical

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
    top = np.finfo(np.float32).max
    if any(np.any(np.abs(x) > top) for x in (cols[0], cols[1], cols[2] * dt / 1000.0)):
        raise ValueError("graded parameters exceed float32")
    lo, span, scale = (
        cols[0][order].astype(np.float32),
        cols[1][order].astype(np.float32),
        (cols[2][order] * dt / 1000.0).astype(np.float32),
    )
    # the kernel computes in float32: check the values it will see
    if not (
        np.isfinite(lo).all() and np.isfinite(span).all() and np.isfinite(scale).all()
    ):
        raise ValueError("graded parameters exceed float32")
    if np.any(span <= 0) or np.any(scale < 0):
        raise ValueError("graded span must stay positive in float32")
    return idx[order], lo, span, scale, mask


@dataclass(frozen=True)
class Membrane:
    """Membrane and threshold parameters of neurons `idx`, replacing those of `Params` for
    them only: membrane and synaptic time constants (ms), rest (also the reset, mV) and
    threshold (mV). No value has a default, so a lock states each one and its source. The
    refractory period, delay and weights stay those of `Params`. Neurons not listed keep
    `Params`, so a network without `Membrane` runs exactly as before."""

    idx: np.ndarray
    tau_m: np.ndarray
    tau_syn: np.ndarray
    v_rest: np.ndarray
    v_th: np.ndarray


def membrane_arrays(membrane: Membrane | None, n: int, p: "Params") -> tuple:
    """Per-neuron float32 kernel arrays (em, es, gv, v_rest, v_th): membrane and synaptic
    decays and the synaptic gain over one step, rest and threshold. Each neuron's values are
    computed in float64 and rounded as `_constants` does, so a neuron that keeps `Params`
    gets exactly the scalar constants. Shared with `runtime.CpuRuntime`."""
    tau_m = np.full(n, p.tau_m)
    tau_syn = np.full(n, p.tau_syn)
    v_rest = np.full(n, p.v_rest)
    v_th = np.full(n, p.v_th)
    if membrane is not None:
        idx = np.asarray(membrane.idx)
        if idx.size and idx.dtype.kind not in "iu":
            raise ValueError("membrane indices must be integers")
        idx = idx.astype(np.int64).reshape(-1)
        if np.unique(idx).size != idx.size or np.any(idx < 0) or np.any(idx >= n):
            raise ValueError("membrane indices must be unique and inside the network")
        cols = [
            np.broadcast_to(np.asarray(x, dtype=np.float64), idx.shape)
            for x in (membrane.tau_m, membrane.tau_syn, membrane.v_rest, membrane.v_th)
        ]
        if not all(np.isfinite(c).all() for c in cols):
            raise ValueError("membrane parameters must be finite")
        if np.any(cols[0] <= 0) or np.any(cols[1] <= 0) or np.any(cols[0] == cols[1]):
            raise ValueError(
                "membrane time constants must be positive and tau_m != tau_syn"
            )
        if np.any(cols[3] <= cols[2]):
            raise ValueError("membrane threshold must lie above rest")
        tau_m[idx], tau_syn[idx], v_rest[idx], v_th[idx] = cols
    em, es = np.exp(-p.dt / tau_m), np.exp(-p.dt / tau_syn)
    gv = tau_syn / (tau_syn - tau_m) * (es - em)
    return tuple(x.astype(np.float32) for x in (em, es, gv, v_rest, v_th))


def kernel_constants(membrane: Membrane | None, n: int, p: "Params") -> tuple:
    """The constants `_advance` takes, in its order: per-neuron (em, es, gv), the scalar
    threshold decay, per-neuron rest and threshold, the scalar Poisson kick."""
    em, es, gv, v_rest, v_th = membrane_arrays(membrane, n, p)
    scalars = _constants(p)
    return em, es, gv, scalars[3], v_rest, v_th, scalars[6]


@dataclass(frozen=True)
class Gap:
    """Electrical synapses between neurons `i[k]` and `j[k]`. `coupling[k]` is the junction's
    conductance over i's leak conductance and `coupling_back[k]` over j's (default: the
    same, a symmetric junction); a coupling coefficient c measured from j to i gives
    c / (1 - c) for i. Coupled neurons follow tau_m dv_i/dt = v_rest - v_i + g_i +
    sum_j coupling_ij (v_j + s_j - v_i), linear between spikes, so each connected group is
    integrated exactly over a step by a precomputed matrix exponential (Van Loan's block
    form for the decaying synaptic input and for the spike term).

    s_j is the spike a LIF reset does not draw: if `spike_mv` and `spike_ms` are given, a
    spike of j adds a rectangular spike_mv[j] to the potential its partners see for the
    `spike_ms` after it (rounded to steps), so spikes cross the junction as spikelets.
    `spike_mv` is one value or one per neuron of the network (0: that neuron's spikes do not
    cross). Without them spikes do not cross. Junctions do not rectify.

    Refractory membranes are continuously clamped at rest, with chemical conductance
    frozen. Free partners retain the sink from contacts to those membranes; an explicit
    spike waveform is a separate prescribed input. Reduced step maps are exact for the
    current refractory mask and cached under a bounded memory budget. `solver="taylor"`
    applies the same exponential as a truncated Taylor series on the state, with as many
    terms as bound its remainder by the float64 unit roundoff (electrical.taylor_terms):
    no map per mask, and the same dynamics to rounding (#155)."""

    i: np.ndarray
    j: np.ndarray
    coupling: np.ndarray
    coupling_back: np.ndarray | None = None
    spike_mv: float | np.ndarray | None = None
    spike_ms: float | None = None
    refractory_mode: str = "continuous"
    solver: str = "dense"


def check_membrane_gap(membrane: Membrane | None, gap_nodes: np.ndarray) -> None:
    """Electrical coupling is integrated with the `Params` membrane: refuse a `Membrane` on a
    coupled neuron rather than integrate it with the wrong time constants or rest."""
    if (
        membrane is not None
        and np.intersect1d(np.asarray(membrane.idx, dtype=np.int64), gap_nodes).size
    ):
        raise ValueError(
            "a Membrane on an electrically coupled neuron is not supported"
        )


# largest coupled group: its dense step matrix is m x 3m float64 and its exponential needs a
# 3m x 3m block (4000 neurons: 1.2 GB for the block)
MAX_GAP_COMPONENT = 4000


def gap_arrays(gap: Gap | None, n: int, p: "Params") -> tuple:
    """Kernel arrays of `gap`: the coupled neurons grouped by connected component (indices,
    component offsets); per component of m neurons the m x 3m float64 step matrix
    [P | Q | S], row-major, with its offsets (the Taylor solver builds none; its offsets
    still count them), such that for free neurons
    v(t + dt) - v_rest = P (v - v_rest) + Q g + S s with s the spike term of each member;
    each neuron's position among the coupled ones (-1 if none); the spike term's length in
    steps (0 when no coupled spike crosses); and each coupled neuron's spike amplitude in
    mV."""
    from scipy.linalg import expm
    from scipy.sparse.csgraph import connected_components

    empty = (
        np.empty(0, dtype=np.int64),
        np.zeros(1, dtype=np.int64),
        np.empty(0, dtype=np.float64),
        np.zeros(1, dtype=np.int64),
        np.full(n, -1, dtype=np.int64),
        0,
        np.empty(0, dtype=np.float64),
    )
    if gap is None:
        return empty
    if gap.refractory_mode not in {"continuous", "boundary"}:
        raise ValueError("unknown electrical refractory mode")
    if gap.solver not in {"dense", "taylor"}:
        raise ValueError("unknown electrical solver")
    if gap.solver == "taylor" and gap.refractory_mode != "continuous":
        raise ValueError("the Taylor solver integrates the continuous clamp only")
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
    back = (
        c
        if gap.coupling_back is None
        else np.broadcast_to(np.asarray(gap.coupling_back, dtype=np.float64), i.shape)
    )
    if not (np.isfinite(c).all() and np.isfinite(back).all()):
        raise ValueError("gap couplings must be finite")
    if np.any(c < 0) or np.any(back < 0) or np.any((c > 0) != (back > 0)):
        raise ValueError(
            "gap couplings must be nonnegative and zero on both sides or none"
        )
    if (gap.spike_mv is None) != (gap.spike_ms is None):
        raise ValueError("spike transmission needs both spike_mv and spike_ms")
    width, amp_all = 0, np.zeros(n)
    if gap.spike_mv is not None:
        width = round(gap.spike_ms / p.dt)
        amp_all = np.broadcast_to(np.asarray(gap.spike_mv, dtype=np.float64), (n,))
        if not (np.isfinite(amp_all).all() and np.all(amp_all >= 0) and width >= 1):
            raise ValueError(
                "spike_mv must be finite and nonnegative, spike_ms at least one step"
            )
    keep = c > 0
    i, j, c, back = i[keep], j[keep], c[keep], back[keep]
    if i.size == 0:
        return empty
    K = sparse.coo_matrix(
        (np.r_[c, back], (np.r_[i, j], np.r_[j, i])), shape=(n, n)
    ).tocsr()
    nodes = np.unique(np.r_[i, j])
    _, label = connected_components(K[nodes][:, nodes], directed=False)
    order = np.lexsort((nodes, label))
    nodes, label = nodes[order], label[order]
    off = np.r_[0, np.cumsum(np.bincount(label))].astype(np.int64)
    if np.diff(off).max() > MAX_GAP_COMPONENT:
        raise ValueError(
            f"an electrically coupled group exceeds {MAX_GAP_COMPONENT} neurons"
        )
    mats, moff = [], [0]
    for a, b in pairwise(off):
        members = nodes[a:b]
        m = members.size
        moff.append(moff[-1] + 3 * m * m)
        if gap.solver == "taylor":
            continue  # the Taylor action reads the generators; no dense step matrix
        Kc = K[members][:, members].toarray()
        A = (Kc - np.diag(1.0 + Kc.sum(axis=1))) / p.tau_m
        block = np.zeros((3 * m, 3 * m))
        block[:m, :m] = A
        block[:m, m : 2 * m] = np.eye(m) / p.tau_m
        block[:m, 2 * m :] = Kc / p.tau_m  # constant spike term over the step
        block[m : 2 * m, m : 2 * m] = -np.eye(m) / p.tau_syn
        E = expm(block * p.dt)
        if not np.isfinite(E).all():
            raise ValueError("gap couplings give a nonfinite step matrix")
        mats.append(E[:m].ravel())
    pos = np.full(n, -1, dtype=np.int64)
    pos[nodes] = np.arange(nodes.size)
    return (
        nodes,
        off,
        np.concatenate(mats) if mats else np.empty(0, dtype=np.float64),
        np.asarray(moff, dtype=np.int64),
        pos,
        width if np.any(amp_all[nodes] > 0) else 0,
        np.ascontiguousarray(amp_all[nodes]),
    )


def network(
    neurons: pd.DataFrame, edges: pd.DataFrame, p: "Params"
) -> sparse.csc_matrix:
    """The weight matrix of a dataset at these parameters: the usual way to build one, from
    the neurons' `sign` column. `weight_matrix` stays for the variants that need another
    sign column or a scaled weight (see `compare`)."""
    return weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)


def weight_matrix(
    edges: pd.DataFrame,
    sign: np.ndarray,
    n: int,
    w_syn: float,
    post_scale: np.ndarray | None = None,
) -> sparse.csc_matrix:
    """Signed (post x pre) matrix; CSC so that columns of spiking neurons slice fast.

    `post_scale` (one value per neuron) multiplies every weight onto that neuron, so a lock
    can state a rule other than count x w_syn, such as synapse density (`density_scale`).
    Without it the weights are count x sign x w_syn, as always."""
    w = edges["weight"].to_numpy() * sign[edges["pre"].to_numpy()] * w_syn
    if post_scale is not None:
        scale = np.asarray(post_scale, dtype=np.float64).reshape(-1)
        if scale.shape != (n,) or not np.isfinite(scale).all() or np.any(scale <= 0):
            raise ValueError("post_scale needs one positive finite value per neuron")
        w = w * scale[edges["post"].to_numpy()]
    keep = w != 0
    return sparse.csc_matrix(
        (
            w[keep].astype(np.float32),
            (edges["post"].to_numpy()[keep], edges["pre"].to_numpy()[keep]),
        ),
        shape=(n, n),
    )


def density_scale(area_um2: np.ndarray, ref_um2: float) -> np.ndarray:
    """`post_scale` for weights proportional to synapse density on the postsynaptic neuron
    (count over its surface area, Liu et al. 2022): ref_um2 / area. The reference area is
    the one at which a synapse keeps the weight w_syn; a lock states it and its source."""
    area = np.asarray(area_um2, dtype=np.float64)
    if not (np.isfinite(area).all() and np.all(area > 0)) or not ref_um2 > 0:
        raise ValueError("areas and the reference area must be positive and finite")
    return ref_um2 / area


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
    membrane: Membrane | None = None,
) -> Result:
    """Simulate; stimulation lasts `stim_ms` (default: the whole run). Neurons in `silence`
    never fire, so they transmit nothing: for the rest of the network this equals zeroing
    their outgoing synapses, as Shiu et al. silence neurons.

    `kicks` replaces the seeded draw: shape (steps, n_stim), applied in order. `trace` records
    every spike step of those neurons, in the order given. The recording is written after the
    spike bookkeeping and does not enter the state update. `graded` makes those neurons
    non-spiking (see `Graded`); their mean potential per bin is returned in `graded_v`.
    `gap` adds electrical synapses (see `Gap`). `membrane` gives listed neurons their own
    membrane and threshold parameters (see `Membrane`).
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
    gap_nodes, gap_off, gap_mat, gap_moff, gap_pos, gap_width, gap_amp = gap_arrays(
        gap, n, p
    )
    gap_gen, gap_keys, gap_clock = electrical.generators(gap, gap_nodes, gap_off, p)
    check_membrane_gap(membrane, gap_nodes)
    constants = kernel_constants(membrane, n, p)
    indptr = W.indptr.astype(np.int64)
    indices = W.indices.astype(np.int64)
    data = W.data.astype(np.float32)
    prepared = prepare_kernel(
        constants[0],
        constants[1],
        constants[2],
        constants[4],
        constants[5],
        gap_nodes,
        gap_off,
        gap_moff,
        gap_gen,
        gap_clock,
        indptr,
        indices,
        data,
        g_idx,
    )
    counts, first, g_vsum = _kernel(
        indptr,
        indices,
        data,
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
        *constants,
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
        gap_pos,
        gap_width,
        gap_amp,
        gap_gen,
        gap_keys,
        gap_clock,
        *prepared,
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


class KernelPrep(NamedTuple):
    """What `_advance` takes after the gap mask.

    Built once from the kernel constants, the gap generators and the graded
    columns of `W`. Scratch is written before it is read on every step, so
    it has no state at a step boundary and is not part of a checkpoint. The
    graded slices are a packed copy of those CSC columns, not extra state.
    """

    special: np.ndarray
    is_special: np.ndarray
    n_special: int
    few: bool
    per_neuron: bool
    scalars: np.ndarray
    saved_v: np.ndarray
    saved_g: np.ndarray
    t_ptr: np.ndarray
    t_col: np.ndarray
    t_a: np.ndarray
    t_c: np.ndarray
    t_x: np.ndarray
    t_g: np.ndarray
    t_nx: np.ndarray
    t_ng: np.ndarray
    t_sum: np.ndarray
    t_free: np.ndarray
    g_ptr: np.ndarray
    g_post: np.ndarray
    g_w: np.ndarray


def _graded_edges(indptr, indices, data, g_idx):
    """Contiguous CSC columns of the graded sources, in `g_idx` order.

    Source `k` keeps `indices[indptr[j]:indptr[j + 1]]` and the matching
    weights, including explicit zeros and repeated targets. Delivery then adds
    the same products, to the same accumulators, in that order.
    """
    n_g = int(g_idx.size)
    g_ptr = np.zeros(n_g + 1, dtype=np.int64)
    if n_g:
        g_ptr[1:] = np.cumsum(indptr[g_idx + 1] - indptr[g_idx], dtype=np.int64)
    total = int(g_ptr[n_g])
    g_post = np.empty(total, dtype=np.int64)
    g_w = np.empty(total, dtype=np.float32)
    for k in range(n_g):
        j = int(g_idx[k])
        a, b = int(indptr[j]), int(indptr[j + 1])
        lo, hi = int(g_ptr[k]), int(g_ptr[k + 1])
        np.copyto(g_post[lo:hi], indices[a:b], casting="no")
        np.copyto(g_w[lo:hi], data[a:b], casting="no")
    return g_ptr, g_post, g_w


def prepare_kernel(
    em,
    es,
    gv,
    v_rest,
    v_th,
    gap_nodes,
    gap_off,
    gap_moff,
    gap_gen,
    gap_clock,
    indptr,
    indices,
    data,
    g_idx,
) -> KernelPrep:
    """Classify membranes, pack graded edges, and build the Taylor sparsity, once.

    Neuron 0 is the scalar class: a neuron is special when any of its five
    float32 constants differs from neuron 0's. Without a `Membrane` every
    neuron shares `Params`, so the hot loops read those scalars, as they did
    before per-neuron membranes. A minority keeps that loop and is recomputed
    with its own constants (the same operations, so the same values); most of
    the network reads every neuron's constants. The Taylor nonzeros are each
    component generator's rows, read from the dense generators once. Graded
    delivery walks every graded source whose delayed release is not exactly 0;
    those CSC columns are copied here so that walk reads contiguous memory.
    `run` and `CpuRuntime` both call this; `_advance` does not.
    """
    n = em.shape[0]
    special_buf = np.empty(n, dtype=np.int64)
    is_special = np.zeros(n, dtype=np.bool_)
    n_special = 0
    for i in range(n):
        if (
            em[i] != em[0]
            or es[i] != es[0]
            or gv[i] != gv[0]
            or v_rest[i] != v_rest[0]
            or v_th[i] != v_th[0]
        ):
            special_buf[n_special] = i
            is_special[i] = True
            n_special += 1
    few = 0 < 2 * n_special < n
    per_neuron = n_special > 0 and not few
    # copies of neuron 0, same float32 bits the scalar loops used to load
    scalars = np.empty(5, dtype=np.float32)
    scalars[0] = em[0]
    scalars[1] = es[0]
    scalars[2] = gv[0]
    scalars[3] = v_rest[0]
    scalars[4] = v_th[0]
    saved_v = np.empty(n_special, dtype=np.float32)
    saved_g = np.empty(n_special, dtype=np.float32)
    # Taylor solver: each component's generator [A | C] as rows of nonzeros
    # (A's pattern is C's plus the diagonal). The term count is the expression
    # `_advance` uses.
    terms = int(gap_clock[4]) if gap_clock.size > 4 else 0
    n_gap = gap_nodes.size
    t_ptr = np.zeros(n_gap + 1, dtype=np.int64)
    if terms > 0:
        for comp in range(gap_off.size - 1):
            a, m = gap_off[comp], gap_off[comp + 1] - gap_off[comp]
            start = gap_moff[comp] // 3 * 2
            for r in range(m):
                nnz = 0
                for q in range(m):
                    if gap_gen[start + r * 2 * m + q] != 0.0:
                        nnz += 1
                t_ptr[a + r + 1] = nnz
        for k in range(n_gap):
            t_ptr[k + 1] += t_ptr[k]
    t_col = np.empty(t_ptr[n_gap], dtype=np.int64)
    t_a = np.empty(t_ptr[n_gap], dtype=np.float64)
    t_c = np.empty(t_ptr[n_gap], dtype=np.float64)
    if terms > 0:
        for comp in range(gap_off.size - 1):
            a, m = gap_off[comp], gap_off[comp + 1] - gap_off[comp]
            start = gap_moff[comp] // 3 * 2
            for r in range(m):
                e = t_ptr[a + r]
                for q in range(m):
                    if gap_gen[start + r * 2 * m + q] != 0.0:
                        t_col[e] = q
                        t_a[e] = gap_gen[start + r * 2 * m + q]
                        t_c[e] = gap_gen[start + r * 2 * m + m + q]
                        e += 1
    return KernelPrep(
        special_buf[:n_special].copy(),
        is_special,
        n_special,
        few,
        per_neuron,
        scalars,
        saved_v,
        saved_g,
        t_ptr,
        t_col,
        t_a,
        t_c,
        np.zeros(n_gap, dtype=np.float64),
        np.zeros(n_gap, dtype=np.float64),
        np.zeros(n_gap, dtype=np.float64),
        np.zeros(n_gap, dtype=np.float64),
        np.zeros(n_gap, dtype=np.float64),
        np.zeros(n_gap, dtype=np.bool_),
        *_graded_edges(indptr, indices, data, g_idx),
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
    gap_pos,
    gap_width,
    gap_amp,
    gap_gen,
    gap_keys,
    gap_clock,
    special,
    is_special,
    n_special,
    few,
    per_neuron,
    scalars,
    saved_v,
    saved_g,
    t_ptr,
    t_col,
    t_a,
    t_c,
    t_x,
    t_g,
    t_nx,
    t_ng,
    t_sum,
    t_free,
    g_ptr,
    g_post,
    g_w,
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
    later at 3, after the spikes, summed per target in CSC column order from the graded
    edge slices packed once by prepare_kernel. Electrically coupled neurons replace the
    update of 1 by their component's exact step [P | Q | S] applied to the state before it
    (potentials relative to rest, conductances of non-refractory neurons, then the spike
    term of members whose spike is still crossing), summed in float64 in that order; a
    member's spike at 4 makes its spike term its `gap_amp` for the next `gap_width` steps."""
    v = v_rest.copy()
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
    gap_pulse = np.zeros(gap_nodes.size, dtype=np.int32)
    gap_current = gap_mat.copy()
    gap_mask = np.zeros(gap_nodes.size, dtype=np.bool_)
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
        gap_pos,
        gap_width,
        gap_amp,
        gap_pulse,
        gap_gen,
        gap_keys,
        gap_clock,
        gap_current,
        gap_mask,
        special,
        is_special,
        n_special,
        few,
        per_neuron,
        scalars,
        saved_v,
        saved_g,
        t_ptr,
        t_col,
        t_a,
        t_c,
        t_x,
        t_g,
        t_nx,
        t_ng,
        t_sum,
        t_free,
        g_ptr,
        g_post,
        g_w,
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
    gap_pos,
    gap_width,
    gap_amp,
    gap_pulse,
    gap_gen,
    gap_keys,
    gap_clock,
    gap_current,
    gap_mask,
    special,
    is_special,
    n_special,
    few,
    per_neuron,
    scalars,
    saved_v,
    saved_g,
    t_ptr,
    t_col,
    t_a,
    t_c,
    t_x,
    t_g,
    t_nx,
    t_ng,
    t_sum,
    t_free,
    g_ptr,
    g_post,
    g_w,
):
    stim_steps = kicks.shape[0]
    # Neuron 0's float32 constants, copied once by prepare_kernel.
    em0 = scalars[0]
    es0 = scalars[1]
    gv0 = scalars[2]
    rest0 = scalars[3]
    th0 = scalars[4]
    zero, one = np.float32(0.0), np.float32(1.0)
    # prepare_kernel counted Taylor terms with this same expression.
    terms = int(gap_clock[4]) if gap_clock.size > 4 else 0
    for t in range(start_step, stop_step):
        # The refractory mask is constant for the full neural step.
        for comp in range(gap_off.size - 1):
            a, m = gap_off[comp], gap_off[comp + 1] - gap_off[comp]
            frozen_mask = np.empty(m, dtype=np.bool_)
            any_frozen, changed = False, False
            for q in range(m):
                frozen_mask[q] = ref_until[gap_nodes[a + q]] > t
                any_frozen = any_frozen or frozen_mask[q]
                changed = changed or frozen_mask[q] != gap_mask[a + q]
            lo, hi = gap_moff[comp], gap_moff[comp + 1]
            if terms > 0:
                # exp(B dt) [x, g, s] summed term by term; refractory cells are clamped
                # (x = 0, no chemical drive, rows zero) and still sink their partners
                # through A's diagonal, and their spikelets cross through C
                tau_m, tau_syn, h = gap_clock[1], gap_clock[2], gap_clock[0]
                for q in range(m):
                    node = gap_nodes[a + q]
                    t_free[a + q] = ref_until[node] <= t
                    if t_free[a + q]:
                        t_x[a + q] = np.float64(v[node]) - np.float64(v_rest[node])
                        t_g[a + q] = np.float64(g[node])
                    else:
                        t_x[a + q] = 0.0
                        t_g[a + q] = 0.0
                    t_sum[a + q] = t_x[a + q]
                for k in range(1, terms + 1):
                    for r in range(m):
                        if not t_free[a + r]:
                            t_nx[a + r] = 0.0
                            t_ng[a + r] = 0.0
                            continue
                        acc = t_g[a + r] / tau_m
                        for e in range(t_ptr[a + r], t_ptr[a + r + 1]):
                            acc += t_a[e] * t_x[a + t_col[e]]
                            if k == 1 and gap_pulse[a + t_col[e]] > 0:
                                acc += t_c[e] / tau_m * gap_amp[a + t_col[e]]
                        t_nx[a + r] = acc * h / k
                        t_ng[a + r] = -t_g[a + r] / tau_syn * h / k
                    for r in range(m):
                        t_x[a + r] = t_nx[a + r]
                        t_g[a + r] = t_ng[a + r]
                        t_sum[a + r] += t_nx[a + r]
                for r in range(m):
                    gap_buf[a + r] = np.float32(
                        np.float64(v_rest[gap_nodes[a + r]]) + t_sum[a + r]
                    )
                gap_mask[a : a + m] = frozen_mask
                continue
            if changed and gap_clock[3] == 0:
                if any_frozen:
                    start = lo // 3 * 2
                    G = gap_gen[start : start + 2 * m * m].reshape(m, 2 * m)
                    digest = gap_keys[comp]
                    with numba.objmode(reduced="float64[:,:]"):
                        reduced = electrical.clamped_map(
                            G, frozen_mask, gap_clock, digest
                        )
                    gap_current[lo:hi] = reduced.ravel()
                else:
                    gap_current[lo:hi] = gap_mat[lo:hi]
                gap_mask[a : a + m] = frozen_mask
            M = gap_current[lo:hi].reshape(m, 3 * m)
            for r in range(m):
                acc = 0.0
                for q in range(m):
                    node = gap_nodes[a + q]
                    acc += M[r, q] * (np.float64(v[node]) - np.float64(v_rest[node]))
                for q in range(m):
                    if ref_until[gap_nodes[a + q]] <= t:
                        acc += M[r, m + q] * np.float64(g[gap_nodes[a + q]])
                for q in range(m):
                    if gap_pulse[a + q] > 0:
                        acc += M[r, 2 * m + q] * gap_amp[a + q]
                gap_buf[a + r] = np.float32(np.float64(v_rest[gap_nodes[a + r]]) + acc)
        for k in range(gap_pulse.size):
            if gap_pulse[k] > 0:
                gap_pulse[k] -= 1
        # 1. state update (refractory: v stays at v_rest, g frozen), branch-free so that
        # it vectorises; the refractory lanes compute and discard
        if per_neuron:
            for i in range(n):
                frozen = ref_until[i] > t
                vi = (v[i] - v_rest[i]) * em[i] + g[i] * gv[i] + v_rest[i]
                gi = g[i] * es[i]
                v[i] = v_rest[i] if frozen else vi
                g[i] = g[i] if frozen else gi
                th[i] = th[i] * decay_th
        else:
            for k in range(n_special if few else 0):
                saved_v[k] = v[special[k]]
                saved_g[k] = g[special[k]]
            for i in range(n):
                frozen = ref_until[i] > t
                vi = (v[i] - rest0) * em0 + g[i] * gv0 + rest0
                gi = g[i] * es0
                v[i] = rest0 if frozen else vi
                g[i] = g[i] if frozen else gi
                th[i] = th[i] * decay_th
            for k in range(n_special if few else 0):
                i = special[k]
                frozen = ref_until[i] > t
                vi = (saved_v[k] - v_rest[i]) * em[i] + saved_g[k] * gv[i] + v_rest[i]
                gi = saved_g[k] * es[i]
                v[i] = v_rest[i] if frozen else vi
                g[i] = saved_g[k] if frozen else gi
        for k in range(gap_nodes.size):
            if ref_until[gap_nodes[k]] <= t:
                v[gap_nodes[k]] = gap_buf[k]
        # 2. threshold
        ns = 0
        if per_neuron:
            for i in range(n):
                if v[i] > v_th[i] + th[i] and not silent[i] and not is_graded[i]:
                    spiking[ns] = i
                    ns += 1
        elif few:
            for i in range(n):
                th_i = v_th[i] if is_special[i] else th0
                if v[i] > th_i + th[i] and not silent[i] and not is_graded[i]:
                    spiking[ns] = i
                    ns += 1
        else:
            for i in range(n):
                if v[i] > th0 + th[i] and not silent[i] and not is_graded[i]:
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
        # g_post/g_w are those CSC columns in g_idx order. Exact 0 release stays
        # unapplied: decay of a negative g can underflow to -0, and g + 0 would
        # turn that into +0.
        nt = 0
        for k in range(g_idx.size):
            a = g_ring[slot, k]
            if a == zero:
                continue
            for q in range(g_ptr[k], g_ptr[k + 1]):
                r = g_post[q]
                c[r] += g_w[q] * a
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
            v[i] = v_rest[i]
            g[i] = 0.0
            th[i] = th[i] + jump[i]
            if not is_stim[i]:
                ref_until[i] = t + ref_steps
            counts[b, i] += 1
            if first[i] < 0:
                first[i] = t
            ring[slot, k] = i
            if gap_width > 0 and gap_pos[i] >= 0:
                gap_pulse[gap_pos[i]] = gap_width
            col = trace_col[i]
            if col >= 0:
                traced[t, col] = 1
        ring_len[slot] = ns
        for k in range(g_idx.size):
            g_ring[slot, k] = g_new[k]
            g_vsum[b, k] += v[g_idx[k]]
