"""G5 (#180): ADR order, fail-closed evidence, the record and replay parity, on toys only."""

import dataclasses
import json

import numpy as np
import pytest
from test_core import chain

from flymsg import closedloop, pose, sim
from flymsg.embodiment import Clock, ContractError
from flymsg.pose import IDENTITY, ActuatorRef, BodyState, Pose, Provenance
from flymsg.runtime import CpuRuntime

PROVENANCE = Provenance("synthetic", "a" * 64, "fixture", 7)
CLOCK = Clock(neural_us=100, body_us=500, control_us=1000)
LIFT = ActuatorRef("lift", 0, "N", "toy")
COMPILED = {"lift": 0}
SYNTHETIC = dict.fromkeys(closedloop.COMPONENTS, "synthetic")
INPUT_IDS, TRACED_IDS = (720575940000000001,), (720575940000000002,)


class ToyBody:
    """One vertical axis; every call is logged so a test can see what ran."""

    def __init__(self, mass_kg=1e-6):
        self.mass_kg, self.calls = mass_kg, []
        self.t, self.z, self.v = 0, 0.0, 0.0

    def _state(self):
        return BodyState(
            self.t,
            Pose("world", "body", (0.0, 0.0, self.z), IDENTITY),
            (0.0, 0.0, self.v),
            (0.0, 0.0, 0.0),
        )

    def reset(self):
        self.calls.append("reset")
        self.t, self.z, self.v = 0, 0.0, 0.0
        return self._state()

    def step(self, commands, dt_us):
        self.calls.append(("step", commands))
        force = sum(v for _, v in commands)
        self.v += force / self.mass_kg * dt_us / 1e6
        self.z += self.v * dt_us / 1e6
        self.t += dt_us
        return self._state(), (("ground", 0.0 if self.z > 0 else 1e-5),)


def runtime(duration_us=40_000, silence=None):
    edges, sign, n = chain([400])
    p = sim.Params()
    return CpuRuntime(
        sim.weight_matrix(edges, sign, n, p.w_syn),
        np.array([0]),
        steps=duration_us // CLOCK.neural_us,
        kicks=np.zeros((0, 1), dtype=np.int64),
        p=p,
        per_bin=CLOCK.control_us // CLOCK.neural_us,
        trace=np.array([1]),
        silence=silence,
    )


def stimulus(t_us, state):
    # one column whose drive grows with time and with the body's height
    return (1.0 + t_us / 1e5 + 1e4 * state.pose.position_m[2],)


def transducer(stim):
    return np.array([200.0 * stim[0]])


def decoder(spikes):
    return ((LIFT, 1e-3 * len(spikes)),) if spikes else ()


def run(arm="intact", mode="synthetic", evidence=None, body=None, **kw):
    kw.setdefault("runtime", runtime())
    return closedloop.run(
        kw.pop("runtime"),
        body or ToyBody(),
        input_ids=INPUT_IDS,
        traced_ids=TRACED_IDS,
        stimulus=kw.pop("stimulus", stimulus),
        transducer=kw.pop("transducer", transducer),
        decoder=kw.pop("decoder", decoder),
        compiled=kw.pop("compiled", COMPILED),
        clock=kw.pop("clock", CLOCK),
        duration_us=40_000,
        arm=arm,
        mode=mode,
        evidence=evidence or SYNTHETIC,
        provenance=PROVENANCE,
        optics_config_sha256="c" * 64,
        run_identity_sha256="b" * 64,
        **kw,
    )


def test_the_schedule_follows_the_adr_order():
    steps = closedloop.schedule(CLOCK, 2000)
    # the B6 v2 / M0 v1 order: commands at control ticks, the rest per body tick
    body_tick = ["sample", "stimulus", "input", "neural", "physics"]
    assert [(s.phase, s.time_us) for s in steps] == [
        ("command", 0),
        *((p, 0) for p in body_tick),
        *((p, 500) for p in body_tick),
        ("command", 1000),
        *((p, 1000) for p in body_tick),
        *((p, 1500) for p in body_tick),
    ]
    with pytest.raises(ContractError, match="multiple"):
        closedloop.schedule(CLOCK, 1500)


