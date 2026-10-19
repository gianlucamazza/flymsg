"""G5 (#180): ADR order, fail-closed evidence, the record and replay parity, on toys only."""

import dataclasses
import hashlib
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

    def snapshot(self, path):
        path.write_text(json.dumps([self.t, self.z, self.v]))

    def restore(self, path):
        self.t, self.z, self.v = json.loads(path.read_text())


class Crash(ToyBody):
    """Dies once its clock reaches `at_us`, as a killed process would."""

    def __init__(self, at_us):
        super().__init__()
        self.at_us = at_us

    def step(self, commands, dt_us):
        if self.t >= self.at_us:
            raise RuntimeError("killed")
        return super().step(commands, dt_us)


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
        input_encoding="counts",
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
        input_gap_steps=kw.pop("input_gap_steps", 0),
        input_encoding=kw.pop("input_encoding", "counts"),
        pathway_sha256=kw.pop("pathway_sha256", None),
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
        ({"stimulus": lambda t, s: (float("nan"),)}, "one finite value per column"),
        ({"stimulus": lambda t, s: ()}, "one finite value per column"),
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
        (("ticks", 2, "input_counts", 0, 0), -1),
        (("ticks", 2, "contacts"), [["ground", -1.0]]),
        (("ticks", 2, "contacts"), [["", 0.0]]),
        (("ticks", 2, "contacts"), [["ground"]]),
        (("evidence",), [["body", "synthetic"], ["body", "measured"]]),
        (("evidence",), [["body", "synthetic", "x"]]),
        (("evidence",), [[]]),
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


