"""Exploratory bridge from sensory rates to the incremental LIF runtime."""

from __future__ import annotations

import math

import numpy as np

from flymsg.sensory import SensoryDrive


def schedule_sensory_drive(
    runtime,
    samples: tuple[SensoryDrive, ...],
    *,
    neural_dt_us: int,
    sample_period_us: int,
    n_stim: int,
    seed: int,
) -> None:
    """Validate a time grid and schedule deterministic Poisson input counts."""
    if type(neural_dt_us) is not int or neural_dt_us <= 0:
        raise ValueError("neural_dt_us must be positive")
    if type(sample_period_us) is not int or sample_period_us <= 0:
        raise ValueError("sample_period_us must be positive")
    if sample_period_us % neural_dt_us:
        raise ValueError("sample period must be divisible by neural timestep")
    if type(n_stim) is not int or n_stim <= 0:
        raise ValueError("n_stim must be positive")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if not samples:
        raise ValueError("at least one sample is required")
    first_us = runtime.step * neural_dt_us
    for i, sample in enumerate(samples):
        if sample.time_us != first_us + i * sample_period_us:
            raise ValueError("sample timestamps must be contiguous and aligned")
        if not math.isfinite(sample.rate_hz) or sample.rate_hz < 0:
            raise ValueError("sample rate must be finite and nonnegative")
    n_per = sample_period_us // neural_dt_us
    rng = np.random.default_rng(seed)
    blocks = [
        rng.poisson(sample.rate_hz * neural_dt_us / 1_000_000, (n_per, n_stim))
        for sample in samples
    ]
    runtime.schedule_inputs(np.concatenate(blocks, axis=0))
