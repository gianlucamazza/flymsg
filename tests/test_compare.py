import numpy as np
import pandas as pd

from flymsg import compare


def test_fingerprint_matches_male_types_to_the_female_set_with_the_same_outputs():
    # female: set "s" (ids 1, 2) projects onto type X, set "w" (id 3) onto type Y
    female_n = pd.DataFrame(
        {"bodyId": [1, 2, 3, 4, 5], "flywireType": ["G", "G", "G", "X", "Y"]}
    )
    female_e = pd.DataFrame({"pre": [0, 1, 2], "post": [3, 3, 4], "weight": [5, 5, 9]})
    # male: type A projects onto X (named in the FAFB vocabulary), type B onto Y
    male_n = pd.DataFrame(
        {"type": ["A", "B", "P", "Q"], "flywireType": [None, None, "X", "Y"]}
    )
    male_e = pd.DataFrame({"pre": [0, 1, 1], "post": [2, 3, 2], "weight": [7, 8, 1]})
    fp = compare.fingerprint(
        (male_n, male_e), (female_n, female_e), ["A", "B"], {"s": [1, 2], "w": [3, 99]}
    )
    assert fp.loc["A", "nearest"] == "s" and fp.loc["B", "nearest"] == "w"
    assert np.isclose(fp.loc["A", "s"], 1.0)
    assert np.isclose(fp.loc["A", "w"], 0.0)


def test_sex_comparison_scores_target_and_shared_type_overlap():
    # both sexes: stim S -> X (shared type) -> T (target); the male also drives M, a type
    # absent from the female dataset, which must not count in the overlap
    def dataset(types):
        n = pd.DataFrame(
            {"flywireType": types, "sign": np.ones(len(types), dtype=np.int8)}
        )
        e = pd.DataFrame(
            {"pre": [0] * (len(types) - 1), "post": range(1, len(types)), "weight": 200}
        )
        return n, e

    male, female = dataset(["S", "X", "T", "M"]), dataset(["S", "X", "T"])
    out = compare.sex_comparison(
        male,
        female,
        {"c": (np.array([0]), np.array([0]), "T")},
        rates_hz=(100.0,),
        seeds=1,
    )
    row = out.iloc[0]
    assert row["male_target_hz"] > 0 and row["female_target_hz"] > 0
    assert row["male_types"] == row["female_types"] == 2  # X and T; M is not shared
    assert row["jaccard"] == 1.0
