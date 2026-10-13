"""MANC muscles on a synthetic Supplementary file 3; no download, no connectome."""

import pandas as pd
import pytest

from flymsg import manc_muscles, motor_map

C = manc_muscles.CERTAINTY


def _supp3() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "type": ["TTMn", "TTMn", "hi2 MN", "hi2 MN", "MNad02", "MNad02", "MNxm01"]
            + ["Ti flexor MN", "X MN", "X MN"],
            "target": ["TTM", "TTM", "hi2", "hi2", "abdomen", "abdomen A2", None]
            + ["Ti flexor", "a", "b"],
            C: [5, 5, 1, 2, None, None, None, None, 3, None],
            "publication_match": ["King & Wyman (1980)", None, None, None, None]
            + [None, None, None, None, None],
            "match_notes": [None] * 10,
        }
    )


def test_by_type_keeps_a_muscle_only_when_one_is_named():
    t = manc_muscles.by_type(_supp3()).set_index("manc_type")
    assert t.loc["TTMn", "muscle"] == "TTM"
    assert t.loc["TTMn", "status"] == "muscle"
    assert t.loc["TTMn", "manc_neurons"] == 2
    assert t.loc["TTMn", "publication_match"] == "King & Wyman (1980)"
    hi2 = t.loc["hi2 MN"]
    assert (hi2["certainty_min"], hi2["certainty_max"]) == (1, 2)
    assert t.loc["Ti flexor MN", "muscle"] == "Ti flexor"
    assert pd.isna(t.loc["Ti flexor MN", "certainty_max"])
    assert t.loc["MNad02", "status"] == "region"
    assert t.loc["MNad02", "target"] == "abdomen | abdomen A2"
    assert t.loc["MNxm01", "status"] == "no_target"
    assert t.loc["X MN", "status"] == "several_targets"
    for name in ("MNad02", "MNxm01", "X MN"):
        assert pd.isna(t.loc[name, "muscle"])
    assert set(t["source"]) == {manc_muscles.SOURCE}


def test_join_matches_on_manc_type_and_names_why_a_neuron_has_no_muscle():
    motor = pd.DataFrame(
        {
            "bodyId": [1, 2, 3, 4, 5, 6],
            "type": ["TTMn", "ADNM1 MN", "MNad18,MNad27", None, "MNad02", "New MN"],
            "mancType": ["TTMn", "ADNM1", "MNad18,MNad27", None, "MNad02", "New MN"],
        }
    )
    supp3 = pd.concat(
        [_supp3(), pd.DataFrame({"type": ["ADNM1"], "target": ["TH1"], C: [5]})]
    )
    j = manc_muscles.join(motor, manc_muscles.by_type(supp3)).set_index("bodyId")
    assert list(j["status"]) == [
        "muscle",
        "muscle",
        "compound_type",
        "untyped",
        "region",
        "not_in_manc",
    ]
    assert j.loc[2, "muscle"] == "TH1"
    assert j["muscle"].notna().sum() == 2
    s = manc_muscles.summary(j.reset_index())
    assert s.loc["muscle", "neurons"] == 2
    assert s.loc["untyped", "types"] == 0


def test_fetch_refuses_a_file_that_is_not_the_pinned_one(tmp_path):
    raw = manc_muscles.raw_dir(tmp_path)
    raw.mkdir(parents=True)
    (raw / manc_muscles.SUPP3_NAME).write_text("type,target\n")
    with pytest.raises(manc_muscles.MancError, match="expected"):
        manc_muscles.fetch(tmp_path)


def test_a_muscle_does_not_open_the_motor_map():
    # the muscle column is derived data; the lock and its refusal are unchanged
    doc = motor_map.assert_locked()
    assert doc["version"] == 1
    assert motor_map.content_hash(doc) == motor_map.VERSION_HASHES[1]
    with pytest.raises(motor_map.MotorMapError, match="unmapped"):
        motor_map.command("TTMn_R", doc)
    with pytest.raises(motor_map.MotorMapError, match="not in the motor map"):
        motor_map.command("TTM", doc)
