"""The looming -> giant fiber timing lock (#34, G3): lock, geometry, readout and scoring."""

import copy
import hashlib
import math

import numpy as np
import pandas as pd
import pytest
from scipy import io

from flymsg import evidence, eye, gf_looming, sim
from flymsg.gf_looming import LoomingError

DOC = gf_looming.assert_matches_code()
P = sim.Params()


def test_the_lock_is_frozen_and_its_evidence_resolves():
    assert evidence.check_lock(DOC, evidence.load(), "gf_looming.yaml")
    with pytest.raises(LoomingError, match="does not match"):
        gf_looming.assert_locked({**DOC, "content_sha256": "0" * 64})
    assert len(gf_looming.cells(DOC)) == 15
    assert "15 gain cells" in gf_looming.summary(DOC)


@pytest.mark.parametrize("rv", [10.0, 80.0])
def test_the_disc_expands_from_10_to_63_degrees_and_holds(rv):
    s = gf_looming.expansion(rv, DOC, P.dt)
    t, theta = s["t"], np.degrees(s["theta"])
    on = np.flatnonzero(t >= s["onset"])[0]
    assert theta[on - 1] == 0.0 and theta[on] == pytest.approx(10.0, abs=0.01)
    after = t >= s["end"]
    assert theta[after] == pytest.approx(63.0, abs=1e-9)
    assert s["collision"] - s["end"] == pytest.approx(rv / math.tan(math.radians(31.5)))
    # theta is eye.looming_radius_deg doubled, and dtheta its derivative in rad/s
    mid = (t > s["onset"]) & (t < s["end"])
    expect = 2 * eye.looming_radius_deg(t[mid], s["collision"], rv)
    assert np.allclose(theta[mid], expect)
    slope = np.gradient(s["theta"], P.dt / 1000.0)
    inner = np.flatnonzero(mid)[5:-5]
    assert np.allclose(s["dtheta"][inner], slope[inner], rtol=1e-3)


def test_rates_stop_at_one_spike_per_refractory_period():
    s = gf_looming.expansion(10.0, DOC, P.dt)
    r4, r2 = gf_looming.rates(s, 1e6, 1e6, P)
    assert r4.max() == r2.max() == pytest.approx(1000.0 / P.t_ref)
    assert r4[s["t"] < s["onset"]].max() == 0.0


def toy():
    # LC4 (0) -> GF_R (2), LPLC2 (1) -> GF_L (3)
    edges = pd.DataFrame({"pre": [0, 1], "post": [2, 3], "weight": [60, 60]})
    W = sim.weight_matrix(edges, np.ones(4, dtype=np.int8), 4, P.w_syn)
    return W, np.array([0]), np.array([1]), np.array([2, 3])


def test_the_toy_giant_fiber_peaks_inside_the_window():
    W, lc4, lplc2, gf = toy()
    r = gf_looming.respond(W, lc4, lplc2, gf, 20.0, 10.0, 200.0, 7, DOC, P)
    s = gf_looming.expansion(20.0, DOC, P.dt)
    assert r["v"].shape[1] == 2
    assert r["depolarization_mv"] >= P.w_syn
    assert s["onset"] < r["peak_ms"] <= s["end"] + DOC["model"]["post_ms"] + P.dt
    assert r["before_collision_ms"] == pytest.approx(s["collision"] - r["peak_ms"])
    again = gf_looming.respond(W, lc4, lplc2, gf, 20.0, 10.0, 200.0, 7, DOC, P)
    assert np.array_equal(r["v"], again["v"])


def test_fit_recovers_the_threshold_model():
    rv = np.array([10.0, 20.0, 40.0, 80.0])
    alpha, delta = gf_looming.fit(rv, 3.0 * rv - 15.0)
    assert (alpha, delta) == pytest.approx((3.0, 15.0))
    assert gf_looming.threshold_deg(alpha) == pytest.approx(
        math.degrees(2 * math.atan(1 / 3))
    )


def test_the_peak_is_the_first_reach_of_its_maximum_and_edges_are_flagged():
    t = np.arange(10.0)
    window = t >= 2
    x = np.array([0, 0, 1, 9.6, 9.7, 10, 9.8, 2, 1, 0], float)
    assert gf_looming.peak_time(x, t, window, 0.0) == (3.0, 10.0, False)
    rising = np.arange(10.0)
    assert gf_looming.peak_time(rising, t, window, 0.0)[2] is True


def rows(alpha, respond=True, spiked=False):
    out = []
    for g4, g2 in gf_looming.cells(DOC):
        for seed in range(3):
            for rv in DOC["stimulus"]["rv_ms"]:
                out.append(
                    {
                        "g4": g4,
                        "g2": g2,
                        "seed": seed,
                        "rv_ms": rv,
                        "depolarization_mv": 1.0 if respond else 0.0,
                        "peak_ms": 0.0,
                        "before_collision_ms": alpha * rv - 10.0,
                        "spiked": spiked,
                        "edge": False,
                        "near_end": False,
                    }
                )
    return pd.DataFrame(out)


