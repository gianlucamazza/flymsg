"""Embodiment M2 (#34): a looming object, the body's pose, and input that follows it.

A disc of radius `r` moves toward the fly along -x at constant speed; the fly sits at x = 0
and its body (`jump.JumpBody`) moves along +z. At every control boundary the angular size
is computed from the object's position and the body's current height, its rate of change
over the next control period gives the drive of the stimulated neurons through an
engineered transducer (`gain × expansion`, capped), and seeded Poisson counts carry it into
`CpuRuntime`. The motor neuron's spikes in that period become a force through the M1
engineered decoder, applied over the next period. So a jump changes the input that follows
it; this is the closed loop, not the one-bit cut-off of the behavior protocol.

Controls, with the same seed: `disconnected` computes the input with the body held at
z = 0 whatever it does; `shuffled` uses the disconnected rate series in a seeded random
order; `replay` feeds back the exact input counts of a recorded run without feedback, which
must reproduce its spikes. The transducer is not an LC4 tuning curve and the decoder is not
a motor map; both are stated by the caller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import sparse

from flymsg import sim
from flymsg.embodiment import MotorCommand
from flymsg.jump import ENGINEERED, JumpBody
from flymsg.runtime import CpuRuntime

MODES = ("closed", "disconnected", "shuffled", "replay")


@dataclass(frozen=True)
class Looming:
    radius_m: float
    start_distance_m: float
    speed_m_s: float

    def angle(self, t_s: float, height_m: float) -> float:
        """Angular size of the disc seen from a body `height_m` above its path."""
        x = max(self.start_distance_m - self.speed_m_s * t_s, 1e-9)
        return 2.0 * math.atan(self.radius_m / math.hypot(x, height_m))


@dataclass(frozen=True)
class Transducer:
    """Engineered: no measured LC4 value exists for either number."""

    gain_hz_per_rad_s: float
    max_rate_hz: float
    baseline_hz: float = 0.0

    def rate(self, expansion_rad_s: float) -> float:
        return min(
            self.max_rate_hz,
            max(0.0, self.baseline_hz + self.gain_hz_per_rad_s * expansion_rad_s),
        )


def run_loop(
    W: sparse.csc_matrix,
    stim: np.ndarray,
    motor: int,
    *,
    looming: Looming,
    transducer: Transducer,
    decoder_gain_n: float,
    mass_kg: float,
    duration_ms: float,
    seed: int,
    mode: str = "closed",
    replay_counts: np.ndarray | None = None,
    p: sim.Params | None = None,
    control_ms: float = 1.0,
) -> dict:
    """One run in `mode`. Returns per control period: time, body height used for the input,
    rate, motor spikes and force; per neural step: the input counts (for a replay)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    p = p or sim.Params()
    stim = np.unique(stim)
    per = round(control_ms / p.dt)
    periods = round(duration_ms / control_ms)
    steps = per * periods
    if mode == "replay" and (
        replay_counts is None or replay_counts.shape != (steps, stim.size)
    ):
        raise ValueError(
            "replay needs the recorded input counts of a run of this length"
        )
    rt = CpuRuntime(
        W, stim, steps=steps, kicks=np.zeros((0, stim.size), dtype=np.int64), p=p,
        per_bin=per, trace=np.array([motor]),
    )  # fmt: skip
    body = JumpBody(mass_kg=mass_kg)
    rng = np.random.default_rng(seed)
    dt_s = control_ms / 1000.0
    open_rates = [
        transducer.rate(
            (looming.angle((k + 1) * dt_s, 0.0) - looming.angle(k * dt_s, 0.0)) / dt_s
        )
        for k in range(periods)
    ]
    if mode == "shuffled":
        open_rates = list(np.random.default_rng(seed + 1).permutation(open_rates))
    counts_all = np.zeros((steps, stim.size), dtype=np.int64)
    rec = {
        k: []
        for k in (
            "t_ms",
            "height_m",
            "seen_height_m",
            "rate_hz",
            "motor_spikes",
            "force_n",
        )
    }
    force = 0.0
    for k in range(periods):
        t0 = k * per
        seen = body.position_m if mode == "closed" else 0.0
        if mode == "closed":
            rate = transducer.rate(
                (looming.angle((k + 1) * dt_s, seen) - looming.angle(k * dt_s, seen))
                / dt_s
            )
        else:
            rate = open_rates[k]
        if mode == "replay":
            counts = replay_counts[t0 : t0 + per]
        else:
            counts = rng.poisson(rate * p.dt / 1000.0, (per, stim.size))
        counts_all[t0 : t0 + per] = counts
        rt.schedule_inputs(counts)
        rt.advance_to(t0 + per)
        n = int(rt.traced_spikes(t0, t0 + per).sum())
        # the period's force was decided at its start from earlier spikes (one period latency)
        state = body.step(
            MotorCommand(round(k * control_ms * 1000), force, ()),
            round(control_ms * 1000),
        )
        force = decoder_gain_n * n
        for key, value in (
            ("t_ms", (k + 1) * control_ms), ("height_m", state.position_m),
            ("seen_height_m", seen), ("rate_hz", rate), ("motor_spikes", n),
            ("force_n", force),
        ):  # fmt: skip
            rec[key].append(value)
    out = {k: np.asarray(v) for k, v in rec.items()}
    out["input_counts"] = counts_all
    out["mode"] = mode
    out["decoder"] = ENGINEERED
    out["result"] = rt.result()
    return out
