"""Weak-pathway timestep metrics (SF2, #148).

The YAML file is the lock. The six sensitivity cases run at the default timestep and at
finer ones, on seeds that the convergence run did not use. Latency, jitter, recruitment
and rate are judged against the finest timestep's seed variability. A missing spike makes
latency and jitter indeterminate. Nothing is chosen from the result, the convergence v1
gate is not rewritten, and the defaults in `sim.Params` do not change.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import convergence, draws, locks, parallel, sensitivity, sim, validate

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "path_metrics.yaml"

VERSION_HASHES = {
    1: "6bc92e5a48e3985b960fa84354a402d5aff6b25ac46c5448fc5615a5ebb7e42f",
}

METRICS = ("latency", "jitter", "recruited", "rate")


class PathMetricsError(ValueError):
    """The path-metrics protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return locks.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, PathMetricsError, "path-metrics protocol")


def assert_matches_code(doc: dict | None = None) -> dict:
    """The timesteps, cases and seeds are the ones the lock names, disjoint from
    the convergence run, and the quanta are the measurement's resolution."""
    doc = assert_locked() if doc is None else doc
    g = doc["grid"]
    dts = g["dt_ms"]
    if dts[0] != sim.Params.dt or dts != sorted(dts, reverse=True) or len(dts) < 3:
        raise PathMetricsError("the timesteps must start at the default and decrease")
    if not all(convergence.steps_exact(dt, sim.Params()) for dt in dts):
        raise PathMetricsError("delay and t_ref must be whole steps at every timestep")
    if (g["rate_hz"], g["stim_ms"], g["duration_ms"]) != (
        validate.RATE_HZ,
        validate.STIM_MS,
        validate.DURATION_MS,
    ):
        raise PathMetricsError("the grid does not use the battery protocol")
    if doc["cases"] != sensitivity.load()["cases"]:
        raise PathMetricsError("the cases are not the sensitivity grid's")
    previous = convergence.load()["grid"]
    ours = range(g["seed0"], g["seed0"] + g["seeds"])
    theirs = range(previous["seed0"], previous["seed0"] + previous["seeds"])
    if set(ours) & set(theirs):
        raise PathMetricsError("seeds overlap the convergence run")
    if g["seeds"] < 3:
        raise PathMetricsError("a seed range needs at least three seeds")
    q = doc["quanta"]
    if (q["latency_ms"], q["jitter_ms"]) != (sim.Params.dt, sim.Params.dt):
        raise PathMetricsError("latency and jitter quanta must be the default step")
    if q["recruited_neurons"] != 1:
        raise PathMetricsError("the recruitment quantum is one neuron")
    if q["rate"] != "one spike in stim_ms":
        raise PathMetricsError("the rate quantum is one spike in the window")
    if list(doc["metrics_decide"]) != list(METRICS):
        raise PathMetricsError("the deciding metrics drifted")
    if doc["claim"]["scored"] is not False or doc["defaults_changed"] is not False:
        raise PathMetricsError(
            "a path-metrics study is not a score and changes no default"
        )
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    g = doc["grid"]
    cases = len(doc["cases"]["positive"]) + len(doc["cases"]["negative"])
    return (
        f"path-metrics v{doc['version']} (issue #{doc['issue']}): dt {g['dt_ms']} ms, "
        f"{cases} cases, seeds {g['seed0']}-{g['seed0'] + g['seeds'] - 1}; "
        "latency, jitter, recruitment and rate; not a score, and not convergence v1"
    )


def quantum(metric: str, doc: dict) -> float:
    if metric == "rate":
        return 1000.0 / doc["grid"]["stim_ms"]
    if metric in ("latency", "jitter"):
        return float(doc["quanta"]["latency_ms"])
    if metric == "recruited":
        return float(doc["quanta"]["recruited_neurons"])
    raise PathMetricsError(f"no quantum for {metric}")


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
    """Finest timestep first: its jobs take the longest, so they start first."""
    c = doc["cases"]
    return [
        (dt, case)
        for dt in sorted(doc["grid"]["dt_ms"])
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


def _values(frame: pd.DataFrame, metric: str) -> tuple[float, float, str]:
    """Seed median and seed range, or the jitter range. Status is indeterminate when a
    latency metric sees a seed with no spike."""
    if metric in ("latency", "jitter"):
        lat = frame["latency"].to_numpy(dtype=float)
        if not np.isfinite(lat).all():
            return float("nan"), float("nan"), "indeterminate"
        if metric == "jitter":
            span = float(lat.max() - lat.min())
            return span, span, "decided"
        return float(np.median(lat)), float(lat.max() - lat.min()), "decided"
    column = frame[metric].to_numpy(dtype=float)
    return float(np.median(column)), float(column.max() - column.min()), "decided"


def judge(cells: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Per case, target, metric and timestep: the statistic against the finest timestep."""
    finest = min(doc["grid"]["dt_ms"])
    rows = []
    for (case, target), group in cells.groupby(["case", "target"], sort=False):
        ref = group[group["dt_ms"] == finest]
        for metric in doc["metrics_decide"]:
            ref_value, ref_range, ref_status = _values(ref, metric)
            tol = (
                max(ref_range, quantum(metric, doc))
                if ref_status == "decided"
                else None
            )
            for dt, frame in group.groupby("dt_ms", sort=False):
                value, seed_range, status = _values(frame, metric)
                if status == "indeterminate" or ref_status == "indeterminate":
                    decided = "indeterminate"
                else:
                    decided = (
                        "converged"
                        if abs(value - ref_value) <= tol + 1e-9
                        else "not_converged"
                    )
                rows.append(
                    {
                        "case": case,
                        "target": target,
                        "dt_ms": float(dt),
                        "metric": metric,
                        "value": value,
                        "seed_range": seed_range,
                        "ref_value": ref_value,
                        "tolerance": tol if tol is not None else float("nan"),
                        "status": decided,
                    }
                )
    return pd.DataFrame(rows)


def verdict(judged: pd.DataFrame, doc: dict) -> str:
    """One clause per metric at the default timestep. Indeterminate responses are named
    and do not fail the metric."""
    at = judged[judged["dt_ms"] == doc["grid"]["dt_ms"][0]]
    parts = []
    for metric in doc["metrics_decide"]:
        rows = at[at["metric"] == metric]
        bad = rows[rows["status"] == "not_converged"]
        quiet = rows[rows["status"] == "indeterminate"]

        def names(frame: pd.DataFrame) -> str:
            return ", ".join(f"{c}/{t}" for c, t in zip(frame.case, frame.target))

        if not bad.empty:
            parts.append(f"{metric}: not_converged ({names(bad)})")
        elif not quiet.empty:
            parts.append(f"{metric}: converged, indeterminate ({names(quiet)})")
        else:
            parts.append(f"{metric}: converged")
    return "; ".join(parts)
