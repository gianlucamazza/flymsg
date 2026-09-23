from typing import ClassVar

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
    rates = sim.run(W, np.array([0]), 150, 500).rate()
    assert rates[0] > 50 and rates[1] > 0 and rates[2] > 0


def test_inhibition_blocks():
    edges, sign, n = chain([200, 200], signs=[-1, 1, 1])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    rates = sim.run(W, np.array([0]), 150, 500).rate()
    assert rates[0] > 50 and rates[1] == 0 and rates[2] == 0


def test_stimulus_window():
    edges, sign, n = chain([200])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    short = sim.run(W, np.array([0]), 150, 500, stim_ms=100).rate()
    full = sim.run(W, np.array([0]), 150, 500).rate()
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


def test_alternative_paths_avoid_previous_types():
    # 0 -> 1 -> 4 is strongest; 0 -> 2 -> 4 runs through a sibling of 1 (same type A) and
    # must be skipped; 0 -> 3 -> 4 is the real alternative
    edges = pd.DataFrame(
        {
            "pre": [0, 1, 0, 2, 0, 3],
            "post": [1, 4, 2, 4, 3, 4],
            "weight": [50, 60, 50, 30, 50, 10],
        }
    )
    groups = np.array(["S", "A", "A", "B", "T"])
    paths = graph.alternative_paths(
        edges, 5, np.array([0]), np.array([4]), groups, k=3, min_weight=1
    )
    assert paths == [[0, 1, 4], [0, 3, 4]]


def test_edge_weights():
    edges, _, _ = chain([7, 9])
    assert graph.edge_weights(edges, [0, 1, 2]) == [7, 9]


def test_stimulated_neurons_do_not_adapt():
    edges, sign, n = chain([200])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    plain = sim.run(W, np.array([0]), 100, 500, p=sim.Params(th_jump=0.0)).rate()
    adapt = sim.run(W, np.array([0]), 100, 500, p=sim.Params(th_jump=4.0)).rate()
    assert adapt[0] == plain[0]  # same seed, no adaptation on the stimulated neuron
    assert adapt[1] < plain[1]  # downstream neuron adapts


def test_poisson_input_kicks_v_like_the_brian2_model():
    edges, sign, n = chain([1])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    # 68.75 mV kicks: with no refractory period every input event is a spike, so the
    # stimulated neuron fires at the input rate (not ~2x, as when kicks went into g)
    # At 1,000 Hz (0.1 events per 0.1 ms step) ~10 % of events fall in the step where the
    # spike from the previous event is reset and are lost, as in brian2's schedule (input
    # before reset); at 100 Hz the loss is ~1 %.
    rate = sim.run(W, np.array([0]), 1000, 1000).rate()[0]
    assert 800 < rate < 950
    # 2.5 mV kicks, 5 Hz: the membrane decays long before a second kick arrives
    weak = sim.run(W, np.array([0]), 5, 1000, p=sim.Params(w_syn=0.01)).rate()
    assert weak[0] == 0


def fake_result(rates_hz, stim_ms=100.0, duration_ms=100.0, bin_ms=10.0):
    """Result with constant rates (Hz) during the stimulus, silence afterwards."""
    bins = round(duration_ms / bin_ms)
    counts = np.zeros((bins, len(rates_hz)), dtype=np.uint16)
    counts[: round(stim_ms / bin_ms)] = np.asarray(rates_hz) * bin_ms / 1000
    first = np.where(np.asarray(rates_hz) > 0, 5.0, np.nan)
    return sim.Result(counts, first, bin_ms, stim_ms)


def test_summarize_counts_silent_neurons_and_seeds():
    neurons = pd.DataFrame(
        {"type": ["S", "A", "A", "B"], "superclass": ["x", "y", "y", "z"]}
    )
    results = [fake_result([100, 200, 0, 0]), fake_result([100, 0, 0, 0])]
    out = cli.summarize(neurons, results, np.array([0]))
    assert out.loc["A", "n"] == 2
    assert out.loc["A", "p_active"] == 0.5  # fired in one seed out of two
    assert out.loc["A", "hz"] == 50.0  # (100 + 0) / 2 seeds; 100 = mean of 200 and 0
    assert out.loc["A", "hz_sd"] == 50.0
    assert (
        "S" not in out.index and "B" not in out.index
    )  # stimulated / silent types dropped
    assert "post_hz" not in out.columns  # no post-stimulus window


def test_result_windows_and_persistence():
    r = fake_result([100, 0], stim_ms=100, duration_ms=300)
    assert r.rate(0, 100).tolist() == [100.0, 0.0]
    assert r.rate(100).tolist() == [0.0, 0.0]
    assert r.persistent().size == 0
    with pytest.raises(ValueError):
        fake_result([1], stim_ms=100, duration_ms=150).persistent()


