"""Engineered descending-neuron readout (DN-arena ADR, Decision 4).

Not a motor map and not connectome-derived (issue #31). The command on an
actuator is the sum of gain times spike rate for each traced neuron wired to
it. Rate is the spike count in the call divided by the control period. Nothing
is kept between calls. Gains come only from the experiment lock and the run
record; this module chooses none. A spike from any other neuron is refused.
BodyIds come from docs/dn-arena-inventory.md (oDN1 is MaleCNS type DNg97).
Evidence status is `engineered`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from flymsg import pose
from flymsg.closedloop import Command
from flymsg.embodiment import Clock, ContractError, SpikeEvent, integer

DECODER_EVIDENCE = "engineered"


@dataclass(frozen=True)
class Term:
    """One readout term: spike rate of one traced neuron times a gain, into one
    actuator."""

    body_id: int
    actuator: str
    gain: float

    def __post_init__(self) -> None:
        integer(self.body_id, "body_id", 1)
        if type(self.actuator) is not str or not self.actuator:
            raise ContractError("actuator must be a non-empty string")
        if (
            type(self.gain) is not float
            or not math.isfinite(self.gain)
            or self.gain == 0.0
        ):
            raise ContractError("gain must be finite and nonzero")


class Decoder:
    """Engineered DN readout (DN-arena ADR): command = sum of gain * rate per
    actuator."""

    def __init__(
        self,
        terms: tuple[Term, ...],
        actuators: dict[str, pose.ActuatorRef],
        clock: Clock,
    ) -> None:
        if (
            type(terms) is not tuple
            or not terms
            or not all(isinstance(term, Term) for term in terms)
        ):
            raise ContractError("terms must be a non-empty tuple of terms")
        pairs = [(term.body_id, term.actuator) for term in terms]
        if len(pairs) != len(set(pairs)):
            raise ContractError("duplicate (body_id, actuator) term")
        if type(actuators) is not dict:
            raise ContractError("actuators must be a dict of actuator references")
        for name, actuator in actuators.items():
            if (
                type(name) is not str
                or not isinstance(actuator, pose.ActuatorRef)
                or actuator.name != name
            ):
                raise ContractError(
                    f"{name} is not the actuator reference of that name"
                )
        for term in terms:
            if term.actuator not in actuators:
                raise ContractError(f"{term.actuator} is not an actuator of this body")
        if not isinstance(clock, Clock):
            raise ContractError("a decoder needs a clock")
        clock.validate()
        self._terms = tuple(
            sorted(terms, key=lambda term: (term.actuator, term.body_id))
        )
        self._actuators = dict(actuators)
        self._window_us = clock.control_us
        self.body_ids = tuple(sorted({term.body_id for term in terms}))

    def __call__(self, spikes: tuple[SpikeEvent, ...]) -> tuple[Command, ...]:
        if type(spikes) is not tuple:
            raise ContractError("spikes must be a tuple of spike events")
        counts = dict.fromkeys(self.body_ids, 0)
        for spike in spikes:
            if not isinstance(spike, SpikeEvent):
                raise ContractError("spikes must be a tuple of spike events")
            if spike.neuron_id not in counts:
                raise ContractError(f"unread neuron {spike.neuron_id}")
            counts[spike.neuron_id] += 1
        window_s = self._window_us / 1e6
        totals = {}
        for term in self._terms:
            rate = counts[term.body_id] / window_s
            totals[term.actuator] = totals.get(term.actuator, 0.0) + term.gain * rate
        commands = []
        for name in sorted(totals):
            value = float(totals[name])
            if not math.isfinite(value):
                raise ContractError(f"{name} command is not finite")
            commands.append((self._actuators[name], value))
        return tuple(commands)

    def describe(self) -> dict:
        """JSON-ready canonical description for a lock or run record."""
        return {
            "kind": "flymsg.dn_decoder/v1",
            "window_us": self._window_us,
            "terms": [
                {
                    "body_id": term.body_id,
                    "actuator": term.actuator,
                    "unit": self._actuators[term.actuator].unit,
                    "gain": term.gain,
                }
                for term in self._terms
            ],
        }
