"""G5 (#180): the closed-loop schedule, evidence gate and record of the body-wiring ADR.

`docs/adr-body-wiring.md` keeps the B6 v2 / M0 v1 clock order. At each control tick T,
spikes of earlier ticks whose time + latency <= T become actuator commands, held until the
next control tick. Then, per body tick [t, t + body):

1. sample: the body state at t (the last one stepped, never a later one);
2. stimulus: the world at t projected onto the columns;
3. input: seeded counts for the neural steps of the tick, recorded;
4. neural: `CpuRuntime` advances to t + body;
5. physics: the body steps to t + body under the held command.

Every component carries an evidence status. A biological run refuses unless all are
`measured`; none is today (transducer, registration and motor map are not), so only
synthetic runs execute, and their record says so. The statuses are declared by the caller;
the motor map is also enforced in code, through `pose.command`. The body is an adapter
passed in: a toy one in the tests, FlyGym's NeuroMechFly in `flymsg.flygym_body`. M0 v1, B6 v2, M2 (`loop`) and
`CpuRuntime` are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Protocol

import numpy as np

from flymsg import optics, pose, runstore
from flymsg.embodiment import Clock, ContractError, SpikeEvent, integer
from flymsg.runtime import CpuRuntime

SCHEMA = "flymsg.closedloop/v1"
PHASES = ("command", "sample", "stimulus", "input", "neural", "physics")
STATUSES = ("measured", "engineered", "unmapped", "synthetic")
COMPONENTS = ("registration", "transducer", "motor_map", "body")
MODES = ("biological", "synthetic")
# disconnected is the open loop: the input sees the body held at its initial pose
ARMS = ("intact", "disconnected", "shuffled", "replay", "silenced")

Command = tuple[pose.ActuatorRef, float]
Contact = tuple[str, float]  # contact name, normal force in N


@dataclass(frozen=True)
class Step:
    phase: str
    time_us: int


def schedule(clock: Clock, duration_us: int) -> tuple[Step, ...]:
    """The ordered steps of a run: a command per control tick, the rest per body tick."""
    clock.validate()
    integer(duration_us, "duration_us", 1)
    if duration_us % clock.control_us:
        raise ContractError("duration must be a multiple of the control period")
    steps = []
    for t in range(0, duration_us, clock.body_us):
        if t % clock.control_us == 0:
            steps.append(Step("command", t))
        steps += [Step(phase, t) for phase in PHASES[1:]]
    return tuple(steps)


def require(evidence: dict[str, str], mode: str) -> None:
    """Refuse a missing or unknown status, and a biological run on anything unmeasured."""
    if mode not in MODES:
        raise ContractError(f"mode must be one of {', '.join(MODES)}")
    if sorted(evidence) != sorted(COMPONENTS):
        raise ContractError(f"evidence must name exactly {', '.join(COMPONENTS)}")
    for name, status in evidence.items():
        if status not in STATUSES:
            raise ContractError(f"{name} has unknown status {status!r}")
    unmeasured = sorted(k for k, v in evidence.items() if v != "measured")
    if mode == "biological" and unmeasured:
        raise ContractError(
            f"a biological run needs measured components; not: {', '.join(unmeasured)}"
        )


class Body(Protocol):
    """A v2 body adapter: B6 v2 states, compiled actuators, named contact forces."""

    def reset(self) -> pose.BodyState: ...

    def step(
        self, commands: tuple[Command, ...], dt_us: int
    ) -> tuple[pose.BodyState, tuple[Contact, ...]]: ...


@dataclass(frozen=True)
class Tick:
    """One body tick [time_us, time_us + body)."""

    time_us: int
    commands: tuple[
        tuple[str, int, float], ...
    ]  # held: actuator name, MuJoCo id, value
    state: pose.BodyState  # the state the stimulus was computed from
    stimulus: tuple[float, ...]  # per column
    input_counts: tuple[tuple[int, ...], ...]  # (neural steps, inputs)
    spikes: tuple[SpikeEvent, ...]  # MaleCNS bodyIds, in time order
    stepped: pose.BodyState  # the body after the physics step
    contacts: tuple[Contact, ...]


@dataclass(frozen=True)
class Record:
    provenance: pose.Provenance
    clock: Clock
    arm: str
    mode: str
    evidence: tuple[tuple[str, str], ...]
    optics_config_sha256: str
    run_identity_sha256: str
    input_ids: tuple[int, ...]  # bodyIds of the inputs, in runtime order
    traced_ids: tuple[int, ...]  # bodyIds whose spikes are recorded
    silenced_ids: tuple[
        int, ...
    ]  # declared by the caller; the runtime does not expose it
    ticks: tuple[Tick, ...]
    schema: str = SCHEMA

    def validate(self) -> None:
        if self.schema != SCHEMA:
            raise ContractError(f"not a {SCHEMA} record")
        self.provenance.validate()
        self.clock.validate()
        if self.arm not in ARMS:
            raise ContractError(f"arm must be one of {', '.join(ARMS)}")
        if any(len(e) != 2 for e in self.evidence) or len(
            {e[0] for e in self.evidence}
        ) != len(self.evidence):
            raise ContractError("evidence must be unique (component, status) pairs")
        require(dict(self.evidence), self.mode)
        for name in ("optics_config_sha256", "run_identity_sha256"):
            _sha256(getattr(self, name), name)
        if (self.arm == "silenced") != bool(self.silenced_ids):
            raise ContractError("only the silenced arm names silenced neurons")
        if not self.input_ids or not self.traced_ids:
            raise ContractError("a record needs input and traced bodyIds")
        for v in (*self.input_ids, *self.traced_ids, *self.silenced_ids):
            integer(v, "bodyId")
        if not self.ticks:
            raise ContractError("a record needs at least one tick")
        c = self.clock
        end = len(self.ticks) * c.body_us
        if end % c.control_us:
            raise ContractError("the record does not end on a control tick")
        per = c.body_us // c.neural_us
        columns = len(self.ticks[0].stimulus)
        last_spike = -1
        for k, tick in enumerate(self.ticks):
            t = k * c.body_us
            if tick.time_us != t:
                raise ContractError(f"tick {k} is off the body grid")
            seen = tick.state.time_us
            if seen % c.body_us or seen >= end:
                raise ContractError(f"tick {k} read a state off the run")
            if self.arm != "shuffled" and seen != t:
                raise ContractError(f"tick {k} did not read the state at its start")
            if tick.stepped.time_us != t + c.body_us:
                raise ContractError(f"tick {k} physics is off the body grid")
            if (
                self.arm in ("intact", "silenced")
                and k
                and tick.state != self.ticks[k - 1].stepped
            ):
                raise ContractError(f"tick {k} did not read the last stepped state")
            if t % c.control_us and tick.commands != self.ticks[k - 1].commands:
                raise ContractError(
                    f"tick {k} changed the command between control ticks"
                )
            for command in tick.commands:
                if len(command) != 3:
                    raise ContractError(f"tick {k} has a malformed command")
                name, mujoco_id, value = command
                integer(mujoco_id, "mujoco_id")
                if type(name) is not str or not name or not _finite(value):
                    raise ContractError(f"tick {k} has a malformed command")
            if not columns or len(tick.stimulus) != columns:
                raise ContractError(f"tick {k} stimulus needs one value per column")
            if not all(_finite(v) for v in tick.stimulus):
                raise ContractError(f"tick {k} stimulus is not finite")
            if len(tick.input_counts) != per or any(
                len(row) != len(self.input_ids) for row in tick.input_counts
            ):
                raise ContractError(f"tick {k} input counts do not fit the tick")
            for row in tick.input_counts:
                for v in row:
                    integer(v, "input count")
            for s in tick.spikes:
                integer(s.time_us, "spike time")
                if (
                    s.neuron_id not in self.traced_ids
                    or not t <= s.time_us < t + c.body_us
                    or s.time_us % c.neural_us
                    or s.time_us < last_spike
                ):
                    raise ContractError(f"tick {k} has a spike out of place")
                last_spike = s.time_us
            _contacts(tick.contacts)

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _sha256(value: str, name: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ContractError(f"{name} must be a lowercase SHA-256")


def _state(d: dict) -> pose.BodyState:
    p = d["pose"]
    q = p["orientation"]
    if set(q) != set("wxyz"):
        raise ContractError("orientation needs exactly w, x, y, z")
    return pose.BodyState(
        d["time_us"],
        pose.Pose(
            p["parent"],
            p["child"],
            tuple(p["position_m"]),
            pose.Quat(*(q[k] for k in "wxyz")),
        ),
        tuple(d["linear_velocity_m_s"]),
        tuple(d["angular_velocity_rad_s"]),
    )


def _tick(t: dict) -> Tick:
    return Tick(
        t["time_us"],
        tuple(tuple(c) for c in t["commands"]),
        _state(t["state"]),
        tuple(t["stimulus"]),
        tuple(tuple(r) for r in t["input_counts"]),
        tuple(SpikeEvent(**s) for s in t["spikes"]),
        _state(t["stepped"]),
        tuple(tuple(c) for c in t["contacts"]),
    )


def from_json(text: str) -> Record:
    """Parse a closed-loop record; another schema, an unknown or missing field refuses."""
    try:
        d = json.loads(text)
        if d.get("schema") != SCHEMA:
            raise ContractError(f"not a {SCHEMA} record")
        if set(d) != {f.name for f in fields(Record)}:
            raise ContractError("unknown or missing record fields")
        record = Record(
            pose.Provenance(**d["provenance"]),
            Clock(**d["clock"]),
            d["arm"],
            d["mode"],
            tuple(tuple(e) for e in d["evidence"]),
            d["optics_config_sha256"],
            d["run_identity_sha256"],
            tuple(d["input_ids"]),
            tuple(d["traced_ids"]),
            tuple(d["silenced_ids"]),
            tuple(_tick(t) for t in d["ticks"]),
            d["schema"],
        )
        record.validate()
    except ContractError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as err:
        raise ContractError(f"malformed closed-loop record: {err!r}") from err
    return record


def _adapter(call, *args, what="body adapter"):
    """A body or runtime call; any failure inside it becomes a ContractError."""
    try:
        return call(*args)
    except ContractError:
        raise
    except Exception as err:
        raise ContractError(f"{what} failed: {err!r}") from err


def _held(state: pose.BodyState, time_us: int) -> pose.BodyState:
    """The body as the open loop sees it: its initial pose, at rest, at `time_us`."""
    return pose.BodyState(time_us, state.pose, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def optical(
    columns: optics.Columns,
    registration: pose.Registration,
    mounts: tuple[pose.EyeMount, pose.EyeMount],
    spheres: tuple[optics.Sphere, ...],
    acceptance_deg: float,
) -> tuple[Callable[[int, pose.BodyState], tuple[float, ...]], str]:
    """The ADR's stimulus step on `optics.sample`, and its configuration hash.

    Per column with a lens, the largest single-sphere coverage of its acceptance profile:
    `optics` does not subtract overlapping silhouettes, so where they overlap this is a
    lower bound on the dark share. Columns without a lens are left out, the same ones at
    every tick. The world is read at the time of the state given, so the stimulus is a pure
    function of (time, state). The columns, spheres and mounts must not be mutated during
    a run: the hash names them, it does not watch them.
    """
    config = optics.config_sha256(
        columns, registration, mounts, spheres, acceptance_deg
    )
    has = np.isfinite(columns.direction).all(axis=1)

    def stimulus(time_us: int, state: pose.BodyState) -> tuple[float, ...]:
        if state.time_us != time_us:
            raise ContractError("the stimulus is read at the state's own time")
        sample = optics.sample(
            columns, registration, mounts, state, spheres, acceptance_deg
        )
        return tuple(float(v) for v in sample.coverage[:, has].max(axis=0))

    return stimulus, config


def run(
    runtime: CpuRuntime,
    body: Body,
    *,
    input_ids: tuple[int, ...],
    traced_ids: tuple[int, ...],
    stimulus: Callable[[int, pose.BodyState], tuple[float, ...]],
    transducer: Callable[[tuple[float, ...]], np.ndarray],
    decoder: Callable[[tuple[SpikeEvent, ...]], tuple[Command, ...]],
    compiled: dict[str, int],
    clock: Clock,
    duration_us: int,
    arm: str,
    mode: str,
    evidence: dict[str, str],
    provenance: pose.Provenance,
    optics_config_sha256: str,
    run_identity_sha256: str,
    input_gap_steps: int,
    silenced_ids: tuple[int, ...] = (),
    replay: Record | None = None,
    checkpoint_dir: Path | None = None,
    checkpoint_every_us: int | None = None,
    tick_wall_s: list[float] | None = None,
) -> Record:
    """One arm of a closed loop in the ADR order.

    Evidence, clock, arm, replay and runtime shape are checked before the body is reset; a
    runtime too short for `duration_us` fails at its first overflowing call, as a
    ContractError. `runtime` is fresh, built by the caller on `clock.neural_us` with zero
    kicks, its inputs in `input_ids` order and `traced_ids` traced (and, for the silenced
    arm, `silenced_ids` silenced: the runtime does not expose it, so the record states what
    the caller declared). `stimulus` must be a pure function of the time and state it is
    given; `transducer` returns one rate in Hz per input; `decoder` turns delivered spikes
    into actuator commands.

    The kernel adds an input kick to the potential even while that neuron is refractory,
    so `input_gap_steps` > 0 keeps at most one kick per step and none within that many
    neural steps of the previous kept one, per input, across body ticks (the rule of
    `stimulus.dead_time`, applied to the same Poisson draws). 0 keeps the raw counts. The
    recorded `input_counts` are the counts delivered.

    With `checkpoint_dir`, the loop writes a checkpoint every `checkpoint_every_us` at a
    control tick (runtime, body and loop state, bound by their hashes) and, if the directory
    holds one, resumes from it: the caller passes a fresh runtime and a body of the same
    construction, and the arguments must be those of the checkpointed run. A resumed run's
    record equals the uninterrupted one. The body must offer `snapshot(path)` and
    `restore(path)`. The identity binds the run's arguments, not the callables or
    `compiled`: those must be the same and `transducer` and `decoder` stateless, which only
    the caller can ensure.

    Optional `tick_wall_s` collects wall seconds for newly computed body ticks, including
    checkpoint work at their control boundaries. It does not enter the record, identity,
    RNG, numerical inputs or checkpoint. An already completed arm appends no samples.
    """
    require(evidence, mode)
    provenance.validate()
    integer(input_gap_steps, "input_gap_steps")
    steps = schedule(clock, duration_us)
    if arm not in ARMS:
        raise ContractError(f"arm must be one of {', '.join(ARMS)}")
    if (arm == "silenced") != bool(silenced_ids):
        raise ContractError("only the silenced arm names silenced neurons")
    if (arm == "replay") != (replay is not None):
        raise ContractError("the replay arm, and only it, needs a recorded run")
    if runtime.step != 0 or runtime.tick_us != clock.neural_us:
        raise ContractError("the runtime must be fresh and on the neural tick")
    if (
        not traced_ids
        or runtime.n_inputs != len(input_ids)
        or runtime.traced_spikes(0, 0).shape[1] != len(traced_ids)
    ):
        raise ContractError("input and traced bodyIds must match the runtime")
    per = clock.body_us // clock.neural_us
    n_ticks = duration_us // clock.body_us
    if replay is not None:
        replay.validate()
        if (
            replay.arm == "replay"
            or replay.clock != clock
            or len(replay.ticks) != n_ticks
            or replay.input_ids != tuple(input_ids)
        ):
            raise ContractError("the recorded run does not fit this replay")
    rng = np.random.default_rng(provenance.seed)
    order = np.arange(n_ticks)
    if arm == "shuffled":
        # the open-loop stimuli in a seeded random order (as in `loop`)
        order = np.random.default_rng(provenance.seed + 1).permutation(n_ticks)

    identity = runstore.digest(
        {
            "schema": SCHEMA,
            "clock": asdict(clock),
            "duration_us": duration_us,
            "arm": arm,
            "mode": mode,
            "evidence": sorted(evidence.items()),
            "provenance": asdict(provenance),
            "ids": [list(input_ids), list(traced_ids), list(silenced_ids)],
            "hashes": [optics_config_sha256, run_identity_sha256],
            "input_gap_steps": input_gap_steps,
            "replay": None if replay is None else runstore.digest(replay.to_json()),
        }
    )
    if (checkpoint_dir is None) != (checkpoint_every_us is None):
        raise ContractError("a checkpoint needs both a directory and an interval")
    if checkpoint_dir is not None:
        integer(checkpoint_every_us, "checkpoint_every_us", 1)
        if checkpoint_every_us % clock.control_us:
            raise ContractError("checkpoints fall on control ticks")
        checkpoint_dir = Path(checkpoint_dir)
    if checkpoint_dir is not None and (checkpoint_dir / DONE).exists():
        return _finished(checkpoint_dir, identity)
    resumed = (
        _resume(checkpoint_dir, identity, runtime, body)
        if checkpoint_dir is not None and (checkpoint_dir / LOOP).exists()
        else None
    )
    if resumed is None:
        last = _adapter(body.reset)
        if not isinstance(last, pose.BodyState) or last.time_us != 0:
            raise ContractError("a body starts at time 0")
        initial, spikes, ticks, segments, begin = last, [], [], [], 0
    else:
        initial, last, spikes, ticks, rng_state, segments, begin = resumed
        rng.bit_generator.state = rng_state
    # neural step of each input's last delivered kick, rebuilt from the recorded ticks
    last_kick = np.full(len(input_ids), -input_gap_steps, dtype=np.int64)
    for j, tick in enumerate(ticks):
        rows, cols = np.nonzero(np.asarray(tick.input_counts, dtype=np.int64))
        last_kick[cols] = np.maximum(last_kick[cols], j * per + rows)
    delivered = 0
    commands: tuple[Command, ...] = ()
    tick_start = time.perf_counter()
    for step in steps:
        t = step.time_us
        k = t // clock.body_us
        if t < begin:
            continue
        if step.phase == "command":
            tick_start = time.perf_counter()
            if (
                checkpoint_dir is not None
                and t > begin
                and t % checkpoint_every_us == 0
            ):
                # delivered spikes live in the ticks; keep only the pending ones
                spikes, delivered = spikes[delivered:], 0
                segments = _checkpoint(
                    checkpoint_dir,
                    identity,
                    runtime,
                    body,
                    t,
                    (initial, last, spikes, ticks, rng.bit_generator.state, segments),
                )
            eligible = delivered
            while (
                eligible < len(spikes)
                and spikes[eligible].time_us + clock.latency_us <= t
            ):
                eligible += 1
            commands = _commands(
                decoder(tuple(spikes[delivered:eligible])), compiled, mode
            )
            delivered = eligible
        elif step.phase == "sample":
            if t % clock.control_us:
                tick_start = time.perf_counter()
            if last.time_us != t:
                raise ContractError("the last stepped state is not at this tick")
            if arm in ("intact", "silenced"):
                seen = last
            else:
                seen = _held(initial, int(order[k]) * clock.body_us)
        elif step.phase == "stimulus":
            if replay is not None:
                stim = replay.ticks[k].stimulus  # what produced the replayed counts
            else:
                stim = tuple(float(v) for v in stimulus(seen.time_us, seen))
                if not stim or not all(math.isfinite(v) for v in stim):
                    raise ContractError(
                        "the stimulus needs one finite value per column"
                    )
        elif step.phase == "input":
            if replay is not None:
                counts = np.asarray(replay.ticks[k].input_counts, dtype=np.int64)
            else:
                rates = np.asarray(transducer(stim), dtype=float)
                if rates.shape != (len(input_ids),) or not (
                    np.isfinite(rates).all() and (rates >= 0).all()
                ):
                    raise ContractError(
                        "the transducer must give one finite rate >= 0 per input"
                    )
                counts = rng.poisson(
                    rates * clock.neural_us / 1e6, (per, len(input_ids))
                )
                if input_gap_steps:
                    counts = _dead_time(counts, k * per, last_kick, input_gap_steps)
            _adapter(runtime.schedule_inputs, counts, what="runtime")
        elif step.phase == "neural":
            start = k * per
            _adapter(runtime.advance_to, start + per, what="runtime")
            bits = runtime.traced_spikes(start, start + per)
            new = [
                SpikeEvent(traced_ids[int(j)], (start + int(i)) * clock.neural_us)
                for i, j in zip(*np.nonzero(bits), strict=True)
            ]
            spikes += new
        else:
            state, contacts = _adapter(body.step, commands, clock.body_us)
            if (
                not isinstance(state, pose.BodyState)
                or state.time_us != t + clock.body_us
            ):
                raise ContractError("the body returned a state off the body grid")
            ticks.append(
                Tick(
                    t,
                    tuple((a.name, a.mujoco_id, v) for a, v in commands),
                    seen,
                    stim,
                    tuple(tuple(int(c) for c in row) for row in counts),
                    tuple(new),
                    state,
                    _contacts(contacts),
                )
            )
            last = state
            if tick_wall_s is not None:
                tick_wall_s.append(time.perf_counter() - tick_start)
    record = Record(
        provenance,
        clock,
        arm,
        mode,
        tuple(sorted(evidence.items())),
        optics_config_sha256,
        run_identity_sha256,
        tuple(input_ids),
        tuple(traced_ids),
        tuple(silenced_ids),
        tuple(ticks),
    )
    record.validate()
    if checkpoint_dir is not None:
        # a finished run answers a rerun with its record, never by computing again
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        runstore.atomic_json(
            checkpoint_dir / DONE,
            {
                "schema": SCHEMA + "/done",
                "identity": identity,
                "record": json.loads(record.to_json()),
            },
        )
    return record


LOOP = "loop.json"
DONE = "record.json"
# the files a checkpoint writes; cleanup touches nothing else in the directory
OWNED = re.compile(r"(neural|body)-\d+\.npz(\.tmp)?|ticks-\d+\.json")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fsync(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _checkpoint(directory, identity, runtime, body, time_us, loop) -> list:
    """Write the runtime, the body and the ticks since the previous checkpoint under names
    of this tick, flush them, then the loop state that binds them by hash; files no loop
    state names go only after the new one is in place. Returns the tick segments so far."""
    initial, last, pending, ticks, rng_state, segments = loop
    directory.mkdir(parents=True, exist_ok=True)
    neural = directory / f"neural-{time_us}.npz"
    physics = directory / f"body-{time_us}.npz"
    segment = directory / f"ticks-{time_us}.json"
    _adapter(runtime.checkpoint, neural, what="runtime")
    _adapter(body.snapshot, physics)
    done = sum(n for _, _, n in segments)
    try:
        segment.write_bytes(runstore.canonical([asdict(t) for t in ticks[done:]]))
    except ValueError as err:  # a non-finite value cannot be stored
        raise ContractError(f"the ticks cannot be checkpointed: {err}") from err
    for path in (neural, physics, segment):
        _fsync(path)
    runstore.sync_dir(directory)
    segments = [*segments, [segment.name, _sha256_file(segment), len(ticks) - done]]
    runstore.atomic_json(
        directory / LOOP,
        {
            "schema": SCHEMA + "/checkpoint",
            "identity": identity,
            "time_us": time_us,
            "files": {
                "neural": [neural.name, _sha256_file(neural)],
                "body": [physics.name, _sha256_file(physics)],
            },
            "segments": segments,
            "initial": asdict(initial),
            "last": asdict(last),
            "pending": [asdict(s) for s in pending],  # spikes not yet delivered
            "rng": rng_state,
        },
    )
    keep = {neural.name, physics.name, LOOP, *(name for name, _, _ in segments)}
    for old in directory.iterdir():
        if old.is_file() and old.name not in keep and OWNED.fullmatch(old.name):
            old.unlink()
    return segments


def _finished(directory: Path, identity: str) -> Record:
    try:
        d = json.loads((directory / DONE).read_text())
        if d.get("schema") != SCHEMA + "/done" or d.get("identity") != identity:
            raise ContractError("the finished record belongs to another run")
        text = json.dumps(d["record"], sort_keys=True, separators=(",", ":"))
    except ContractError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OSError) as err:
        raise ContractError(f"malformed finished record: {err!r}") from err
    return from_json(text)


def _resume(directory, identity, runtime, body):
    try:
        d = json.loads((directory / LOOP).read_text())
        if d.get("schema") != SCHEMA + "/checkpoint" or d.get("identity") != identity:
            raise ContractError("the checkpoint belongs to another run")
        paths = {}
        for key, (name, digest) in d["files"].items():
            paths[key] = directory / name
            if _sha256_file(paths[key]) != digest:
                raise ContractError(f"the {key} checkpoint does not match its hash")
        ticks = []
        for name, digest, count in d["segments"]:
            if _sha256_file(directory / name) != digest:
                raise ContractError(f"the tick segment {name} does not match its hash")
            part = json.loads((directory / name).read_text())
            if len(part) != count:
                raise ContractError(f"the tick segment {name} has the wrong length")
            ticks += [_tick(t) for t in part]
        _adapter(runtime.restore, paths["neural"], what="runtime")
        _adapter(body.restore, paths["body"])
        last = _state(d["last"])
        time_us = d["time_us"]
        integer(time_us, "checkpoint time")
        if (
            last.time_us != time_us
            or runtime.step * runtime.tick_us != time_us
            or (ticks and ticks[-1].stepped != last)
        ):
            raise ContractError("the checkpoint parts disagree on its time")
        return (
            _state(d["initial"]),
            last,
            [SpikeEvent(**s) for s in d["pending"]],
            ticks,
            d["rng"],
            [list(seg) for seg in d["segments"]],
            time_us,
        )
    except ContractError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OSError) as err:
        raise ContractError(f"malformed checkpoint: {err!r}") from err


def _dead_time(
    counts: np.ndarray, start: int, last_kick: np.ndarray, gap: int
) -> np.ndarray:
    """`stimulus.dead_time` continued across ticks; updates `last_kick` in place."""
    out = np.zeros(counts.shape, np.int64)
    for i, j in zip(
        *np.nonzero(counts), strict=True
    ):  # row-major: time order per input
        t = start + int(i)
        if t - last_kick[j] >= gap:
            out[i, j] = 1
            last_kick[j] = t
    return out


def _commands(raw, compiled: dict[str, int], mode: str) -> tuple[Command, ...]:
    out = []
    for actuator, value in raw:
        if not isinstance(actuator, pose.ActuatorRef) or not _finite(value):
            raise ContractError("a command is an actuator and a finite value")
        if mode == "biological":
            pose.command(actuator, compiled)  # the motor map refuses every row today
        elif compiled.get(actuator.name) != actuator.mujoco_id:
            raise ContractError(
                f"{actuator.name} is not compiled actuator {actuator.mujoco_id}"
            )
        out.append((actuator, float(value)))
    return tuple(out)


def _contacts(raw) -> tuple[Contact, ...]:
    out = tuple(tuple(c) for c in raw)
    if any(
        len(c) != 2
        or type(c[0]) is not str
        or not c[0]
        or not _finite(c[1])
        or c[1] < 0
        for c in out
    ):
        raise ContractError("a contact is a name and a finite normal force >= 0 in N")
    return tuple((name, float(force)) for name, force in out)


def replay_parity(original: Record, replayed: Record) -> None:
    """Refuse unless the replay fed the same counts and produced the same spikes."""
    if replayed.arm != "replay" or original.arm == "replay":
        raise ContractError("compare a recorded arm with its replay")
    if len(original.ticks) != len(replayed.ticks):
        raise ContractError("the replay has a different length")
    for a, b in zip(original.ticks, replayed.ticks, strict=True):
        if a.input_counts != b.input_counts:
            raise ContractError(f"input counts differ at {a.time_us} us")
        if a.spikes != b.spikes:
            raise ContractError(f"spikes differ at {a.time_us} us")