def test_latency_and_bins_follow_propagation():
    edges, sign, n = chain([200, 200])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    r = sim.run(W, np.array([0]), 150, 300, stim_ms=100)
    assert r.counts.shape == (30, 3)
    lat = r.first_spike_ms
    assert lat[0] < lat[1] < lat[2]  # each hop adds delay
    assert (
        r.counts.sum() == r.counts[:12].sum() or r.rate(200).sum() == 0
    )  # silence after pulse
    assert r.persistent().size == 0


def test_duration_must_fit_bins():
    edges, sign, n = chain([1])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    with pytest.raises(ValueError):
        sim.run(W, np.array([0]), 100, 105)


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


def test_matches_the_brian2_reference_on_a_two_neuron_network():
    # Reference: the published brian2 model (model.py at commit 91bdd1e, brian2 2.10.1),
    # neuron 0 stimulated at 200 Hz, 60 synapses onto neuron 1, 20 seeds x 2 s:
    # post 44.4 Hz with t_ref 2.2 ms. It is sensitive to the refractory rules (input lost
    # while refractory, 2.2 ms = 22 steps): keeping that input gave 49.9 Hz.
    edges = pd.DataFrame({"pre": [0], "post": [1], "weight": [60]})
    p = sim.Params(w_syn=sim.SHIU_W_SYN, th_jump=0.0)
    W = sim.weight_matrix(edges, np.ones(2, dtype=np.int8), 2, p.w_syn)
    post = np.mean(
        [sim.run(W, np.array([0]), 200, 2000, p=p, seed=s).rate()[1] for s in range(10)]
    )
    assert 41.5 < post < 47.5  # ~2 SD of a 10-seed mean around 44.4


def test_silenced_neurons_neither_fire_nor_transmit():
    edges, sign, n = chain([200, 200])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    rates = sim.run(W, np.array([0]), 150, 500, silence=np.array([1])).rate()
    assert rates[0] > 50 and rates[1] == 0 and rates[2] == 0


def test_kernel_reproduces_the_numpy_reference_exactly():
    # the compiled kernel must give the same spikes as the NumPy loop it replaced
    # (tests/reference_sim.py): same operations, order and float rounding
    from reference_sim import run_reference

    rng = np.random.default_rng(1)
    n = 1500
    edges = pd.DataFrame(
        {
            "pre": rng.integers(0, n, 45000),
            "post": rng.integers(0, n, 45000),
            "weight": rng.integers(1, 40, 45000),
        }
    )
    sign = np.where(rng.random(n) < 0.7, 1, -1).astype(np.int8)
    for th_jump, silence in [(0.0, None), (6.0, None), (2.0, np.arange(40, 80))]:
        p = sim.Params(th_jump=th_jump)
        W = sim.weight_matrix(edges, sign, n, p.w_syn)
        a = sim.run(W, np.arange(30), 150, 400, 250, p, 3, silence=silence)
        b = run_reference(W, np.arange(30), 150, 400, 250, p, 3, silence=silence)
        assert a.counts.sum() > 0
        assert np.array_equal(a.counts, b.counts)
        assert np.array_equal(np.isnan(a.first_spike_ms), np.isnan(b.first_spike_ms))
        assert np.allclose(a.first_spike_ms, b.first_spike_ms, equal_nan=True, rtol=0)


def test_download_writes_through_a_part_file_and_checks_the_size(tmp_path, monkeypatch):
    import io

    from flymsg import data as d

    class Response(io.BytesIO):
        def __init__(self, body, length):
            super().__init__(body)
            self.headers = {"Content-Length": str(length)}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    dest = tmp_path / "file.bin"
    monkeypatch.setattr(d.urllib.request, "urlopen", lambda *a, **k: Response(b"xy", 2))
    d.download("http://x/file", dest)
    assert dest.read_bytes() == b"xy" and not dest.with_suffix(".bin.part").exists()

    # a truncated body is rejected, and the partial file is not left behind
    monkeypatch.setattr(d.urllib.request, "urlopen", lambda *a, **k: Response(b"x", 2))
    with pytest.raises(OSError, match="size 1 != 2"):
        d.download("http://x/file2", tmp_path / "file2.bin")
    assert not (tmp_path / "file2.bin.part").exists()


def test_download_retries_a_server_error_but_not_a_404(tmp_path, monkeypatch):
    import io
    import urllib.error

    from flymsg import data as d

    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError("u", 503, "busy", {}, None)

        class R(io.BytesIO):
            headers: ClassVar = {"Content-Length": "1"}

            def __enter__(self):
                return self

            def __exit__(self, *x):
                return False

        return R(b"z")

    monkeypatch.setattr(d.urllib.request, "urlopen", flaky)
    d.download("http://x/f", tmp_path / "f.bin")
    assert len(calls) == 3 and (tmp_path / "f.bin").read_bytes() == b"z"

    monkeypatch.setattr(
        d.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.HTTPError("u", 404, "gone", {}, None)
        ),
    )
    with pytest.raises(urllib.error.HTTPError):
        d.download("http://x/missing", tmp_path / "g.bin")
