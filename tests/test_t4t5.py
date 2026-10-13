"""The T4/T5 test is locked before any run; no data are loaded."""

import numpy as np
import pandas as pd
import pytest

from flymsg import cli, t4t5


def test_locked_to_the_sourced_values():
    doc = t4t5.assert_matches_code()
    assert doc["version"] == 3
    assert t4t5.content_hash(doc) == t4t5.VERSION_HASHES[3]
    assert doc["protocol"]["acceptance_deg"] == 8.23
    assert doc["protocol"]["preferred"] == {
        "a": "front_to_back",
        "b": "back_to_front",
        "c": "upward",
        "d": "downward",
    }
    assert doc["supersedes"]["verdict"] == "robust: neither"
    assert doc["protocol"]["graded_medulla"] == ["Mi1", "Tm3", "Mi4", "Mi9", "C3"]
    assert t4t5.n_runs(doc) == 200


def test_version_3_scans_both_unmeasured_rates_at_the_middle_ranges():
    grid = t4t5.configurations(t4t5.load())
    assert len(grid) == 25
    assert {(c["photoreceptor_mv"], c["lmc_mv"]) for c in grid} == {(52.5, 32.5)}
    assert {(c["lmc_rate_hz"], c["medulla_rate_hz"]) for c in grid} == {
        (r, m) for r in t4t5.LMC_RATE_HZ for m in t4t5.MEDULLA_RATE_HZ
    }


def test_the_version_2_envelope_has_17_configurations():
    doc = t4t5.load()
    doc["protocol"] = {
        k: v
        for k, v in doc["protocol"].items()
        if k not in ("graded_medulla", "medulla_mv")
    }
    grid = t4t5.configurations(doc)
    assert len(grid) == 17
    assert {c["lmc_mv"] for c in grid} == set(t4t5.LMC_MV)
    assert {c["photoreceptor_mv"] for c in grid} == set(t4t5.PHOTORECEPTOR_MV)
    assert {c["lmc_rate_hz"] for c in grid} == set(t4t5.LMC_RATE_HZ)
    assert len({tuple(c.values())[1:] for c in grid}) == 17


def test_an_envelope_outside_the_sources_is_refused():
    doc = t4t5.load()
    doc["protocol"]["envelope"]["lmc_hyperpolarisation_mv"] = [10.0, 32.5, 45.0]
    with pytest.raises(t4t5.T4T5Error, match="sourced"):
        t4t5.assert_matches_code(doc)
    doc = t4t5.load()
    for seed in (91, 93):
        doc["protocol"]["seed"] = seed
        with pytest.raises(t4t5.T4T5Error, match="spent"):
            t4t5.assert_matches_code(doc)


def test_medulla_ranges_must_be_the_measured_types_and_contain_the_dark_level():
    doc = t4t5.load()
    doc["protocol"]["medulla_mv"]["Mi1"]["dark"] = -70.0
    with pytest.raises(t4t5.T4T5Error, match="outside"):
        t4t5.assert_matches_code(doc)
    doc = t4t5.load()
    doc["protocol"]["graded_medulla"] = ["Mi1", "Tm3"]
    with pytest.raises(t4t5.T4T5Error, match="measured"):
        t4t5.assert_matches_code(doc)
    doc = t4t5.load()
    doc["decides"]["subtypes"] = ["T4a", "T5a"]
    with pytest.raises(t4t5.T4T5Error, match="T4 subtypes"):
        t4t5.assert_matches_code(doc)


def test_medulla_curve_anchors_the_dark_potential_at_rest():
    from flymsg import sim

    p = sim.Params()
    doc = t4t5.load()
    mv = doc["protocol"]["medulla_mv"]
    cfg = {
        "photoreceptor_mv": 52.5,
        "lmc_mv": 32.5,
        "lmc_rate_hz": 100.0,
        "medulla_rate_hz": 50.0,
    }
    g = t4t5.graded_spec(
        np.array([0]), np.array([1]), cfg, 900.0, p, {"Mi9": np.array([2, 3])}, mv
    )
    assert g.idx.tolist() == [0, 1, 2, 3]
    assert g.v_lo[2:] == pytest.approx(p.v_rest - (-58.0 - -62.5))
    assert g.span[2:] == pytest.approx(-50.4 - -62.5)
    assert g.rate_hz.tolist() == [900.0, 100.0, 50.0, 50.0]
    # in darkness Mi9 releases the measured share of its range below the dark level
    share = (p.v_rest - g.v_lo[2]) / g.span[2]
    assert share == pytest.approx(4.5 / 12.1)


def test_photoreceptor_gain_holds_the_response_at_steady_state():
    # one isolated graded photoreceptor under full light settles response_mv above rest
    from scipy import sparse

    from flymsg import sim

    p = sim.Params()
    W = sparse.csc_matrix((2, 2), dtype=np.float32)
    gain = t4t5.photoreceptor_gain(52.5, p)
    g = sim.Graded(idx=np.array([0]), v_lo=p.v_rest, span=52.5, rate_hz=100.0)
    r = sim.run(
        W, np.array([0]), duration_ms=300, p=p, kicks=np.full((3000, 1), gain), graded=g
    )
    assert r.graded_v[-1, 0] - p.v_rest == pytest.approx(52.5, rel=1e-3)


