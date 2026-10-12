"""M2: the body's movement changes the next input; the controls hold it fixed."""

import numpy as np
import pytest
from test_core import chain

from flymsg import loop, sim

LOOM = loop.Looming(radius_m=0.01, start_distance_m=0.1, speed_m_s=1.0)
TRANS = loop.Transducer(gain_hz_per_rad_s=20.0, max_rate_hz=500.0)


def _run(mode, gain=1e-3, replay=None, seed=3):
    edges, sign, n = chain([400])
    p = sim.Params()
    W = sim.weight_matrix(edges, sign, n, p.w_syn)
    return loop.run_loop(
        W, np.array([0]), 1, looming=LOOM, transducer=TRANS, decoder_gain_n=gain,
        mass_kg=1e-6, duration_ms=80.0, seed=seed, mode=mode, replay_counts=replay, p=p,
    )  # fmt: skip


def test_a_jump_changes_the_input_that_follows():
    closed, fixed = _run("closed"), _run("disconnected")
    lift = int(np.argmax(closed["height_m"] > 0))
    assert closed["height_m"][lift] > 0
    # the input reads the pose at the start of a period: equal until the body has moved
    assert np.array_equal(closed["rate_hz"][: lift + 1], fixed["rate_hz"][: lift + 1])
    assert closed["seen_height_m"][lift + 1] == closed["height_m"][lift]
    assert not np.allclose(closed["rate_hz"][lift + 1 :], fixed["rate_hz"][lift + 1 :])


def test_disconnected_input_ignores_the_body():
    a, b = _run("disconnected", gain=0.0), _run("disconnected", gain=1e-3)
    assert (
        b["height_m"].max() > 0 and a["height_m"].max() == 0
    )  # the body did move in b
    assert np.array_equal(a["input_counts"], b["input_counts"])
    assert not b["seen_height_m"].any()


def test_replaying_the_recorded_input_reproduces_the_spikes():
    closed = _run("closed")
    again = _run("replay", replay=closed["input_counts"])
    assert np.array_equal(again["motor_spikes"], closed["motor_spikes"])
    assert np.array_equal(again["result"].counts, closed["result"].counts)


def test_shuffled_input_keeps_the_rates_and_breaks_their_order():
    fixed, mixed = _run("disconnected"), _run("shuffled")
    assert np.allclose(np.sort(fixed["rate_hz"]), np.sort(mixed["rate_hz"]))
    assert not np.allclose(fixed["rate_hz"], mixed["rate_hz"])


def test_bad_modes_and_replays_are_refused():
    with pytest.raises(ValueError, match="mode"):
        _run("other")
    with pytest.raises(ValueError, match="replay"):
        _run("replay", replay=np.zeros((5, 1), dtype=np.int64))
