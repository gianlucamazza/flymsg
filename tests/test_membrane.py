"""Per-neuron membrane parameters (`sim.Membrane`): absent, the model is unchanged bit for
bit; present, the kernel, the NumPy oracle and the incremental runtime agree exactly."""

import numpy as np
import pytest
from reference_sim import run_reference
from scipy import sparse

from flymsg import sim
from flymsg.native import export_fixture
from flymsg.runtime import CpuRuntime


def random_network(n=60, density=0.12, seed=3):
    rng = np.random.default_rng(seed)
    mask = rng.random((n, n)) < density
    np.fill_diagonal(mask, False)
    counts = rng.integers(1, 120, size=(n, n)) * mask
    signs = np.where(rng.random(n) < 0.75, 1, -1)
    return sparse.csc_matrix((counts * signs[None, :] * 0.275).astype(np.float32))


def random_membrane(n, k=25, seed=5):
    rng = np.random.default_rng(seed)
    idx = rng.choice(n, size=k, replace=False)
    v_rest = rng.uniform(-65.0, -48.0, k)
    return sim.Membrane(
        idx=idx,
        tau_m=rng.uniform(5.0, 40.0, k),
        tau_syn=rng.uniform(1.0, 4.0, k),
        v_rest=v_rest,
        v_th=v_rest + rng.uniform(3.0, 12.0, k),
    )


STIM = np.array([0, 1, 2, 3])


def test_params_values_given_per_neuron_change_nothing():
    W, p = random_network(), sim.Params()
    n = W.shape[0]
    idx = np.arange(n)
    same = sim.Membrane(
        idx=idx,
        tau_m=np.full(n, p.tau_m),
        tau_syn=np.full(n, p.tau_syn),
        v_rest=np.full(n, p.v_rest),
        v_th=np.full(n, p.v_th),
    )
    a = sim.run(W, STIM, 200, 300, seed=1)
    b = sim.run(W, STIM, 200, 300, seed=1, membrane=same)
    assert a.counts.sum() > 0
    np.testing.assert_array_equal(a.counts, b.counts)
    np.testing.assert_array_equal(a.first_spike_ms, b.first_spike_ms)
    # and the arrays hold exactly the scalar constants
    em, es, gv, rest, th = sim.membrane_arrays(None, n, p)
    c = sim._constants(p)
    for arr, scalar in ((em, c[0]), (es, c[1]), (gv, c[2]), (rest, c[4]), (th, c[5])):
        assert arr.dtype == np.float32 and np.all(arr == scalar)


def test_kernel_matches_the_oracle_with_per_neuron_membranes():
    W = random_network()
    n = W.shape[0]
    # a minority of neurons takes the scalar loops with a fix-up, a majority the
    # per-neuron loops; both must match the oracle
    for membrane in (random_membrane(n), random_membrane(n, k=n * 3 // 4)):
        for seed in (0, 1):
            got = sim.run(W, STIM, 180, 300, seed=seed, membrane=membrane)
            want = run_reference(W, STIM, 180, 300, seed=seed, membrane=membrane)
            assert got.counts.sum() > 0
            np.testing.assert_array_equal(got.counts, want.counts)
            np.testing.assert_array_equal(got.first_spike_ms, want.first_spike_ms)


def test_runtime_in_chunks_matches_run_and_names_the_membrane_in_its_identity():
    W = random_network()
    n, p = W.shape[0], sim.Params()
    membrane = random_membrane(n)
    steps = 3000
    kicks = sim.poisson_kicks(4, 180, p.dt, steps, STIM.size)
    want = sim.run(W, STIM, duration_ms=300, kicks=kicks, membrane=membrane)
    rt = CpuRuntime(
        W,
        STIM,
        steps=steps,
        kicks=kicks,
        membrane=membrane,
        input_encoding="counts",
    )
    for t in (700, 1900, steps):
        rt.advance_to(t)
    np.testing.assert_array_equal(rt.result().counts, want.counts)
    plain = CpuRuntime(W, STIM, steps=steps, kicks=kicks, input_encoding="counts")
    assert plain._identity != rt._identity
    assert np.all(plain.snapshot()["v"] == np.float32(p.v_rest))
    rest = (
        rt.snapshot()
    )  # after the run; a fresh runtime starts each neuron at its rest
    fresh = CpuRuntime(
        W,
        STIM,
        steps=steps,
        kicks=kicks,
        membrane=membrane,
        input_encoding="counts",
    )
    np.testing.assert_array_equal(
        fresh.snapshot()["v"][membrane.idx], np.float32(membrane.v_rest)
    )
    assert rest["v"].shape == (n,)


def test_a_lower_threshold_lets_a_weak_input_through():
    # 0 drives 1 and 2 through 20 synapses; only 2 has a threshold 2 mV above its rest
    W = sparse.csc_matrix(
        ([20 * 0.192, 20 * 0.192], ([1, 2], [0, 0])), shape=(3, 3), dtype=np.float32
    )
    membrane = sim.Membrane(
        idx=np.array([2]),
        tau_m=np.array([20.0]),
        tau_syn=np.array([5.0]),
        v_rest=np.array([-52.0]),
        v_th=np.array([-50.0]),
    )
    rates = sim.run(W, np.array([0]), 150, 500, membrane=membrane).rate()
    assert rates[0] > 50 and rates[1] == 0 and rates[2] > 0


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("idx", np.array([0, 0]), "unique"),
        ("idx", np.array([0, 99]), "inside"),
        ("tau_m", np.array([5.0, 0.0]), "positive"),
        ("tau_syn", np.array([20.0, 5.0]), "tau_m != tau_syn"),
        ("v_th", np.array([-60.0, -40.0]), "above rest"),
        ("v_rest", np.array([np.nan, -52.0]), "finite"),
    ],
)
def test_invalid_membranes_are_refused(field, value, message):
    base = {
        "idx": np.array([0, 1]),
        "tau_m": np.array([20.0, 20.0]),
        "tau_syn": np.array([5.0, 5.0]),
        "v_rest": np.array([-52.0, -52.0]),
        "v_th": np.array([-45.0, -45.0]),
    }
    base[field] = value
    with pytest.raises(ValueError, match=message):
        sim.membrane_arrays(sim.Membrane(**base), 10, sim.Params())


def test_coupled_neurons_refuse_a_membrane_and_native_exports_uncoupled(tmp_path):
    W = random_network(n=10)
    membrane = sim.Membrane(
        idx=np.array([4]),
        tau_m=np.array([10.0]),
        tau_syn=np.array([3.0]),
        v_rest=np.array([-55.0]),
        v_th=np.array([-48.0]),
    )
    gap = sim.Gap(i=np.array([4]), j=np.array([5]), coupling=np.array([0.1]))
    with pytest.raises(ValueError, match="electrically coupled"):
        sim.run(W, STIM, 100, 50, gap=gap, membrane=membrane)
    kicks = np.ones((100, STIM.size), dtype=np.int64)
    with pytest.raises(ValueError, match="electrically coupled"):
        CpuRuntime(
            W,
            STIM,
            steps=100,
            kicks=kicks,
            gap=gap,
            membrane=membrane,
            input_encoding="counts",
        )
    rt = CpuRuntime(
        W,
        STIM,
        steps=100,
        kicks=kicks,
        membrane=membrane,
        input_encoding="counts",
    )
    assert (
        export_fixture(rt, tmp_path / "fixture.bin")["schema"]
        == "flymsg.native_fixture/v4"
    )
