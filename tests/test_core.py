import numpy as np
import pandas as pd
import pytest

from flymsg import data, graph, sim


def chain(weights, signs=None):
    """Linear chain 0 -> 1 -> ... with the given synapse counts."""
    n = len(weights) + 1
    edges = pd.DataFrame(
        {"pre": np.arange(n - 1), "post": np.arange(1, n), "weight": weights}
    )
    sign = (
        np.ones(n, dtype=np.int8) if signs is None else np.asarray(signs, dtype=np.int8)
    )
    return edges, sign, n


def test_strongest_path_prefers_dominant_input():
    # 0 -> 1 -> 3 carries all of 3's input from 1; 0 -> 2 -> 3 is a weak side branch
    edges = pd.DataFrame(
        {"pre": [0, 1, 0, 2], "post": [1, 3, 2, 3], "weight": [50, 90, 50, 10]}
    )
    assert graph.strongest_path(
        edges, 4, np.array([0]), np.array([3]), min_weight=1
    ) == [0, 1, 3]


def test_strongest_path_respects_min_weight():
    edges, _, n = chain([10, 3])
    assert (
        graph.strongest_path(edges, n, np.array([0]), np.array([2]), min_weight=5) == []
    )


def test_excitation_propagates():
    edges, sign, n = chain([200, 200])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    rates = sim.run(W, np.array([0]), 150, 500)
    assert rates[0] > 50 and rates[1] > 0 and rates[2] > 0


def test_inhibition_blocks():
    edges, sign, n = chain([200, 200], signs=[-1, 1, 1])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    rates = sim.run(W, np.array([0]), 150, 500)
    assert rates[0] > 50 and rates[1] == 0 and rates[2] == 0


def test_stimulus_window():
    edges, sign, n = chain([200])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    short = sim.run(W, np.array([0]), 150, 500, stim_ms=100)
    full = sim.run(W, np.array([0]), 150, 500)
    assert 0 < short[0] < full[0]


def test_resolve():
    neurons = pd.DataFrame(
        {
            "bodyId": [10, 11, 12],
            "type": ["A", "A", "B"],
            "instance": ["A_L", "A_R", "B_L"],
        }
    )
    assert data.resolve(neurons, "A").tolist() == [0, 1]
    assert data.resolve(neurons, "A_R").tolist() == [1]
    assert data.resolve(neurons, "12").tolist() == [2]
    with pytest.raises(KeyError):
        data.resolve(neurons, "C")
