"""The authored motor map refuses a command and does not edit the behavior lock."""

import pytest

from flymsg import behavior, motor_map, sim


def _names() -> list[str]:
    names = [
        f"adhere_claw_T{seg}_{side}" for seg in (1, 2, 3) for side in ("left", "right")
    ]
    names += ["head_abduct", "head_twist", "head", "abdomen_abduct", "abdomen"]
    joints = (
        "coxa_abduct",
        "coxa_twist",
        "coxa",
        "femur_twist",
        "femur",
        "tibia",
        "tarsus",
        "tarsus2",
    )
    names += [
        f"{joint}_T{seg}_{side}"
        for seg in (1, 2, 3)
        for side in ("left", "right")
        for joint in joints
    ]
    return names


def test_the_map_lists_every_walking_actuator_and_both_ttmn():
    doc = motor_map.assert_locked()
    assert doc["version"] == 1
    assert motor_map.content_hash(doc) == motor_map.VERSION_HASHES[1]
    assert [row["name"] for row in doc["actuators"]] == _names()
    assert len(_names()) == 59
    assert {row["status"] for row in doc["actuators"]} == {"unmapped"}
    assert {row["status"] for row in doc["neurons"]} == {"unmapped"}
    assert "published_assignment" not in {
        row["status"] for row in [*doc["actuators"], *doc["neurons"]]
    }


def test_a_command_is_refused():
    with pytest.raises(motor_map.MotorMapError, match="unmapped"):
        motor_map.command("TTMn_R")
    with pytest.raises(motor_map.MotorMapError, match="unmapped"):
        motor_map.command("femur_T2_left")
    with pytest.raises(motor_map.MotorMapError, match="not in the motor map"):
        motor_map.command("MN9")


def test_an_edit_without_a_version_bump_fails():
    doc = motor_map.load()
    doc["actuators"][0]["status"] = "published_assignment"
    doc["content_sha256"] = motor_map.content_hash(doc)
    with pytest.raises(motor_map.MotorMapError, match="without a bump"):
        motor_map.assert_locked(doc)


def test_the_behavior_lock_stays_the_one_bit_protocol():
    doc = behavior.assert_matches_code()
    assert behavior.content_hash(doc) == behavior.VERSION_HASHES[1]
    assert doc["flybody"]["selected"] is False
    assert doc["controller"]["learned"] is False
    assert doc["protocol"]["w_syn"] == sim.Params.w_syn
    assert doc["protocol"]["th_jump"] == sim.Params.th_jump
