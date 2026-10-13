"""Electrical synapses (#85): exact parity with the NumPy reference and the runtime, the
coupling coefficient they produce, and the spiking model untouched without them."""

import numpy as np
import pytest
from reference_sim import run_reference
from scipy import sparse
from test_graded import _network

from flymsg import native, sim
from flymsg.runtime import CpuRuntime


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
    exported = native.export_fixture(
        CpuRuntime(W, np.arange(30), **kw), tmp_path / "f.bin"
    )
    assert exported["schema"].endswith("/v2")


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
    # expm(A (dt - s)) exp(-s / tau_syn) ds and S = int_0^dt expm(A (dt - s)) ds K / tau_m by
    # Gauss-Legendre quadrature, for asymmetric junctions
    from scipy.linalg import expm

    p = sim.Params()
    rng = np.random.default_rng(1)
    i, j = np.array([0, 0, 1, 2]), np.array([1, 2, 3, 3])
    c, back = rng.uniform(0.1, 3.0, 4), rng.uniform(0.1, 3.0, 4)
    gap = sim.Gap(i=i, j=j, coupling=c, coupling_back=back, spike_mv=40.0, spike_ms=1.0)
    nodes, off, mat, _, pos, width, amp = sim.gap_arrays(gap, 4, p)
    assert nodes.tolist() == [0, 1, 2, 3] and off.tolist() == [0, 4]
    assert pos.tolist() == [0, 1, 2, 3] and width == 10
    assert amp.tolist() == [40.0] * 4
    M = mat.reshape(4, 12)
    K = np.zeros((4, 4))
    K[i, j], K[j, i] = c, back
    A = (K - np.diag(1.0 + K.sum(axis=1))) / p.tau_m
    x, w = np.polynomial.legendre.leggauss(40)
    s = (x + 1) * p.dt / 2
    kernel = [
        wk * p.dt / 2 * expm(A * (p.dt - sk)) for sk, wk in zip(s, w, strict=True)
    ]
    Q = sum(k * np.exp(-sk / p.tau_syn) for k, sk in zip(kernel, s, strict=True))
    assert np.allclose(M[:, :4], expm(A * p.dt), rtol=0, atol=1e-15)
    assert np.allclose(M[:, 4:8], Q / p.tau_m, rtol=0, atol=1e-15)
    assert np.allclose(M[:, 8:], sum(kernel) @ K / p.tau_m, rtol=0, atol=1e-15)


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


def _spiking_gap(n=1200, m=400, seed=4):
    rng = np.random.default_rng(seed)
    i, j = rng.integers(0, n, m), rng.integers(0, n, m)
    keep = i != j
    return sim.Gap(
        i=i[keep],
        j=j[keep],
        coupling=rng.uniform(0.05, 1.0, keep.sum()),
        coupling_back=rng.uniform(0.05, 1.0, keep.sum()),
        spike_mv=40.0,
        spike_ms=1.0,
    )


def test_spikelets_and_asymmetry_match_the_reference_bit_for_bit(tmp_path):
    W = _network(400, 12000)
    p = sim.Params()
    gap = _spiking_gap(n=400, m=150)
    steps = 1500
    kicks = sim.poisson_kicks(9, 150.0, p.dt, steps, 30)
    _, rec = run_reference(
        W, np.arange(30), 150, steps * p.dt, None, p, 9, record=np.arange(400), gap=gap
    )
    kw = {"steps": steps, "kicks": kicks, "p": p, "per_bin": 100, "gap": gap}
    rt = CpuRuntime(W, np.arange(30), **kw)
    rt.advance_to(733)
    assert rt.snapshot()["gap_pulse"].any()  # a spike term is crossing at the boundary
    rt.checkpoint(tmp_path / "c.npz")
    resumed = CpuRuntime(W, np.arange(30), **kw)
    resumed.restore(tmp_path / "c.npz")
    for r in (rt, resumed):
        r.advance_to(steps)
        s = r.snapshot()
        for name in ("v", "g", "th"):
            assert np.array_equal(
                s[name].view(np.uint32), rec[name][-1].view(np.uint32)
            ), name


def test_a_spike_crosses_as_a_spikelet():
    # neuron 0 spikes once (one large kick); its passive partner 1 (graded, no release)
    # depolarizes only when the spike term is on, for spike_ms after the spike
    p = sim.Params()
    W = sparse.csc_matrix((2, 2), dtype=np.float32)
    g = sim.Graded(idx=np.array([1]), v_lo=0.0, span=1.0, rate_hz=0.0)
    kick = 10.0 / (p.poisson_scale * p.w_syn)
    kicks = np.r_[[[kick]], np.zeros((199, 1))]
    out = {}
    for spike in (None, 40.0):
        gap = sim.Gap(
            i=np.array([1]),
            j=np.array([0]),
            coupling=0.5,
            spike_mv=spike,
            spike_ms=None if spike is None else 1.0,
        )
        r = sim.run(
            W,
            np.array([0]),
            duration_ms=20,
            p=p,
            kicks=kicks,
            graded=g,
            gap=gap,
            bin_ms=0.1,
        )
        assert r.counts[:, 0].sum() == 1
        out[spike] = r.graded_v[:, 0] - p.v_rest
    lift = out[40.0] - out[None]
    assert np.all(lift[:2] == 0)  # spike at step 1, term from step 2
    assert lift[2:12].min() > 0 and lift[11] == lift.max()
    assert np.all(np.diff(lift[12:40]) < 0)  # then relaxes


def test_per_neuron_spike_amplitudes_and_a_silent_crossing():
    # only neuron 0's spikes cross (40 mV); with no amplitude anywhere there is no term
    p = sim.Params()
    amps = np.zeros(3)
    amps[0] = 40.0
    gap = sim.Gap(
        i=np.array([0, 1]),
        j=np.array([1, 2]),
        coupling=0.3,
        spike_mv=amps,
        spike_ms=1.0,
    )
    *_, width, amp = sim.gap_arrays(gap, 3, p)
    assert width == 10 and amp.tolist() == [40.0, 0.0, 0.0]
    none = sim.Gap(
        i=np.array([0]), j=np.array([1]), coupling=0.3, spike_mv=0.0, spike_ms=1.0
    )
    assert sim.gap_arrays(none, 2, p)[5] == 0
    with pytest.raises(ValueError, match="nonnegative"):
        sim.gap_arrays(
            sim.Gap(
                i=np.array([0]),
                j=np.array([1]),
                coupling=0.3,
                spike_mv=-1.0,
                spike_ms=1.0,
            ),
            2,
            p,
        )
