"""N1's shuffle and its confirmatory rule, on tables small enough to see by hand."""

import numpy as np
import pandas as pd
import pytest

from flymsg import wiring


def _edges():
    return pd.DataFrame(
        {
            "pre": np.array([0, 0, 1, 1, 2], dtype=np.int32),
            "post": np.array([1, 2, 3, 4, 5], dtype=np.int32),
            "weight": np.array([10, 20, 30, 40, 50], dtype=np.int32),
        }
    )


def test_seed_zero_permutation_is_locked():
    # numpy 2.5 Generator.permutation of [1, 2, 3, 4, 5]. A change here is a different N1.
    shuffled, _ = wiring.shuffle_targets(_edges())
    assert shuffled["post"].tolist() == [3, 5, 4, 1, 2]
    assert shuffled["post"].dtype == np.int32


def test_degrees_and_outgoing_weights_stay_and_the_source_is_untouched():
    edges = _edges()
    original_post = edges["post"].tolist()
    shuffled, stats = wiring.shuffle_targets(edges)
    assert edges["post"].tolist() == original_post
    assert shuffled["pre"].tolist() == edges["pre"].tolist()
    assert shuffled["weight"].tolist() == edges["weight"].tolist()
    assert sorted(shuffled["post"]) == sorted(edges["post"])
    assert stats["n_edges"] == 5
    assert stats["n_self_loops"] == 2  # posts 1 and 2 land on pres 1 and 2
    again, _ = wiring.shuffle_targets(edges)
    assert again["post"].tolist() == shuffled["post"].tolist()


def test_census_counts_self_loops_and_extra_copies_without_dropping_them():
    pre = np.array([0, 2, 2, 2])
    post = np.array([0, 1, 1, 1])  # one self-loop; pair (2, 1) three times
    stats = wiring.census(pre, post)
    assert stats == {
        "n_edges": 4,
        "n_self_loops": 1,
        "n_duplicate_pairs": 1,
        "n_extra_edges": 2,
    }
    assert wiring.census(np.array([]), np.array([]))["n_edges"] == 0


def test_confirmatory_rule_ignores_checks_the_real_graph_fails():
    def report(specific_passed, positive_passed=True):
        return pd.DataFrame(
            [
                ("sugar feeding", "specific", "MN9", specific_passed),
                ("sugar feeding", "positive", "MN9", positive_passed),
                ("looming escape", "specific", "TTMn", False),
            ],
            columns=["case", "kind", "subject", "passed"],
        )

    table = wiring.confirmatory(report(True), report(False))
    assert table["subject"].tolist() == ["MN9", "TTMn"]
    sugar = table[table["subject"] == "MN9"].iloc[0]
    assert sugar["applies"] and sugar["held"]
    looming = table[table["subject"] == "TTMn"].iloc[0]
    assert not looming["applies"] and looming["held"]
    assert "1/1" in wiring.verdict(table)
    assert "finding" not in wiring.verdict(table)


def test_a_specific_check_that_survives_the_shuffle_is_a_finding():
    rows = [("sugar feeding", "specific", "MN9", True)]
    columns = ["case", "kind", "subject", "passed"]
    report = pd.DataFrame(rows, columns=columns)
    text = wiring.verdict(wiring.confirmatory(report, report))
    assert "0/1" in text
    assert "sugar feeding / MN9" in text


def test_confirmatory_rejects_reports_that_do_not_list_the_same_checks():
    columns = ["case", "kind", "subject", "passed"]
    real = pd.DataFrame([("sugar feeding", "specific", "MN9", True)], columns=columns)
    shuffled = pd.DataFrame(
        [("sugar feeding", "specific", "TTMn", False)], columns=columns
    )
    with pytest.raises(ValueError, match="different specific checks"):
        wiring.confirmatory(real, shuffled)


def test_verdict_when_nothing_on_the_real_graph_is_specific():
    report = pd.DataFrame(
        [("sugar feeding", "specific", "MN9", False)],
        columns=["case", "kind", "subject", "passed"],
    )
    assert "does not apply" in wiring.verdict(wiring.confirmatory(report, report))