def test_a_resumed_run_equals_the_uninterrupted_one(tmp_path):
    whole = run()
    (tmp_path / "notes.txt").write_text("the caller's")
    (tmp_path / "outputs").mkdir()
    with pytest.raises(ContractError, match="killed"):
        run(body=Crash(23_500), checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "body-20000.npz",
        "loop.json",
        "neural-20000.npz",
        "notes.txt",
        "outputs",
        "ticks-10000.json",
        "ticks-15000.json",
        "ticks-20000.json",
        "ticks-5000.json",
    ]
    body = ToyBody()
    resumed = run(body=body, checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    assert "reset" not in body.calls
    assert resumed == whole
    # a finished run answers again with its record and runs nothing
    idle = ToyBody()
    assert run(body=idle, checkpoint_dir=tmp_path, checkpoint_every_us=5000) == whole
    assert idle.calls == []
    (tmp_path / "record.json").unlink()
    # another run's checkpoint, or a changed part, refuses
    with pytest.raises(ContractError, match="another run"):
        run("disconnected", checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    # the resumed run went on writing checkpoints; corrupt the current body part
    (current,) = tmp_path.glob("body-*.npz")
    current.write_text("[0, 0.0, 0.0]")
    with pytest.raises(ContractError, match="does not match its hash"):
        run(checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    with pytest.raises(ContractError, match="both a directory and an interval"):
        run(checkpoint_dir=tmp_path)
    with pytest.raises(ContractError, match="control ticks"):
        run(checkpoint_dir=tmp_path / "x", checkpoint_every_us=1500)


def _fast(_stim):
    return np.array([3000.0])  # many kicks within one gap


GAP = 7  # neural steps, longer than a body tick, so it crosses tick boundaries


def test_the_input_dead_time_is_stimulus_dead_time_across_ticks():
    from flymsg.stimulus import dead_time

    record = run(transducer=_fast, input_gap_steps=GAP)
    per = CLOCK.body_us // CLOCK.neural_us
    rng = np.random.default_rng(PROVENANCE.seed)
    draws = np.concatenate(
        [
            rng.poisson(3000.0 * CLOCK.neural_us / 1e6, (per, len(INPUT_IDS)))
            for _ in record.ticks
        ]
    )
    delivered = np.concatenate([np.asarray(t.input_counts) for t in record.ticks])
    assert not np.array_equal(delivered, draws)  # the gap removed kicks
    assert np.array_equal(delivered, dead_time(draws, GAP))


def test_a_zero_gap_keeps_the_raw_counts_and_a_negative_one_refuses():
    assert run(input_gap_steps=0) == run()
    with pytest.raises(ContractError, match="input_gap_steps"):
        run(input_gap_steps=-1)


def test_a_resumed_run_keeps_the_dead_time_across_the_break(tmp_path):
    whole = run(transducer=_fast, input_gap_steps=GAP)
    with pytest.raises(ContractError, match="killed"):
        run(
            body=Crash(23_500),
            transducer=_fast,
            input_gap_steps=GAP,
            checkpoint_dir=tmp_path,
            checkpoint_every_us=5000,
        )
    with pytest.raises(ContractError, match="another run"):
        run(
            transducer=_fast,
            input_gap_steps=GAP + 1,
            checkpoint_dir=tmp_path,
            checkpoint_every_us=5000,
        )
    resumed = run(
        transducer=_fast,
        input_gap_steps=GAP,
        checkpoint_dir=tmp_path,
        checkpoint_every_us=5000,
    )
    assert resumed == whole


V1_FIELDS = {
    "arm",
    "clock",
    "evidence",
    "input_ids",
    "mode",
    "optics_config_sha256",
    "provenance",
    "run_identity_sha256",
    "schema",
    "silenced_ids",
    "ticks",
    "traced_ids",
}
V1_TICK_FIELDS = {
    "commands",
    "contacts",
    "input_counts",
    "spikes",
    "state",
    "stepped",
    "stimulus",
    "time_us",
}
PATHWAY = "d" * 64
OTHER_PATHWAY = "e" * 64


def kick_runtime(duration_us=40_000):
    edges, sign, n = chain([400])
    p = sim.Params()
    return CpuRuntime(
        sim.weight_matrix(edges, sign, n, p.w_syn),
        np.array([0]),
        steps=duration_us // CLOCK.neural_us,
        kicks=np.zeros((0, 1), dtype=np.float32),
        p=p,
        per_bin=CLOCK.control_us // CLOCK.neural_us,
        trace=np.array([1]),
        input_encoding="kick_equivalent",
    )


def kick_transducer(stim):
    """One kick per step, with the first step a float32 fraction of the stimulus."""
    per = CLOCK.body_us // CLOCK.neural_us
    raw = max(0.0, stim[0])
    unit = np.float32(raw / (1.0 + raw))
    drive = np.full((per, 1), np.float32(1.0), dtype=np.float32)
    drive[0, 0] = unit
    return drive


def kick_run(arm="intact", body=None, **kw):
    if "runtime" not in kw:
        kw["runtime"] = kick_runtime()
    kw.setdefault("transducer", kick_transducer)
    kw.setdefault("input_encoding", "kick_equivalent")
    kw.setdefault("pathway_sha256", PATHWAY)
    return run(arm, body=body, **kw)


def test_a_counts_run_stays_byte_identical_to_the_v1_record():
    plain = run()
    text = plain.to_json()
    assert type(plain) is closedloop.Record
    assert plain.schema == closedloop.SCHEMA == "flymsg.closedloop/v1"
    assert closedloop.from_json(text) == plain
    assert closedloop.from_json(text).to_json() == text
    document = json.loads(text)
    assert set(document) == V1_FIELDS
    assert set(document["ticks"][0]) == V1_TICK_FIELDS
    assert "input_drive" not in text
    assert "input_encoding" not in text
    assert "pathway_sha256" not in text
    # the bytes the code produced before record v2 (main 155058f, same toy runs)
    assert hashlib.sha256(text.encode()).hexdigest() == (
        "3dce36bcb451d021620eecb78e1911756a9b3717276a2b9e7fa22cc2e23e5208"
    )
    gapped = run(transducer=_fast, input_gap_steps=GAP).to_json()
    assert hashlib.sha256(gapped.encode()).hexdigest() == (
        "337446edc5f17d5206e37615fdc067ed2722dac7b0ed4e51cbbcf2d0edc53b32"
    )
    with pytest.raises(ContractError, match="no pathway"):
        run(pathway_sha256=PATHWAY)
    archived = json.dumps(document, sort_keys=True, separators=(",", ":"))
    assert archived == text
    assert closedloop.from_json(archived).to_json() == archived


def test_kick_equivalent_records_the_drive_and_replays_it():
    delivered = []

    def watch(stim):
        drive = kick_transducer(stim)
        delivered.append(drive.copy())
        return drive

    rt = kick_runtime()
    record = kick_run(runtime=rt, transducer=watch)
    assert type(record) is closedloop.RecordV2
    assert record.schema == closedloop.SCHEMA_V2 == "flymsg.closedloop/v2"
    assert record.input_encoding == "kick_equivalent"
    assert record.pathway_sha256 == PATHWAY
    text = record.to_json()
    assert closedloop.from_json(text) == record
    assert closedloop.from_json(text).to_json() == text
    stacked = np.concatenate(delivered)
    recorded = np.concatenate(
        [np.asarray(tick.input_drive, dtype=np.float64) for tick in record.ticks]
    )
    assert recorded.shape == stacked.shape
    assert recorded.tobytes() == stacked.astype(np.float64).tobytes()
    stored = rt.snapshot()["input_drive"][: recorded.shape[0]]
    assert stored.tobytes() == recorded.tobytes()
    again = kick_run("replay", replay=record)
    closedloop.replay_parity(record, again)
    assert [tick.spikes for tick in again.ticks] == [
        tick.spikes for tick in record.ticks
    ]
    assert any(tick.spikes for tick in record.ticks)
    replayed = np.concatenate(
        [np.asarray(tick.input_drive, dtype=np.float64) for tick in again.ticks]
    )
    assert replayed.tobytes() == recorded.tobytes()
    rows = list(record.ticks[0].input_drive)
    rows[0] = (rows[0][0] + 1.0,)
    ticks = list(record.ticks)
    ticks[0] = dataclasses.replace(ticks[0], input_drive=tuple(rows))
    with pytest.raises(ContractError, match="input drive differs"):
        closedloop.replay_parity(dataclasses.replace(record, ticks=tuple(ticks)), again)


def test_encoding_pathway_and_drive_refuse_before_any_step(tmp_path):
    record = kick_run()
    closed = run()
    body = ToyBody()
    with pytest.raises(ContractError, match="encoding or pathway"):
        run("replay", replay=record, body=body)
    assert body.calls == []
    body = ToyBody()
    with pytest.raises(ContractError, match="encoding or pathway"):
        kick_run("replay", replay=record, body=body, pathway_sha256=OTHER_PATHWAY)
    assert body.calls == []
    body = ToyBody()
    with pytest.raises(ContractError, match="no pathway"):
        run(
            "replay",
            replay=closed,
            body=body,
            pathway_sha256=PATHWAY,
            runtime=runtime(),
        )
    assert body.calls == []
    body = ToyBody()
    with pytest.raises(ContractError, match="encoding or pathway"):
        kick_run("replay", replay=closed, body=body)
    assert body.calls == []
    body = ToyBody()
    with pytest.raises(ContractError, match="kick_equivalent"):
        kick_run(body=body, input_gap_steps=1)
    assert body.calls == []
    body = ToyBody()
    with pytest.raises(ContractError, match="pathway"):
        kick_run(body=body, pathway_sha256=None)
    assert body.calls == []
    body = ToyBody()
    with pytest.raises(ContractError, match="runtime input encoding"):
        kick_run(body=body, runtime=runtime())
    assert body.calls == []

    text = record.to_json()
    bad = json.loads(text)
    bad["ticks"][0]["input_drive"][0][0] = 0.1
    with pytest.raises(ContractError, match="float32"):
        closedloop.from_json(json.dumps(bad))
    bad = json.loads(text)
    bad["ticks"][0]["input_drive"][0][0] = -1.0
    with pytest.raises(ContractError, match="finite"):
        closedloop.from_json(json.dumps(bad))
    bad = json.loads(text)
    bad["ticks"][0]["input_drive"][0][0] = float("nan")
    with pytest.raises(ContractError, match="finite"):
        closedloop.from_json(json.dumps(bad))
    bad = json.loads(text)
    bad["pathway_sha256"] = None
    with pytest.raises(ContractError, match="pathway"):
        closedloop.from_json(json.dumps(bad))
    del bad["pathway_sha256"]
    with pytest.raises(ContractError, match="missing"):
        closedloop.from_json(json.dumps(bad))

    counted = json.loads(text)
    counted["input_encoding"] = "counts"
    counted["pathway_sha256"] = None
    width = len(counted["ticks"][0]["input_drive"])
    for tick in counted["ticks"]:
        tick["input_drive"] = [[0] for _ in range(width)]
        tick["input_drive"][0] = [1]
    parsed = closedloop.from_json(json.dumps(counted))
    assert parsed.input_encoding == "counts" and parsed.pathway_sha256 is None
    assert parsed.to_json() == closedloop.from_json(parsed.to_json()).to_json()
    counted["ticks"][0]["input_drive"][0][0] = -1
    with pytest.raises(ContractError, match="integer"):
        closedloop.from_json(json.dumps(counted))
    counted["ticks"][0]["input_drive"][0][0] = 1
    counted["pathway_sha256"] = PATHWAY
    with pytest.raises(ContractError, match="no pathway"):
        closedloop.from_json(json.dumps(counted))

    with pytest.raises(ContractError, match="killed"):
        run(body=Crash(23_500), checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    idle = ToyBody()
    with pytest.raises(ContractError, match="encoding or pathway"):
        kick_run(body=idle, checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    assert idle.calls == []
    idle = ToyBody()
    with pytest.raises(ContractError, match="no pathway"):
        run(
            body=idle,
            pathway_sha256=OTHER_PATHWAY,
            checkpoint_dir=tmp_path,
            checkpoint_every_us=5000,
        )
    assert idle.calls == []


def test_a_resumed_kick_equivalent_run_equals_the_uninterrupted_one(tmp_path):
    whole = kick_run()
    with pytest.raises(ContractError, match="killed"):
        kick_run(body=Crash(23_500), checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    idle = ToyBody()
    with pytest.raises(ContractError, match="encoding or pathway"):
        kick_run(
            body=idle,
            pathway_sha256=OTHER_PATHWAY,
            checkpoint_dir=tmp_path,
            checkpoint_every_us=5000,
        )
    assert idle.calls == []
    idle = ToyBody()
    with pytest.raises(ContractError, match="encoding or pathway"):
        run(body=idle, checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    assert idle.calls == []
    resumed = kick_run(checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    assert resumed == whole
    assert resumed.to_json() == whole.to_json()
