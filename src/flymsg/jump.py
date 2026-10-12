"""Embodiment M1 (#33): a one-DOF jump body driven through an engineered decoder.

`JumpBody` is a point mass over a rigid floor: gravity, an actuator force along +z, and
ground contact (no penetration, no bounce). It plugs into the M0 contract (`run_fixture`).
The decoder from `TTMn_R` spikes to force is `ENGINEERED`: a gain in newtons per spike
held for one control period, chosen by the caller. It is not a MaleCNS motor map, it never
goes through `motor_map.command` (which stays fail-closed), and every output carries that
label. A jump here shows that spikes can move a body through the contract, not that the fly
jumps this way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from flymsg.embodiment import (
    BodyState,
    Clock,
    ContractError,
    MotorCommand,
    Provenance,
    SensorSample,
    SpikeEvent,
    run_fixture,
)

ENGINEERED = "engineered_decoder"
NOTE = (
    "engineered decoder: an arbitrary gain from TTMn_R spikes to a vertical force; not an "
    "experimentally established MaleCNS motor map"
)


@dataclass
class JumpBody:
    """Height above a rigid floor (m) and vertical velocity (m/s); semi-implicit Euler."""

    mass_kg: float
    gravity_m_s2: float = 9.81
    position_m: float = 0.0
    velocity_m_s: float = 0.0
    frame: str = "world/+z"

    def __post_init__(self) -> None:
        if not math.isfinite(self.mass_kg) or self.mass_kg <= 0:
            raise ContractError("mass must be finite and positive")
        if not math.isfinite(self.gravity_m_s2) or self.gravity_m_s2 < 0:
            raise ContractError("gravity must be finite and non-negative")

    def step(self, command: MotorCommand, dt_us: int) -> BodyState:
        dt = dt_us / 1_000_000
        self.velocity_m_s += (command.force_n / self.mass_kg - self.gravity_m_s2) * dt
        self.position_m += self.velocity_m_s * dt
        if self.position_m <= 0.0:  # the floor stops the body; it does not bounce
            self.position_m = 0.0
            self.velocity_m_s = max(0.0, self.velocity_m_s)
        return BodyState(command.time_us + dt_us, self.position_m, self.velocity_m_s)

    def sensors(self, state: BodyState) -> tuple[SensorSample, ...]:
        return (
            SensorSample(state.time_us, "height", state.position_m, frame=self.frame),
        )


def spike_events(spike_steps: np.ndarray, body_id: int, dt_ms: float) -> tuple:
    """Spike steps of one neuron as M0 events on the integer microsecond clock."""
    tick = round(dt_ms * 1000)
    return tuple(SpikeEvent(int(body_id), int(s) * tick) for s in np.sort(spike_steps))


def run_jump(
    spike_steps: np.ndarray,
    *,
    body_id: int,
    gain_n: float,
    mass_kg: float,
    duration_us: int,
    provenance: Provenance,
    dt_ms: float = 0.1,
) -> dict:
    """Drive a `JumpBody` with one neuron's spikes; return the trajectory and a summary."""
    if not math.isfinite(gain_n) or gain_n < 0:
        raise ContractError("gain must be finite and non-negative")
    clock = Clock()
    # an event must be delivered before the run ends (M0 rule); later spikes are reported
    last = duration_us - clock.control_us
    events = spike_events(spike_steps, body_id, dt_ms)
    used = tuple(e for e in events if e.time_us + clock.latency_us <= last)
    body = JumpBody(mass_kg=mass_kg)
    trace = run_fixture(
        used,
        duration_us=duration_us,
        provenance=provenance,
        motor_map={int(body_id): float(gain_n)},
        sensor_map={"height": int(body_id)},
        body=body,
        clock=clock,
        expected_dataset_sha256=provenance.dataset_sha256,
    )
    heights = np.array([s.position_m for s in trace.states])
    times = np.array([s.time_us for s in trace.states])
    airborne = heights > 0
    return {
        "decoder": ENGINEERED,
        "note": NOTE,
        "gain_n_per_spike": gain_n,
        "mass_kg": mass_kg,
        "spikes": len(events),
        "spikes_after_last_command": len(events) - len(used),
        "takeoff_ms": float(times[airborne][0] / 1000) if airborne.any() else None,
        "max_height_m": float(heights.max()),
        "time_ms": (times / 1000).tolist(),
        "height_m": heights.tolist(),
        "contact": (~airborne).tolist(),
        "force_n": [c.force_n for c in trace.commands],
    }
