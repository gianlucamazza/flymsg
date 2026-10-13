"""Tergotrochanteral muscle (TTM) force from TTMn spikes (issue #94).

Each TTMn innervates the TTM of its side, which extends the mesothoracic coxa-trochanter
joint. Zumstein et al. 2004 (J Exp Biol 207:3515, doi:10.1242/jeb.01181) measured the force
of the main jumping muscle at the mesothoracic leg of tethered wild-type females: peak
101 ± 4.4 µN, reached 8.2 ms after onset. Allen & Murphey 2007 (doi:10.1111/
j.1460-9568.2007.05686.x) measured 0.85 ms from giant fiber stimulation to the TTM
potential, an upper bound for TTMn spike to muscle. The twitch decay, the summation of
several spikes and saturation are not measured; `TWITCH` names those choices.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Twitch:
    peak_n: float = 101e-6  # Zumstein et al. 2004
    time_to_peak_ms: float = 8.2  # Zumstein et al. 2004
    delay_ms: float = 0.85  # Allen & Murphey 2007, upper bound
    # compensations: an alpha-function shape (rise and decay set by the time to peak) and
    # linear summation of twitches without saturation; neither is measured
    shape: str = "alpha"
    summation: str = "linear"


TWITCH = Twitch()


def twitch(t_ms: np.ndarray, tw: Twitch = TWITCH) -> np.ndarray:
    """Force in newtons of one twitch at `t_ms` after its spike: an alpha function that
    rises to `peak_n` at `delay_ms + time_to_peak_ms`."""
    s = (np.asarray(t_ms, dtype=float) - tw.delay_ms) / tw.time_to_peak_ms
    return np.where(s > 0, tw.peak_n * s * np.exp(1.0 - s), 0.0)


def force(spike_ms, t_ms: np.ndarray, tw: Twitch = TWITCH) -> np.ndarray:
    """Force in newtons at times `t_ms` from a train of spikes at `spike_ms`, summed."""
    t = np.asarray(t_ms, dtype=float)
    out = np.zeros_like(t)
    for s in np.asarray(spike_ms, dtype=float):
        out += twitch(t - s, tw)
    return out
