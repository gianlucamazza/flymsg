"""The locked TTM-driven jump (issues #90, #94): neural run, replay into the body, verdict."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, jump3d, locks, prereg, sim, ttm
from flymsg.paths import repository_root

ROOT = repository_root()
PATH = ROOT / "validation" / "jump3d.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "c93eeebd796df1913769f3625ec033745a0ff29ae188bcced938d0b9bab9e8d2",  # LC4 bilateral, TTM twitch, NeuroMechFly, range 28.6-37.75 mm, seeds 110-112
}


class Jump3DError(ValueError):
    """The jump protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    locks.check(doc, VERSION_HASHES, Jump3DError, "jump protocol")
    return doc


def assert_matches_code(doc: dict | None = None) -> dict:
    doc = assert_locked() if doc is None else doc
    b, d = doc["body"], doc["decides"]
    if (ttm.TWITCH.peak_n, ttm.TWITCH.time_to_peak_ms) != (101e-6, 8.2):
        raise Jump3DError("the twitch is not the measured one")
    if (d["range_min_mm"], d["range_max_mm"]) != (28.6, round(30.2 / 0.8, 2)):
        raise Jump3DError("the bounds are not the measured ones")
    if b["timestep_s"] != sim.Params.dt / 1000.0:
        raise Jump3DError("the body does not step at the neural step")
    if b["posture_kp"] != jump3d.DEFAULT.posture_kp:
        raise Jump3DError("the posture gain is not the body default")
    for name, row in doc["reported"].items():
        if row["decides"] is not False:
            raise Jump3DError(f"reported row {name} must not decide")
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    n, d = doc["neural"], doc["decides"]
    return (
        f"jump3d v{doc['version']} (issues #90, #94): {n['stimulus']} at {n['rate_hz']:g} Hz "
        f"-> TTMn_L/R -> TTM twitch -> NeuroMechFly; seeds "
        f"{', '.join(map(str, n['seeds']))}; consistent if the drag-free range is "
        f"{d['range_min_mm']}-{d['range_max_mm']} mm"
    )


def decide(ranges, takeoffs, lo: float, hi: float) -> str:
    if any(t is None or not np.isfinite(t) for t in takeoffs):
        return "no_takeoff"
    mean = float(np.mean(ranges))
    if mean < lo:
        return "short"
    return "long" if mean > hi else "consistent"


def run(neurons: pd.DataFrame, edges: pd.DataFrame) -> dict:
    doc = assert_matches_code()
    n, b, d = doc["neural"], doc["body"], doc["decides"]
    stim = data.resolve(neurons, n["stimulus"])
    if stim.size != n["stimulus_n"]:
        raise Jump3DError(f"{n['stimulus']} has {stim.size} neurons")
    motor = {
        side: int(data.resolve(neurons, name)[0]) for side, name in n["motor"].items()
    }
    order = list(motor)
    W = sim.network(neurons, edges, sim.Params())
    p = sim.Params()
    cfg = jump3d.BodyConfig(
        posture_kp=b["posture_kp"], settle_ms=b["settle_ms"], timestep_s=b["timestep_s"]
    )
    rows = []
    for seed in n["seeds"]:
        r = sim.run(
            W,
            stim,
            n["rate_hz"],
            n["duration_ms"],
            n["stim_ms"],
            p,
            seed,
            trace=np.array([motor[s] for s in order]),
        )
        spikes = {
            s: (np.flatnonzero(r.traced[:, i]) * p.dt).tolist()
            for i, s in enumerate(order)
        }
        out = jump3d.jump(spikes, b["replay_ms"], cfg)
        before = out["takeoff_ms"] if out["takeoff_ms"] is not None else b["replay_ms"]
        rows.append(
            {
                "seed": seed,
                "takeoff_ms": out["takeoff_ms"],
                "range_mm": out["range_mm"],
                "velocity_m_s": out["velocity_m_s"],
                "ttmn_spikes_before_takeoff": {
                    s: int(sum(t < before for t in spikes[s])) for s in order
                },
                "first_spike_ms": {
                    s: (spikes[s][0] if spikes[s] else None) for s in order
                },
            }
        )
    table = pd.DataFrame(rows)
    verdict = decide(
        [r["range_mm"] for r in rows],
        [r["takeoff_ms"] for r in rows],
        d["range_min_mm"],
        d["range_max_mm"],
    )
    return {"table": table, "verdict": verdict}
