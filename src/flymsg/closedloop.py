"""G5 (#180): the closed-loop schedule, evidence gate and record of the body-wiring ADR.

`docs/adr-body-wiring.md` fixes one causal order per control tick T, period [T, T + control):

1. command: spikes of earlier periods whose time + latency <= T become actuator commands;
2. sample: the body state at T (`pose.state_at`, never a later one);
3. stimulus: the world at T projected onto the columns;
4. input: seeded counts for the neural steps of the period, recorded;
5. neural: `CpuRuntime` advances to T + control;
6. physics: the body steps in body ticks under the command of step 1, held.

Every component carries an evidence status. A biological run refuses unless all are
`measured`; none is today (transducer, registration and motor map are not), so only
synthetic runs execute, and their record says so. No body is wired here: the body is an
adapter passed in, and the tests use a toy one. M0 v1, B6 v2 and `CpuRuntime` are unchanged.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

from flymsg import pose
from flymsg.embodiment import Clock, ContractError, SpikeEvent, integer
from flymsg.runtime import CpuRuntime

SCHEMA = "flymsg.closedloop/v1"
PHASES = ("command", "sample", "stimulus", "input", "neural", "physics")
STATUSES = ("measured", "engineered", "unmapped", "synthetic")
COMPONENTS = ("registration", "transducer", "motor_map", "body")
MODES = ("biological", "synthetic")
ARMS = ("intact", "disconnected", "shuffled", "replay", "silenced")

Command = tuple[pose.ActuatorRef, float]
Contact = tuple[str, float]  # contact name, normal force in N


@dataclass(frozen=True)
class Step:
    phase: str
    time_us: int


def schedule(clock: Clock, duration_us: int) -> tuple[Step, ...]:
    """The ordered steps of a run; physics appears once per body tick."""
    clock.validate()
    integer(duration_us, "duration_us", 1)
    if duration_us % clock.control_us:
        raise ContractError("duration must be a multiple of the control period")
    steps = []
    for t in range(0, duration_us, clock.control_us):
        steps += [Step(phase, t) for phase in PHASES[:-1]]
        steps += [
            Step("physics", b) for b in range(t, t + clock.control_us, clock.body_us)
        ]
    return tuple(steps)


def check_order(steps: tuple[Step, ...], clock: Clock) -> None:
    """Refuse steps out of the ADR order, off their grid or going back in time."""
    clock.validate()
    expected_physics = clock.control_us // clock.body_us
    i, t = 0, 0
    while i < len(steps):
        head = steps[i : i + len(PHASES) - 1]
        if [(s.phase, s.time_us) for s in head] != [(p, t) for p in PHASES[:-1]]:
            raise ContractError(f"steps at {t} us are not in the ADR order")
        body = steps[i + len(head) : i + len(head) + expected_physics]
        if [(s.phase, s.time_us) for s in body] != [
            ("physics", b) for b in range(t, t + clock.control_us, clock.body_us)
        ]:
            raise ContractError(f"physics at {t} us is off the body grid")
        i += len(head) + expected_physics
        t += clock.control_us


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
class Physics:
    state: pose.BodyState
    contacts: tuple[Contact, ...]


@dataclass(frozen=True)
class Tick:
    """One control period [time_us, time_us + control)."""

    time_us: int
    commands: tuple[tuple[str, int, float], ...]  # actuator name, MuJoCo id, value
    state: pose.BodyState  # the state the stimulus was computed from
    stimulus: tuple[float, ...]  # per column
    input_counts: tuple[tuple[int, ...], ...]  # (neural steps, inputs)
    spikes: tuple[SpikeEvent, ...]  # MaleCNS bodyIds
    physics: tuple[Physics, ...]  # one per body tick


@dataclass(frozen=True)
class Record:
    provenance: pose.Provenance
    clock: Clock
    arm: str
    mode: str
    evidence: tuple[tuple[str, str], ...]
    optics_config_sha256: str
    run_identity_sha256: str
    input_ids: tuple[int, ...]  # bodyIds of the input columns, in order
    silenced_ids: tuple[int, ...]
    ticks: tuple[Tick, ...]
    schema: str = SCHEMA

    def validate(self) -> None:
        if self.schema != SCHEMA:
            raise ContractError(f"not a {SCHEMA} record")
        self.provenance.validate()
        self.clock.validate()
        if self.arm not in ARMS:
            raise ContractError(f"arm must be one of {', '.join(ARMS)}")
        require(dict(self.evidence), self.mode)
        for name in ("optics_config_sha256", "run_identity_sha256"):
            _sha256(getattr(self, name), name)
        if (self.arm == "silenced") != bool(self.silenced_ids):
            raise ContractError("only the silenced arm names silenced neurons")
        for v in (*self.input_ids, *self.silenced_ids):
            integer(v, "bodyId")
        per = self.clock.control_us // self.clock.neural_us
        columns = len(self.ticks[0].stimulus) if self.ticks else 0
        for k, tick in enumerate(self.ticks):
            t = k * self.clock.control_us
            if tick.time_us != t:
                raise ContractError(f"tick {k} is off the control grid")
            if self.arm in ("intact", "silenced") and tick.state.time_us != t:
                raise ContractError(f"tick {k} did not read the state at its start")
            if any(
                not name or type(i) is not int or not math.isfinite(v)
                for name, i, v in tick.commands
            ):
                raise ContractError(f"tick {k} has a malformed command")
            if len(tick.stimulus) != columns or not all(
                math.isfinite(v) for v in tick.stimulus
            ):
                raise ContractError(f"tick {k} stimulus is not finite per column")
            if len(tick.input_counts) != per or any(
                len(row) != len(self.input_ids) or min(row, default=0) < 0
                for row in tick.input_counts
            ):
                raise ContractError(f"tick {k} input counts do not fit the period")
            for s in tick.spikes:
                integer(s.neuron_id, "bodyId")
                integer(s.time_us, "spike time")
            if any(not t <= s.time_us < t + self.clock.control_us for s in tick.spikes):
                raise ContractError(f"tick {k} has a spike outside its period")
            times = [p.state.time_us for p in tick.physics]
            if times != list(
                range(
                    t + self.clock.body_us,
                    t + self.clock.control_us + 1,
                    self.clock.body_us,
                )
            ):
                raise ContractError(f"tick {k} physics is off the body grid")

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def _sha256(value: str, name: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ContractError(f"{name} must be a lowercase SHA-256")


def _state(d: dict) -> pose.BodyState:
    q = d["pose"]["orientation"]
    if set(q) != set("wxyz"):
        raise ContractError("orientation needs exactly w, x, y, z")
    p = d["pose"]
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


def from_json(text: str) -> Record:
    """Parse a closed-loop record; any other schema or a missing field refuses."""
    try:
        d = json.loads(text)
        if d.get("schema") != SCHEMA:
            raise ContractError(f"not a {SCHEMA} record")
        record = Record(
            pose.Provenance(**d["provenance"]),
            Clock(**d["clock"]),
            d["arm"],
            d["mode"],
            tuple(tuple(e) for e in d["evidence"]),
            d["optics_config_sha256"],
            d["run_identity_sha256"],
            tuple(d["input_ids"]),
            tuple(d["silenced_ids"]),
            tuple(
                Tick(
                    t["time_us"],
                    tuple(tuple(c) for c in t["commands"]),
                    _state(t["state"]),
                    tuple(t["stimulus"]),
                    tuple(tuple(r) for r in t["input_counts"]),
                    tuple(SpikeEvent(**s) for s in t["spikes"]),
                    tuple(
                        Physics(
                            _state(p["state"]), tuple(tuple(c) for c in p["contacts"])
                        )
                        for p in t["physics"]
                    ),
                )
                for t in d["ticks"]
            ),
            d["schema"],
        )
    except ContractError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as err:
        raise ContractError(f"malformed closed-loop record: {err!r}") from err
    record.validate()
    return record


def _adapter(call, *args):
    """A body call; any failure inside it becomes a ContractError that stops the run."""
    try:
        return call(*args)
    except ContractError:
        raise
    except Exception as err:
        raise ContractError(f"body adapter failed: {err!r}") from err


def _held(state: pose.BodyState, time_us: int) -> pose.BodyState:
    """The body as the disconnected arm sees it: its initial pose, at rest, at `time_us`."""
    return pose.BodyState(time_us, state.pose, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


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
    silenced_ids: tuple[int, ...] = (),
    replay: Record | None = None,
) -> Record:
    """One arm of a closed loop in the ADR order; refuses before the first step when the
    evidence, clock, horizon or arm inputs do not fit.

    `runtime` is fresh, built by the caller on `clock.neural_us` with zero kicks, its inputs
    in `input_ids` order and `traced_ids` traced (and, for the silenced arm, `silenced_ids`
    silenced). `stimulus` sees only the time and the sampled state; `transducer` returns one
    rate in Hz per input; `decoder` turns delivered spikes into actuator commands.
    """
    require(evidence, mode)
    provenance.validate()
    steps = schedule(clock, duration_us)
    if arm not in ARMS:
        raise ContractError(f"arm must be one of {', '.join(ARMS)}")
    if (arm == "silenced") != bool(silenced_ids):
        raise ContractError("only the silenced arm names silenced neurons")
    if (arm == "replay") != (replay is not None):
        raise ContractError("the replay arm, and only it, needs a recorded run")
    if runtime.step != 0 or runtime.tick_us != clock.neural_us:
        raise ContractError("the runtime must be fresh and on the neural tick")
    if runtime.n_inputs != len(input_ids) or not traced_ids:
        raise ContractError("input and traced bodyIds must match the runtime")
    per = clock.control_us // clock.neural_us
    periods = duration_us // clock.control_us
    if replay is not None:
        replay.validate()
        if (
            replay.clock != clock
            or len(replay.ticks) != periods
            or replay.input_ids != tuple(input_ids)
        ):
            raise ContractError("the recorded run does not fit this replay")
    rng = np.random.default_rng(provenance.seed)
    dt_s = clock.neural_us / 1_000_000

    def counts_for(rates) -> np.ndarray:
        rates = np.asarray(rates, dtype=float)
        if rates.shape != (len(input_ids),) or not (
            np.isfinite(rates).all() and (rates >= 0).all()
        ):
            raise ContractError(
                "the transducer must give one finite rate >= 0 per input"
            )
        return rng.poisson(rates * dt_s, (per, len(input_ids)))

    initial = _adapter(body.reset)
    if initial.time_us != 0:
        raise ContractError("a body starts at time 0")
    states = [initial]
    order = np.arange(periods)
    if arm == "shuffled":
        # the disconnected stimuli, in a seeded random order (as in `loop`)
        order = np.random.default_rng(provenance.seed + 1).permutation(periods)
    spikes: list[SpikeEvent] = []
    delivered = 0
    ticks = []
    commands: tuple[Command, ...] = ()
    for step in steps:
        t = step.time_us
        if step.phase == "command":
            k = t // clock.control_us
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
            sampled = pose.state_at(tuple(states), t, clock)
            if arm in ("intact", "silenced"):
                seen = sampled
            else:
                seen = _held(initial, int(order[k]) * clock.control_us)
        elif step.phase == "stimulus":
            stim = tuple(float(v) for v in stimulus(seen.time_us, seen))
        elif step.phase == "input":
            if replay is not None:
                counts = np.asarray(replay.ticks[k].input_counts, dtype=np.int64)
            else:
                counts = counts_for(transducer(stim))
            runtime.schedule_inputs(counts)
        elif step.phase == "neural":
            start = k * per
            runtime.advance_to(start + per)
            bits = runtime.traced_spikes(start, start + per)
            if bits.shape[1] != len(traced_ids):
                raise ContractError("traced bodyIds must match the runtime")
            new = [
                SpikeEvent(traced_ids[int(j)], (start + int(i)) * clock.neural_us)
                for i, j in zip(*np.nonzero(bits), strict=True)
            ]
            spikes += new
            physics = []
        else:
            state, contacts = _adapter(body.step, commands, clock.body_us)
            if (
                not isinstance(state, pose.BodyState)
                or state.time_us != t + clock.body_us
            ):
                raise ContractError("the body returned a state off the body grid")
            physics.append(Physics(state, _contacts(contacts)))
            states.append(state)
            if state.time_us % clock.control_us == 0:
                ticks.append(
                    Tick(
                        k * clock.control_us,
                        tuple((a.name, a.mujoco_id, v) for a, v in commands),
                        seen,
                        stim,
                        tuple(tuple(int(c) for c in row) for row in counts),
                        tuple(new),
                        tuple(physics),
                    )
                )
    record = Record(
        provenance,
        clock,
        arm,
        mode,
        tuple(sorted(evidence.items())),
        optics_config_sha256,
        run_identity_sha256,
        tuple(input_ids),
        tuple(silenced_ids),
        tuple(ticks),
    )
    record.validate()
    return record


def _commands(raw, compiled: dict[str, int], mode: str) -> tuple[Command, ...]:
    out = []
    for actuator, value in raw:
        if not isinstance(actuator, pose.ActuatorRef) or not math.isfinite(value):
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
    out = tuple((str(name), float(force)) for name, force in raw)
    if any(not name or not math.isfinite(f) or f < 0 for name, f in out):
        raise ContractError("a contact is a name and a finite normal force >= 0 in N")
    return out


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
