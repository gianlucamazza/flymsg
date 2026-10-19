"""The visual pathway builder on a toy network; no connectome is loaded."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from flymsg import eye, sim, visual_pathway

TYPES = [
    "R1-R6",
    "R7",
    "R8",
    "L1",
    "L2",
    "L3",
    "Mi1",
    "Tm3",
    "Mi4",
    "Mi9",
    "C3",
    "Tm1",
    "Tm2",
    "T4a",
]
MEDULLA = ["Mi1", "Tm3", "Mi4", "Mi9", "C3"]
LIT = np.array([0, 1])


def _neurons() -> pd.DataFrame:
    return pd.DataFrame({"type": TYPES})


def _weights() -> sparse.csc_matrix:
    rows = [3, 4, 5, 6, 7, 11, 13]
    cols = [0, 0, 1, 3, 4, 5, 2]
    data = np.array([-2, -4, -6, 1.5, 2.5, 3.5, 8], dtype=np.float32)
    return sparse.csc_matrix((data, (rows, cols)), shape=(len(TYPES), len(TYPES)))


def _ranges() -> dict:
    return {
        name: {"lowest": -70.0 - i, "dark": -60.0 - i, "highest": -40.0 - i}
        for i, name in enumerate(MEDULLA)
    }


def _protocol(name: str) -> tuple[dict, dict]:
    proto = {"graded_lmc": ["L1", "L2", "L3"], "settle_ms": 200.0}
    cfg = {"photoreceptor_mv": 52.5, "lmc_mv": 32.5, "lmc_rate_hz": 100.0}
    if name == "v2":
        return proto, cfg
    proto["graded_medulla"] = list(MEDULLA)
    proto["medulla_mv"] = _ranges()
    cfg["medulla_rate_hz"] = 50.0
    if name == "v3":
        return proto, cfg
    proto["timing"] = {
        "Mi1": {"after": "Tm3", "delay_ms": 18.0},
        "Tm1": {"after": "Tm2", "delay_ms": 13.0},
    }
    proto["dark_anchor_passes"] = 6
    cfg["lamina_medulla_gain"] = 4.0
    return proto, cfg


def _dark(W, graded) -> np.ndarray:
    shift = np.float64(np.sum(np.asarray(graded.v_lo, dtype=np.float64)))
    return np.arange(graded.idx.size, dtype=np.float64) + np.float64(W.sum()) + shift


def _inline(W, neurons, proto, cfg, lit, p, dark):
    """The old `protocol` prefix and configuration prefix, in that order."""
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
        membrane, per_type = visual_pathway.timing(types, proto, p)
        for cells, _ts, scale in per_type.values():
            W_timed = visual_pathway.scale_block(W_timed, cells, None, scale)
    settle_steps = round(proto["settle_ms"] / p.dt)
    rate_r, receiving = visual_pathway.photoreceptor_rate(W, lit, lmc, cfg["lmc_mv"], p)
    Wc = W_timed
    if "lamina_medulla_gain" in cfg:
        graded_cells = np.concatenate(list(medulla_cells.values()))
        Wc = visual_pathway.scale_block(
            Wc, graded_cells, lmc, cfg["lamina_medulla_gain"]
        )
    mv = proto.get("medulla_mv")
    graded = visual_pathway.graded_spec(
        receptors_all, lmc, cfg, rate_r, p, medulla_cells, mv
    )
    order = np.sort(graded.idx)
    watch = np.searchsorted(order, receiving)
    watch_medulla = {t: np.searchsorted(order, c) for t, c in medulla_cells.items()}
    anchor, residual = None, {}
    if "dark_anchor_passes" in proto:
        previous = None
        for _ in range(proto["dark_anchor_passes"]):
            v_dark = dark(Wc, graded)
            anchor = {t: v_dark[i] for t, i in watch_medulla.items()}
            v_lo = {t: anchor[t] - (mv[t]["dark"] - mv[t]["lowest"]) for t in mv}
            graded = visual_pathway.graded_spec(
                receptors_all, lmc, cfg, rate_r, p, medulla_cells, mv, v_lo
            )
            if previous is not None:
                residual = {
                    t: float(np.median(np.abs(anchor[t] - previous[t]))) for t in mv
                }
            previous = anchor
    gain = visual_pathway.photoreceptor_gain(cfg["photoreceptor_mv"], p)
    return {
        "types": types,
        "receptors_all": receptors_all,
        "lmc": lmc,
        "medulla_cells": medulla_cells,
        "membrane": membrane,
        "W": W,
        "W_timed": W_timed,
        "settle_steps": settle_steps,
        "Wc": Wc,
        "graded": graded,
        "gain": gain,
        "rate_hz": rate_r,
        "receiving": receiving,
        "anchor": anchor,
        "residual": residual,
        "watch": watch,
        "watch_medulla": watch_medulla,
    }


def _same_array(a, b) -> None:
    a, b = np.asarray(a), np.asarray(b)
    assert np.array_equal(a, b)
    assert a.dtype == b.dtype


def _same_csc(a, b) -> None:
    assert a.shape == b.shape
    for name in ("data", "indices", "indptr"):
        _same_array(getattr(a, name), getattr(b, name))


def _same_membrane(a, b) -> None:
    assert (a is None) == (b is None)
    if a is None:
        return
    for name in ("idx", "tau_m", "tau_syn", "v_rest", "v_th"):
        _same_array(getattr(a, name), getattr(b, name))


def _same_graded(a, b) -> None:
    for name in ("idx", "v_lo", "span", "rate_hz"):
        _same_array(getattr(a, name), getattr(b, name))


def _same_columns(a: dict, b: dict) -> None:
    assert a.keys() == b.keys()
    for key, value in a.items():
        _same_array(value, b[key])


@pytest.mark.parametrize("name", ["v2", "v3", "v4"])
def test_build_matches_the_inline_block(name):
    W, neurons, lit = _weights(), _neurons(), LIT
    proto, cfg = _protocol(name)
    p = sim.Params()
    static = visual_pathway.prepare(W, neurons, proto, p)
    got = visual_pathway.build(static, cfg, proto, lit, p, _dark)
    exp = _inline(W, neurons, proto, cfg, lit, p, _dark)
    _same_array(static.types, exp["types"])
    _same_array(static.receptors_all, exp["receptors_all"])
    _same_array(static.lmc, exp["lmc"])
    _same_columns(static.medulla_cells, exp["medulla_cells"])
    _same_membrane(static.membrane, exp["membrane"])
    _same_csc(static.W, exp["W"])
    _same_csc(static.W_timed, exp["W_timed"])
    assert static.settle_steps == exp["settle_steps"]
    _same_csc(got.W, exp["Wc"])
    _same_membrane(got.membrane, exp["membrane"])
    _same_graded(got.graded, exp["graded"])
    _same_array(got.gain, exp["gain"])
    _same_array(got.rate_hz, exp["rate_hz"])
    _same_array(got.receiving, exp["receiving"])
    _same_array(got.watch, exp["watch"])
    _same_columns(got.watch_medulla, exp["watch_medulla"])
    assert got.residual == exp["residual"]
    if exp["anchor"] is None:
        assert got.anchor is None
    else:
        _same_columns(got.anchor, exp["anchor"])
    assert static.receptors_all.tolist() == [0, 1, 2]
    assert static.lmc.tolist() == [3, 4, 5]
    if name == "v2":
        assert static.membrane is None and got.anchor is None
        assert static.medulla_cells == {}
        assert got.graded.idx.tolist() == [0, 1, 2, 3, 4, 5]
    elif name == "v3":
        assert static.membrane is None and got.anchor is None
        assert got.graded.idx.tolist() == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    else:
        assert static.membrane.idx.tolist() == [6, 11]
        assert set(got.anchor) == set(MEDULLA)
        assert set(got.residual) == set(MEDULLA)


def _bump(a: np.ndarray) -> np.ndarray:
    out = np.array(a, copy=True)
    out.flat[0] = out.flat[0] + 1
    return out


def _graded_like(graded: sim.Graded, **kwargs) -> sim.Graded:
    fields = {
        name: kwargs.get(name, getattr(graded, name))
        for name in ("idx", "v_lo", "span", "rate_hz")
    }
    return sim.Graded(**fields)


def test_config_hash_is_stable_and_tracks_each_input():
    W, neurons = _weights(), _neurons()
    proto, cfg = _protocol("v4")
    p = sim.Params()
    static = visual_pathway.prepare(W, neurons, proto, p)
    pathway = visual_pathway.build(static, cfg, proto, LIT, p, _dark)
    base = visual_pathway.config_hash(static, pathway)
    assert base == visual_pathway.config_hash(static, pathway)
    assert len(base) == 64

    changed = pathway.W.tocsc(copy=True)
    changed.data[0] = changed.data[0] + 1
    assert visual_pathway.config_hash(static, replace(pathway, W=changed)) != base
    changed = pathway.W.tocsc(copy=True)
    changed.indices[0] = changed.indices[0] + 1
    assert visual_pathway.config_hash(static, replace(pathway, W=changed)) != base
    changed = pathway.W.tocsc(copy=True)
    changed.indptr[1] -= 1
    assert visual_pathway.config_hash(static, replace(pathway, W=changed)) != base
    changed = sparse.csc_matrix(
        (pathway.W.data.copy(), pathway.W.indices.copy(), pathway.W.indptr.copy()),
        shape=(pathway.W.shape[0] + 1, pathway.W.shape[1]),
    )
    assert visual_pathway.config_hash(static, replace(pathway, W=changed)) != base
    changed = pathway.W.tocsc(copy=True)
    changed.data = changed.data.astype(np.float64)
    assert visual_pathway.config_hash(static, replace(pathway, W=changed)) != base

    for name in ("idx", "tau_m", "tau_syn", "v_rest", "v_th"):
        fields = {
            field: _bump(getattr(pathway.membrane, field))
            if field == name
            else getattr(pathway.membrane, field)
            for field in ("idx", "tau_m", "tau_syn", "v_rest", "v_th")
        }
        bumped = replace(pathway, membrane=sim.Membrane(**fields))
        assert visual_pathway.config_hash(static, bumped) != base
    assert visual_pathway.config_hash(static, replace(pathway, membrane=None)) != base

    for name in ("idx", "v_lo", "span", "rate_hz"):
        graded = _graded_like(
            pathway.graded, **{name: _bump(getattr(pathway.graded, name))}
        )
        bumped = replace(pathway, graded=graded)
        assert visual_pathway.config_hash(static, bumped) != base
    same_bytes = pathway.graded.idx.astype(np.uint64)
    assert same_bytes.tobytes() == np.ascontiguousarray(pathway.graded.idx).tobytes()
    bumped = replace(pathway, graded=_graded_like(pathway.graded, idx=same_bytes))
    assert visual_pathway.config_hash(static, bumped) != base

    gained = replace(pathway, gain=pathway.gain + 1)
    assert visual_pathway.config_hash(static, gained) != base
    stepped = replace(static, settle_steps=static.settle_steps + 1)
    assert visual_pathway.config_hash(stepped, pathway) != base
    for name, value in vars(p).items():
        params = sim.Params(**{**vars(p), name: value + 1})
        assert (
            visual_pathway.config_hash(static, replace(pathway, params=params)) != base
        )
    lit = np.append(pathway.lit, pathway.lit[-1] + 1)
    assert visual_pathway.config_hash(static, replace(pathway, lit=lit)) != base
    passes = replace(pathway, dark_passes=pathway.dark_passes + 1)
    assert visual_pathway.config_hash(static, passes) != base
    untouched = replace(pathway, anchor=None, residual={})
    assert visual_pathway.config_hash(static, untouched) == base
    assert visual_pathway.config_hash(static, pathway) == base


def test_photoreceptor_rate_rejects_a_missing_lmc_target():
    W = sparse.csc_matrix((4, 4), dtype=np.float32)
    with pytest.raises(visual_pathway.PathwayError, match="no LMC receives"):
        visual_pathway.photoreceptor_rate(
            W, np.array([0]), np.array([1, 2]), 20.0, sim.Params()
        )
    assert issubclass(visual_pathway.PathwayError, ValueError)


def test_a_supplied_rate_replaces_photoreceptor_rate():
    W, neurons, lit = _weights(), _neurons(), LIT
    proto, cfg = _protocol("v4")
    p = sim.Params()
    static = visual_pathway.prepare(W, neurons, proto, p)
    default = visual_pathway.build(static, cfg, proto, lit, p, _dark)
    same = visual_pathway.build(
        static,
        cfg,
        proto,
        lit,
        p,
        _dark,
        rate=(default.rate_hz, default.receiving),
    )
    _same_graded(same.graded, default.graded)
    _same_array(same.receiving, default.receiving)
    assert same.gain == default.gain
    assert same.residual == default.residual
    _same_columns(same.anchor, default.anchor)
    assert visual_pathway.config_hash(static, same) == visual_pathway.config_hash(
        static, default
    )

    doubled = default.rate_hz * 2
    other = visual_pathway.build(
        static, cfg, proto, lit, p, _dark, rate=(doubled, default.receiving)
    )
    n = static.receptors_all.size
    _same_array(other.graded.rate_hz[:n], np.full(n, doubled))
    _same_array(other.graded.rate_hz[n:], default.graded.rate_hz[n:])
    _same_array(other.receiving, default.receiving)
    assert other.gain == default.gain
    _same_columns(other.anchor, default.anchor)
    assert visual_pathway.config_hash(static, other) != visual_pathway.config_hash(
        static, default
    )

    bare = sparse.csc_matrix(W.shape, dtype=np.float32)
    bare_static = visual_pathway.prepare(bare, neurons, proto, p)
    with pytest.raises(visual_pathway.PathwayError, match="no LMC receives"):
        visual_pathway.build(bare_static, cfg, proto, lit, p, _dark)
    supplied = visual_pathway.build(
        bare_static,
        cfg,
        proto,
        lit,
        p,
        _dark,
        rate=(default.rate_hz, default.receiving),
    )
    assert supplied.rate_hz == default.rate_hz
    _same_array(supplied.receiving, default.receiving)
    assert supplied.gain == default.gain
    with pytest.raises(visual_pathway.PathwayError, match="finite"):
        visual_pathway.build(
            static,
            cfg,
            proto,
            lit,
            p,
            _dark,
            rate=(float("nan"), default.receiving),
        )