def test_the_no_go_needs_four_responding_graded_cells():
    fits = gf_looming.model_fits(rows(2.0), DOC)
    assert fits.scored.all() and fits.increasing.all()
    assert fits.alpha.to_numpy() == pytest.approx(2.0)
    assert gf_looming.no_go(fits, DOC)[0]
    assert not gf_looming.no_go(gf_looming.model_fits(rows(2.0, False), DOC), DOC)[0]
    spiking = gf_looming.model_fits(rows(2.0, spiked=True), DOC)
    assert spiking.responds.all() and not spiking.scored.any()
    assert not gf_looming.no_go(spiking, DOC)[0]


def write_fly(directory, fly, alpha, delta, rng):
    """Two trials whose peak sits alpha * rv - delta before the virtual collision."""
    i = DOC["inputs"]
    fs, n = i["sample_rate_hz"], round(i["sample_rate_hz"] * i["trace_s"])
    t = (np.arange(n) / fs - i["onset_s"]) * 1000.0
    names = []
    for trial in (1, 2):
        cols = []
        for rv in i["columns_rv_ms"]:
            s = gf_looming.expansion(rv, DOC, 1000.0 / fs)
            at = (s["collision"] - s["onset"]) - (alpha * rv - delta)
            cols.append(-70.0 + 6.0 * np.exp(-(((t - at) / 8.0) ** 2)))
        trace = np.stack(cols, axis=1) + rng.normal(0, 0.05, (n, 4))
        name = f"{fly}_trial0{trial}.mat"
        io.savemat(directory / name, {"data": trace})
        names.append(name)
    return names


def synthetic(tmp_path, alphas, delta=20.0):
    rng = np.random.default_rng(0)
    doc = copy.deepcopy(DOC)
    md5 = {}
    for k, a in enumerate(alphas):
        for name in write_fly(tmp_path, f"fly{k:02d}", a, delta, rng):
            md5[name] = hashlib.md5((tmp_path / name).read_bytes()).hexdigest()
    doc["inputs"]["control_md5"] = md5
    return doc


def test_the_data_rule_recovers_each_flys_slope(tmp_path):
    alphas = [2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4]
    doc = synthetic(tmp_path, alphas)
    flies = gf_looming.data_fits(tmp_path, doc)
    assert len(flies) == 10
    # the filter's lag grows with r/v and biases alpha a little; the model gets the same
    assert flies.alpha.to_numpy() == pytest.approx(alphas, abs=0.05)
    assert flies.delta_ms.to_numpy() == pytest.approx(20.0, abs=1.5)
    model = gf_looming.model_fits(rows(2.95), doc)
    assert gf_looming.judge(model, flies, doc)["verdict"] == "pass"
    none = gf_looming.model_fits(rows(2.95, spiked=True), doc)
    assert (
        gf_looming.judge(none, flies, doc)["verdict"] == "uninformative: no scored cell"
    )
    assert gf_looming.judge(gf_looming.model_fits(rows(5.0), doc), flies, doc)[
        "verdict"
    ] == ("fail")
    mixed = model.copy()
    mixed.loc[mixed.index[:3], "alpha"] = 5.0
    assert gf_looming.judge(mixed, flies, doc)["verdict"] == "partial"
    assert gf_looming.judge(model, flies.head(7), doc)["verdict"].startswith(
        "uninformative"
    )


def test_a_changed_or_odd_file_refuses_and_a_missing_one_drops_its_fly(tmp_path):
    doc = synthetic(tmp_path, [2.0, 2.0])
    (tmp_path / "fly00_trial01.mat").unlink()
    assert list(gf_looming.data_fits(tmp_path, doc).fly) == ["fly01"]
    io.savemat(tmp_path / "fly01_trial02.mat", {"data": np.zeros((10, 4))})
    with pytest.raises(LoomingError, match="locked md5"):
        gf_looming.data_fits(tmp_path, doc)
    with pytest.raises(LoomingError, match="trace array"):
        gf_looming.read_trace(tmp_path / "fly01_trial02.mat", doc)


def test_stimulus_followers_set_a_band_and_an_overlapping_interval_is_uninformative(
    tmp_path,
):
    locked = gf_looming.stimulus_locked(DOC)
    lo, hi = locked["band"]
    assert 1.6 < lo < hi < 2.1
    assert locked["onset"] == pytest.approx(1 / math.tan(math.radians(5)))
    mid = (lo + hi) / 2
    doc = synthetic(tmp_path, [mid - 0.1, mid - 0.05, mid, mid + 0.05, mid + 0.1] * 2)
    flies = gf_looming.data_fits(tmp_path, doc)
    verdict = gf_looming.judge(gf_looming.model_fits(rows(mid), doc), flies, doc)
    assert verdict["verdict"] == (
        "uninformative: the flies' slope does not separate the circuit from a "
        "stimulus-locked peak (followers)"
    )
