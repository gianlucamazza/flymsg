"""Engineered DN readout: windowed rates into kinematic commands (DN-arena ADR)."""

import json
import math

import numpy as np
import pytest
from test_core import chain

from flymsg import closedloop, sim
from flymsg.arena import Arena
from flymsg.dn_decoder import DECODER_EVIDENCE, Decoder, Term
from flymsg.embodiment import Clock, ContractError, SpikeEvent
from flymsg.pose import ActuatorRef, Provenance, Quat
from flymsg.runtime import CpuRuntime

SOURCE = "test kinematic planar"
# MaleCNS bodyIds from docs/dn-arena-inventory.md. oDN1 is type DNg97.
DNA01_L, DNA01_R = 10442, 10760
ODN1_L, ODN1_R = 13805, 230783
TEST_GAIN = 2.0
TEST_GAIN_NEG = -0.5
TEST_GAIN_FWD = 0.25
TEST_GAIN_FWD_R = 1.5
CLOCK = Clock(neural_us=100, body_us=1000, control_us=500_000)
PROVENANCE = Provenance("synthetic", "a" * 64, "fixture", 7)


def arena():
    return Arena(z_m=1e-3, roll_rad=0.0, pitch_rad=0.0, source=SOURCE)


def terms():
    return (
        Term(DNA01_R, "yaw", TEST_GAIN_NEG),
        Term(ODN1_R, "forward", TEST_GAIN_FWD_R),
        Term(DNA01_L, "yaw", TEST_GAIN),
        Term(ODN1_L, "forward", TEST_GAIN_FWD),
    )


def build():
    body = arena()
    return Decoder(terms(), body.actuators, CLOCK), body


def spikes():
    return (
        SpikeEvent(DNA01_L, 0),
        SpikeEvent(ODN1_L, 100),
        SpikeEvent(DNA01_R, 200),
        SpikeEvent(DNA01_L, 300),
        SpikeEvent(DNA01_R, 400),
        SpikeEvent(ODN1_L, 500),
        SpikeEvent(DNA01_R, 600),
        SpikeEvent(DNA01_L, 700),
        SpikeEvent(DNA01_R, 800),
    )


def test_rates_sum_per_actuator_in_name_order():
    dec, body = build()
    # 500_000 us is 0.5 s, so rate = count / 0.5.
    # yaw = 2 * (3 / 0.5) + (-0.5) * (4 / 0.5) = 8
    # forward = 0.25 * (2 / 0.5) + 1.5 * (0 / 0.5) = 1
    # counts: DNa01 L 3, DNa01 R 4, oDN1 L 2, oDN1 R 0
    commands = dec(spikes())
    assert commands == (
        (body.actuators["forward"], 1.0),
        (body.actuators["yaw"], 8.0),
    )
    assert [actuator.name for actuator, _value in commands] == ["forward", "yaw"]
    assert all(type(value) is float for _actuator, value in commands)
    assert dec(()) == (
        (body.actuators["forward"], 0.0),
        (body.actuators["yaw"], 0.0),
    )
    assert dec.body_ids == (DNA01_L, DNA01_R, ODN1_L, ODN1_R)


def test_the_same_spikes_always_give_the_same_commands():
    dec, _body = build()
    window = spikes()
    first = dec(window)
    assert dec(window) == first
    assert dec(tuple(reversed(window))) == first


def _raise(case):
    body = arena()
    if case == "empty":
        Decoder((), body.actuators, CLOCK)
    elif case == "duplicate":
        Decoder(
            (Term(DNA01_L, "yaw", TEST_GAIN), Term(DNA01_L, "yaw", TEST_GAIN_NEG)),
            body.actuators,
            CLOCK,
        )
    elif case == "unknown":
        Decoder((Term(DNA01_L, "lift", TEST_GAIN),), body.actuators, CLOCK)
    elif case == "mismatched":
        bad = dict(body.actuators)
        bad["yaw"] = ActuatorRef(
            "forward", body.actuators["yaw"].mujoco_id, "rad/s", SOURCE
        )
        Decoder((Term(DNA01_L, "yaw", TEST_GAIN),), bad, CLOCK)
    elif case == "zero":
        Term(DNA01_L, "yaw", 0.0)
    elif case == "nan":
        Term(DNA01_L, "yaw", float("nan"))
    elif case == "inf":
        Term(DNA01_L, "yaw", float("inf"))
    elif case == "body":
        Term(0, "yaw", TEST_GAIN)
    elif case == "unread":
        dec, _body = build()
        dec((SpikeEvent(10001, 0),))
    else:
        raise AssertionError(case)


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("empty", "non-empty"),
        ("duplicate", "duplicate"),
        ("unknown", "not an actuator of this body"),
        ("mismatched", "actuator reference"),
        ("zero", "finite and nonzero"),
        ("nan", "finite and nonzero"),
        ("inf", "finite and nonzero"),
        ("body", ">= 1"),
        ("unread", "unread neuron"),
    ],
)
def test_bad_terms_and_unread_spikes_refuse(case, match):
    with pytest.raises(ContractError, match=match):
        _raise(case)


