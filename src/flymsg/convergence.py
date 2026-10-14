"""Timestep convergence of the battery's responses (SF2, #148).

The YAML file is the lock. The six sensitivity cases run at the default timestep and at finer
ones with the default parameters otherwise; a response converges at a timestep when its
holds verdict equals the finest timestep's and its seed-median rate lies within the finest
timestep's seed range of the finest median. Numerical error is judged against seed
variability, not against a chosen tolerance. Nothing is chosen from the result and the
defaults in `sim.Params` do not change.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from flymsg import draws, locks, parallel, sensitivity, sim, validate

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "convergence.yaml"

VERSION_HASHES = {
    1: "8cd705e7b606fb68e72e2199883c2a850ed5d7d35d7960dfc663e2e958ea123b",
}


class ConvergenceError(ValueError):
    """The convergence protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return locks.prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, ConvergenceError, "convergence protocol")


def steps_exact(dt: float, p: sim.Params) -> bool:
    """Delay and refractory period are whole numbers of steps at this timestep."""
    return all(abs(x / dt - round(x / dt)) < 1e-9 for x in (p.delay, p.t_ref))


def assert_matches_code(doc: dict | None = None) -> dict:
    """The default timestep is the coarsest, every timestep keeps delay and refractory
    period exact, and the cases and protocol are the sensitivity grid's."""
    doc = assert_locked() if doc is None else doc
    g = doc["grid"]
    dts = g["dt_ms"]
    if dts[0] != sim.Params.dt or dts != sorted(dts, reverse=True) or len(dts) < 3:
        raise ConvergenceError("the timesteps must start at the default and decrease")
    if not all(steps_exact(dt, sim.Params()) for dt in dts):
        raise ConvergenceError("delay and t_ref must be whole steps at every timestep")
    if (g["rate_hz"], g["stim_ms"], g["duration_ms"]) != (
        validate.RATE_HZ,
        validate.STIM_MS,
        validate.DURATION_MS,
    ):
        raise ConvergenceError("the grid does not use the battery protocol")
    grid = sensitivity.load()
    if doc["cases"] != grid["cases"]:
        raise ConvergenceError("the cases are not the sensitivity grid's")
    if doc["holds"] != {
        k: grid["report"][k]
        for k in ("holds_min_spikes", "holds_seed_share_num", "holds_seed_share_den")
    }:
        raise ConvergenceError("the holds rule is not the v4 floor")
    if doc["claim"]["scored"] is not False:
        raise ConvergenceError("a convergence study is not a score")
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    g = doc["grid"]
    cases = len(doc["cases"]["positive"]) + len(doc["cases"]["negative"])
    return (
        f"convergence v{doc['version']} (issue #{doc['issue']}): dt {g['dt_ms']} ms, "
        f"{cases} cases, seeds {g['seed0']}-{g['seed0'] + g['seeds'] - 1}; "
        "a numerical check, not a score"
    )


def _job(job: tuple) -> list[dict]:
    (neurons, edges, doc), _checkpoint, _meta = parallel.context()
    dt, case = job
    g = doc["grid"]
    p = replace(sim.Params(), dt=dt)
    W = sim.network(neurons, edges, p)
    stim, targets = sensitivity.case_inputs(case, neurons)
    rows = sensitivity.measure(
        W,
        neurons,
        stim,
        targets,
        p,
        seed0=g["seed0"],
        seeds=g["seeds"],
        rate_hz=g["rate_hz"],
        stim_ms=g["stim_ms"],
        duration_ms=g["duration_ms"],
    )
    for row in rows:
        row.update(dt_ms=dt, case=case)
    return rows


def jobs(doc: dict) -> list[tuple]:
    c = doc["cases"]
    return [
        (dt, case)
        for dt in doc["grid"]["dt_ms"]
        for case in [*c["positive"], *c["negative"]]
    ]


def run(
    neurons, edges, workers: int = 1, checkpoint: Path | None = None
) -> pd.DataFrame:
    doc = assert_matches_code()
    meta = {"version": doc["version"], "sha256": doc["content_sha256"]}
    rows = draws.map_jobs(
        _job, jobs(doc), workers, (neurons, edges, doc), checkpoint, meta
    )
    return pd.DataFrame(rows)


def judge(cells: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Per case, target and timestep: seed medians, holds, and whether the response
    converged against the finest timestep."""
    h = doc["holds"]
    stim_s = doc["grid"]["stim_ms"] / 1000.0
    need = h["holds_seed_share_num"] / h["holds_seed_share_den"]
    cells = cells.assign(
        at_floor=cells["rate"] * stim_s >= h["holds_min_spikes"] - 1e-9
    )
    finest = min(doc["grid"]["dt_ms"])
    rows = []
    for (case, target), g in cells.groupby(["case", "target"], sort=False):
        ref = g[g["dt_ms"] == finest]
        ref_median = float(ref["rate"].median())
        ref_range = float(ref["rate"].max() - ref["rate"].min())
        ref_holds = bool(ref["at_floor"].mean() >= need - 1e-9)
        for dt, d in g.groupby("dt_ms", sort=False):
            holds = bool(d["at_floor"].mean() >= need - 1e-9)
            median = float(d["rate"].median())
            rows.append(
                {
                    "case": case,
                    "target": target,
                    "dt_ms": dt,
                    "rate_median": median,
                    "rate_range": float(d["rate"].max() - d["rate"].min()),
                    "latency_median": float(d["latency"].median()),
                    "recruited_median": float(d["recruited"].median()),
                    "persistent_median": float(d["persistent"].median()),
                    "holds": holds,
                    "delta_vs_finest": median - ref_median,
                    "finest_seed_range": ref_range,
                    "converged": holds == ref_holds
                    and abs(median - ref_median) <= ref_range + 1e-9,
                }
            )
    return pd.DataFrame(rows)


def verdict(judged: pd.DataFrame, doc: dict) -> str:
    """`converged` if every response converges at the default timestep; otherwise the
    responses that do not."""
    at = judged[judged["dt_ms"] == doc["grid"]["dt_ms"][0]]
    bad = at[~at["converged"]]
    if bad.empty:
        return "converged"
    return "not_converged: " + ", ".join(
        f"{c}/{t}" for c, t in zip(bad.case, bad.target)
    )
