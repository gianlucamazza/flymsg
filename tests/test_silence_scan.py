"""The residual TTMn_R scan is locked before any run. These tests never load the connectome."""

import math

import numpy as np
import pandas as pd
import pytest

from flymsg import cli, silence_scan


def test_scan_is_locked_to_the_behavior_silence_arm():
    doc = silence_scan.assert_matches_code()
    assert doc["version"] == 3
    assert silence_scan.content_hash(doc) == silence_scan.VERSION_HASHES[3]
    assert doc["supersedes"]["version"] == 2
    assert doc["replication"]["of_version"] == 2
    assert doc["replication"]["changed"] == ["confirm.seed0"]
    assert doc["issue"] == 20
    assert doc["blind"]["ranking_used"] is False
    assert doc["protocol"]["motor"] == "TTMn_R"
    assert doc["protocol"]["base_silence"] == "DNp01"
    assert doc["screen"]["decides"] is False
    assert doc["confirm"]["seed0"] == 30
    assert doc["confirm"]["pool_excludes_screen_passes"] is True
    assert doc["reported"]["partner_counts"]["decides"] is False


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
    assert "confirm seeds 30-32" in out


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


def _toy():
    # 0 stim -> 1 base -> 2 motor; 0 -> 3 (type A) -> 2; 0 -> 4, 5 (type B, same
    # superclass and sign as A) -> nothing. With 1 silenced, only A still drives 2.
    neurons = pd.DataFrame(
        {
            "bodyId": np.arange(10, 16),
            "type": ["S", "G", "M", "A", "B", "B"],
            "superclass": ["s", "g", "m", "x", "x", "x"],
            "sign": np.ones(6, dtype=np.int8),
        }
    )
    neurons["type"] = neurons["type"].astype("string")
    edges = pd.DataFrame(
        {
            "pre": [0, 1, 0, 3, 0, 0],
            "post": [1, 2, 3, 2, 4, 5],
            "weight": [400, 400, 400, 400, 400, 400],
        }
    )
    return neurons, edges


def _small(doc, draws):
    doc = {**doc, "confirm": {**doc["confirm"], "min_draws": draws}}
    return doc


def test_scan_names_the_only_remaining_route(tmp_path):
    neurons, edges = _toy()
    doc = _small(silence_scan.load(), 20)
    out = silence_scan.scan(
        neurons, edges, doc, np.array([0]), 2, np.array([1]),
        checkpoint=tmp_path / "scan.ckpt.jsonl",
    )  # fmt: skip
    assert min(out["base_screen"]) > 2
    assert out["screen"]["unit"].tolist() == ["A"]
    assert out["m"] == 1
    row = out["confirm"].iloc[0]
    assert row["draws"] == 20 and row["p"] == 1 / 21
    assert out["verdict"] == "names_partner: A"
    # a rerun replays the checkpoint
    again = silence_scan.scan(
        neurons, edges, doc, np.array([0]), 2, np.array([1]),
        checkpoint=tmp_path / "scan.ckpt.jsonl",
    )  # fmt: skip
    assert again["verdict"] == out["verdict"]


def test_scan_stops_when_the_base_arm_already_holds_the_bar():
    neurons, edges = _toy()
    edges = edges[edges["pre"] != 3]  # A no longer reaches the motor
    out = silence_scan.scan(
        neurons, edges, _small(silence_scan.load(), 20), np.array([0]), 2, np.array([1])
    )
    assert out["verdict"] == "no_residual: screen seeds"


def test_v2_refuses_the_v1_confirm_seeds_and_a_shared_pool():
    doc = silence_scan.load()
    doc["confirm"]["seed0"] = 10
    with pytest.raises(silence_scan.ScanError, match="v1 confirmation"):
        silence_scan.assert_matches_code(doc)
    doc = silence_scan.load()
    doc["confirm"]["pool_excludes_screen_passes"] = False
    with pytest.raises(silence_scan.ScanError, match="every screen pass"):
        silence_scan.assert_matches_code(doc)


def test_the_null_pool_of_one_pass_holds_no_other_pass(monkeypatch):
    # A (3) and one B neuron (4) both synapse onto the motor; every unit is made to pass
    # the screen, so the confirmation runs a null for each and must keep the other out
    neurons, edges = _toy()
    edges = pd.concat(
        [edges, pd.DataFrame({"pre": [4], "post": [2], "weight": [400]})],
        ignore_index=True,
    )
    monkeypatch.setattr(silence_scan, "screen_pass", lambda *_: True)
    seen = []
    real = silence_scan.draws.matched_pool_shortfall

    def spy(key, pool, like):
        seen.append((tuple(like.tolist()), pool.copy()))
        return real(key, pool, like)

    monkeypatch.setattr(silence_scan.draws, "matched_pool_shortfall", spy)
    out = silence_scan.scan(
        neurons, edges, _small(silence_scan.load(), 20), np.array([0]), 2, np.array([1])
    )
    assert out["m"] == 2
    assert {like for like, _ in seen} == {(3,), (4, 5)}
    for _, pool in seen:  # no draw for one pass may silence any pass
        assert not pool[[3, 4, 5]].any()
    # v3 reports each arm's other pass, per seed, as a description
    counts = dict(zip(out["confirm"]["unit"], out["confirm"]["partner_counts"]))
    assert set(counts["A"]) == {"B"} and set(counts["B"]) == {"A"}
    assert all(len(v) == 3 for c in counts.values() for v in c.values())


def test_v3_repeats_v2_with_only_the_confirm_seeds_changed():
    import subprocess

    old = silence_scan.prereg.load_yaml(
        subprocess.run(
            ["git", "show", "v0.8.27:validation/silence_scan.yaml"],
            capture_output=True, text=True, check=True, cwd=silence_scan.ROOT,
        ).stdout
    )  # fmt: skip
    new = silence_scan.load()
    for key in ("protocol", "candidates", "base_arm", "screen", "decides", "parent"):
        assert new[key] == old[key], key
    assert {k: v for k, v in new["confirm"].items() if k != "seed0"} == {
        k: v for k, v in old["confirm"].items() if k != "seed0"
    }


@pytest.mark.parametrize("seed0", [20, 21, 22, 10])
def test_v3_refuses_spent_confirm_seeds(seed0):
    doc = silence_scan.load()
    doc["confirm"]["seed0"] = seed0
    with pytest.raises(silence_scan.ScanError, match="must not reuse"):
        silence_scan.assert_matches_code(doc)


def test_v3_needs_its_failure_rule():
    doc = silence_scan.load()
    del doc["replication"]["on_failure"]
    with pytest.raises(silence_scan.ScanError, match="failure rule"):
        silence_scan.assert_matches_code(doc)


def test_partner_counts_are_the_other_passes_spikes_per_seed():
    class R:
        def __init__(self, counts):
            self.counts = np.asarray(counts)

    results = [R([[0, 2, 1], [0, 1, 0]]), R([[0, 0, 3], [0, 0, 0]])]
    units = {"A": np.array([1]), "B": np.array([2]), "C": np.array([0])}
    got = silence_scan.partner_counts(results, units, ["A", "B"], "A")
    assert got == {"B": [1, 3]}
