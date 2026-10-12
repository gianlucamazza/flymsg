"""The residual partner follow-up is locked before any run. These tests never load the
connectome."""

import math

import numpy as np
import pandas as pd
import pytest

from flymsg import cli, partner_followup


def test_followup_is_locked_to_the_scan_v3_naming():
    doc = partner_followup.assert_matches_code()
    assert doc["version"] == 1
    assert partner_followup.content_hash(doc) == partner_followup.VERSION_HASHES[1]
    assert doc["issue"] == 76
    assert doc["parent"]["verdict"] == "names_partner: DNp02, DNp06"
    assert list(partner_followup.seeds(doc)) == [40, 41, 42]
    assert doc["left"]["units"] == ["DNp02", "DNp06"]
    assert doc["drive"]["rate_hz"] == 200.0
    assert "mirror" in doc["seen_before_lock"]


def test_an_edit_without_a_version_bump_fails():
    doc = partner_followup.load()
    doc["drive"]["rate_hz"] = 300.0
    doc["content_sha256"] = partner_followup.content_hash(doc)
    with pytest.raises(partner_followup.FollowupError, match="without a bump"):
        partner_followup.assert_locked(doc)


@pytest.mark.parametrize("seed0", [0, 1, 10, 20, 30])
def test_spent_seeds_are_refused(seed0):
    doc = partner_followup.load()
    doc["seeds"]["seed0"] = seed0
    with pytest.raises(partner_followup.FollowupError, match="fresh"):
        partner_followup.assert_matches_code(doc)


def test_the_left_test_mirrors_the_scan_and_tests_only_its_naming():
    doc = partner_followup.load()
    doc["left"]["stimulus"] = "LC4_R"
    with pytest.raises(partner_followup.FollowupError, match="mirrors"):
        partner_followup.assert_matches_code(doc)
    doc = partner_followup.load()
    doc["left"]["units"] = ["DNp02", "GFC2"]
    with pytest.raises(partner_followup.FollowupError, match="named"):
        partner_followup.assert_matches_code(doc)
    doc = partner_followup.load()
    doc["left"]["draws"] = 500
    with pytest.raises(partner_followup.FollowupError, match="draws"):
        partner_followup.assert_matches_code(doc)


def test_followup_prints_the_protocol_and_does_not_load_data(
    monkeypatch, capsys, tmp_path
):
    def boom(*_args, **_kwargs):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    monkeypatch.setattr(
        "sys.argv", ["flymsg", "--data", str(tmp_path), "partner-followup"]
    )
    cli.main()
    out = capsys.readouterr().out
    assert "LC4_L -> TTMn_L with DNp01 silenced" in out
    assert "seeds 40-42" in out


def test_left_verdicts():
    rows = pd.DataFrame(
        {
            "unit": ["DNp02", "DNp06"],
            "p": [0.001, 0.001],
            "counts": [[0, 0, 0], [0, 1, 2]],
        }
    )
    decided, v = partner_followup.decide_left(rows, [3, 2, 4], 0.05, 3)
    assert v == "replicates" and decided["names_partner"].all()
    _, v = partner_followup.decide_left(
        rows.assign(p=[0.001, 0.03]), [3, 2, 4], 0.05, 3
    )
    assert v == "partial"
    _, v = partner_followup.decide_left(rows.assign(p=0.5), [3, 2, 4], 0.05, 3)
    assert v == "not_replicated"
    _, v = partner_followup.decide_left(
        rows.assign(p=[0.001, math.nan]), [3, 2, 4], 0.05, 3
    )
    assert v == "undetermined"
    _, v = partner_followup.decide_left(rows, [2, 1, 2], 0.05, 3)
    assert v == "no_residual"


@pytest.mark.parametrize(
    ("arms", "p", "expected"),
    [
        (
            {"a": [3, 4, 3], "b": [0, 0, 0], "pair": [9, 9, 9]},
            0.001,
            "single_sufficient: a",
        ),
        ({"a": [0, 1, 2], "b": [0, 0, 0], "pair": [5, 4, 3]}, 0.001, "conjunction"),
        ({"a": [0, 3, 2], "b": [0, 0, 0], "pair": [5, 4, 3]}, 0.001, "pair_sufficient"),
        ({"a": [0, 0, 0], "b": [0, 0, 0], "pair": [5, 4, 3]}, 0.2, "not_specific"),
        ({"a": [0, 0, 0], "b": [0, 0, 0], "pair": [5, 2, 3]}, 0.001, "insufficient"),
    ],
)
def test_drive_verdicts(arms, p, expected):
    assert partner_followup.decide_drive(arms, p, 0.05, 3) == expected


def test_p_upper():
    assert partner_followup.p_upper(3.0, [1.0, 3.0, 5.0]) == 0.75
    assert partner_followup.p_upper(9.0, [0.0] * 999) == 0.001


def _toy():
    # left: 0 stim -> 1 base -> 2 motor_L; 0 -> 3 (A) -> 4 (B) -> 2, so with 1 silenced
    # only the A -> B route drives 2; 5, 6 are responders of A/B's superclass with no
    # output. drive: 7 motor_R; 8 (A_R), 9 (B_R) each drive 7; 10, 11 match them, silent.
    neurons = pd.DataFrame(
        {
            "bodyId": np.arange(100, 112),
            "type": ["S", "G", "ML", "A", "B", "X", "X", "MR", "A", "B", "Y", "Y"],
            "superclass": ["s", "g", "m", "d", "d", "d", "d", "m", "d", "d", "d", "d"],
            "sign": np.ones(12, dtype=np.int8),
        }
    )
    neurons["type"] = neurons["type"].astype("string")
    edges = pd.DataFrame(
        {
            "pre": [0, 1, 0, 3, 4, 0, 0, 8, 9],
            "post": [1, 2, 3, 4, 2, 5, 6, 7, 7],
            "weight": [400] * 9,
        }
    )
    idx = {
        "LC4_L": np.array([0]),
        "TTMn_L": np.array([2]),
        "DNp01": np.array([1]),
        "DNp02": np.array([3, 8]),
        "DNp06": np.array([4, 9]),
        "TTMn_R": np.array([7]),
        "DNp02_R": np.array([8]),
        "DNp06_R": np.array([9]),
    }
    return neurons, edges, idx


def _small(draws):
    doc = partner_followup.load()
    doc["left"]["draws"] = draws
    doc["drive"]["draws"] = draws
    return doc


def test_followup_end_to_end_on_a_small_graph(tmp_path):
    neurons, edges, idx = _toy()
    doc = _small(40)  # 1 / 41 is below alpha / 2
    ckpt = tmp_path / "f.ckpt.jsonl"
    out = partner_followup.followup(neurons, edges, doc, idx, checkpoint=ckpt)
    assert min(out["left_base"]) >= 3
    assert out["left_verdict"] == "replicates"
    assert out["left"]["p"].tolist() == [1 / 41, 1 / 41]
    # each driven neuron alone drives the motor here
    assert out["drive_verdict"] == "single_sufficient: DNp02_R, DNp06_R"
    assert out["drive"]["p"] == 1 / 41
    nd = out["null_draws"]
    assert len(nd) == 120 and set(nd["part"]) == {"left", "drive"}
    assert out["driven_spikes"]["pair"]["DNp02_R"][0] > 0
    again = partner_followup.followup(neurons, edges, doc, idx, checkpoint=ckpt)
    assert again["null_draws"].equals(nd)