def test_a_biological_run_refuses_anything_unmeasured_before_the_body_moves():
    closedloop.require(dict.fromkeys(closedloop.COMPONENTS, "measured"), "biological")
    evidence = {
        **dict.fromkeys(closedloop.COMPONENTS, "measured"),
        "transducer": "engineered",
    }
    with pytest.raises(ContractError, match="not: transducer"):
        closedloop.require(evidence, "biological")
    body = ToyBody()
    with pytest.raises(ContractError, match="measured components"):
        run(mode="biological", body=body)
    assert body.calls == []
    with pytest.raises(ContractError, match="exactly"):
        closedloop.require({"body": "synthetic"}, "synthetic")
    with pytest.raises(ContractError, match="unknown status"):
        closedloop.require({**SYNTHETIC, "body": "guessed"}, "synthetic")
    with pytest.raises(ContractError, match="mode"):
        closedloop.require(SYNTHETIC, "animal")


def test_a_measured_run_still_refuses_through_the_motor_map():
    measured = dict.fromkeys(closedloop.COMPONENTS, "measured")
    with pytest.raises(ContractError, match="lift is not in the motor map"):
        run(mode="biological", evidence=measured)


def test_the_input_reads_the_state_at_the_start_of_its_period():
    seen = []

    def watch(t_us, state):
        seen.append((t_us, state.time_us))
        return stimulus(t_us, state)

    record = run(stimulus=watch)
    assert seen == [(k * 500, k * 500) for k in range(80)]
    assert all(t.state.time_us == t.time_us for t in record.ticks)
    ticks = list(record.ticks)
    ticks[5] = dataclasses.replace(ticks[5], state=ticks[6].state)
    with pytest.raises(ContractError, match="state at its start"):
        dataclasses.replace(record, ticks=tuple(ticks)).validate()


def test_spikes_reach_the_body_one_control_period_later_at_the_earliest():
    delivered = []

    def watch(spikes):
        delivered.append(spikes)
        return decoder(spikes)

    for latency in (0, 1500):
        delivered.clear()
        record = run(
            decoder=watch, clock=dataclasses.replace(CLOCK, latency_us=latency)
        )
        assert sum(len(t.spikes) for t in record.ticks) > 0
        assert delivered[0] == ()  # nothing is delivered at T = 0
        for k, spikes in enumerate(delivered):
            assert all(s.time_us + latency <= k * 1000 for s in spikes)
        out = [s for batch in delivered for s in batch]
        assert out == [s for t in record.ticks for s in t.spikes][: len(out)]


def test_the_body_changes_the_input_that_follows_and_the_controls_do_not():
    closed, fixed = run(), run("disconnected")
    assert closed.ticks[-1].state.pose.position_m[2] > 0
    lift = next(k for k, t in enumerate(closed.ticks) if t.state.pose.position_m[2] > 0)
    assert [t.stimulus for t in closed.ticks[:lift]] == [
        t.stimulus for t in fixed.ticks[:lift]
    ]
    assert closed.ticks[lift].stimulus != fixed.ticks[lift].stimulus
    assert all(t.state.pose.position_m == (0.0, 0.0, 0.0) for t in fixed.ticks)
    mixed = run("shuffled")
    assert sorted(t.stimulus for t in mixed.ticks) == sorted(
        t.stimulus for t in fixed.ticks
    )
    assert [t.stimulus for t in mixed.ticks] != [t.stimulus for t in fixed.ticks]


def test_a_replay_reproduces_the_recorded_spikes_exactly():
    closed = run()
    again = run("replay", replay=closed)
    closedloop.replay_parity(closed, again)
    ticks = list(closed.ticks)
    ticks[3] = dataclasses.replace(ticks[3], input_counts=((5,),) * 5)
    tampered = dataclasses.replace(closed, ticks=tuple(ticks))
    with pytest.raises(ContractError, match="input counts differ"):
        closedloop.replay_parity(tampered, again)
    k = next(k for k, t in enumerate(again.ticks) if t.spikes)
    ticks = list(again.ticks)
    ticks[k] = dataclasses.replace(ticks[k], spikes=ticks[k].spikes[1:])
    with pytest.raises(ContractError, match="spikes differ"):
        closedloop.replay_parity(closed, dataclasses.replace(again, ticks=tuple(ticks)))
    with pytest.raises(ContractError, match="needs a recorded run"):
        run("replay")


