import numpy as np
import pandas as pd
import pytest

from flymsg import cli, data, graph, sim


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


def test_strongest_path_uses_full_input_totals():
    # 1 gets 10 weak inputs (below min_weight) besides 0: its real input share from 0
    # is 50/90. Filtering before normalising would make 0 -> 1 -> 3 look best.
    weak = pd.DataFrame({"pre": np.arange(4, 14), "post": 1, "weight": 4})
    main = pd.DataFrame(
        {"pre": [0, 1, 0, 2], "post": [1, 3, 2, 3], "weight": [50, 20, 50, 15]}
    )
    edges = pd.concat([main, weak], ignore_index=True)
    assert graph.strongest_path(
        edges, 14, np.array([0]), np.array([3]), min_weight=5
    ) == [0, 2, 3]


def test_edge_weights():
    edges, _, _ = chain([7, 9])
    assert graph.edge_weights(edges, [0, 1, 2]) == [7, 9]


def test_stimulated_neurons_do_not_adapt():
    edges, sign, n = chain([200])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    plain = sim.run(W, np.array([0]), 100, 500, p=sim.Params(th_jump=0.0))
    adapt = sim.run(W, np.array([0]), 100, 500, p=sim.Params(th_jump=4.0))
    assert adapt[0] == plain[0]  # same seed, no adaptation on the stimulated neuron
    assert adapt[1] < plain[1]  # downstream neuron adapts


def test_poisson_weight_scales_with_w_syn():
    edges, sign, n = chain([1])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    weak = sim.run(W, np.array([0]), 100, 500, p=sim.Params(w_syn=0.01))
    assert weak[0] == 0  # 2.5 mV kicks never reach the 7 mV threshold


def test_summarize_counts_silent_neurons():
    neurons = pd.DataFrame(
        {"type": ["S", "A", "A", "B"], "superclass": ["x", "y", "y", "z"]}
    )
    out = cli.summarize(neurons, np.array([100.0, 40.0, 0.0, 0.0]), np.array([0]))
    assert out.loc["A", "n"] == 2 and out.loc["A", "active"] == 1
    assert out.loc["A", "mean_hz"] == 20.0
    assert (
        "S" not in out.index and "B" not in out.index
    )  # stimulated / silent types dropped


def test_label_handles_missing_names():
    neurons = pd.DataFrame(
        {
            "bodyId": [1, 2],
            "type": ["T", np.nan],
            "instance": [np.nan, np.nan],
            "nt": ["gaba", "gaba"],
            "superclass": ["x", "x"],
        }
    )
    assert cli.label(neurons, 0).startswith("T (") and cli.label(neurons, 1).startswith(
        "untyped ("
    )


def test_build_compacts_tables(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    ann = pd.DataFrame({c: [None] * 3 for c in data.ANN_COLS})
    ann["bodyId"] = [30, 10, 20]
    ann["type"] = ["C", "A", "B"]
    ann["status"] = ["Traced", "Traced", "Orphan"]
    ann.to_feather(raw / data.RAW["annotations"])
    pd.DataFrame(
        {"body": [10, 20, 30], "consensus_nt": ["gaba", "acetylcholine", "dopamine"]}
    ).to_feather(raw / data.RAW["nt"])
    pd.DataFrame(
        {"body_pre": [10, 30, 20], "body_post": [30, 10, 10], "weight": [5, 3, 9]}
    ).to_feather(raw / data.RAW["weights"])
    data.build(tmp_path)
    neurons, edges = data.load(tmp_path)
    assert neurons["bodyId"].tolist() == [10, 30]  # orphan dropped, sorted by bodyId
    assert neurons["sign"].tolist() == [-1, 0]
    assert edges[["pre", "post", "weight"]].values.tolist() == [
        [0, 1, 5],
        [1, 0, 3],
    ]  # edge from orphan dropped


def test_load_without_data(tmp_path):
    with pytest.raises(FileNotFoundError, match="flymsg build"):
        data.load(tmp_path)
