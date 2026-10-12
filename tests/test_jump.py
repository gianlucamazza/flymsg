"""M1: a jump body through the M0 contract, driven by an engineered decoder."""

import numpy as np
import pytest

from flymsg import jump
from flymsg.embodiment import ContractError, MotorCommand, Provenance

PROV = Provenance("synthetic", "a" * 64, "fixture", 0)


def _run(steps, gain=1e-3, mass=1e-6, duration_us=500_000):
    return jump.run_jump(
        np.asarray(steps, dtype=np.int64), body_id=7, gain_n=gain, mass_kg=mass,
        duration_us=duration_us, provenance=PROV,
    )  # fmt: skip


def test_no_spike_no_motion():
    out = _run([])
    assert out["takeoff_ms"] is None and out["max_height_m"] == 0.0
    assert all(out["contact"])


def test_an_impulse_lifts_the_body_and_it_lands_again():
    out = _run([0])
    # 1 ms at F/m - g, then free flight: height peaks at v^2 / 2g
    v = (1e-3 / 1e-6 - 9.81) * 1e-3
    assert out["max_height_m"] == pytest.approx(v * v / (2 * 9.81), rel=0.02)
    assert out["takeoff_ms"] == pytest.approx(1.0)
    assert out["contact"][-1]  # back on the floor by 500 ms
    assert min(out["height_m"]) == 0.0  # never below the floor


def test_a_force_below_weight_does_not_lift():
    out = _run([0, 10, 20], gain=0.5e-5)  # below m g = 9.81e-6 N
    assert out["max_height_m"] == 0.0


def test_replay_is_deterministic_and_labelled():
    a, b = _run([0, 30, 60]), _run([0, 30, 60])
    assert a == b
    assert a["decoder"] == jump.ENGINEERED and "not an experimentally" in a["note"]


def test_late_spikes_are_counted_not_dropped_silently():
    out = _run([0, 4995], duration_us=500_000)  # 499.5 ms is after the last command
    assert out["spikes"] == 2 and out["spikes_after_last_command"] == 1


def test_floor_contact_never_penetrates():
    body = jump.JumpBody(mass_kg=1e-6)
    state = body.step(MotorCommand(0, 0.0, ()), 1000)
    assert state.position_m == 0.0 and state.velocity_m_s == 0.0
    with pytest.raises(ContractError):
        jump.JumpBody(mass_kg=0.0)
