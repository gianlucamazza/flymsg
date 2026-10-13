"""Electrical synapses (#85): exact parity with the NumPy reference and the runtime, the
coupling coefficient they produce, and the spiking model untouched without them."""

import numpy as np
import pytest
from reference_sim import run_reference
from scipy import sparse
from test_graded import _network

from flymsg import native, sim
from flymsg.runtime import CpuRuntime


@pytest.mark.parametrize("conductance", [0.0, 4.0])
def test_refractory_partner_is_clamped_throughout_the_exact_step(conductance):
    p, c = sim.Params(), 5.0
    rt = CpuRuntime(
        sparse.csc_matrix((2, 2), dtype=np.float32),
        np.array([], dtype=int),
        steps=1,
        kicks=np.zeros((0, 0), dtype=np.int32),
        p=p,
        per_bin=1,
        gap=sim.Gap(np.array([0]), np.array([1]), c),
    )
    rt._state["v"][0] = p.v_rest + 5
    rt._state["g"][:] = [conductance, 99.0]
    rt._state["ref_until"][1] = 100
    rt.advance_to(1)
    decay = -(1 + c) / p.tau_m
    exact = p.v_rest + 5 * np.exp(decay * p.dt)
    exact += (
        conductance
        / p.tau_m
        * (np.exp(decay * p.dt) - np.exp(-p.dt / p.tau_syn))
        / (decay + 1 / p.tau_syn)
    )
    state = rt.snapshot()
    assert state["v"][0] == np.float32(exact)
    assert state["v"][1] == p.v_rest and state["g"][1] == 99.0


def test_all_clamped_cells_and_release_at_integer_boundary():
    p = sim.Params()
    rt = CpuRuntime(
        sparse.csc_matrix((3, 3), dtype=np.float32),
        np.array([], dtype=int),
        steps=3,
        kicks=np.zeros((0, 0), dtype=np.int32),
        p=p,
        per_bin=1,
        gap=sim.Gap(np.array([0, 1]), np.array([1, 2]), 0.4),
    )
    rt._state["ref_until"][:] = 2
    rt._state["g"][:] = 3.0
    rt.advance_to(2)
    assert np.all(rt.snapshot()["v"] == p.v_rest)
    assert np.all(rt.snapshot()["g"] == 3.0)
    rt.advance_to(3)
    assert np.all(rt.snapshot()["v"] > p.v_rest)
    assert np.all(rt.snapshot()["g"] < 3.0)


def test_old_electrical_semantics_are_refused_without_mutating_state(tmp_path):
    import json

    rt = CpuRuntime(
        sparse.csc_matrix((2, 2), dtype=np.float32),
        np.array([], dtype=int),
        steps=2,
        kicks=np.zeros((0, 0), dtype=np.int32),
        per_bin=1,
        gap=sim.Gap(np.array([0]), np.array([1]), 0.4),
    )
    path = tmp_path / "checkpoint.npz"
    rt.checkpoint(path)
    with np.load(path, allow_pickle=False) as doc:
        arrays = {k: doc[k] for k in doc.files}
    meta = json.loads(str(arrays["metadata"]))
    meta["semantics"] = "flymsg.lif/ordered-f32-v1"
    arrays["metadata"] = np.array(json.dumps(meta))
    np.savez(path, **arrays)
    before = rt.snapshot()
    with pytest.raises(ValueError, match="incompatible"):
        rt.restore(path)
    for name, value in before.items():
        np.testing.assert_array_equal(rt.snapshot()[name], value)


def test_refractory_map_cache_has_a_byte_budget(monkeypatch):
    from flymsg import electrical

    with electrical._lock:
        electrical._maps.clear()
        electrical._bytes = 0
    monkeypatch.setattr(electrical, "CACHE_BYTES", 64)
    A = np.diag([-0.2, -0.3])
    for i in range(6):
        electrical.clamped_map(
            A,
            np.array([False, bool(i % 2)]),
            np.array([0.1, 20.0, 5.0]),
            np.array([i, 0, 0, 0], dtype=np.uint64),
        )
        assert electrical._bytes <= electrical.CACHE_BYTES


