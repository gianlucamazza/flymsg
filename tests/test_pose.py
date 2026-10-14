import json
import math

import pytest

from flymsg import embodiment, motor_map, pose
from flymsg.embodiment import Clock, ContractError
from flymsg.pose import (
    IDENTITY,
    ActuatorRef,
    BodyState,
    EyeMount,
    Pose,
    Provenance,
    Quat,
    Registration,
    Trace,
)

PROVENANCE = Provenance("synthetic", "a" * 64, "fixture", 7)
S = math.sqrt(0.5)


def close(a, b, tol=1e-12):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def yaw(deg):
    h = math.radians(deg) / 2
    return Quat.of((math.cos(h), 0.0, 0.0, math.sin(h)))


def state(t=0, position=(0.0, 0.0, 0.0), q=IDENTITY):
    return BodyState(
        t, Pose("world", "body", position, q), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    )


# A left eye camera: optical axis (-z) along the fly's left (+y), image up +z, right +x.
LEFT = EyeMount(
    "L",
    Pose(
        "body",
        "eye/L",
        (0.7e-3, 0.38e-3, 1.3e-3),
        Quat.from_matrix([[1, 0, 0], [0, 0, -1], [0, 1, 0]]),
    ),
    "synthetic",
)


def test_quaternion_order_canonical_sign_and_degenerates():
    assert Quat.of((-1, 0, 0, 0)) == IDENTITY  # q and -q: one stored form
    assert close(yaw(90).rotate((1, 0, 0)), (0, 1, 0))  # (w, x, y, z), right-handed
    for bad in ((0, 0, 0, 0), (2, 0, 0, 0), (math.nan, 0, 0, 1), (1, 0, 0)):
        with pytest.raises(ContractError):
            Quat.of(bad)
    with pytest.raises(ContractError):
        Quat.from_matrix([[1, 0, 0], [0, -1, 0], [0, 0, 1]])  # a reflection


@pytest.mark.parametrize("deg", [0, 45, 90, 179.9, 180, -135])
def test_matrix_round_trip(deg):
    q = yaw(deg) * Quat.of((S, S, 0, 0))
    back = Quat.from_matrix(q.matrix())
    assert close((back.w, back.x, back.y, back.z), (q.w, q.x, q.y, q.z), 1e-12)


@pytest.mark.parametrize("position", [(0, 0, 0), (1e3, -1e3, 5e2), (-1e-9, 2e-9, 0)])
def test_frames_round_trip_at_extreme_positions(position):
    s = state(position=position, q=yaw(37) * Quat.of((S, 0, S, 0)))
    to_eye = pose.world_to_eye(s, LEFT)
    p = (0.01, -0.02, 0.003)
    back = pose.eye_pose(s, LEFT).apply(to_eye.apply(p))
    assert close(back, p, 1e-9 * max(1.0, max(abs(c) for c in position)))
    assert (to_eye.parent, to_eye.child) == ("eye/L", "world")


def test_sign_inversions_and_frame_checks():
    s = state(q=yaw(180))
    # a point ahead of a fly turned around lies behind it
    assert close(s.pose.inverse().apply((1, 0, 0)), (-1, 0, 0))
    with pytest.raises(ContractError):
        s.pose @ s.pose  # world<-body composed with world<-body
    with pytest.raises(ContractError):
        Pose("world", "head", (0, 0, 0), IDENTITY)
    with pytest.raises(ContractError):
        Pose("world", "body", (0, math.inf, 0), IDENTITY)


def test_left_eye_looks_left_and_mirror_is_proper():
    s = state()
    axis = pose.eye_pose(s, LEFT).direction((0, 0, -1))
    assert close(axis, (0, 1, 0))
    right = pose.mirror(LEFT)
    assert right.side == "R" and right.pose.position_m == (0.7e-3, -0.38e-3, 1.3e-3)
    r = pose.eye_pose(s, right)
    assert close(r.direction((0, 0, -1)), (0, -1, 0))  # optical axis mirrored
    assert close(r.direction((0, 1, 0)), (0, 0, 1))  # image up stays up
    m = right.pose.orientation.matrix()
    det = (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )
    assert abs(det - 1) < 1e-12
    assert pose.mirror(right).pose == LEFT.pose  # an involution


