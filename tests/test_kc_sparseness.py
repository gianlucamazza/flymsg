"""The Kenyon cell sparseness diagnostic is locked before any run; no data are loaded."""

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from flymsg import cli, kc_sparseness


def test_locked_to_the_measured_bounds_and_the_plasticity_odors():
    doc = kc_sparseness.assert_matches_code()
    assert doc["version"] == 4
    assert kc_sparseness.content_hash(doc) == kc_sparseness.VERSION_HASHES[4]
    assert list(doc["arms"]) == ["A", "E", "F"]
    assert doc["supersedes"]["verdict"] == "none"
    assert len(kc_sparseness.coupled_arms(doc)) == 12
    assert doc["protocol"]["odors"] == ["3-octanol", "4-methylcyclohexanol"]
    assert doc["decides"]["sparse_min"] == 0.01
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
    out = capsys.readouterr().out
    assert "E ach_ln_pn" in out and "DoOR" in out and "12 coupled arms" in out


@pytest.mark.parametrize(
    ("seeds", "spent"), [([60, 61, 62], 1), ([70, 71, 72], 2), ([80, 81, 82], 3)]
)
def test_v3_refuses_spent_seeds(seeds, spent):
    doc = kc_sparseness.load()
    doc["protocol"]["seeds"] = seeds
    with pytest.raises(kc_sparseness.SparsenessError, match=f"version {spent}"):
        kc_sparseness.assert_matches_code(doc)


def test_v3_uses_hige_odors():
    doc = kc_sparseness.load()
    doc["protocol"]["odors"] = ["3-octanol", "ethyl acetate"]
    with pytest.raises(kc_sparseness.SparsenessError, match="Hige"):
        kc_sparseness.assert_matches_code(doc)


def test_the_sister_coefficient_is_the_measured_one():
    doc = kc_sparseness.load()
    doc["coupling"]["sister_cc"] = 0.05
    with pytest.raises(kc_sparseness.SparsenessError, match="sourced"):
        kc_sparseness.assert_matches_code(doc)
    doc = kc_sparseness.load()
    doc["coupling"]["eln_pn"] = [0.1, 1.0]
    with pytest.raises(kc_sparseness.SparsenessError, match="start at 0"):
        kc_sparseness.assert_matches_code(doc)


def _antennal_lobe():
    # neurons 0-1 cholinergic LNs, 2-4 PNs (2, 3 same type and side, 4 other side)
    neurons = pd.DataFrame(
        {
            "type": ["LN", "LN", "DM6_adPN", "DM6_adPN", "DM6_adPN"],
            "instance": ["a_R", "b_R", "DM6_adPN_R", "DM6_adPN_R", "DM6_adPN_L"],
        }
    )
    edges = pd.DataFrame(
        {"pre": [0, 0, 1, 3, 2], "post": [2, 3, 3, 1, 4], "weight": [10, 20, 30, 5, 7]}
    )
    idx = {"ACH_LN": np.array([0, 1]), "PN": np.array([2, 3, 4])}
    return neurons, edges, idx


def test_gap_pairs_join_chemical_partners_and_ipsilateral_sisters():
    neurons, edges, idx = _antennal_lobe()
    eln, sisters = kc_sparseness.gap_pairs(neurons, edges, idx)
    got = {(r.ln, r.pn): r.weight for r in eln.itertuples()}
    assert got == {(0, 2): 10, (0, 3): 20, (1, 3): 35}
    assert sisters.values.tolist() == [[2, 3]]


def test_gap_for_scales_the_median_pn_total_to_the_grid_value():
    neurons, edges, idx = _antennal_lobe()
    eln = kc_sparseness.gap_for(
        *kc_sparseness.gap_pairs(neurons, edges, idx), 0.3, 0.013
    )
    totals = {}
    for i, j, c in zip(eln.i, eln.j, eln.coupling, strict=True):
        if i in (0, 1):
            totals[j] = totals.get(j, 0.0) + c
    # PN totals 10 and 55 synapses: median 32.5 -> 0.3
    assert np.median(list(totals.values())) == pytest.approx(0.3)
    assert eln.coupling[-1] == pytest.approx(0.013 / 0.987)
    only_sisters = kc_sparseness.gap_for(
        *kc_sparseness.gap_pairs(neurons, edges, idx), 0.0, 0.013
    )
    assert only_sisters.i.tolist() == [2]


