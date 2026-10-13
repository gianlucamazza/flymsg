"""The Kenyon cell sparseness diagnostic is locked before any run; no data are loaded."""

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from flymsg import cli, kc_sparseness


def test_locked_to_the_measured_bounds_and_the_plasticity_odors():
    doc = kc_sparseness.assert_matches_code()
    assert doc["version"] == 2
    assert kc_sparseness.content_hash(doc) == kc_sparseness.VERSION_HASHES[2]
    assert list(doc["arms"]) == ["A", "B", "E", "F"]
    assert doc["supersedes"]["verdict"] == "not_recurrence"
    assert doc["protocol"]["odors"] == ["ORN_VA1d", "ORN_DL3"]
    assert doc["defaults_changed"] is False


def test_an_edit_without_a_version_bump_fails():
    doc = kc_sparseness.load()
    doc["decides"]["sparse_max"] = 0.3
    doc["content_sha256"] = kc_sparseness.content_hash(doc)
    with pytest.raises(kc_sparseness.SparsenessError, match="without a bump"):
        kc_sparseness.assert_locked(doc)


def test_bounds_other_than_the_measured_ones_are_refused():
    doc = kc_sparseness.load()
    doc["decides"]["sparse_max"] = 0.3
    with pytest.raises(kc_sparseness.SparsenessError, match="measured"):
        kc_sparseness.assert_matches_code(doc)


def test_prints_the_protocol_without_data(monkeypatch, capsys, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    monkeypatch.setattr(
        "sys.argv", ["flymsg", "--data", str(tmp_path), "kc-sparseness"]
    )
    cli.main()
    assert "E ach_ln_pn" in capsys.readouterr().out


def test_v2_refuses_the_v1_seeds():
    doc = kc_sparseness.load()
    doc["protocol"]["seeds"] = [60, 61, 62]
    with pytest.raises(kc_sparseness.SparsenessError, match="version 1"):
        kc_sparseness.assert_matches_code(doc)


def test_responders_need_two_of_three_seeds():
    seeds = [np.array([1, 0, 1]), np.array([1, 0, 0]), np.array([0, 2, 0])]
    assert kc_sparseness.responders(seeds, 2).tolist() == [True, False, False]


def _row(arm, f1, f2, s1, s2):
    return {
        "arm": arm,
        "fraction_1": f1,
        "fraction_2": f2,
        "shared_of_1": s1,
        "shared_of_2": s2,
    }


def test_decide_lists_the_arms_within():
    t = pd.DataFrame(
        [
            _row("A", 0.25, 0.25, 0.95, 0.95),
            _row("B", 0.17, 0.16, 0.95, 0.95),
            _row("E", 0.06, 0.05, 0.3, 0.3),
            _row("F", 0.05, 0.05, 0.2, 0.2),
        ]
    )
    assert kc_sparseness.decide(t, 0.17, 0.646) == "within: E, F"
    assert kc_sparseness.decide(t.iloc[:2], 0.17, 0.646) == "none"


def test_kc_recurrence_spreads_an_odor_and_arm_b_removes_it():
    # 0, 1: two ORNs; 2-5: Kenyon cells; ORN 0 -> KC 2, ORN 1 -> KC 3; every KC excites
    # every other KC, so in arm A both odors recruit all four; 6: APL, no output here
    n = 7
    pre, post = [0, 1], [2, 3]
    for i in range(2, 6):
        for j in range(2, 6):
            if i != j:
                pre.append(i)
                post.append(j)
    W = sparse.csc_matrix(
        (np.full(len(pre), 60.0, dtype=np.float32), (post, pre)), shape=(n, n)
    )
    idx = {
        "ORN_VA1d": np.array([0]),
        "ORN_DL3": np.array([1]),
        "APL": np.array([6]),
        "KC": np.arange(2, 6),
        "PN": np.array([], dtype=int),
        "ACH_LN": np.array([], dtype=int),
    }
    doc = kc_sparseness.load()
    doc = {**doc, "decides": {**doc["decides"], "sparse_max": 0.3}}
    out = kc_sparseness.protocol(W, idx, doc)
    t = out["table"].set_index("arm")
    assert t.loc["A", "responders_1"] == 4 and t.loc["A", "shared"] == 4
    assert t.loc["B", "responders_1"] == 1 and t.loc["B", "shared"] == 0
    assert out["verdict"] == "within: B, F"