def test_missing_or_wrong_mount_and_registration_refuse():
    with pytest.raises(ContractError):
        EyeMount("L", Pose("body", "eye/R", (0, 0, 0), IDENTITY), "x")
    with pytest.raises(ContractError):
        EyeMount("L", LEFT.pose, "")
    with pytest.raises(ContractError):
        Registration(Pose("body", "eyemap", (0, 0, 0), IDENTITY), "")
    with pytest.raises(ContractError):
        Trace(PROVENANCE, Clock(), (LEFT,), ()).validate()  # one eye missing


def test_no_future_pose_enters_an_earlier_input():
    clock = Clock()
    states = tuple(state(t) for t in range(0, 5000, clock.body_us))
    for t in range(0, 5000, clock.neural_us):
        got = pose.state_at(states, t, clock)
        assert got.time_us <= t < got.time_us + clock.body_us
    with pytest.raises(ContractError):
        pose.state_at(states[1:], 500, clock)  # before the first state
    with pytest.raises(ContractError):
        pose.state_at((state(1000), state(0)), 1000, clock)  # out of order
    with pytest.raises(ContractError):
        pose.state_at((state(150),), 200, clock)  # off the body grid


def test_v2_json_round_trip_and_version_isolation():
    states = (state(0), state(1000, (1e-3, 0, 0), yaw(10)))
    trace = Trace(PROVENANCE, Clock(), (LEFT, pose.mirror(LEFT)), states)
    text = trace.to_json()
    assert pose.from_json(text) == trace
    assert pose.from_json(text).to_json() == text
    doc = json.loads(text)
    doc["provenance"]["schema"] = embodiment.SCHEMA
    with pytest.raises(ContractError):
        pose.from_json(json.dumps(doc))
    del doc["mounts"]
    with pytest.raises(ContractError):
        pose.from_json(json.dumps(doc))
    with pytest.raises(ContractError):
        embodiment.Provenance(**json.loads(text)["provenance"]).validate()
    # M0 v1 is untouched
    assert embodiment.SCHEMA == "flymsg.embodiment/v1"
    assert embodiment.Provenance("d", "a" * 64, "c", 0).schema == "flymsg.embodiment/v1"


def test_body_state_conventions():
    with pytest.raises(ContractError):
        BodyState(-1, state().pose, (0, 0, 0), (0, 0, 0))
    with pytest.raises(ContractError):
        BodyState(0, LEFT.pose, (0, 0, 0), (0, 0, 0))
    with pytest.raises(ContractError):
        BodyState(0, state().pose, (0, 0), (0, 0, 0))
    assert pose.mm(1.0) == 1e-3


def test_unknown_or_unpublished_actuator_refuses():
    doc = motor_map.assert_locked()
    name = doc["actuators"][0]["name"]
    compiled = {name: 3}
    with pytest.raises(ContractError, match="not compiled"):
        pose.command(ActuatorRef(name, 4, "N*m"), compiled)
    with pytest.raises(ContractError, match="not compiled"):
        pose.command(ActuatorRef("no_such_actuator", 0, "N*m"), compiled)
    with pytest.raises(ContractError, match="unmapped"):
        pose.command(ActuatorRef(name, 3, "N*m"), compiled)
    with pytest.raises(ContractError):
        ActuatorRef(name, 3, "mm")


def test_flygym_eye_mounts_are_mirrored_and_off_the_thorax():
    left, right = pose.flygym_eye_mounts()
    # FlyGym 2.1.0: eyes 0.23 mm anterior, 0.38 mm lateral, 0.02 mm dorsal of c_thorax
    assert close(left.pose.position_m, (0.2297e-3, 0.38e-3, 0.0177e-3), 1e-7)
    assert close(right.pose.position_m, (0.2297e-3, -0.38e-3, 0.0177e-3), 1e-7)
    axis = pose.eye_pose(state(), left).direction((0, 0, -1))
    azimuth = math.degrees(math.atan2(axis[1], axis[0]))
    assert 62.5 < azimuth < 63.5 and abs(axis[2]) < 1e-3  # optical axis 63° left, level
    # the right mount is the mirrored left one within FlyGym's own asymmetry (< 0.2°)
    m = pose.mirror(left).pose.orientation
    r = right.pose.orientation
    dot = abs(m.w * r.w + m.x * r.x + m.y * r.y + m.z * r.z)
    assert math.degrees(2 * math.acos(min(1.0, dot))) < 0.2
