"""Kinematic planar body: rest, analytic steering, checkpoint (DN-arena ADR)."""

import math

import pytest

from flymsg.embodiment import ContractError
from flymsg.pose import IDENTITY, SCHEMA, ActuatorRef

SOURCE = "test kinematic planar"


def body(z_m=1e-3, roll_rad=0.0, pitch_rad=0.0, source=SOURCE):
    from flymsg.arena import Arena

    return Arena(z_m=z_m, roll_rad=roll_rad, pitch_rad=pitch_rad, source=source)


def yaw_q(rad):
    from flymsg.pose import Quat

    h = rad / 2
    return Quat.of((math.cos(h), 0.0, 0.0, math.sin(h)))


def close(a, b, tol=1e-12):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def test_zero_command_holds_the_lock_constants():
    arena = body(z_m=2e-3, roll_rad=0.1, pitch_rad=-0.05)
    state = arena.reset()
    assert state.time_us == 0
    assert pose_parent_child(state)
    assert state.pose.position_m == (0.0, 0.0, 2e-3)
    assert SCHEMA == "flymsg.embodiment/v2"
    stepped, contacts = arena.step((), 1000)
    assert stepped.time_us == 1000
    assert stepped.pose.position_m == (0.0, 0.0, 2e-3)
    assert stepped.linear_velocity_m_s == (0.0, 0.0, 0.0)
    assert stepped.angular_velocity_rad_s == (0.0, 0.0, 0.0)
    assert contacts == ()
    # roll and pitch stay; heading is still zero
    assert stepped.pose.orientation == state.pose.orientation
    assert state.pose.orientation != IDENTITY


def pose_parent_child(state):
    return (state.pose.parent, state.pose.child) == ("world", "body")


def test_constant_forward_is_a_straight_line():
    arena = body()
    arena.reset()
    yaw, forward = arena.actuators["yaw"], arena.actuators["forward"]
    assert (yaw.unit, forward.unit) == ("rad/s", "m/s")
    assert arena.compiled == {"yaw": 0, "forward": 1}
    state, _ = arena.step(((forward, 0.2), (yaw, 0.0)), 500_000)
    assert close(state.pose.position_m, (0.1, 0.0, 1e-3))
    assert state.pose.orientation == IDENTITY
    assert close(state.linear_velocity_m_s, (0.2, 0.0, 0.0))
    assert state.angular_velocity_rad_s == (0.0, 0.0, 0.0)
    # two half-steps match one whole step (exact integration)
    again = body()
    again.reset()
    again.step(((forward, 0.2),), 250_000)
    half, _ = again.step(((forward, 0.2),), 250_000)
    assert half == state


def test_constant_yaw_and_forward_is_an_analytic_arc():
    arena = body()
    arena.reset()
    yaw, forward = arena.actuators["yaw"], arena.actuators["forward"]
    omega, speed = math.pi / 2, 0.1
    state, _ = arena.step(((yaw, omega), (forward, speed)), 1_000_000)
    radius = speed / omega
    assert close(state.pose.position_m, (radius, radius, 1e-3))
    assert state.pose.orientation == yaw_q(math.pi / 2)
    assert close(state.linear_velocity_m_s, (0.0, speed, 0.0))
    assert close(state.angular_velocity_rad_s, (0.0, 0.0, omega))


def test_snapshot_restore_is_bit_identical(tmp_path):
    arena = body()
    arena.reset()
    yaw, forward = arena.actuators["yaw"], arena.actuators["forward"]
    arena.step(((yaw, 0.4), (forward, 0.05)), 2000)
    path = tmp_path / "body.npz"
    arena.snapshot(path)
    continued, _ = arena.step(((yaw, 0.4), (forward, 0.05)), 2000)
    twin = body()
    twin.restore(path)
    again, _ = twin.step(((yaw, 0.4), (forward, 0.05)), 2000)
    assert again == continued
    stranger = body(z_m=2e-3)
    with pytest.raises(ContractError, match="another body construction"):
        stranger.restore(path)


def test_unknown_or_foreign_actuators_refuse():
    arena = body()
    arena.reset()
    with pytest.raises(ContractError, match="not an actuator of this body"):
        arena.step(((ActuatorRef("lift", 0, "N", "toy"), 1.0),), 1000)
    with pytest.raises(ContractError, match="not an actuator of this body"):
        arena.step(((ActuatorRef("yaw", 0, "rad/s", "other"), 0.1),), 1000)
    with pytest.raises(ContractError, match="reset the body"):
        body().step((), 1000)
    from flymsg.arena import Arena

    with pytest.raises(TypeError):
        Arena(z_m=1e-3, roll_rad=0.0)


def test_existing_synthetic_closedloop_replay_is_unchanged():
    from test_closedloop import test_a_replay_reproduces_the_recorded_spikes_exactly

    test_a_replay_reproduces_the_recorded_spikes_exactly()


def test_heading_is_unwrapped_past_a_full_turn():
    arena = body()
    arena.reset()
    yaw = arena.actuators["yaw"]
    state, _ = arena.step(((yaw, 3 * math.pi),), 1_000_000)
    assert arena.yaw_rad == 3 * math.pi
    # the quaternion only shows the heading modulo a full turn
    q, ref = state.pose.orientation, yaw_q(math.pi)
    assert close((q.w, q.x, q.y, q.z), (ref.w, ref.x, ref.y, ref.z))


def test_an_actuator_commanded_twice_refuses():
    arena = body()
    arena.reset()
    yaw = arena.actuators["yaw"]
    with pytest.raises(ContractError, match="twice"):
        arena.step(((yaw, 0.1), (yaw, 0.2)), 1000)


def test_heading_before_reset_refuses():
    with pytest.raises(ContractError, match="reset"):
        _ = body().yaw_rad


def test_a_tiny_yaw_rate_still_moves_the_body():
    arena = body()
    arena.reset()
    yaw, forward = arena.actuators["yaw"], arena.actuators["forward"]
    arena.step(((yaw, 1.0),), 1_000_000)
    state, _ = arena.step(((yaw, 1e-14), (forward, 0.1)), 1000)
    expected = (1e-4 * math.cos(1.0), 1e-4 * math.sin(1.0), 1e-3)
    assert close(state.pose.position_m, expected, tol=1e-18)