def test_describe_is_canonical_and_json_round_trips():
    dec, _body = build()
    described = dec.describe()
    assert described == {
        "kind": "flymsg.dn_decoder/v1",
        "window_us": CLOCK.control_us,
        "terms": [
            {
                "body_id": ODN1_L,
                "actuator": "forward",
                "unit": "m/s",
                "gain": TEST_GAIN_FWD,
            },
            {
                "body_id": ODN1_R,
                "actuator": "forward",
                "unit": "m/s",
                "gain": TEST_GAIN_FWD_R,
            },
            {
                "body_id": DNA01_L,
                "actuator": "yaw",
                "unit": "rad/s",
                "gain": TEST_GAIN,
            },
            {
                "body_id": DNA01_R,
                "actuator": "yaw",
                "unit": "rad/s",
                "gain": TEST_GAIN_NEG,
            },
        ],
    }
    assert json.loads(json.dumps(described)) == described
    assert DECODER_EVIDENCE == "engineered"


def _stimulus(_t_us, _state):
    return (1.0,)


def _transducer(stim):
    return np.array([500.0 * stim[0]])


def test_a_synthetic_loop_records_the_windowed_commands():
    clock = Clock(neural_us=100, body_us=500, control_us=1000, latency_us=500)
    duration_us = 8_000
    body = arena()
    dec = Decoder(terms(), body.actuators, clock)
    edges, sign, n = chain([400] * len(dec.body_ids))
    params = sim.Params()
    runtime = CpuRuntime(
        sim.weight_matrix(edges, sign, n, params.w_syn),
        np.array([0]),
        steps=duration_us // clock.neural_us,
        kicks=np.zeros((0, 1), dtype=np.int64),
        p=params,
        per_bin=clock.control_us // clock.neural_us,
        trace=np.arange(1, len(dec.body_ids) + 1),
    )
    record = closedloop.run(
        runtime,
        body,
        input_ids=(1,),
        traced_ids=dec.body_ids,
        stimulus=_stimulus,
        transducer=_transducer,
        decoder=dec,
        compiled=body.compiled,
        clock=clock,
        duration_us=duration_us,
        arm="intact",
        mode="synthetic",
        evidence=dict.fromkeys(closedloop.COMPONENTS, "synthetic"),
        provenance=PROVENANCE,
        optics_config_sha256="c" * 64,
        run_identity_sha256="b" * 64,
    )
    assert record.traced_ids == dec.body_ids
    assert sum(len(tick.spikes) for tick in record.ticks) > 0
    # Command at T uses spikes already produced, with time + latency <= T.
    produced = []
    cursor = 0
    held = None
    for tick in record.ticks:
        if tick.time_us % clock.control_us == 0:
            start = cursor
            while (
                cursor < len(produced)
                and produced[cursor].time_us + clock.latency_us <= tick.time_us
            ):
                cursor += 1
            got = dec(tuple(produced[start:cursor]))
            held = tuple(
                (actuator.name, actuator.mujoco_id, value) for actuator, value in got
            )
            assert tick.commands == held
        else:
            assert tick.commands == held
        produced.extend(tick.spikes)
    assert any(value != 0.0 for tick in record.ticks for _, _, value in tick.commands)
    # Heading is the integral of the recorded yaw command (roll and pitch are 0).
    yaw = 0.0
    step_s = clock.body_us / 1e6
    for tick in record.ticks:
        omega = next(value for name, _, value in tick.commands if name == "yaw")
        yaw += omega * step_s
        expect = Quat.of((math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)))
        got = tick.stepped.pose.orientation.components()
        assert all(
            abs(a - b) <= 1e-9 for a, b in zip(got, expect.components(), strict=True)
        )
