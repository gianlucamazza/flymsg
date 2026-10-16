"""The identifiability re-read is locked, and a blocked parameter gets no interval."""

import pandas as pd
import pytest

from flymsg import evidence, identifiability, sensitivity


def _cells(rows):
    frame = []
    for factor, th, rates in rows:
        for seed, rate in enumerate(rates):
            frame.append(
                {
                    "case": "sugar feeding",
                    "target": "MN9",
                    "seed": seed,
                    "rate": rate,
                    "w_syn_factor": factor,
                    "th_jump": th,
                }
            )
    return pd.DataFrame(frame)


def test_locked_against_the_sensitivity_archive_and_blocks_intervals():
    doc = identifiability.assert_matches_code()
    assert doc["archive"]["sensitivity_sha256"] == sensitivity.load()["content_sha256"]
    assert evidence.check_lock(doc, evidence.load(), "identifiability") == []
    table = identifiability.parameter_table(doc)
    assert set(table["parameter"]) == {
        "w_syn",
        "th_jump",
        "sensory_gains",
        "membrane",
        "release",
    }
    assert (table["interval"] == "none").all()
    edited = identifiability.load()
    edited["parameters"][0]["status"] = "sourced"
    edited["content_sha256"] = identifiability.content_hash(edited)
    with pytest.raises(identifiability.IdentifiabilityError, match="without a bump"):
        identifiability.assert_locked(edited)


def test_cells_split_when_the_rate_shift_exceeds_the_seed_range():
    doc = identifiability.load()
    judged = identifiability.judge(
        _cells([(1.0, 0.0, [20, 20, 20]), (0.8, 0.0, [40, 40, 40])]),
        doc,
    )
    row = judged.iloc[0]
    assert row["classes"] == 2
    assert not row["undecidable"]
    assert not row["matches_silent_null"]


def test_a_seed_range_that_covers_the_grid_is_undecidable():
    doc = identifiability.load()
    judged = identifiability.judge(
        _cells([(1.0, 0.0, [15, 25, 20]), (1.2, 0.0, [22, 22, 22])]),
        doc,
    )
    row = judged.iloc[0]
    assert row["classes"] == 1
    assert row["undecidable"]


def test_a_sourced_parameter_must_name_evidence():
    doc = identifiability.load()
    doc["parameters"] = [{"name": "w_syn", "status": "sourced", "why": "x"}]
    with pytest.raises(identifiability.IdentifiabilityError, match="evidence id"):
        identifiability.check_parameters(doc)