def test_least_coupling_is_the_smallest_within_arm():
    doc = kc_sparseness.load()
    rows = []
    for name, _base, k in kc_sparseness.coupled_arms(doc):
        good = name.startswith("E") and k >= 0.1
        f = 0.06 if good else 0.3
        rows.append(
            {
                "arm": name,
                "fraction_1": f,
                "fraction_2": f,
                "shared_of_1": 0.3,
                "shared_of_2": 0.3,
            }
        )
    assert kc_sparseness.least_coupling(pd.DataFrame(rows), doc) == {
        "E": 0.1,
        "F": None,
    }


def test_the_lower_bound_rejects_a_silent_arm():
    assert not kc_sparseness.within([0.002, 0.0], [0.0, 0.0], 0.17, 0.646, 0.01)
    assert kc_sparseness.within([0.05, 0.06], [0.3, 0.3], 0.17, 0.646, 0.01)


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
        "stimuli": {
            "3-octanol": (np.array([0]), np.array([100.0])),
            "4-methylcyclohexanol": (np.array([1]), np.array([100.0])),
        },
        "APL": np.array([6]),
        "KC": np.arange(2, 6),
        "PN": np.array([], dtype=int),
        "ACH_LN": np.array([], dtype=int),
    }
    doc = kc_sparseness.load()
    arms = {a: "" for a in ("A", "B", "E", "F")}
    base = {k: v for k, v in doc.items() if k != "coupling"}
    base = {**base, "arms": arms, "decides": {**doc["decides"], "sparse_max": 0.3}}
    out = kc_sparseness.protocol(W, idx, base)
    t = out["table"].set_index("arm")
    assert t.loc["A", "responders_1"] == 4 and t.loc["A", "shared"] == 4
    assert t.loc["B", "responders_1"] == 1 and t.loc["B", "shared"] == 0
    assert out["verdict"] == "within: B, F"
    # coupled arms without any pair behave as their base
    idx["eln"] = pd.DataFrame({"ln": [], "pn": [], "weight": []}, dtype=int)
    idx["sisters"] = pd.DataFrame({"i": [], "j": []}, dtype=int)
    idx["eln"] = pd.concat(
        [idx["eln"], pd.DataFrame({"ln": [0], "pn": [1], "weight": [1]})]
    )
    coupled = {**doc, "decides": base["decides"]}
    out = kc_sparseness.protocol(W, idx, coupled)
    t = out["table"].set_index("arm")
    assert t.loc["F+gap0", "responders_1"] == t.loc["F", "responders_1"] == 1
    assert out["prediction"]["F"] == 0.0


def test_an_interrupted_run_resumes_to_the_same_table(tmp_path):
    from flymsg import progress

    n = 4
    W = sparse.csc_matrix(
        (np.full(2, 60.0, dtype=np.float32), ([2, 3], [0, 1])), shape=(n, n)
    )
    idx = {
        "stimuli": {
            "3-octanol": (np.array([0]), np.array([100.0])),
            "4-methylcyclohexanol": (np.array([1]), np.array([100.0])),
        },
        "APL": np.array([], dtype=int),
        "KC": np.array([2, 3]),
        "PN": np.array([], dtype=int),
        "ACH_LN": np.array([], dtype=int),
    }
    doc = {k: v for k, v in kc_sparseness.load().items() if k != "coupling"}
    whole = kc_sparseness.protocol(W, idx, doc)["table"]
    steps = progress.Steps(tmp_path, doc["content_sha256"])
    kc_sparseness.protocol(W, idx, doc, steps)
    (tmp_path / "arm-E" / "done").unlink()  # E did not finish
    again = progress.Steps(tmp_path, doc["content_sha256"])
    resumed = kc_sparseness.protocol(W, idx, doc, again)["table"]
    assert again.resumed == ["arm-A", "arm-F"]
    pd.testing.assert_frame_equal(resumed, whole)
