import numpy as np
import pandas as pd

from flymsg import data, quality


def test_side_from_instance_suffix():
    assert quality.side_of("MN9_L") == "L"
    assert quality.side_of("DNp01(GF)_R") == "R"
    assert quality.side_of("hg1 MN_L") == "L"
    assert quality.side_of("LB3b") is None and quality.side_of(None) is None


def test_pair_asymmetry_flags_only_the_outlier_pair():
    # 30 symmetric-ish types plus one pair whose right neuron has 10x fewer inputs
    rng = np.random.default_rng(0)
    types, inst, inp = [], [], []
    for k in range(30):
        base = rng.integers(500, 2000)
        for side, jitter in (("L", 1.0), ("R", rng.uniform(0.85, 1.15))):
            types.append(f"T{k}")
            inst.append(f"T{k}_{side}")
            inp.append(base * jitter)
    types += ["X", "X"]
    inst += ["X_L", "X_R"]
    inp += [5000, 500]
    neurons = pd.DataFrame({"type": types, "instance": inst})
    totals = pd.DataFrame({"in": inp, "out": np.ones(len(inp))})
    a = quality.pair_asymmetry(neurons, totals)
    assert a.loc["X", "flag"] and a["flag"].sum() == 1
    assert np.isclose(a.loc["X", "log2_RL"], np.log2(501 / 5001))


def test_traced_input_share_counts_untraced_fragments(tmp_path):
    # neuron 10 (traced) gets 6 synapses from traced 20 and 4 from fragment 99
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame(
        {"body_pre": [20, 99, 10], "body_post": [10, 10, 20], "weight": [6, 4, 3]}
    ).to_feather(raw / data.RAW["weights"])
    neurons = pd.DataFrame({"bodyId": [10, 20]})
    share = quality.traced_input_share(tmp_path, neurons, np.array([0, 1]))
    assert share.loc[0] == 0.6 and share.loc[1] == 1.0
