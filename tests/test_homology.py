"""The mapping gives every male type one category; the pilot needs no global scale."""

import numpy as np
import pandas as pd

from flymsg import homology


def _male():
    return pd.DataFrame(
        {
            "type": ["LC4", "LC4", "DNp01", "IN01", "pMP", "X", "Y"],
            "flywireType": ["LC4", "LC4", "DNp01", None, None, None, "GONE"],
            "superclass": ["vp", "vp", "dn", "vnc_intrinsic", "cb", "cb", "cb"],
            "dimorphism": [None, None, None, None, "male-specific", None, None],
            "instance": ["LC4_R", "LC4_R", "DNp01_R", "", "", "", ""],
        }
    )


def _female():
    return pd.DataFrame(
        {"type": ["LC4", "DNp01", "ONLYF"], "instance": ["", "DNp01_R", ""]}
    )


def test_every_male_type_gets_one_category():
    t = homology.mapping(_male(), _female()).set_index("flywire_types", drop=False)
    by_type = t[t["male_type"] != ""].set_index("male_type")["category"].to_dict()
    assert by_type == {
        "DNp01": "matched",
        "IN01": "outside FAFB tissue",
        "LC4": "matched",
        "X": "not mapped",
        "Y": "annotation not in FAFB table",
        "pMP": "male-specific annotation",
    }
    assert t.loc["ONLYF", "category"] == "female type with no male mapping"
    assert set(t["category"]) <= set(homology.CATEGORIES)


def test_pilot_reports_raw_scaled_and_share_of_input():
    male = _male()
    # LC4 (0, 1) -> DNp01 (2): 30 synapses; other input 70; density ratio from LC4 and DNp01
    me = pd.DataFrame({"pre": [0, 1, 5], "post": [2, 2, 2], "weight": [10, 20, 70]})
    female = _female()
    fe = pd.DataFrame({"pre": [0, 2], "post": [1, 1], "weight": [5, 5]})
    got = homology.pilot((male, me), (female, fe)).set_index("dataset")
    assert got.loc["male", "LC4_synapses"] == 30
    assert got.loc["male", "share_of_input"] == 0.3
    assert got.loc["female", "share_of_input"] == 0.5
    assert np.isfinite(got.loc["male", "density_scaled"])
