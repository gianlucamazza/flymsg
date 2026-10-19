"""Engineered descending-neuron decoder (DN-arena ADR).

In a declared control window, spike rates of DNa01 / DNa02 (steering) and oDN1
(forward; MaleCNS type `DNg97`) map to `(yaw, forward)` commands of
`flymsg.arena.Arena`. Gains and the window are required caller values (the lock
and the record will name them; this module invents none). `closedloop.run` hands
the decoder one control period of spikes per call, so a rate is that call's count
over `clock.control_us`; the window only gates which spikes count. BodyIds are the mapped
rows in `docs/dn-arena-inventory.md`. Not a motor map and not a connectome-derived
controller.
"""

from __future__ import annotations

import math

from flymsg.closedloop import Command
from flymsg.embodiment import Clock, ContractError, SpikeEvent, integer
from flymsg.pose import ActuatorRef

# arena-1 inventory (MaleCNS v1.0). MDN and DNp01 are later-version only.
NEURONS = {
    10442: ("DNa01", "L"),
    10760: ("DNa01", "R"),
    523769: ("DNa02", "L"),
    10360: ("DNa02", "R"),
    13805: ("oDN1", "L"),
    230783: ("oDN1", "R"),
}
TYPES = ("DNa01", "DNa02", "oDN1")


def _finite(value, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ContractError(f"{name} must be finite")
    return out


class Decoder:
    """Windowed rates → (yaw, forward). Stateless; no default gain or window."""

    def __init__(
        self,
        *,
        gains: dict[str, float],
        window: tuple[int, int],
        actuators: dict[str, ActuatorRef],
        clock: Clock,
    ):
        if set(gains) != set(TYPES):
            raise ContractError("gains must name exactly DNa01, DNa02 and oDN1")
        self.gains = {name: _finite(gains[name], f"{name} gain") for name in TYPES}
        if len(window) != 2:
            raise ContractError("window is a start_us and an end_us")
        start_us, end_us = window
        integer(start_us, "window start")
        integer(end_us, "window end")
        if end_us <= start_us:
            raise ContractError("window end must be after its start")
        self.start_us = start_us
        self.end_us = end_us
        yaw, forward = actuators.get("yaw"), actuators.get("forward")
        if not isinstance(yaw, ActuatorRef) or not isinstance(forward, ActuatorRef):
            raise ContractError("actuators must name yaw and forward")
        self._yaw = yaw
        self._forward = forward
        if not isinstance(clock, Clock):
            raise ContractError("a decoder needs the loop's clock")
        clock.validate()
        self.control_us = clock.control_us

    def __call__(self, spikes: tuple[SpikeEvent, ...]) -> tuple[Command, ...]:
        counts = dict.fromkeys(
            ((name, side) for name in TYPES for side in ("L", "R")), 0
        )
        for spike in spikes:
            if not isinstance(spike, SpikeEvent):
                raise ContractError("a spike is a SpikeEvent")
            key = NEURONS.get(spike.neuron_id)
            if key is None:
                raise ContractError(f"unknown descending neuron {spike.neuron_id}")
            if self.start_us <= spike.time_us < self.end_us:
                counts[key] += 1
        period_s = self.control_us / 1e6

        def rate(name: str, side: str) -> float:
            return counts[(name, side)] / period_s

        yaw = self.gains["DNa01"] * (
            rate("DNa01", "L") - rate("DNa01", "R")
        ) + self.gains["DNa02"] * (rate("DNa02", "L") - rate("DNa02", "R"))
        forward = self.gains["oDN1"] * (rate("oDN1", "L") + rate("oDN1", "R"))
        return ((self._yaw, yaw), (self._forward, forward))
