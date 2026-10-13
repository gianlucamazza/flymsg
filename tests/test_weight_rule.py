"""The locked count-vs-density comparison (issue #139) on synthetic connectomes."""

import numpy as np
import pandas as pd
import pytest

from flymsg import weight_rule


def tiny():
    """Two glomeruli (PNs on both sides) onto two LHN types of different size."""
    doc = {
        "protocol": {"pn_types": ["DM1_lPN", "VA2_adPN"], "seed": 1},
        "matched_types": {"L1": ["LHA"], "L2": ["LHB"]},
        "partial_types": {},
    }
    neurons = pd.DataFrame(
        {
            "bodyId": range(8),
            "type": [
                "DM1_lPN",
                "DM1_lPN",
                "VA2_adPN",
                "VA2_adPN",
                "LHA",
                "LHA",
                "LHB",
                "LHB",
            ],
            "somaSide": ["L", "R", "L", "R", "L", "R", "L", "R"],
        }
    )
    # DM1 -> LHA: 10 on the left, 6 on the right; VA2 -> LHB: 4 left only;
    # a contralateral DM1(L) -> LHA(R) edge must not count
    edges = pd.DataFrame(
        {
            "pre": [0, 1, 2, 0],
            "post": [4, 5, 6, 5],
            "weight": [10, 6, 4, 99],
        }
    )
    return doc, neurons, edges


def test_counts_are_ipsilateral_means_over_sides():
    doc, neurons, edges = tiny()
    pairs = [
        {"pair": "DM1/L1", "uepsp_mv": 2.0},
        {"pair": "VA2/L2", "uepsp_mv": 1.0},
        {"pair": "VA2/L1", "uepsp_mv": 0.0},
    ]
    t = weight_rule.pair_counts(doc, neurons, edges, pairs).set_index("pair")
    assert t.loc["DM1/L1", "count"] == 8.0  # (10 + 6) / 2 sides
    assert t.loc["VA2/L2", "count"] == 2.0  # left 4, right 0
    assert t.loc["VA2/L1", "count"] == 0.0
    assert set(t["sides"]) == {2}


def test_type_areas_need_every_mesh():
    doc, _, _ = tiny()
    areas = pd.DataFrame(
        {
            "bodyId": [4, 5, 6, 7],
            "type": ["LHA", "LHA", "LHB", "LHB"],
            "area_um2": [100.0, 300.0, 50.0, np.nan],
        }
    )
    a = weight_rule.type_areas(doc, areas)
    assert a["L1"] == 200.0 and np.isnan(a["L2"])


def test_rules_rank_identically_within_one_type_and_the_verdict_follows_the_interval():
    # one area: density is count scaled, so both rules give the same rho
    t = pd.DataFrame(
        {
            "uepsp_mv": [0.0, 1.0, 2.0, 3.0],
            "count": [0, 2, 3, 9],
            "density": [0, 0.2, 0.3, 0.9],
        }
    )
    s = weight_rule.compare(t, seed=0, n_boot=200)
    assert s["rho_count"] == pytest.approx(s["rho_density"]) and s["delta"] == 0
    assert (
        weight_rule.verdict({**s, "pairs": 12, "ci_low": 0.1, "ci_high": 0.4}, 6)
        == "density"
    )
    assert (
        weight_rule.verdict({**s, "pairs": 12, "ci_low": -0.4, "ci_high": -0.1}, 6)
        == "count"
    )
    assert (
        weight_rule.verdict({**s, "pairs": 12, "ci_low": -0.1, "ci_high": 0.1}, 6)
        == "undecided"
    )
    assert weight_rule.verdict({**s, "pairs": 9}, 6) == "not_testable"
    assert weight_rule.verdict({**s, "pairs": 12}, 3) == "not_testable"


def test_the_lock_matches_its_hash_and_lists_the_source_table():
    doc = weight_rule.assert_locked()
    assert len(doc["pairs"]) == 57 and len(doc["sensitivity_pairs"]) == 19
    pairs = {p["pair"]: p["uepsp_mv"] for p in doc["pairs"]}
    # Liu et al. 2022 Table S3, read from Document S1
    assert pairs["DM1/L1"] == pytest.approx(1.61617573)
    assert pairs["VA6/local5"] == pytest.approx(6.63, abs=0.01)
    assert sum(v > 0 for v in pairs.values()) == 13
    with pytest.raises(weight_rule.WeightRuleError):
        weight_rule.assert_locked({**doc, "pairs": doc["pairs"][:-1]})
