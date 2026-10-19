"""Script and wiring-null fixture controls (DN-arena ADR Decision 5).

Separate fixture runs. They do not change `closedloop.ARMS` or
`flymsg.closedloop/v1`. The control name lives in the return value and notes,
never in `closedloop.Record.arm`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from flymsg import closedloop, wiring
from flymsg.closedloop import Command
from flymsg.embodiment import Clock, ContractError, integer
from flymsg.pose import BodyState
from flymsg.runtime import CpuRuntime

SCRIPT = "script"
WIRING_NULL = "wiring-null"


@dataclass(frozen=True)
class ScriptTick:
    time_us: int
    commands: tuple[tuple[str, int, float], ...]
    state: BodyState
    stimulus: tuple[float, ...]
    stepped: BodyState


@dataclass(frozen=True)
class ScriptControl:
    control: str
    clock: Clock
    duration_us: int
    ticks: tuple[ScriptTick, ...]
    notes: dict[str, object]


@dataclass(frozen=True)
class WiringNullControl:
    control: str
    seed: int
    record: closedloop.Record
    stats: dict[str, int]
    notes: dict[str, object]


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
    """Drive `arena.step` from a caller-supplied rule. No connectome, no runtime."""
    steps = closedloop.schedule(clock, duration_us)
    last = body.reset()
    commands: tuple[Command, ...] = ()
    ticks: list[ScriptTick] = []
    pending_command = False
    seen = last
    stim: tuple[float, ...] = ()
    for step in steps:
        t = step.time_us
        if step.phase == "command":
            pending_command = True
        elif step.phase == "sample":
            seen = last
        elif step.phase == "stimulus":
            stim = _stimulus(stimulus, seen)
            if pending_command:
                commands = rule(t, seen, stim)
                pending_command = False
        elif step.phase == "physics":
            state, _contacts = body.step(commands, clock.body_us)
            ticks.append(
                ScriptTick(
                    t,
                    tuple((a.name, a.mujoco_id, float(v)) for a, v in commands),
                    seen,
                    stim,
                    state,
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
        **kwargs,
    )
    return WiringNullControl(
        WIRING_NULL,
        seed,
        record,
        stats,
        {"control": WIRING_NULL, "shuffle_seed": seed},
    )
