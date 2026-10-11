"""Null families and real-vs-null scores, on tables small enough to see by hand."""

import numpy as np
import pandas as pd
import pytest

from flymsg import nulls, prereg, wiring


def _net():
    """Two types. S0 → T0 is strong; S1 → T1 is weak. Extra edges give the
    shuffles something to mix."""
    neurons = pd.DataFrame(
        {
            "type": ["S", "S", "T", "T", "X"],
            "sign": np.array([1, 1, 1, -1, 1], dtype=np.int8),
        }
    )
    edges = pd.DataFrame(
        {
            "pre": np.array([0, 0, 1, 1, 4], dtype=np.int32),
            "post": np.array([2, 3, 2, 4, 3], dtype=np.int32),
            "weight": np.array([50, 1, 2, 40, 3], dtype=np.int32),
        }
    )
    return neurons, edges


def test_degree_preserving_is_n1_and_seed_zero_stays_locked():
    _neurons, edges = _net()
    shuffled, _ = wiring.shuffle_targets(edges, 0)
    again = nulls.shuffle_degree_preserving(edges, 0)
    assert again["post"].tolist() == shuffled["post"].tolist()
    assert again["weight"].tolist() == edges["weight"].tolist()


def test_cell_type_preserving_keeps_type_to_type_and_in_degrees():
    neurons, edges = _net()
    shuffled = nulls.shuffle_cell_type_preserving(edges, neurons, seed=1)
    types = nulls.cell_types(neurons)
    assert sorted(types[shuffled["post"]]) == sorted(types[edges["post"]])
    assert shuffled["pre"].tolist() == edges["pre"].tolist()
    assert shuffled["weight"].tolist() == edges["weight"].tolist()
    assert sorted(shuffled["post"]) == sorted(edges["post"])


def test_weight_within_type_keeps_topology_and_the_type_weight_bag():
    neurons, edges = _net()
    shuffled = nulls.shuffle_weight_within_type(edges, neurons, seed=2)
    assert shuffled["pre"].tolist() == edges["pre"].tolist()
    assert shuffled["post"].tolist() == edges["post"].tolist()
    types = nulls.cell_types(neurons)
    for label in np.unique(types[edges["pre"]]):
        idx = np.flatnonzero(types[edges["pre"]] == label)
        assert sorted(shuffled["weight"].iloc[idx]) == sorted(edges["weight"].iloc[idx])


def test_sign_shuffle_keeps_zeros_and_the_plus_minus_counts():
    neurons, _ = _net()
    shuffled = nulls.shuffle_signs(neurons, seed=3)
    assert (shuffled["sign"] == 0).sum() == (neurons["sign"] == 0).sum()
    assert sorted(shuffled["sign"]) == sorted(neurons["sign"])
    again = nulls.shuffle_signs(neurons, seed=3)
    assert again["sign"].tolist() == shuffled["sign"].tolist()


def test_pathway_scores_sum_and_max_are_the_signed_stim_weights():
    neurons, edges = _net()
    pathways = [
        {
            "case": "toy",
            "target": "T",
            "kind": "specific",
            "tail": "upper",
            "stim": np.array([0]),
        }
    ]
    scores = nulls.pathway_scores(neurons, edges, pathways)
    # S0 → T0 (50, +) and S0 → T1 (1, +)
    assert scores["sum"].iloc[0] == 51.0
    assert scores["max"].iloc[0] == 50.0


def test_empirical_p_and_z_use_every_draw():
    nulls_vals = np.array([1.0, 2.0, 3.0, 4.0])
    assert nulls.empirical_p(5.0, nulls_vals, "upper") == 1 / 5
    assert nulls.empirical_p(0.0, nulls_vals, "upper") == 5 / 5
    assert nulls.empirical_p(0.0, nulls_vals, "lower") == 1 / 5
    z = nulls.z_score(5.0, nulls_vals)
    assert z == pytest.approx((5.0 - 2.5) / nulls_vals.std(ddof=1))
    assert nulls.z_score(1.0, np.array([1.0, 1.0])) == 0.0


def test_run_family_reports_all_pathways_and_the_locked_draw_counts(monkeypatch):
    neurons, edges = _net()
    pathways = [
        {
            "case": "toy",
            "target": "T",
            "kind": "specific",
            "tail": "upper",
            "stim": np.array([0]),
        },
        {
            "case": "bitter feeding",
            "target": "T",
            "kind": "negative",
            "tail": "lower",
            "stim": np.array([1]),
        },
    ]
    monkeypatch.setattr(nulls, "pathway_rows", lambda *_a, **_k: pathways)
    locked = prereg.load()["nulls"]
    for draws in (locked["draws_ci"], locked["draws_full"]):
        got = nulls.run_family(
            "degree_preserving", neurons, edges, draws, pathways=pathways
        )
        assert len(got["nulls"]) == draws
        table = got["by_metric"]["sum"]
        assert list(table["case"]) == ["toy", "bitter feeding"]
        assert table["n_draws"].tolist() == [draws, draws]
        assert set(table["p"]) <= {i / (1 + draws) for i in range(1, draws + 2)}
        assert len(got["headline"]) == 2


def test_unknown_family_is_a_keyerror():
    neurons, edges = _net()
    with pytest.raises(KeyError, match="unknown null family"):
        nulls.apply_family("not-a-family", neurons, edges, 0)
