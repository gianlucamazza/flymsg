"""Script and wiring-null fixture controls (DN-arena ADR Decision 5)."""

import math

import numpy as np
import pandas as pd
import pytest

from flymsg import closedloop, sim, wiring
from flymsg.embodiment import Clock, ContractError
from flymsg.pose import Provenance
from flymsg.runtime import CpuRuntime

# docs/dn-arena-inventory.md (MaleCNS v1.0); not a gain
DNA01_L, ODN1_L = 10442, 13805
CLOCK = Clock(neural_us=100, body_us=500, control_us=1000)
DURATION = 4_000
PROVENANCE = Provenance("synthetic", "a" * 64, "fixture", 7)
SYNTHETIC = dict.fromkeys(closedloop.COMPONENTS, "synthetic")
GAINS = {"DNa01": 0.5, "DNa02": 0.25, "oDN1": 0.1}


def arena():
    from flymsg.arena import Arena

    return Arena(z_m=1e-3, roll_rad=0.0, pitch_rad=0.0, source="test kinematic")


def decoder(body=None):
    from flymsg.dn_decoder import Decoder

    body = body or arena()
    return Decoder(
        gains=dict(GAINS),
        window=(0, DURATION),
        actuators=body.actuators,
        clock=CLOCK,
    )


def constant_rule(yaw_rad_s, forward_m_s, body=None):
    body = body or arena()
    yaw, forward = body.actuators["yaw"], body.actuators["forward"]

    def rule(_t_us, _state, _stim):
        return ((yaw, yaw_rad_s), (forward, forward_m_s))

    return rule


def stimulus(_t_us, _state):
    return (0.25,)


def toy_edges():
    return pd.DataFrame(
        {
            "pre": np.array([0, 0, 1], dtype=np.int32),
            "post": np.array([1, 2, 2], dtype=np.int32),
            "weight": np.array([400, 200, 100], dtype=np.int32),
        }
    )


def runtime_from_edges(edges):
    n = 3
    params = sim.Params()
    return CpuRuntime(
        sim.weight_matrix(edges, np.ones(n, dtype=np.int8), n, params.w_syn),
        np.array([0]),
        steps=DURATION // CLOCK.neural_us,
        kicks=np.zeros((0, 1), dtype=np.int64),
        p=params,
        per_bin=CLOCK.control_us // CLOCK.neural_us,
        trace=np.array([1, 2]),
    )


def run_script(**kw):
    from flymsg.arena_controls import script

    body = kw.pop("body", None) or arena()
    kw.setdefault("clock", CLOCK)
    kw.setdefault("duration_us", DURATION)
    kw.setdefault("rule", constant_rule(0.0, 0.1, body))
    kw.setdefault("stimulus", stimulus)
    return script(body, **kw)


def run_wiring_null(**kw):
    from flymsg.arena_controls import wiring_null

    body = kw.pop("body", None) or arena()
    kw.setdefault("edges", toy_edges())
    kw.setdefault("seed", 3)
    kw.setdefault("runtime_from_edges", runtime_from_edges)
    kw.setdefault("decoder", decoder(body))
    kw.setdefault("input_ids", (1,))
    kw.setdefault("traced_ids", (DNA01_L, ODN1_L))
    kw.setdefault("stimulus", stimulus)
    kw.setdefault("transducer", lambda stim: np.array([200.0 * stim[0]]))
    kw.setdefault("compiled", body.compiled)
    kw.setdefault("clock", CLOCK)
    kw.setdefault("duration_us", DURATION)
    kw.setdefault("mode", "synthetic")
    kw.setdefault("evidence", SYNTHETIC)
    kw.setdefault("provenance", PROVENANCE)
    kw.setdefault("optics_config_sha256", "c" * 64)
    kw.setdefault("run_identity_sha256", "b" * 64)
    return wiring_null(body, **kw)


def test_script_is_deterministic_for_a_given_rule_and_clock():
    first = run_script()
    second = run_script()
    assert first.control == "script"
    assert first.notes["control"] == "script"
    assert "arm" not in first.notes
    assert first.clock == CLOCK
    assert first.duration_us == DURATION
    assert [t.stepped for t in first.ticks] == [t.stepped for t in second.ticks]
    assert [t.commands for t in first.ticks] == [t.commands for t in second.ticks]
    assert [t.stimulus for t in first.ticks] == [t.stimulus for t in second.ticks]


def test_script_steps_the_arena_on_the_clock_without_a_runtime(monkeypatch):
    from flymsg import arena_controls

    body = arena()
    yaw, forward = body.actuators["yaw"], body.actuators["forward"]
    omega, speed = math.pi / 2, 0.1
    clock = Clock(neural_us=100, body_us=1_000_000, control_us=1_000_000)

    def rule(_t_us, _state, _stim):
        return ((yaw, omega), (forward, speed))

    called = []

    def closed(*_a, **_k):
        called.append("run")
        raise AssertionError("script must not call closedloop.run")

    monkeypatch.setattr(arena_controls.closedloop, "run", closed)
    result = run_script(body=body, clock=clock, duration_us=2_000_000, rule=rule)
    assert called == []
    assert len(result.ticks) == 2
    # one control period of latency: the first period holds no command
    assert result.ticks[0].commands == ()
    assert result.ticks[0].stepped.pose.position_m[:2] == (0.0, 0.0)
    state = result.ticks[1].stepped
    radius = speed / omega
    assert abs(state.pose.position_m[0] - radius) <= 1e-12
    assert abs(state.pose.position_m[1] - radius) <= 1e-12
    assert result.ticks[1].yaw_rad == omega
    assert result.ticks[1].commands[0][0] == "yaw"
    assert result.ticks[1].commands[1][0] == "forward"