def test_the_silenced_arm_names_its_neurons():
    record = run(
        "silenced", runtime=runtime(silence=np.array([1])), silenced_ids=TRACED_IDS
    )
    assert not any(t.spikes for t in record.ticks)
    with pytest.raises(ContractError, match="silenced"):
        run("silenced")
    with pytest.raises(ContractError, match="silenced"):
        run(silenced_ids=TRACED_IDS)


def test_the_record_round_trips_bit_for_bit_and_never_parses_as_a_pose_trace():
    record = run()
    text = record.to_json()
    assert closedloop.from_json(text) == record
    assert closedloop.from_json(text).to_json() == text
    with pytest.raises(ContractError):
        pose.from_json(text)
    trace = pose.Trace(PROVENANCE, CLOCK, pose.flygym_eye_mounts(), ())
    with pytest.raises(ContractError, match="closedloop"):
        closedloop.from_json(trace.to_json())
    d = json.loads(text)
    del d["ticks"][0]["spikes"]
    with pytest.raises(ContractError, match="malformed"):
        closedloop.from_json(json.dumps(d))


@pytest.mark.parametrize(
    ("kw", "match"),
    [
        ({"compiled": {"lift": 3}}, "not compiled actuator"),
        ({"transducer": lambda s: np.array([1.0, 2.0])}, "one finite rate"),
        ({"transducer": lambda s: np.array([np.nan])}, "one finite rate"),
        ({"decoder": lambda s: (("lift", 1.0),)}, "an actuator and a finite value"),
        ({"clock": Clock(neural_us=200, body_us=1000, control_us=1000)}, "neural tick"),
        ({"arm": "open"}, "arm"),
    ],
)
def test_bad_inputs_refuse(kw, match):
    arm = kw.pop("arm", "intact")
    with pytest.raises(ContractError, match=match):
        run(arm, **kw)


class Broken(ToyBody):
    def __init__(self, fault):
        super().__init__()
        self.fault = fault

    def step(self, commands, dt_us):
        state, contacts = super().step(commands, dt_us)
        if self.fault == "raise":
            raise RuntimeError("physics diverged")
        if self.fault == "time":
            return dataclasses.replace(state, time_us=state.time_us + 1), contacts
        return state, (("ground", -1.0),)


@pytest.mark.parametrize(
    ("fault", "match"),
    [
        ("raise", "body adapter failed"),
        ("time", "off the body grid"),
        ("contact", "normal force"),
    ],
)
def test_a_failing_body_stops_the_run(fault, match):
    with pytest.raises(ContractError, match=match):
        run(body=Broken(fault))


def test_a_short_runtime_stops_the_run_as_a_contract_error():
    with pytest.raises(ContractError, match="runtime failed"):
        run(runtime=runtime(duration_us=20_000))


def _mutate(d, path, value):
    *head, last = path
    for key in head:
        d = d[key]
    d[last] = value


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("ticks", 2, "input_counts", 0, 0), 1.5),
        (("ticks", 2, "input_counts", 0, 0), True),
        (("ticks", 2, "contacts"), [["ground", -1.0]]),
        (("ticks", 2, "contacts"), [["", 0.0]]),
        (("ticks", 2, "contacts"), [["ground"]]),
        (("evidence",), [["body", "synthetic"], ["body", "measured"]]),
        (("evidence",), [["body", "synthetic", "x"]]),
        (("ticks", 2, "commands"), [[5, -3, 1.0]]),
        (("ticks", 2, "commands"), [["lift", 0]]),
        (("ticks",), []),
        (("ticks", 2, "stimulus"), []),
        (("extra",), 1),
        (("ticks", 2, "state", "time_us"), 1500),
    ],
)
def test_a_malformed_record_refuses(path, value):
    d = json.loads(run().to_json())
    _mutate(d, path, value)
    with pytest.raises(ContractError):
        closedloop.from_json(json.dumps(d))


def test_spikes_out_of_order_or_off_grid_refuse():
    record = run()
    k = next(k for k, t in enumerate(record.ticks) if t.spikes)
    spike = record.ticks[k].spikes[0]
    for moved in (spike.time_us + 1, spike.time_us + 500):
        ticks = list(record.ticks)
        bad = dataclasses.replace(spike, time_us=moved)
        ticks[k] = dataclasses.replace(ticks[k], spikes=(bad,))
        with pytest.raises(ContractError, match="spike out of place"):
            dataclasses.replace(record, ticks=tuple(ticks)).validate()
