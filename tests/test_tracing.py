"""State tracing records without changing spikes, and matches the NumPy oracle."""

import warnings

import numpy as np
import pytest
from reference_sim import run_reference
from test_core import chain

from flymsg import sim, tracing


def _net(th_jump=0.0):
    edges, sign, n = chain([400, 400, 400], signs=[1, 1, -1, 1])
    p = sim.Params(th_jump=th_jump)
    return sim.weight_matrix(edges, sign, n, p.w_syn), p


@pytest.mark.parametrize("th_jump", [0.0, 2.0])
def test_recording_leaves_the_run_unchanged(th_jump):
    W, p = _net(th_jump)
    args = (W, np.array([0]), 150.0, 300.0, 200.0, p, 5)
    ref = sim.run(*args, silence=np.array([3]))
    trace, got = tracing.record(
        W,
        np.array([0]),
        np.array([1, 2, 3]),
        rate_hz=150.0,
        duration_ms=300.0,
        stim_ms=200.0,
        seed=5,
        p=p,
        silence=np.array([3]),
    )
    assert np.array_equal(got.counts, ref.counts)
    assert np.array_equal(got.first_spike_ms, ref.first_spike_ms, equal_nan=True)
    assert trace.spikes.shape == (3000, 3)
    assert trace.spikes[:, 2].sum() == 0  # the silenced neuron never fires
    assert trace.spikes[:, 0].sum() == got.counts[:, 1].sum()


@pytest.mark.parametrize("th_jump", [0.0, 2.0])
def test_states_match_the_numpy_oracle(th_jump):
    W, p = _net(th_jump)
    watch = np.array([0, 1, 2, 3])
    ref, states = run_reference(
        W, np.array([0]), 150.0, 200.0, 150.0, p, 9, record=watch
    )
    trace, got = tracing.record(
        W,
        np.array([0]),
        watch,
        rate_hz=150.0,
        duration_ms=200.0,
        stim_ms=150.0,
        seed=9,
        p=p,
    )
    assert np.array_equal(got.counts, ref.counts)
    for k in ("v", "g", "th"):
        assert np.array_equal(getattr(trace, k), states[k]), k  # bit for bit
    assert (trace.v[:, 1] > p.v_rest).any()  # the second neuron is actually driven


def test_subsampling_keeps_every_nth_sample_and_full_spikes():
    W, p = _net()
    kw = {"rate_hz": 150.0, "duration_ms": 100.0, "stim_ms": None, "seed": 2, "p": p}
    full, _ = tracing.record(W, np.array([0]), np.array([1]), **kw)
    sub, _ = tracing.record(W, np.array([0]), np.array([1]), every=10, **kw)
    assert np.array_equal(sub.v, full.v[9::10])
    assert np.array_equal(sub.spikes, full.spikes)
    assert sub.times_ms[0] == pytest.approx(1.0)


def test_input_and_refractory_are_recorded():
    W, p = _net()
    trace, _ = tracing.record(
        W,
        np.array([0]),
        np.array([0, 1]),
        rate_hz=500.0,
        duration_ms=50.0,
        stim_ms=20.0,
        seed=1,
        p=p,
    )
    assert (
        trace.input_counts[:200, 0].sum() > 0 and trace.input_counts[200:, 0].sum() == 0
    )
    assert not trace.input_counts[:, 1].any()  # not stimulated
    spike_steps = np.flatnonzero(trace.spikes[:, 1])
    assert spike_steps.size and trace.refractory[spike_steps[0], 1]


def test_large_requests_warn_and_huge_ones_are_refused(monkeypatch):
    W, p = _net()
    monkeypatch.setattr(tracing, "WARN_VALUES", 100)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tracing.record(
            W,
            np.array([0]),
            np.array([1]),
            rate_hz=1.0,
            duration_ms=20.0,
            stim_ms=None,
            seed=0,
            p=p,
        )
    assert any("recording" in str(w.message) for w in caught)
    monkeypatch.setattr(tracing, "MAX_VALUES", 100)
    with pytest.raises(ValueError, match="limit"):
        tracing.record(
            W,
            np.array([0]),
            np.array([1]),
            rate_hz=1.0,
            duration_ms=20.0,
            stim_ms=None,
            seed=0,
            p=p,
        )
