"""M0 neural/body contracts and deterministic fixture runner (no motor anatomy)."""

import math
from dataclasses import asdict, dataclass
from typing import Protocol

SCHEMA = "flymsg.embodiment/v1"
CLOCK = "flymsg.clock/us-v1"


class ContractError(ValueError):
    """Invalid coupling: no further actuator calls are permitted."""


def integer(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ContractError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True)
class Provenance:
    dataset: str
    dataset_sha256: str
    commit: str
    seed: int
    schema: str = SCHEMA
    clock: str = CLOCK

    def validate(self) -> None:
        if self.schema != SCHEMA or self.clock != CLOCK:
            raise ContractError("incompatible contract or clock")
        if not self.dataset or not self.commit:
            raise ContractError("dataset and commit are required")
        if len(self.dataset_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.dataset_sha256
        ):
            raise ContractError("dataset_sha256 must be a lowercase SHA-256")
        integer(self.seed, "seed")


@dataclass(frozen=True)
class Clock:
    neural_us: int = 100  # existing LIF default: 0.1 ms
    body_us: int = 1000
    control_us: int = 1000
    latency_us: int = 0

    def validate(self) -> None:
        for name in ("neural_us", "body_us", "control_us"):
            integer(getattr(self, name), name, 1)
        integer(self.latency_us, "latency_us")
        if self.control_us % self.body_us or self.body_us % self.neural_us:
            raise ContractError("control must divide into body, body into neural ticks")
        if self.latency_us % self.neural_us:
            raise ContractError("latency must be on the neural grid")


@dataclass(frozen=True)
class SpikeEvent:
    """Dataset bodyId, never the transient matrix row index; time in microseconds."""

    neuron_id: int
    time_us: int


@dataclass(frozen=True)
class MotorCommand:
    time_us: int
    force_n: float
    source_events: tuple[SpikeEvent, ...]


@dataclass(frozen=True)
class BodyState:
    """Mock world frame: +x forward, metres and metres/second."""

    time_us: int
    position_m: float
    velocity_m_s: float


@dataclass(frozen=True)
class SensorSample:
    time_us: int
    name: str
    value: float
    unit: str = "m"
    frame: str = "world/+x"


class Body(Protocol):
    def step(self, command: MotorCommand, dt_us: int) -> BodyState: ...

    def sensors(self, state: BodyState) -> tuple[SensorSample, ...]: ...


@dataclass
class MockBody:
    """One translational DOF, semi-implicit Euler, no gravity/contact/biology."""

    mass_kg: float = 1.0
    position_m: float = 0.0
    velocity_m_s: float = 0.0

    def __post_init__(self) -> None:
        # checked at construction, so a bad body fails before the first actuator call
        if not math.isfinite(self.mass_kg) or self.mass_kg <= 0:
            raise ContractError("mass must be finite and positive")

    def step(self, command: MotorCommand, dt_us: int) -> BodyState:
        dt = dt_us / 1_000_000
        self.velocity_m_s += command.force_n / self.mass_kg * dt
        self.position_m += self.velocity_m_s * dt
        return BodyState(command.time_us + dt_us, self.position_m, self.velocity_m_s)

    def sensors(self, state: BodyState) -> tuple[SensorSample, ...]:
        return (SensorSample(state.time_us, "position", state.position_m),)


@dataclass(frozen=True)
class Trace:
    provenance: Provenance
    clock: Clock
    motor_map: tuple[tuple[int, float], ...]
    sensor_map: tuple[tuple[str, int], ...]
    commands: tuple[MotorCommand, ...]
    states: tuple[BodyState, ...]
    sensors: tuple[SensorSample, ...]
    feedback: tuple[SpikeEvent, ...]

    def to_dict(self) -> dict:
        """JSON-ready deterministic record, usable as run_manifest extra metadata."""
        return asdict(self)


def _adapter(call, *args):
    """A body call; any failure inside it becomes a ContractError that stops the run."""
    try:
        return call(*args)
    except ContractError:
        raise
    except Exception as err:
        raise ContractError(f"body adapter failed: {err!r}") from err


