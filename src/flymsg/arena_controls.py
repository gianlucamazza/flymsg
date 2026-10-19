"""Script and wiring-null fixture controls (DN-arena ADR Decision 5).

Separate fixture runs. They do not change `closedloop.ARMS` or
`flymsg.closedloop/v1`. The control name lives in the return value and notes,
never in `closedloop.Record.arm`.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields

import pandas as pd

from flymsg import closedloop, wiring
from flymsg.closedloop import Command
from flymsg.embodiment import Clock, ContractError, integer
from flymsg.pose import BodyState
from flymsg.runtime import CpuRuntime

SCRIPT = "script"
WIRING_NULL = "wiring-null"
SCRIPT_SCHEMA = "flymsg.arena_script/v1"
WIRING_NULL_SCHEMA = "flymsg.arena_wiring_null/v1"
_CENSUS = ("n_edges", "n_self_loops", "n_duplicate_pairs", "n_extra_edges")


@dataclass(frozen=True)
class ScriptTick:
    time_us: int
    commands: tuple[tuple[str, int, float], ...]
    state: BodyState
    stimulus: tuple[float, ...]
    stepped: BodyState
    yaw_rad: float  # unwrapped heading after the step (`Arena.yaw_rad`)


@dataclass(frozen=True)
class ScriptControl:
    control: str
    clock: Clock
    duration_us: int
    ticks: tuple[ScriptTick, ...]
    notes: dict[str, object]
    schema: str = SCRIPT_SCHEMA

    def validate(self) -> None:
        if self.schema != SCRIPT_SCHEMA:
            raise ContractError(f"not a {SCRIPT_SCHEMA} record")
        if self.control != SCRIPT:
            raise ContractError("control must be script")
        self.clock.validate()
        integer(self.duration_us, "duration_us", 1)
        if self.duration_us % self.clock.control_us:
            raise ContractError("duration must be a multiple of the control period")
        if not self.ticks or len(self.ticks) * self.clock.body_us != self.duration_us:
            raise ContractError("ticks do not cover the duration")
        _notes(self.notes)
        c = self.clock
        columns = len(self.ticks[0].stimulus)
        for k, tick in enumerate(self.ticks):
            t = k * c.body_us
            integer(tick.time_us, "time_us")
            if tick.time_us % c.body_us:
                raise ContractError(f"tick {k} is off the body grid")
            if tick.time_us != t:
                raise ContractError(f"tick {k} is out of order")
            if tick.state.time_us != t:
                raise ContractError(f"tick {k} did not read the state at its start")
            if tick.stepped.time_us != t + c.body_us:
                raise ContractError(f"tick {k} physics is off the body grid")
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
            if not _finite(tick.yaw_rad):
                raise ContractError(f"tick {k} heading is not finite")

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class WiringNullControl:
    control: str
    seed: int
    record: closedloop.Record
    stats: dict[str, int]
    notes: dict[str, object]
    schema: str = WIRING_NULL_SCHEMA

    def validate(self) -> None:
        if self.schema != WIRING_NULL_SCHEMA:
            raise ContractError(f"not a {WIRING_NULL_SCHEMA} record")
        if self.control != WIRING_NULL:
            raise ContractError("control must be wiring-null")
        integer(self.seed, "seed")
        if type(self.record) is not closedloop.Record:
            raise ContractError("wiring-null embeds a closed-loop record")
        self.record.validate()
        _stats(self.stats)
        _notes(self.notes)

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def _stimulus(
    stimulus: Callable[[int, BodyState], tuple[float, ...]], seen: BodyState
) -> tuple[float, ...]:
    stim = tuple(float(v) for v in stimulus(seen.time_us, seen))
    if not stim or not all(math.isfinite(v) for v in stim):
        raise ContractError("the stimulus needs one finite value per column")
    return stim


def script(
    body,
    *,
    clock: Clock,
    duration_us: int,
    rule: Callable[[int, BodyState, tuple[float, ...]], tuple[Command, ...]],
    stimulus: Callable[[int, BodyState], tuple[float, ...]],
) -> ScriptControl:
    """Drive `arena.step` from a caller-supplied rule. No connectome, no runtime.

    Causal order as in `closedloop.run`: the command at a control tick is fixed
    before that tick's sample, so it is the rule applied to the sample and
    stimulus of the previous control tick (one control period of latency, the
    intact loop's minimum). The first control period holds no command.
    """
    steps = closedloop.schedule(clock, duration_us)
    last = body.reset()
    commands: tuple[Command, ...] = ()
    ticks: list[ScriptTick] = []
    previous: tuple[int, BodyState, tuple[float, ...]] | None = None
    seen = last
    stim: tuple[float, ...] = ()
    for step in steps:
        t = step.time_us
        if step.phase == "command":
            commands = rule(*previous) if previous is not None else ()
        elif step.phase == "sample":
            seen = last
        elif step.phase == "stimulus":
            stim = _stimulus(stimulus, seen)
            if t % clock.control_us == 0:
                previous = (t, seen, stim)
        elif step.phase == "physics":
            state, _contacts = body.step(commands, clock.body_us)
            ticks.append(
                ScriptTick(
                    t,
                    tuple((a.name, a.mujoco_id, float(v)) for a, v in commands),
                    seen,
                    stim,
                    state,
                    body.yaw_rad,
                )
            )
            last = state
    return ScriptControl(
        SCRIPT,
        clock,
        duration_us,
        tuple(ticks),
        {"control": SCRIPT},
    )


def wiring_null(
    body,
    *,
    edges: pd.DataFrame,
    seed: int,
    runtime_from_edges: Callable[[pd.DataFrame], CpuRuntime],
    decoder: Callable,
    input_ids: tuple[int, ...],
    traced_ids: tuple[int, ...],
    stimulus: Callable,
    transducer: Callable,
    compiled: dict[str, int],
    clock: Clock,
    duration_us: int,
    mode: str,
    evidence: dict[str, str],
    provenance,
    optics_config_sha256: str,
    run_identity_sha256: str,
    input_gap_steps: int,
    **kwargs,
) -> WiringNullControl:
    """Intact `closedloop.run` on a degree-preserving shuffle of `edges`."""
    if "arm" in kwargs:
        raise ContractError("wiring-null is not a closedloop.Record.arm")
    integer(seed, "seed")
    if not isinstance(edges, pd.DataFrame) or not {"pre", "post", "weight"} <= set(
        edges.columns
    ):
        raise ContractError("edges need pre, post and weight")
    shuffled, stats = wiring.shuffle_targets(edges, seed)
    record = closedloop.run(
        runtime_from_edges(shuffled),
        body,
        input_ids=input_ids,
        traced_ids=traced_ids,
        stimulus=stimulus,
        transducer=transducer,
        decoder=decoder,
        compiled=compiled,
        clock=clock,
        duration_us=duration_us,
        arm="intact",
        mode=mode,
        evidence=evidence,
        provenance=provenance,
        optics_config_sha256=optics_config_sha256,
        run_identity_sha256=run_identity_sha256,
        input_gap_steps=input_gap_steps,
        **kwargs,
    )
    return WiringNullControl(
        WIRING_NULL,
        seed,
        record,
        stats,
        {"control": WIRING_NULL, "shuffle_seed": seed},
    )


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _notes(notes) -> None:
    if type(notes) is not dict:
        raise ContractError("notes must be a dict of JSON scalars")
    for key, value in notes.items():
        if type(key) is not str or not _scalar(value):
            raise ContractError("notes must be a dict of JSON scalars")


def _scalar(value) -> bool:
    if type(value) is float:
        return math.isfinite(value)
    return type(value) in (str, int, bool) or value is None


def _stats(stats) -> None:
    if type(stats) is not dict or set(stats) != set(_CENSUS):
        raise ContractError(
            "stats must name n_edges, n_self_loops, n_duplicate_pairs and n_extra_edges"
        )
    for name in _CENSUS:
        integer(stats[name], name)


def _script_tick(t: dict) -> ScriptTick:
    return ScriptTick(
        t["time_us"],
        tuple(tuple(c) for c in t["commands"]),
        closedloop._state(t["state"]),
        tuple(t["stimulus"]),
        closedloop._state(t["stepped"]),
        t["yaw_rad"],
    )


def script_from_json(text: str) -> ScriptControl:
    """Parse a script record; another schema, an unknown or missing field refuses."""
    try:
        d = json.loads(text)
        if d.get("schema") != SCRIPT_SCHEMA:
            raise ContractError(f"not a {SCRIPT_SCHEMA} record")
        if set(d) != {f.name for f in fields(ScriptControl)}:
            raise ContractError("unknown or missing record fields")
        parsed = ScriptControl(
            d["control"],
            Clock(**d["clock"]),
            d["duration_us"],
            tuple(_script_tick(t) for t in d["ticks"]),
            d["notes"],
            d["schema"],
        )
        parsed.validate()
    except ContractError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as err:
        raise ContractError(f"malformed script record: {err!r}") from err
    return parsed


def wiring_null_from_json(text: str) -> WiringNullControl:
    """Parse a wiring-null record; the embedded record is a closed-loop object."""
    try:
        d = json.loads(text)
        if d.get("schema") != WIRING_NULL_SCHEMA:
            raise ContractError(f"not a {WIRING_NULL_SCHEMA} record")
        if set(d) != {f.name for f in fields(WiringNullControl)}:
            raise ContractError("unknown or missing record fields")
        embedded = d["record"]
        if type(embedded) is not dict:
            raise ContractError("the closed-loop record must be an object")
        record = closedloop.from_json(
            json.dumps(embedded, sort_keys=True, separators=(",", ":"))
        )
        parsed = WiringNullControl(
            d["control"],
            d["seed"],
            record,
            d["stats"],
            d["notes"],
            d["schema"],
        )
        parsed.validate()
    except ContractError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as err:
        raise ContractError(f"malformed wiring-null record: {err!r}") from err
    return parsed
