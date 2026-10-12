"""The residual TTMn_R scan is locked before any run. These tests never load the connectome."""

import math

import numpy as np
import pandas as pd
import pytest

from flymsg import cli, silence_scan


def test_scan_is_locked_to_the_behavior_silence_arm():
    doc = silence_scan.assert_matches_code()
    assert doc["version"] == 1
    assert silence_scan.content_hash(doc) == silence_scan.VERSION_HASHES[1]
    assert doc["issue"] == 20
    assert doc["blind"]["ranking_used"] is False
    assert doc["protocol"]["motor"] == "TTMn_R"
    assert doc["protocol"]["base_silence"] == "DNp01"
    assert doc["screen"]["decides"] is False
    assert doc["confirm"]["seed0"] == 10


def test_an_edit_without_a_version_bump_fails():
    doc = silence_scan.load()
    doc["screen"]["pass_fraction_of_base"] = 0.8
    doc["content_sha256"] = silence_scan.content_hash(doc)
    with pytest.raises(silence_scan.ScanError, match="without a bump"):
        silence_scan.assert_locked(doc)


def test_overlapping_seeds_are_refused():
    doc = silence_scan.load()
    doc["confirm"]["seed0"] = 2
    with pytest.raises(silence_scan.ScanError, match="fresh"):
        silence_scan.assert_matches_code(doc)


def test_scan_prints_the_protocol_and_does_not_load_data(monkeypatch, capsys, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    monkeypatch.setattr("sys.argv", ["flymsg", "--data", str(tmp_path), "silence-scan"])
    cli.main()
    out = capsys.readouterr().out
    assert "LC4_R -> TTMn_R with DNp01 silenced" in out
    assert "not run" in out


def _graph():
    # 0 stim, 1 motor, 2 command; 3-4 type A; 5 type B; 6 untyped; 7 type C (silent);
    # 8 type D (weak); 9 type A outside the motor's inputs
    neurons = pd.DataFrame(
        {
            "bodyId": np.arange(100, 110),
            "type": ["S", "M", "G", "A", "A", "B", None, "C", "D", "A"],
            "sign": [1, 1, 1, 1, 1, -1, 1, 1, 1, 1],
        }
    )
    neurons["type"] = neurons["type"].astype("string")
    edges = pd.DataFrame(
        {
            "pre": [3, 4, 5, 6, 7, 8, 2, 1],
            "post": [1, 1, 1, 1, 1, 1, 1, 1],
            "weight": [3, 3, 9, 6, 50, 4, 70, 5],
        }
    )
    active = np.ones(10, dtype=bool)
    active[7] = False
    return neurons, edges, active


def test_candidates_follow_the_rule_not_a_ranking():
    neurons, edges, active = _graph()
    got = silence_scan.candidates(neurons, edges, 1, active, np.array([0, 1, 2]), 5)
    assert got["unit"].tolist() == ["106", "A", "B"]  # sorted by name
    a = got.set_index("unit").loc["A"]
    assert a["weight"] == 6  # 3 + 3, summed over the type
    assert a["neurons"].tolist() == [3, 4, 9]  # the whole type is silenced
    assert got.set_index("unit").loc["B", "sign"] == "-1"  # inhibitory stays in


def test_motor_and_command_are_never_in_a_unit():
    neurons, edges, active = _graph()
    neurons.loc[2, "type"] = "A"  # the command shares a type with a candidate
    got = silence_scan.candidates(neurons, edges, 1, active, np.array([0, 1, 2]), 5)
    assert 2 not in got.set_index("unit").loc["A", "neurons"].tolist()
    assert "M" not in got["unit"].tolist()  # autapse on the motor is excluded


def test_screen_draws_p_and_verdict():
    assert silence_scan.no_residual([2, 1, 0], 2)
    assert not silence_scan.no_residual([2, 3, 0], 2)
    assert silence_scan.screen_pass([10, 10, 10], [5, 5, 5], 0.5)
    assert not silence_scan.screen_pass([10, 10, 10], [6, 5, 5], 0.5)
    assert silence_scan.n_draws(3, 1000, 20) == 1000
    assert silence_scan.n_draws(60, 1000, 20) == 1200
    m = 60
    assert 1 / (1 + silence_scan.n_draws(m, 1000, 20)) <= 0.05 / m
    assert silence_scan.p_lower(1.0, [1.0, 2.0, 3.0]) == 0.5
    assert silence_scan.p_lower(0.0, [1.0] * 999) == 0.001

    rows = pd.DataFrame(
        {
            "unit": ["A", "B", "C"],
            "p": [0.001, 0.001, math.nan],
            "counts": [[0, 1, 2], [3, 1, 0], [0, 0, 0]],
        }
    )
    decided = silence_scan.decide(rows, m=2, alpha=0.05, max_spikes=2)
    assert decided["contributes"].tolist() == [True, True, False]
    assert decided["names_partner"].tolist() == [True, False, False]
    assert silence_scan.verdict(decided, 2) == "names_partner: A"
    only_b = decided[decided["unit"] != "A"]
    assert silence_scan.verdict(only_b, 2) == "contributes: B"
    weak = silence_scan.decide(rows.assign(p=0.03), m=2, alpha=0.05, max_spikes=2)
    assert silence_scan.verdict(weak, 2).startswith("none")
    assert silence_scan.verdict(rows.iloc[:0].assign(contributes=[]), 0).startswith(
        "none"
    )
