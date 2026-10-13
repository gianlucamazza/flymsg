"""Graded (non-spiking) neurons (#97): exact parity with the NumPy reference and the runtime,
and the spiking model untouched without them."""

import numpy as np
import pandas as pd
import pytest
from reference_sim import run_reference

from flymsg import native, sim
from flymsg.runtime import CpuRuntime


def _network(n=1200, m=36000, seed=2):
    rng = np.random.default_rng(seed)
    edges = pd.DataFrame(
        {
            "pre": rng.integers(0, n, m),
            "post": rng.integers(0, n, m),
            "weight": rng.integers(1, 40, m),
        }
    )
    sign = np.where(rng.random(n) < 0.7, 1, -1).astype(np.int8)
    return sim.weight_matrix(edges, sign, n, sim.Params().w_syn)


def _graded(idx, p):
    # tonic at rest: release at v_rest is half the saturated one
    return sim.Graded(
        idx=idx, v_lo=p.v_rest - 10.0, span=20.0, rate_hz=np.linspace(50, 300, idx.size)
    )


def test_graded_kernel_reproduces_the_numpy_reference_exactly():
    W = _network()
    p = sim.Params()
    # graded neurons include stimulated (0..9) and silenced (60..69) ones, in shuffled order
    idx = np.random.default_rng(0).permutation(np.r_[0:10, 50:120, 400:460])
    for silence in (None, np.arange(60, 100)):
        a = sim.run(
            W,
            np.arange(30),
            150,
            300,
            200,
            p,
            3,
            silence=silence,
            graded=_graded(idx, p),
        )
        b = run_reference(
            W,
            np.arange(30),
            150,
            300,
            200,
            p,
            3,
            silence=silence,
            graded=_graded(idx, p),
        )
        assert a.counts.sum() > 0
        assert a.counts[:, idx].sum() == 0
        assert np.array_equal(a.counts, b.counts)
        assert np.allclose(a.first_spike_ms, b.first_spike_ms, equal_nan=True, rtol=0)
        assert np.array_equal(a.graded_v, b.graded_v)


def test_without_graded_neurons_nothing_changes():
    W = _network()
    p = sim.Params()
    a = sim.run(W, np.arange(30), 150, 300, 200, p, 3)
    b = sim.run(
        W, np.arange(30), 150, 300, 200, p, 3, graded=_graded(np.empty(0, int), p)
    )
    assert a.graded_v is None
    assert np.array_equal(a.counts, b.counts)


def test_tonic_release_drives_a_target_and_inhibition_lowers_it():
    # neuron 0 graded, at rest above v_lo: it excites 1 without input; hyperpolarising 0
    # through an inhibitory input (2 -> 0) silences 1
    p = sim.Params()
    edges = pd.DataFrame({"pre": [0, 2], "post": [1, 0], "weight": [100, 200]})
    W = sim.weight_matrix(edges, np.array([1, 1, -1], dtype=np.int8), 3, p.w_syn)
    g = sim.Graded(idx=np.array([0]), v_lo=p.v_rest - 10.0, span=20.0, rate_hz=200.0)
    rest = sim.run(W, np.array([2]), 0.0, 200, p=p, graded=g, bin_ms=10)
    lit = sim.run(W, np.array([2]), 400.0, 200, p=p, graded=g, bin_ms=10)
    assert rest.counts[:, 0].sum() == lit.counts[:, 0].sum() == 0
    assert rest.rate(100)[1] > 0
    assert lit.rate(100)[1] < rest.rate(100)[1]
    assert lit.graded_v[-1, 0] < rest.graded_v[-1, 0]


