"""Stimulus primitives shared by experiments.

`dead_time` is the kick gate used by song and by giant-fiber looming. Song
re-exports this function, so `song.dead_time` is the same object. The gate
draws no random numbers and does no rounding; callers keep their own streams
and pass an integer gap.
"""

from __future__ import annotations

import numpy as np


def dead_time(k: np.ndarray, gap: int) -> np.ndarray:
    """At most one kick per step and none within `gap` steps of the previous kept one."""
    out = np.zeros(k.shape, np.int8)
    for j in range(k.shape[1]):
        last = -gap
        for t in np.flatnonzero(k[:, j]):
            if t - last >= gap:
                out[t, j] = 1
                last = t
    return out