def test_photoreceptor_rate_hyperpolarizes_the_median_lmc_by_the_target():
    # three saturated photoreceptors (0-2) inhibit LMCs 3 and 4; the median LMC must settle
    # hyper_mv below rest
    import pandas as pd

    from flymsg import sim

    p = sim.Params()
    edges = pd.DataFrame(
        {
            "pre": [0, 1, 2, 0, 1],
            "post": [3, 3, 3, 4, 4],
            "weight": [30, 30, 30, 50, 50],
        }
    )
    sign = np.array([-1, -1, -1, 1, 1], dtype=np.int8)
    W = sim.weight_matrix(edges, sign, 5, p.w_syn)
    rate, receiving = t4t5.photoreceptor_rate(
        W, np.arange(3), np.array([3, 4]), 20.0, p
    )
    assert receiving.tolist() == [3, 4]
    g = sim.Graded(
        idx=np.arange(5),
        v_lo=np.r_[[p.v_rest - 1e3] * 3, [p.v_rest] * 2],
        span=1.0,
        rate_hz=np.r_[[rate] * 3, [0.0] * 2],
    )
    r = sim.run(W, np.array([0]), 0.0, 400, p=p, graded=g)
    settled = r.graded_v[-1, 3:] - p.v_rest
    assert np.median(settled) == pytest.approx(-20.0, rel=1e-3)


def test_envelope_verdict():
    import pandas as pd

    assert t4t5.envelope_verdict(pd.Series(["neither"] * 17)) == "robust: neither"
    mixed = t4t5.envelope_verdict(pd.Series(["neither"] * 12 + ["polarity only"] * 5))
    assert mixed == "depends: neither 12, polarity only 5"


def test_an_unsourced_acceptance_is_refused():
    doc = t4t5.load()
    doc["protocol"]["acceptance_deg"] = 5.0
    with pytest.raises(t4t5.T4T5Error, match="sourced"):
        t4t5.assert_matches_code(doc)


def test_prints_the_protocol_without_data(monkeypatch, capsys, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    monkeypatch.setattr("sys.argv", ["flymsg", "--data", str(tmp_path), "t4t5"])
    cli.main()
    out = capsys.readouterr().out
    assert "ON/OFF edges, 4 directions" in out
    assert "graded Mi1/Tm3/Mi4/Mi9/C3" in out and "decides on T4a/T4b/T4c/T4d" in out


def test_vector_sum_and_angle_error():
    front = t4t5.preferred_angle({"front_to_back": 10, "back_to_front": 2})
    assert t4t5.angle_error(front, 0.0) == pytest.approx(0.0, abs=1e-9)
    assert t4t5.preferred_angle({"upward": 5, "downward": 1}) == pytest.approx(90.0)
    assert t4t5.angle_error(350.0, 10.0) == 20.0


def test_off_edges_darken_and_on_edges_light_what_they_crossed():
    cov = np.array([0.0, 0.5, 1.0])
    assert t4t5.light(cov, "off").tolist() == [1.0, 0.5, 0.0]
    assert t4t5.light(cov, "on").tolist() == [0.0, 0.5, 1.0]


def _table(t4_pd, t5_pd):
    rows = []
    for sub in ["T4a", "T4b", "T4c", "T4d", "T5a", "T5b", "T5c", "T5d"]:
        pref = "on" if sub.startswith("T4") else "off"
        good = t4_pd if sub.startswith("T4") else t5_pd
        target = {
            "a": "front_to_back",
            "b": "back_to_front",
            "c": "upward",
            "d": "downward",
        }[sub[-1]]
        for direction in t4t5.ANGLE:
            for pol in ("on", "off"):
                spikes = 1
                if pol == pref:
                    spikes = 10 if (direction == target and good) else 3
                rows.append(
                    {
                        "subtype": sub,
                        "direction": direction,
                        "polarity": pol,
                        "seed": 0,
                        "spikes": spikes,
                    }
                )
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("t4", "t5", "expected"), [(True, True, "both"), (False, False, "polarity only")]
)
def test_decide(t4, t5, expected):
    doc = t4t5.load()
    out = t4t5.decide(_table(t4, t5), doc["protocol"]["preferred"])
    assert out["verdict"] == expected
    assert out["metrics"]["polarity_ok"].all()


def test_decide_on_t4_only():
    doc = t4t5.load()
    out = t4t5.decide(
        _table(True, False),
        doc["protocol"]["preferred"],
        ["T4a", "T4b", "T4c", "T4d"],
        3,
    )
    assert out["verdict"] == "both"
    assert out["metrics"]["subtype"].tolist() == ["T4a", "T4b", "T4c", "T4d"]


def test_medulla_ranges_of_a_trace():
    from flymsg import medulla

    traces = np.full((2, 2, 8000), -60.0)
    traces[0, :, :1000] = [[-66.0], [-64.0]]
    traces[0, 0, 4000] = -40.0
    traces[1, 1, 5000] = -80.0
    got = medulla.ranges_of(traces)
    assert got == {"n": 2, "dark_mv": -65.0, "lowest_mv": -70.0, "highest_mv": -50.0}


def test_a_file_that_is_not_the_deposited_one_is_removed(monkeypatch, tmp_path):
    from flymsg import medulla

    monkeypatch.setattr(medulla, "FILES", {"Mi1": (1, "0" * 64)})
    bad = medulla.raw_dir(tmp_path) / "fig3_Mi1.npy"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"truncated")
    with pytest.raises(ValueError, match="sha256"):
        medulla.fetch(tmp_path)
    assert not bad.exists()
