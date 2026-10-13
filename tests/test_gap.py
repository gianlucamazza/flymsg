"""Electrical synapses (#85): exact parity with the NumPy reference and the runtime, the
coupling coefficient they produce, and the spiking model untouched without them."""

import numpy as np
import pytest
from reference_sim import run_reference
from scipy import sparse
from test_graded import _network

from flymsg import native, sim
from flymsg.runtime import CpuRuntime


def _gap(n=1200, m=3000, seed=4, coupling=0.3):
    rng = np.random.default_rng(seed)
    i, j = rng.integers(0, n, m), rng.integers(0, n, m)
    keep = i != j
    return sim.Gap(i=i[keep], j=j[keep], coupling=coupling)


@pytest.mark.parametrize(
    ("th_jump", "silence"), [(0.0, None), (2.0, np.arange(40, 80))]
)
def test_gap_kernel_reproduces_the_numpy_reference_exactly(th_jump, silence):
    W = _network()
    p = sim.Params(th_jump=th_jump)
    a = sim.run(W, np.arange(30), 150, 300, 200, p, 3, silence=silence, gap=_gap())
    b = run_reference(
        W, np.arange(30), 150, 300, 200, p, 3, silence=silence, gap=_gap()
    )
    plain = sim.run(W, np.arange(30), 150, 300, 200, p, 3, silence=silence)
    assert a.counts.sum() > 0
    assert not np.array_equal(a.counts, plain.counts)
    assert np.array_equal(a.counts, b.counts)
    assert np.allclose(a.first_spike_ms, b.first_spike_ms, equal_nan=True, rtol=0)


def test_gap_and_graded_together_match_the_reference():
    from test_graded import _graded

    W = _network()
    p = sim.Params()
    g = _graded(np.r_[0:10, 50:120], p)
    a = sim.run(W, np.arange(30), 150, 300, 200, p, 3, graded=g, gap=_gap())
    b = run_reference(W, np.arange(30), 150, 300, 200, p, 3, graded=g, gap=_gap())
    assert np.array_equal(a.counts, b.counts)
    assert np.array_equal(a.graded_v, b.graded_v)


def test_empty_gap_changes_nothing():
    W = _network()
    p = sim.Params()
    a = sim.run(W, np.arange(30), 150, 300, 200, p, 3)
    empty = sim.Gap(i=np.empty(0, int), j=np.empty(0, int), coupling=1.0)
    assert np.array_equal(
        a.counts, sim.run(W, np.arange(30), 150, 300, 200, p, 3, gap=empty).counts
    )


def test_two_coupled_cells_give_the_coupling_coefficient():
    # a steady depolarization of cell 0 reaches cell 1 scaled by c / (1 + c); cells are
    # graded so that neither spikes (no release: rate 0)
    p = sim.Params()
    W = sparse.csc_matrix((2, 2), dtype=np.float32)
    c = 0.25
    g = sim.Graded(idx=np.array([0, 1]), v_lo=0.0, span=1.0, rate_hz=0.0)
    kick = 10.0 * (1 - np.exp(-p.dt / p.tau_m)) / (p.poisson_scale * p.w_syn)
    r = sim.run(
        W,
        np.array([0]),
        duration_ms=500,
        p=p,
        kicks=np.full((5000, 1), kick),
        graded=g,
        gap=sim.Gap(i=np.array([0]), j=np.array([1]), coupling=c),
    )
    d0, d1 = r.graded_v[-1] - p.v_rest
    assert d1 / d0 == pytest.approx(c / (1 + c), rel=1e-2)


def test_gap_runtime_chunks_and_checkpoints_match_the_run(tmp_path):
    W = _network()
    p = sim.Params()
    steps = 3000
    kicks = sim.poisson_kicks(5, 150.0, p.dt, 2000, 30)
    ref = sim.run(
        W, np.arange(30), duration_ms=steps * p.dt, p=p, kicks=kicks, gap=_gap()
    )
    kw = {"steps": steps, "kicks": kicks, "p": p, "per_bin": 100, "gap": _gap()}
    rt = CpuRuntime(W, np.arange(30), **kw)
    rt.advance_to(777)
    rt.checkpoint(tmp_path / "c.npz")
    resumed = CpuRuntime(W, np.arange(30), **kw)
    resumed.restore(tmp_path / "c.npz")
    for r in (rt, resumed):
        r.advance_to(steps)
        assert np.array_equal(r.result().counts, ref.counts)
    plain = CpuRuntime(W, np.arange(30), steps=steps, kicks=kicks, p=p, per_bin=100)
    with pytest.raises(ValueError, match="incompatible"):
        plain.restore(tmp_path / "c.npz")
    with pytest.raises(ValueError, match="electrical"):
        native.export_fixture(rt.__class__(W, np.arange(30), **kw), tmp_path / "f.bin")


@pytest.mark.parametrize(
    "bad",
    [
        {"i": np.array([1]), "j": np.array([1]), "coupling": 0.1},
        {"i": np.array([1]), "j": np.array([9]), "coupling": 0.1},
        {"i": np.array([1]), "j": np.array([2]), "coupling": -0.1},
        {"i": np.array([1]), "j": np.array([2]), "coupling": np.inf},
        {"i": np.array([1.0]), "j": np.array([2]), "coupling": 0.1},
        {"i": np.array([1]), "j": np.array([2]), "coupling": 200.0},
    ],
)
def test_gap_parameters_are_checked(bad):
    with pytest.raises(ValueError):
        sim.gap_arrays(sim.Gap(**bad), 5, sim.Params())