def _gap(n=1200, m=400, seed=4, coupling=0.3):
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
    # the drive arrives as a kick at the end of each step, which the partner sees one step
    # later: the ratio is c / (1 + c) up to that discretisation of the input
    assert d1 / d0 == pytest.approx(c / (1 + c), rel=5e-3)


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
    ],
)
def test_gap_parameters_are_checked(bad):
    with pytest.raises(ValueError):
        sim.gap_arrays(sim.Gap(**bad), 5, sim.Params())


def test_coupled_potentials_follow_the_exact_solution():
    # two free cells, one kicked once: the mean relaxes with tau_m and the difference with
    # tau_m / (1 + 2c), whatever the coupling strength
    p = sim.Params()
    W = sparse.csc_matrix((2, 2), dtype=np.float32)
    g = sim.Graded(idx=np.array([0, 1]), v_lo=0.0, span=1.0, rate_hz=0.0)
    for c in (0.1, 5.0):
        kick = 20.0 / (p.poisson_scale * p.w_syn)
        r = sim.run(
            W,
            np.array([0]),
            duration_ms=20,
            p=p,
            kicks=np.r_[[[kick]], np.zeros((199, 1))],
            graded=g,
            gap=sim.Gap(i=np.array([0]), j=np.array([1]), coupling=c),
            bin_ms=0.1,
        )
        t = (np.arange(200) + 1) * p.dt - p.dt  # potentials at the end of each step
        d = r.graded_v - p.v_rest
        mean = 10.0 * np.exp(-t / p.tau_m)
        diff = 20.0 * np.exp(-t * (1 + 2 * c) / p.tau_m)
        assert np.allclose(d[:, 0], mean + diff / 2, atol=1e-4)
        assert np.allclose(d[:, 1], mean - diff / 2, atol=1e-4)


def test_step_matrices_match_quadrature_of_the_coupled_equation():
    # independent of the block form: P = expm(A dt), Q = (1/tau_m) int_0^dt
    # expm(A (dt - s)) exp(-s / tau_syn) ds by Gauss-Legendre quadrature
    from scipy.linalg import expm

    p = sim.Params()
    rng = np.random.default_rng(1)
    i, j = np.array([0, 0, 1, 2]), np.array([1, 2, 3, 3])
    c = rng.uniform(0.1, 3.0, 4)
    nodes, off, mat, _ = sim.gap_arrays(sim.Gap(i=i, j=j, coupling=c), 4, p)
    assert nodes.tolist() == [0, 1, 2, 3] and off.tolist() == [0, 4]
    M = mat.reshape(4, 8)
    K = np.zeros((4, 4))
    K[i, j] = K[j, i] = c
    A = (K - np.diag(1.0 + K.sum(axis=1))) / p.tau_m
    x, w = np.polynomial.legendre.leggauss(40)
    s = (x + 1) * p.dt / 2
    Q = (
        sum(
            wk * p.dt / 2 * expm(A * (p.dt - sk)) * np.exp(-sk / p.tau_syn)
            for sk, wk in zip(s, w, strict=True)
        )
        / p.tau_m
    )
    assert np.allclose(M[:, :4], expm(A * p.dt), rtol=0, atol=1e-15)
    assert np.allclose(M[:, 4:], Q, rtol=0, atol=1e-15)


def test_an_oversized_or_overflowing_coupling_is_refused(monkeypatch):
    monkeypatch.setattr(sim, "MAX_GAP_COMPONENT", 2)
    with pytest.raises(ValueError, match="exceeds 2"):
        sim.gap_arrays(
            sim.Gap(i=np.array([0, 1]), j=np.array([1, 2]), coupling=1.0),
            3,
            sim.Params(),
        )
    with pytest.raises(ValueError, match="nonfinite"):
        sim.gap_arrays(
            sim.Gap(i=np.array([0]), j=np.array([1]), coupling=1e308), 2, sim.Params()
        )
