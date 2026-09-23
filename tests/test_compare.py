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


def _tiny_pair():
    """A male and a female dataset sharing the FAFB vocabulary: two partner types, and one
    source type that is split into two subtypes on the male side."""
    male_n = pd.DataFrame(
        {
            "bodyId": [1, 2, 3, 4],
            "type": ["Aa", "Ab", "P", "Q"],
            "flywireType": ["A", "A", "P", "Q"],
        }
    )
    male_e = pd.DataFrame({"pre": [0, 1], "post": [2, 3], "weight": [10, 10]})
    female_n = pd.DataFrame(
        {
            "bodyId": [11, 12, 13, 14],
            "type": ["A", "A", "P", "Q"],
            "flywireType": ["A", "A", "P", "Q"],
        }
    )
    female_e = pd.DataFrame({"pre": [0, 1], "post": [2, 3], "weight": [5, 2]})
    return (male_n, male_e), (female_n, female_e)


def test_output_profile_and_cosine_compare_partner_shares():
    male, _ = _tiny_pair()
    p = compare.output_profile(*male, np.array([0]))
    assert p.to_dict() == {"P": 1.0}
    assert compare.cosine(p, p) == 1.0
    assert compare.cosine(p, compare.output_profile(*male, np.array([1]))) == 0.0


def test_synapse_density_ratio_is_the_median_over_matched_types():
    male, female = _tiny_pair()
    # male P gets 10 synapses vs 5 in the female, male Q 10 vs 2: ratios 2 and 5
    rho, n = compare.synapse_density_ratio(male, female)
    assert (rho, n) == (3.5, 2)


def test_responding_types_names_the_firing_types_without_the_stimulus():
    male, _ = _tiny_pair()
    rates = np.array([1.0, 0.0, 3.0, 0.0])
    assert compare.responding_types(male[0], rates, np.array([0])) == {"P"}


def test_lb3_split_assigns_each_female_lb3_neuron_and_tags_its_shiu_set(monkeypatch):
    male_n = pd.DataFrame(
        {"bodyId": [1, 2], "type": ["LB3b", "LB3d"], "flywireType": ["LB3", "LB3"]}
    )
    male_e = pd.DataFrame({"pre": [0, 1], "post": [1, 0], "weight": [10, 10]})
    female_n = pd.DataFrame(
        {"bodyId": [101, 102], "type": ["LB3", "LB3"], "flywireType": ["LB3", "LB3"]}
    )
    female_e = pd.DataFrame({"pre": [0, 1], "post": [1, 0], "weight": [10, 10]})
    monkeypatch.setattr(compare, "LB3_SUBTYPES", ["LB3b", "LB3d"])
    monkeypatch.setattr(compare, "REFERENCE_SETS", {"sugar": [101], "water": [999]})
    split = compare.lb3_split((male_n, male_e), (female_n, female_e)).set_index(
        "bodyId"
    )
    assert (
        split.loc[101, "shiu_set"] == "sugar" and split.loc[102, "shiu_set"] == "none"
    )
    assert set(split["nearest"]) <= {"LB3b", "LB3d"}