def test_graded_runtime_chunks_and_checkpoints_match_the_run(tmp_path):
    W = _network()
    p = sim.Params()
    idx = np.r_[0:10, 50:120]
    steps = 3000
    kicks = sim.poisson_kicks(5, 150.0, p.dt, 2000, 30)
    ref = sim.run(
        W,
        np.arange(30),
        duration_ms=steps * p.dt,
        p=p,
        kicks=kicks,
        graded=_graded(idx, p),
    )
    kw = {
        "steps": steps,
        "kicks": kicks,
        "p": p,
        "per_bin": 100,
        "graded": _graded(idx, p),
    }
    rt = CpuRuntime(W, np.arange(30), **kw)
    rt.advance_to(1234)
    rt.checkpoint(tmp_path / "c.npz")
    resumed = CpuRuntime(W, np.arange(30), **kw)
    resumed.restore(tmp_path / "c.npz")
    for r in (rt, resumed):
        r.advance_to(steps)
        out = r.result()
        assert np.array_equal(out.counts, ref.counts)
        assert np.array_equal(out.graded_v, ref.graded_v)
    plain = CpuRuntime(W, np.arange(30), steps=steps, kicks=kicks, p=p, per_bin=100)
    with pytest.raises(ValueError, match="incompatible"):
        plain.restore(tmp_path / "c.npz")
    assert "graded_ring" not in plain.snapshot()


def test_native_refuses_graded_neurons(tmp_path):
    W = _network(200, 4000)
    p = sim.Params()
    rt = CpuRuntime(
        W,
        np.array([0]),
        steps=100,
        kicks=np.zeros((100, 1), dtype=np.int64),
        p=p,
        graded=_graded(np.array([3, 4]), p),
    )
    with pytest.raises(ValueError, match="graded"):
        native.export_fixture(rt, tmp_path / "f.bin")


@pytest.mark.parametrize(
    "bad",
    [
        {"idx": np.array([1, 1]), "v_lo": 0.0, "span": 1.0, "rate_hz": 1.0},
        {"idx": np.array([5]), "v_lo": 0.0, "span": 1.0, "rate_hz": 1.0},
        {"idx": np.array([1]), "v_lo": 0.0, "span": 0.0, "rate_hz": 1.0},
        {"idx": np.array([1]), "v_lo": 0.0, "span": 1.0, "rate_hz": -1.0},
        {"idx": np.array([1]), "v_lo": np.nan, "span": 1.0, "rate_hz": 1.0},
        {"idx": np.array([1.0]), "v_lo": 0.0, "span": 1.0, "rate_hz": 1.0},
        {"idx": np.array([1]), "v_lo": 0.0, "span": 1e-50, "rate_hz": 1.0},
        {"idx": np.array([1]), "v_lo": 1e50, "span": 1.0, "rate_hz": 1.0},
        {"idx": np.array([1]), "v_lo": 0.0, "span": 1.0, "rate_hz": 1e50},
    ],
)
def test_graded_parameters_are_checked(bad):
    with pytest.raises(ValueError):
        sim.graded_arrays(sim.Graded(**bad), 5, 0.1)


def test_every_state_bit_matches_the_reference_with_graded_and_gap():
    # potentials, conductances and thresholds of every neuron after every step, not only
    # spikes: kernel (through the runtime) against the NumPy reference
    from test_gap import _gap

    W = _network(400, 12000)
    p = sim.Params(th_jump=2.0)
    idx = np.r_[0:10, 50:90]
    steps = 1500
    kicks = sim.poisson_kicks(9, 150.0, p.dt, steps, 30)
    g, gap = _graded(idx, p), _gap(n=400, m=150)
    _, rec = run_reference(
        W,
        np.arange(30),
        150,
        steps * p.dt,
        None,
        p,
        9,
        record=np.arange(400),
        graded=g,
        gap=gap,
    )
    rt = CpuRuntime(
        W, np.arange(30), steps=steps, kicks=kicks, p=p, per_bin=100, graded=g, gap=gap
    )
    for stop in (1, 7, 500, steps):
        rt.advance_to(stop)
        s = rt.snapshot()
        for name in ("v", "g", "th"):
            assert np.array_equal(
                s[name].view(np.uint32), rec[name][stop - 1].view(np.uint32)
            ), (name, stop)