def run_fixture(
    events: tuple[SpikeEvent, ...],
    *,
    duration_us: int,
    provenance: Provenance,
    motor_map: dict[int, float],
    sensor_map: dict[str, int],
    body: Body,
    clock: Clock | None = None,
    expected_dataset_sha256: str,
) -> Trace:
    """Consume motor events, aggregate at control ticks, hold force over body ticks.

    Events become eligible at time + latency, including the control boundary.
    Equal-time input order is retained. Sensor-to-neuron events are a synthetic
    positive-position encoder, recorded for a future online neural adapter.
    The complete input is validated before the first body call. Runtime adapter
    errors abort immediately; callers must discard/reset the partially run body.
    """
    clock = clock or Clock()
    motor_map = dict(motor_map)
    sensor_map = dict(sensor_map)
    provenance.validate()
    clock.validate()
    integer(duration_us, "duration_us", 1)
    if provenance.dataset_sha256 != expected_dataset_sha256:
        raise ContractError("incompatible dataset")
    if duration_us % clock.control_us:
        raise ContractError("duration must be a multiple of control period")
    if not sensor_map:
        raise ContractError("at least one required sensor must be mapped")
    for neuron, gain in motor_map.items():
        integer(neuron, "motor bodyId")
        if not math.isfinite(gain):
            raise ContractError("motor gain must be finite (N/event)")
    for name, neuron in sensor_map.items():
        if not name:
            raise ContractError("sensor name must be nonempty")
        integer(neuron, "sensor bodyId")
    previous = -1
    for event in events:
        integer(event.neuron_id, "bodyId")
        integer(event.time_us, "event time")
        if event.time_us < previous or event.time_us % clock.neural_us:
            raise ContractError("events must be ordered and on the neural grid")
        if event.neuron_id not in motor_map:
            raise ContractError("unmapped motor neuron")
        # Never silently lose a trailing event to latency/control quantisation.
        if event.time_us + clock.latency_us > duration_us - clock.control_us:
            raise ContractError("event delivery falls outside the run")
        previous = event.time_us
    commands, states, sensors, feedback = [], [], [], []
    cursor = 0
    command = MotorCommand(0, 0.0, ())
    for time in range(0, duration_us, clock.body_us):
        if time % clock.control_us == 0:
            start = cursor
            while (
                cursor < len(events)
                and events[cursor].time_us + clock.latency_us <= time
            ):
                cursor += 1
            sources = events[start:cursor]
            force = sum(motor_map[event.neuron_id] for event in sources)
            if not math.isfinite(force):
                raise ContractError("aggregated force is not finite")
            command = MotorCommand(time, force, sources)
            commands.append(command)
        held = MotorCommand(time, command.force_n, command.source_events)
        state = _adapter(body.step, held, clock.body_us)
        if state.time_us != time + clock.body_us or not all(
            math.isfinite(v) for v in (state.position_m, state.velocity_m_s)
        ):
            raise ContractError("invalid body state")
        samples = _adapter(body.sensors, state)
        names = [sample.name for sample in samples]
        if len(names) != len(set(names)) or set(names) != set(sensor_map):
            raise ContractError("missing, duplicate or unmapped sensor")
        for sample in samples:
            if (
                sample.time_us != state.time_us
                or sample.unit != "m"
                or sample.frame != "world/+x"
                or not math.isfinite(sample.value)
            ):
                raise ContractError("invalid sensor timestamp, unit, frame or value")
            if sample.value > 0:
                feedback.append(SpikeEvent(sensor_map[sample.name], sample.time_us))
        states.append(state)
        sensors.extend(samples)
    return Trace(
        provenance,
        clock,
        tuple(sorted(motor_map.items())),
        tuple(sorted(sensor_map.items())),
        tuple(commands),
        tuple(states),
        tuple(sensors),
        tuple(feedback),
    )