def test_script_holds_commands_between_control_ticks_and_sees_stimulus():
    body = arena()
    yaw, forward = body.actuators["yaw"], body.actuators["forward"]
    seen = []

    def rule(t_us, _state, stim):
        seen.append((t_us, stim))
        return ((yaw, stim[0]), (forward, 0.0))

    def geom(t_us, state):
        return (0.5 if state.time_us == 0 else 0.0,)

    result = run_script(body=body, rule=rule, stimulus=geom)
    # the command at a control tick comes from the previous tick's sample
    assert seen == [(0, (0.5,)), (1000, (0.0,)), (2000, (0.0,))]
    held = [t.commands[0][2] if t.commands else None for t in result.ticks]
    assert held == [None, None, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0]


def test_wiring_null_shuffle_preserves_degree_and_is_seed_deterministic():
    edges = toy_edges()
    captured = []

    def capture(shuffled):
        captured.append(shuffled.copy())
        return runtime_from_edges(shuffled)

    first = run_wiring_null(edges=edges, seed=3, runtime_from_edges=capture)
    second = run_wiring_null(edges=edges, seed=3, runtime_from_edges=capture)
    expected, stats = wiring.shuffle_targets(edges, 3)
    assert first.control == "wiring-null"
    assert first.notes["control"] == "wiring-null"
    assert first.notes["shuffle_seed"] == 3
    assert first.record.arm == "intact"
    assert first.record.schema == closedloop.SCHEMA
    assert first.seed == 3
    assert captured[0]["post"].tolist() == expected["post"].tolist()
    assert captured[0]["pre"].tolist() == edges["pre"].tolist()
    assert captured[0]["weight"].tolist() == edges["weight"].tolist()
    assert sorted(captured[0]["post"]) == sorted(edges["post"])
    assert first.stats == stats
    assert second.record.to_json() == first.record.to_json()
    other = run_wiring_null(edges=edges, seed=4, runtime_from_edges=capture)
    assert captured[2]["post"].tolist() != expected["post"].tolist()
    assert other.seed == 4 and other.notes["shuffle_seed"] == 4
    # the source graph is not mutated
    assert edges["post"].tolist() == toy_edges()["post"].tolist()


def test_five_arm_record_still_parses_and_arms_are_unchanged():
    assert closedloop.ARMS == (
        "intact",
        "disconnected",
        "shuffled",
        "replay",
        "silenced",
    )
    assert closedloop.SCHEMA == "flymsg.closedloop/v1"
    assert closedloop.COMPONENTS == (
        "registration",
        "transducer",
        "motor_map",
        "body",
    )
    from test_closedloop import (
        test_the_record_round_trips_bit_for_bit_and_never_parses_as_a_pose_trace,
    )

    test_the_record_round_trips_bit_for_bit_and_never_parses_as_a_pose_trace()
    result = run_wiring_null()
    result.record.validate()
    assert result.record.arm in closedloop.ARMS
    assert result.control not in closedloop.ARMS


def test_existing_replay_parity_and_silenced_arm_stay_unchanged():
    from test_closedloop import (
        test_a_replay_reproduces_the_recorded_spikes_exactly,
        test_the_silenced_arm_names_its_neurons,
    )

    test_a_replay_reproduces_the_recorded_spikes_exactly()
    test_the_silenced_arm_names_its_neurons()


def test_missing_or_nonfinite_parameters_refuse():
    from flymsg.arena_controls import script, wiring_null

    body = arena()
    with pytest.raises(TypeError):
        script(body)
    with pytest.raises(ContractError, match="duration"):
        run_script(duration_us=0)
    with pytest.raises(ContractError, match="multiple"):
        run_script(duration_us=1500)
    with pytest.raises(ContractError, match="finite"):
        run_script(rule=constant_rule(float("nan"), 0.0, body), body=body)
    with pytest.raises(ContractError, match="finite"):
        run_script(stimulus=lambda t, s: (float("nan"),))
    with pytest.raises(ContractError, match="seed"):
        run_wiring_null(seed=-1)
    with pytest.raises(ContractError, match="seed"):
        run_wiring_null(seed=1.5)
    with pytest.raises(ContractError, match="arm"):
        run_wiring_null(arm="wiring-null")
    with pytest.raises(ContractError, match="edges"):
        run_wiring_null(edges=pd.DataFrame({"pre": [0]}))
    with pytest.raises(TypeError):
        wiring_null(body)
