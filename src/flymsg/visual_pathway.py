"""Graded visual pathway shared by the T4/T5 protocol and the closed loop.

`prepare` is the configuration-independent part of `t4t5.protocol`; `build` is one
configuration, including the dark anchor when the caller supplies `dark`. Neither
function simulates. `config_hash` names the dynamics those two produce.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize, sparse

from flymsg import eye, sim


class PathwayError(ValueError):
    """The visual pathway cannot be built."""


def steady_gain(p: sim.Params) -> float:
    """Steady-state potential change (mV) per unit of conductance delivered every step:
    g = c / (1 - es), v - v_rest = g * gv / (1 - em)."""
    em, es = np.exp(-p.dt / p.tau_m), np.exp(-p.dt / p.tau_syn)
    gv = p.tau_syn / (p.tau_syn - p.tau_m) * (es - em)
    return float(gv / ((1.0 - es) * (1.0 - em)))


def filter_peak_ms(tau_m: float, tau_syn: float) -> float:
    """Time to peak of the potential after one synaptic event (a difference of exponentials)."""
    return tau_m * tau_syn * np.log(tau_m / tau_syn) / (tau_m - tau_syn)


def delay_tau_syn(delay_ms: float, p: sim.Params) -> float:
    """The synaptic time constant that delays a neuron's filter peak by `delay_ms` over a
    neuron with the `Params` membrane, membrane time constant unchanged (version 4)."""
    target = filter_peak_ms(p.tau_m, p.tau_syn) + delay_ms
    return float(
        optimize.brentq(
            lambda ts: filter_peak_ms(p.tau_m, ts) - target,
            p.tau_m + 1e-3,
            10.0 * target,
        )
    )


def timing(types: np.ndarray, proto: dict, p: sim.Params) -> tuple[sim.Membrane, dict]:
    """Version 4: the slower cell of each measured pair gets the synaptic time constant of its
    delay; its incoming weights are scaled so its steady gain stays that of `Params`.
    Returns the membranes and, per type, (cells, tau_syn, weight scale)."""
    idx, tau_syn, per_type = [], [], {}
    for name, row in proto["timing"].items():
        cells = np.flatnonzero(types == name)
        ts = delay_tau_syn(row["delay_ms"], p)
        scale = steady_gain(p) / steady_gain(sim.Params(**{**vars(p), "tau_syn": ts}))
        per_type[name] = (cells, ts, scale)
        idx.append(cells)
        tau_syn.append(np.full(cells.size, ts))
    idx = np.concatenate(idx)
    return (
        sim.Membrane(
            idx=idx,
            tau_m=np.full(idx.size, p.tau_m),
            tau_syn=np.concatenate(tau_syn),
            v_rest=np.full(idx.size, p.v_rest),
            v_th=np.full(idx.size, p.v_th),
        ),
        per_type,
    )


def scale_block(
    W: sparse.csc_matrix, rows: np.ndarray, cols: np.ndarray | None, factor: float
) -> sparse.csc_matrix:
    """W with the synapses onto `rows` (from `cols`, or from every neuron) times `factor`."""
    W = W.tocsc(copy=True)
    pre = np.repeat(np.arange(W.shape[1]), np.diff(W.indptr))
    hit = np.isin(W.indices, rows)
    if cols is not None:
        hit &= np.isin(pre, cols)
    W.data[hit] = (W.data[hit] * factor).astype(W.data.dtype)
    return W


def photoreceptor_gain(response_mv: float, p: sim.Params) -> float:
    """Kicks per step at full light that hold a photoreceptor `response_mv` above rest."""
    return response_mv * (1.0 - np.exp(-p.dt / p.tau_m)) / (p.poisson_scale * p.w_syn)


def photoreceptor_rate(
    W: sparse.csc_matrix,
    lit: np.ndarray,
    lmc: np.ndarray,
    hyper_mv: float,
    p: sim.Params,
) -> tuple[float, np.ndarray]:
    """Saturated photoreceptor release rate (Hz) at which full light on `lit` lowers the
    median LMC receiving their synapses by `hyper_mv` at steady state, photoreceptor input
    only. Also returns those LMCs."""
    total = np.asarray(W[:, lit].sum(axis=1)).ravel()[lmc]
    receiving = lmc[total < 0]
    if receiving.size == 0:
        raise PathwayError("no LMC receives synapses from the lit photoreceptors")
    per_step = hyper_mv / (steady_gain(p) * float(np.median(-total[total < 0])))
    return per_step * 1000.0 / p.dt, receiving


def graded_spec(
    receptors_all: np.ndarray,
    lmc: np.ndarray,
    cfg: dict,
    rate_r: float,
    p: sim.Params,
    medulla_cells: dict | None = None,
    medulla_mv: dict | None = None,
    medulla_v_lo: dict | None = None,
) -> sim.Graded:
    """Photoreceptors: no release at rest, saturated `photoreceptor_mv` above. LMCs: half
    release at rest, none `lmc_mv` below, saturated `lmc_mv` above. Medulla types (version
    3): rest stands for the measured dark potential; no release at the lowest measured
    potential, saturated at the highest. Version 4 passes `medulla_v_lo`, each neuron's
    no-release potential anchored at its own settled potential in darkness."""
    a, h = cfg["photoreceptor_mv"], cfg["lmc_mv"]
    nr, nl = receptors_all.size, lmc.size
    idx = [receptors_all, lmc]
    v_lo = [np.full(nr, p.v_rest), np.full(nl, p.v_rest - h)]
    span = [np.full(nr, a), np.full(nl, 2.0 * h)]
    rate = [np.full(nr, rate_r), np.full(nl, cfg["lmc_rate_hz"])]
    for name, cells in (medulla_cells or {}).items():
        r = medulla_mv[name]
        idx.append(cells)
        if medulla_v_lo is not None:
            v_lo.append(medulla_v_lo[name])
        else:
            v_lo.append(np.full(cells.size, p.v_rest - (r["dark"] - r["lowest"])))
        span.append(np.full(cells.size, r["highest"] - r["lowest"]))
        rate.append(np.full(cells.size, cfg["medulla_rate_hz"]))
    return sim.Graded(
        idx=np.concatenate(idx),
        v_lo=np.concatenate(v_lo),
        span=np.concatenate(span),
        rate_hz=np.concatenate(rate),
    )


@dataclass(frozen=True)
class Static:
    """What `prepare` fixes before any configuration.

    `W` is the caller's matrix (the photoreceptor rate uses it). `W_timed` is `W`
    after the version-4 timing scale, or `W` itself when the protocol has no timing.
    `membrane` is None in that case.
    """

    types: np.ndarray
    receptors_all: np.ndarray
    lmc: np.ndarray
    medulla_cells: dict[str, np.ndarray]
    membrane: sim.Membrane | None
    W: sparse.csc_matrix
    W_timed: sparse.csc_matrix
    settle_steps: int


@dataclass(frozen=True)
class Pathway:
    """One configuration, as `sim.run` receives it.

    `W` includes the timing scale and, when the configuration sets one, the lamina to
    medulla gain. `anchor` is None without dark-anchor passes. `watch` indexes
    `receiving` in sorted `graded.idx` order; `watch_medulla` does the same per type.
    """

    W: sparse.csc_matrix
    membrane: sim.Membrane | None
    graded: sim.Graded
    gain: float
    rate_hz: float
    receiving: np.ndarray
    anchor: dict | None
    residual: dict
    watch: np.ndarray
    watch_medulla: dict[str, np.ndarray]


def prepare(
    W: sparse.csc_matrix, neurons: pd.DataFrame, proto: dict, p: sim.Params
) -> Static:
    """Receptors, LMCs, graded medulla, version-4 timing and the settle length."""
    types = neurons["type"].fillna("").to_numpy()
    pattern = "|".join(f"(?:{x})" for x in eye.RECEPTORS.values())
    receptors_all = np.flatnonzero(
        neurons["type"].fillna("").str.contains(pattern).to_numpy()
    )
    lmc = np.flatnonzero(np.isin(types, proto["graded_lmc"]))
    medulla_cells = {
        t: np.flatnonzero(types == t) for t in proto.get("graded_medulla", [])
    }
    membrane, W_timed = None, W
    if "timing" in proto:
        membrane, per_type = timing(types, proto, p)
        for cells, _ts, scale in per_type.values():
            W_timed = scale_block(W_timed, cells, None, scale)
    settle_steps = round(proto["settle_ms"] / p.dt)
    return Static(
        types=types,
        receptors_all=receptors_all,
        lmc=lmc,
        medulla_cells=medulla_cells,
        membrane=membrane,
        W=W,
        W_timed=W_timed,
        settle_steps=settle_steps,
    )


def build(
    static: Static,
    cfg: dict,
    proto: dict,
    lit: np.ndarray,
    p: sim.Params,
    dark: Callable[[sparse.csc_matrix, sim.Graded], np.ndarray],
) -> Pathway:
    """One configuration. `lit` is the caller's photoreceptors. `dark(W, graded)` returns
    each graded neuron's settled potential in darkness; this function does not simulate."""
    rate_r, receiving = photoreceptor_rate(static.W, lit, static.lmc, cfg["lmc_mv"], p)
    Wc = static.W_timed
    if "lamina_medulla_gain" in cfg:
        graded_cells = np.concatenate(list(static.medulla_cells.values()))
        Wc = scale_block(Wc, graded_cells, static.lmc, cfg["lamina_medulla_gain"])
    mv = proto.get("medulla_mv")
    graded = graded_spec(
        static.receptors_all, static.lmc, cfg, rate_r, p, static.medulla_cells, mv
    )
    order = np.sort(graded.idx)
    watch = np.searchsorted(order, receiving)
    watch_medulla = {
        t: np.searchsorted(order, c) for t, c in static.medulla_cells.items()
    }
    anchor, residual = None, {}
    if "dark_anchor_passes" in proto:
        # each neuron's measured range is anchored at its own settled potential in
        # darkness; a second pass settles with the anchored release
        previous = None
        for _ in range(proto["dark_anchor_passes"]):
            v_dark = dark(Wc, graded)
            anchor = {t: v_dark[i] for t, i in watch_medulla.items()}
            v_lo = {t: anchor[t] - (mv[t]["dark"] - mv[t]["lowest"]) for t in mv}
            graded = graded_spec(
                static.receptors_all,
                static.lmc,
                cfg,
                rate_r,
                p,
                static.medulla_cells,
                mv,
                v_lo,
            )
            if previous is not None:
                residual = {
                    t: float(np.median(np.abs(anchor[t] - previous[t]))) for t in mv
                }
            previous = anchor
    gain = photoreceptor_gain(cfg["photoreceptor_mv"], p)
    return Pathway(
        W=Wc,
        membrane=static.membrane,
        graded=graded,
        gain=gain,
        rate_hz=rate_r,
        receiving=receiving,
        anchor=anchor,
        residual=residual,
        watch=watch,
        watch_medulla=watch_medulla,
    )


