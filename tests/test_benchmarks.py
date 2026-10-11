"""The held-out manifest matches criterion v4 and rejects a silent edit."""

import numpy as np
import pandas as pd

from flymsg import benchmarks, cli, sim, validate


def test_manifest_is_locked_to_the_live_battery():
    doc = benchmarks.assert_matches_code()
    assert doc["version"] == 1
    assert benchmarks.content_hash(doc) == benchmarks.VERSION_HASHES[1]
    case = doc["confirmatory"]
    assert case["stimulus"] == "ORN_DM1"
    assert case["target"] == "DM1_lPN"
    assert case["decides"] is True
    assert doc["reported"]["decides"] is False
    assert doc["endpoints"]["checks"] == ["positive", "specific", "stability"]
    assert "biological_hz" in doc["endpoints"]["not_scored"]
    assert doc["sensitivity"]["scored"]["w_syn"] == sim.Params.w_syn
    assert [c.name for c in validate.CASES] == doc["partition"]["calibration"][:-1]


def test_a_held_out_edit_without_a_version_bump_fails():
    doc = benchmarks.load()
    doc["confirmatory"]["target"] = "MN9"
    doc["content_sha256"] = benchmarks.content_hash(doc)
    try:
        benchmarks.assert_locked(doc)
        raise AssertionError("expected a lock failure")
    except benchmarks.BenchmarkError as err:
        assert "without a bump" in str(err)


def test_benchmarks_prints_the_manifest_and_does_not_need_data(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["flymsg", "--data", str(tmp_path), "benchmarks"])
    cli.main()
    out = capsys.readouterr().out
    assert "ORN_DM1 -> DM1_lPN" in out
    assert "confirmatory FAIL" in out


def test_benchmarks_run_needs_the_dataset(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["flymsg", "--data", str(tmp_path), "benchmarks", "--run"]
    )
    try:
        cli.main()
    except SystemExit as err:
        assert "fetch" in str(err)
    else:
        raise AssertionError("expected a missing-data exit")


def _held_out_neurons() -> pd.DataFrame:
    rows = []
    for type_, n in (
        ("ORN_DM1", 74),
        ("DM1_lPN", 2),
        ("ORN_V", 55),
        ("V_ilPN", 2),
        ("V_l2PN", 2),
        ("ORN_XX", 80),
    ):
        for _ in range(n):
            rows.append(type_)
    frame = pd.DataFrame({"type": rows})
    frame["instance"] = None
    frame["bodyId"] = np.arange(len(frame))
    frame["class"] = "olfactory"
    frame["superclass"] = np.where(
        frame["type"].str.startswith("ORN"), "cb_sensory", "cb_intrinsic"
    )
    frame["sign"] = 1
    return frame


def test_score_applies_v4_and_leaves_the_battery_alone(monkeypatch):
    neurons = _held_out_neurons()
    edges = pd.DataFrame(
        {
            "pre": np.array([], dtype=int),
            "post": np.array([], dtype=int),
            "weight": np.array([], dtype=float),
        }
    )
    calls = []

    def fake_network(*_args, **_kwargs):
        return None

    def fake_respond(
        W,
        neurons,
        stim,
        targets,
        p,
        seeds,
        rate_hz=validate.RATE_HZ,
        silence=None,
        seed0=0,
        duration_ms=validate.DURATION_MS,
    ):
        calls.append((rate_hz, seeds, seed0, duration_ms, tuple(targets)))
        out = {
            t: {
                "rate": 30.0,
                "reliable": 3,
                "latencies": np.array([10.0, 11.0, 12.0]),
                "seed_rates": np.array([30.0, 30.0, 30.0]),
                "latency": 11.0,
            }
            for t in targets
        }
        return out, 0.0

    monkeypatch.setattr(sim, "network", fake_network)
    monkeypatch.setattr(validate, "respond", fake_respond)
    before = [case.name for case in validate.CASES]
    report = benchmarks.score(neurons, edges)
    assert [case.name for case in validate.CASES] == before
    assert set(report["kind"]) == {"positive", "specific", "stability"}
    deciding = report[report["decides"]]
    assert set(deciding["case"]) == {"ORN_DM1 to DM1_lPN"}
    assert bool(deciding.loc[deciding["kind"] == "positive", "passed"].all())
    assert not bool(deciding.loc[deciding["kind"] == "specific", "passed"].all())
    assert benchmarks.verdict(report).endswith("FAIL")
    assert calls and {c[0] for c in calls} == {validate.RATE_HZ}
    assert {c[1] for c in calls} == {3}
    try:
        benchmarks.score(neurons, edges, sim.Params(w_syn=0.275))
    except benchmarks.BenchmarkError as err:
        assert "scored corner" in str(err)
    else:
        raise AssertionError("expected the scored corner to be required")
