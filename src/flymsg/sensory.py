"""Experimental sensory stimulus encoding; not a validated biological receptor model.

This module deliberately does not modify the calibrated LIF engine. It generates
timestamped, deterministic drive-rate samples for a future online neural adapter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LoomingStimulus:
    radius_m: float
    initial_distance_m: float
    approach_speed_m_s: float
    duration_us: int
    sample_period_us: int = 1000

    def __post_init__(self) -> None:
        values = (self.radius_m, self.initial_distance_m, self.approach_speed_m_s)
        if any(not math.isfinite(x) or x <= 0 for x in values):
            raise ValueError("radius, distance and approach speed must be finite and positive")
        if self.initial_distance_m <= self.radius_m:
            raise ValueError("initial distance must exceed object radius")
        if self.duration_us <= 0 or self.sample_period_us <= 0:
            raise ValueError("duration and sample period must be positive")
        if self.duration_us % self.sample_period_us:
            raise ValueError("duration must be divisible by sample period")
        if self.approach_speed_m_s * (self.duration_us / 1_000_000) >= self.initial_distance_m:
            raise ValueError("object would reach the observer during stimulus")


@dataclass(frozen=True)
class SensoryDrive:
    time_us: int
    angular_size_rad: float
    angular_velocity_rad_s: float
    rate_hz: float


def encode_looming(
    stimulus: LoomingStimulus, *, baseline_hz: float = 0.0, gain_hz_per_rad_s: float = 100.0,
    max_rate_hz: float = 200.0,
) -> tuple[SensoryDrive, ...]:
    """Encode optical expansion into an engineered, bounded Poisson drive rate.

    This is a synthetic proxy, not an experimentally fitted LC4 tuning curve.
    Samples are at interval starts; the final interval ends at duration_us.
    """
    if any(not math.isfinite(v) or v < 0 for v in (baseline_hz, gain_hz_per_rad_s, max_rate_hz)):
        raise ValueError("rates and gain must be finite and nonnegative")
    if baseline_hz > max_rate_hz:
        raise ValueError("baseline cannot exceed maximum rate")
    samples = []
    for t in range(0, stimulus.duration_us, stimulus.sample_period_us):
        distance = stimulus.initial_distance_m - stimulus.approach_speed_m_s * t / 1_000_000
        radius = stimulus.radius_m
        speed = stimulus.approach_speed_m_s
        angle = 2 * math.atan(radius / distance)
        expansion = 2 * radius * speed / (distance * distance + radius * radius)
        rate = min(max_rate_hz, baseline_hz + gain_hz_per_rad_s * expansion)
        samples.append(SensoryDrive(t, angle, expansion, rate))
    return tuple(samples)