def _feed(h, blob: bytes) -> None:
    h.update(np.uint64(len(blob)).tobytes())
    h.update(blob)


def _feed_array(h, a: np.ndarray) -> None:
    """dtype.str, shape (int64) and contiguous native-endian bytes."""
    a = np.ascontiguousarray(a)
    _feed(h, a.dtype.str.encode("ascii"))
    _feed(h, np.asarray(a.shape, dtype=np.int64).tobytes())
    _feed(h, a.tobytes())


def config_hash(static: Static, pathway: Pathway) -> str:
    """sha256 hex of the bytes that set this pathway's dynamics.

    Every piece is a native-endian uint64 length and then those bytes. Order:
    `W.shape` as int64; `W.data`, `W.indices`, `W.indptr`, each as `dtype.str`,
    int64 shape and contiguous native-endian bytes; membrane `idx`, `tau_m`,
    `tau_syn`, `v_rest`, `v_th` (empty int64, then four empty float64, when
    `membrane` is None); graded `idx`, `v_lo`, `span`, `rate_hz`; `gain` as
    float64; `settle_steps` as int64, taken from `static`.
    """
    h = hashlib.sha256()
    W = pathway.W.tocsc()
    _feed(h, np.asarray(W.shape, dtype=np.int64).tobytes())
    for part in (W.data, W.indices, W.indptr):
        _feed_array(h, part)
    membrane = pathway.membrane
    if membrane is None:
        parts = (
            np.empty(0, np.int64),
            np.empty(0, np.float64),
            np.empty(0, np.float64),
            np.empty(0, np.float64),
            np.empty(0, np.float64),
        )
    else:
        parts = (
            membrane.idx,
            membrane.tau_m,
            membrane.tau_syn,
            membrane.v_rest,
            membrane.v_th,
        )
    for part in parts:
        _feed_array(h, part)
    graded = pathway.graded
    for part in (graded.idx, graded.v_lo, graded.span, graded.rate_hz):
        _feed_array(h, part)
    _feed(h, np.float64(pathway.gain).tobytes())
    _feed(h, np.int64(static.settle_steps).tobytes())
    return h.hexdigest()
