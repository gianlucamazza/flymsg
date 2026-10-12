import json
from dataclasses import replace

import pytest

from flymsg import sim
from flymsg.embodiment import (
    BodyState,
    Clock,
    ContractError,
    MockBody,
    Provenance,
    SpikeEvent,
    run_fixture,
)

PROVENANCE = Provenance("synthetic", "a" * 64, "fixture", 7)


def run(events=(), **kwargs):
    options = {
        "duration_us": 4000,
        "provenance": PROVENANCE,
        "motor_map": {10: 2.0, 11: -1.0},
        "sensor_map": {"position": 20},
        "body": MockBody(),
        "expected_dataset_sha256": "a" * 64,
    }
    options.update(kwargs)
    return run_fixture(events, **options)


def test_repeatable_round_trip_and_physical_units():
    events = (SpikeEvent(10, 0), SpikeEvent(11, 100), SpikeEvent(10, 1000))
    trace = run(events)
    assert json.dumps(trace.to_dict(), sort_keys=True) == json.dumps(
        run(events).to_dict(), sort_keys=True
    )
    assert [c.force_n for c in trace.commands] == [2, 1, 0, 0]
    assert tuple(e for c in trace.commands for e in c.source_events) == events
    assert trace.states[0] == BodyState(1000, 2e-6, 0.002)
    assert trace.feedback[0] == SpikeEvent(20, 1000)
    assert [s.time_us for s in trace.sensors] == [1000, 2000, 3000, 4000]


def test_latency_boundary_equal_time_order_and_hold():
    events = (SpikeEvent(11, 0), SpikeEvent(10, 0), SpikeEvent(10, 100))
    trace = run(events, clock=Clock(body_us=200, control_us=1000, latency_us=100))
    assert [c.force_n for c in trace.commands] == [0, 3, 0, 0]
    assert trace.commands[1].source_events == events
    assert trace.states[4].position_m == 0
    assert trace.states[9].velocity_m_s == pytest.approx(0.003)


def test_no_command_no_movement():
    trace = run()
    assert all(s.position_m == s.velocity_m_s == 0 for s in trace.states)
    assert trace.feedback == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"provenance": replace(PROVENANCE, schema="v2")},
        {"provenance": replace(PROVENANCE, clock="v2")},
        {"expected_dataset_sha256": "b" * 64},
        {"clock": Clock(body_us=150)},
        {"clock": Clock(neural_us=True)},
        {"clock": Clock(latency_us=50)},
        {"duration_us": 3500},
        {"motor_map": {10: float("nan")}},
        {"sensor_map": {}},
    ],
)
def test_invalid_configuration_fails_before_actuation(kwargs):
    class NoCalls(MockBody):
        def step(self, command, dt_us):
            pytest.fail("invalid input reached actuator")

    with pytest.raises(ContractError):
        run(body=NoCalls(), **kwargs)


@pytest.mark.parametrize(
    "events",
    [
        (SpikeEvent(99, 0),),
        (SpikeEvent(10, 50),),
        (SpikeEvent(10, 100), SpikeEvent(10, 0)),
        (SpikeEvent(10, 3100),),
        (SpikeEvent(10, -100),),
    ],
)
def test_invalid_events(events):
    with pytest.raises(ContractError):
        run(events)


def test_missing_sensor_aborts_before_next_step():
    class MissingSensor(MockBody):
        calls = 0

        def step(self, command, dt_us):
            self.calls += 1
            return super().step(command, dt_us)

        def sensors(self, state):
            return ()

    body = MissingSensor()
    with pytest.raises(ContractError, match="sensor"):
        run(body=body)
    assert body.calls == 1


@pytest.mark.parametrize("kind", ["time", "unit", "frame", "nan", "duplicate", "state"])
def test_invalid_adapter_output_stops_run(kind):
    from flymsg.embodiment import SensorSample

    class InvalidBody(MockBody):
        calls = 0

        def step(self, command, dt_us):
            self.calls += 1
            state = super().step(command, dt_us)
            return replace(state, time_us=0) if kind == "state" else state

        def sensors(self, state):
            sample = SensorSample(state.time_us, "position", state.position_m)
            edits = {
                "time": {"time_us": 0},
                "unit": {"unit": "mm"},
                "frame": {"frame": "body"},
                "nan": {"value": float("nan")},
            }
            sample = replace(sample, **edits.get(kind, {}))
            return (sample, sample) if kind == "duplicate" else (sample,)

    body = InvalidBody()
    with pytest.raises(ContractError):
        run(body=body)
    assert body.calls == 1


def test_exhaustive_grid_event_conservation_and_delivery_bound():
    events = tuple(SpikeEvent(10, t) for t in range(0, 2900, 100))
    trace = run(events, clock=Clock(latency_us=100))
    assert tuple(e for c in trace.commands for e in c.source_events) == events
    for command in trace.commands:
        for event in command.source_events:
            assert 100 <= command.time_us - event.time_us < 1100


def test_default_neural_tick_is_the_simulator_step():
    assert Clock().neural_us == round(sim.Params.dt * 1000)


def test_bad_mass_fails_at_construction():
    with pytest.raises(ContractError, match="mass"):
        MockBody(mass_kg=0.0)


def test_any_adapter_exception_becomes_a_contract_error():
    class Broken(MockBody):
        calls = 0

        def step(self, command, dt_us):
            self.calls += 1
            raise ZeroDivisionError("backend")

    body = Broken()
    with pytest.raises(ContractError, match="adapter") as err:
        run(body=body)
    assert isinstance(err.value.__cause__, ZeroDivisionError)
    assert body.calls == 1
