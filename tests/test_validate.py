from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flymsg import data, sim, validate

DATA = Path(__file__).parent.parent / "data"


def test_control_matches_superclasses_and_skips_target_inputs():
    neurons = pd.DataFrame({"superclass": ["a", "a", "a", "a", "b", "b", "t"]})
    # 1 (class a) feeds the target 6 strongly, so it must never be picked
    edges = pd.DataFrame({"pre": [1, 2], "post": [6, 6], "weight": [10, 2]})
    rng = np.random.default_rng(0)
    for _ in range(20):
        ctrl = validate.control_idx(
            neurons, edges, np.array([0, 4]), np.array([6]), rng
        )
        assert sorted(neurons["superclass"].iloc[ctrl]) == ["a", "b"]
        assert not np.isin(ctrl, [0, 1, 4, 6]).any()


@pytest.mark.slow
@pytest.mark.skipif(
    not (DATA / "edges.parquet").exists(), reason="needs `flymsg build`"
)
def test_battery_passes_with_default_params():
    neurons, edges = data.load(DATA)
    report = validate.run(neurons, edges, sim.Params(), seeds=3)
    assert report["passed"].all(), report[~report["passed"]].to_string()


def test_respond_reports_best_neuron_reliability_and_latency():
    # 0 drives 1 strongly and 2 weakly; 1 and 2 share type "T"
    neurons = pd.DataFrame({"type": ["S", "T", "T"]})
    edges = pd.DataFrame({"pre": [0, 0], "post": [1, 2], "weight": [200, 1]})
    W = sim.weight_matrix(edges, np.ones(3, dtype=np.int8), 3, 0.275)
    out, persistent = validate.respond(
        W, neurons, np.array([0]), ["T"], sim.Params(), seeds=3
    )
    t = out["T"]
    assert t["reliable"] == 3 and t["rate"] > 0
    assert 0 < t["latency"] < validate.STIM_MS
    assert persistent == 0
