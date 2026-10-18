"""Sensitivity grid (#28): how the battery's responses move with `w_syn` and `th_jump`.

The YAML file is the lock. Every cell of the grid is run and reported; nothing is chosen
from it, the defaults in `sim.Params` do not change, and no frozen score is replaced. Seed
spread (at one cell) and parameter spread (across cells) are reported apart.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import draws, figures, locks, parallel, sim, validate

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "sensitivity.yaml"

VERSION_HASHES = {
    1: "59806931f038d4565eeaee40cb15f5671db1bb3931ddf319f0c0b0b61eb55fef",
}


class SensitivityError(ValueError):
    """The sensitivity grid drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return locks.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, SensitivityError, "sensitivity grid")


def assert_matches_code(doc: dict | None = None) -> dict:
    """The grid is centred on the live defaults and uses the battery's protocol."""
    doc = assert_locked() if doc is None else doc
    g = doc["grid"]
    if 1.0 not in g["w_syn_factors"] or sim.Params.th_jump not in g["th_jump"]:
        raise SensitivityError("the grid does not contain the default cell")
    if (g["rate_hz"], g["stim_ms"], g["duration_ms"]) != (
        validate.RATE_HZ,
        validate.STIM_MS,
        validate.DURATION_MS,
    ):
        raise SensitivityError("the grid does not use the battery protocol")
    known = {c.name for c in validate.CASES}
    if set(doc["cases"]["positive"]) != known:
        raise SensitivityError("the positive cases are not the battery's")
    if set(doc["cases"]["negative"]) != {name for name, *_ in validate.NEGATIVES}:
        raise SensitivityError("the negative cases are not the battery's")
    r = doc["report"]
    if (
        r["holds_min_spikes"] != validate.MIN_SPIKES
        or r["holds_seed_share_num"] / r["holds_seed_share_den"]
        != validate.MIN_SEED_SHARE
    ):
        raise SensitivityError("the holds rule is not the v4 floor")
    if doc["claim"]["scored"] is not False:
        raise SensitivityError("a sensitivity grid is not a score")
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    g = doc["grid"]
    cells = len(g["w_syn_factors"]) * len(g["th_jump"])
    cases = len(doc["cases"]["positive"]) + len(doc["cases"]["negative"])
    return (
        f"sensitivity v{doc['version']} (issue #{doc['issue']}): {cells} cells "
        f"(w_syn x {g['w_syn_factors']}, th_jump {g['th_jump']}), {cases} cases, "
        f"seeds {g['seed0']}-{g['seed0'] + g['seeds'] - 1}; a report, not a score"
    )


def cell_params(factor: float, th_jump: float) -> sim.Params:
    return sim.Params(w_syn=sim.Params.w_syn * factor, th_jump=th_jump)


def case_targets(name: str) -> list[str]:
    """Target types of a battery case, positive or negative."""
    for case in validate.CASES:
        if case.name == name:
            return list(case.targets)
    for neg, _stim, target, *_ in validate.NEGATIVES:
        if neg == name:
            return [target]
    raise KeyError(f"no battery case {name!r}")


def case_inputs(name: str, neurons: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Stimulus rows and target types of a battery case, positive or negative."""
    for case in validate.CASES:
        if case.name == name:
            return case.stim_idx(neurons), list(case.targets)
    for neg, stim, target, *_ in validate.NEGATIVES:
        if neg == name:
            return np.asarray(stim(neurons)), [target]
    raise KeyError(f"no battery case {name!r}")


def measure(
    W,
    neurons,
    stim,
    targets,
    p,
    *,
    seed0,
    seeds,
    rate_hz,
    stim_ms,
    duration_ms,
    results: list[sim.Result] | None = None,
) -> list[dict]:
    """Per seed and target: the best neuron's rate and first spike, plus the recruited and
    persistent counts of the run. The best neuron is the one with the highest mean rate
    over the seeds, as `validate.respond` picks it. `results` are the seeds' runs when
    another backend computed them (`sim.run`'s, bit for bit); by default they run here."""
    if results is None:
        results = [
            sim.run(W, stim, rate_hz, duration_ms, stim_ms, p, s)
            for s in range(seed0, seed0 + seeds)
        ]
    types = neurons["type"].to_numpy()
    on = [r.rate(0, stim_ms) for r in results]
    rows = []
    for t in targets:
        idx = np.flatnonzero(types == t)
        best = idx[np.argmax(np.mean([rate[idx] for rate in on], axis=0))]
        for i, (r, rate) in enumerate(zip(results, on, strict=True)):
            fired = rate > 0
            fired[stim] = False
            rows.append(
                {
                    "seed": seed0 + i,
                    "target": t,
                    "rate": float(rate[best]),
                    "latency": float(r.first_spike_ms[best]),
                    "recruited": int(fired.sum()),
                    "persistent": int((r.rate(400.0, duration_ms) > 0).sum()),
                }
            )
    return rows


def _job(job: tuple) -> list[dict]:
    (neurons, edges, doc), _checkpoint, _meta = parallel.context()
    factor, th_jump, case = job
    g = doc["grid"]
    p = cell_params(factor, th_jump)
    W = sim.network(neurons, edges, p)
    stim, targets = case_inputs(case, neurons)
    rows = measure(
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
        row.update(w_syn_factor=factor, th_jump=th_jump, case=case)
    return rows


def jobs(doc: dict) -> list[tuple]:
    g, c = doc["grid"], doc["cases"]
    return [
        (f, th, case)
        for f in g["w_syn_factors"]
        for th in g["th_jump"]
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


def holds(cells: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Per cell, case and target: the share of seeds at the v4 floor and whether it holds."""
    r = doc["report"]
    stim_s = doc["grid"]["stim_ms"] / 1000.0
    spikes = cells.assign(
        at_floor=cells["rate"] * stim_s >= r["holds_min_spikes"] - 1e-9
    )
    out = (
        spikes.groupby(["case", "target", "w_syn_factor", "th_jump"])["at_floor"]
        .mean()
        .rename("share")
        .reset_index()
    )
    need = r["holds_seed_share_num"] / r["holds_seed_share_den"]
    out["holds"] = out["share"] >= need - 1e-9
    return out


def spreads(cells: pd.DataFrame) -> pd.DataFrame:
    """For each case, target and metric: the seed range at the default cell, and the range
    of the seed medians over all cells. The first is noise, the second sensitivity."""
    rows = []
    default = cells[(cells["w_syn_factor"] == 1.0) & (cells["th_jump"] == 0.0)]
    for (case, target), g in cells.groupby(["case", "target"]):
        d = default[(default["case"] == case) & (default["target"] == target)]
        for metric in ("rate", "latency", "recruited", "persistent"):
            med = g.groupby(["w_syn_factor", "th_jump"])[metric].median()
            rows.append(
                {
                    "case": case,
                    "target": target,
                    "metric": metric,
                    "default_median": float(d[metric].median()),
                    "seed_range_at_default": float(d[metric].max() - d[metric].min()),
                    "median_min": float(med.min()),
                    "median_max": float(med.max()),
                }
            )
    return pd.DataFrame(rows)


def svg(cells: pd.DataFrame, doc: dict) -> str:
    """Small multiples: one panel per case and target, target rate (median and seed range)
    against the w_syn factor, one line per th_jump, and the v4 floor as a dashed line. No
    dependency beyond the standard library, so the figure is reproducible wherever the
    grid runs."""

    panels = list(cells.groupby(["case", "target"], sort=False))
    factors = doc["grid"]["w_syn_factors"]
    ths = doc["grid"]["th_jump"]
    colours = [figures.BLUE, figures.RED, figures.GREEN, figures.GOLD]
    r = doc["report"]
    floor = r["holds_min_spikes"] / (doc["grid"]["stim_ms"] / 1000.0)
    pw, ph, cols = 200, 130, 4
    rows_n = math.ceil(len(panels) / cols)
    drawn = []
    for n, ((case, target), g) in enumerate(panels):
        x0 = 60 + (n % cols) * (pw + 60)
        y0 = 100 + (n // cols) * (ph + 60)
        top = max(floor * 1.5, float(g["rate"].max()) * 1.1)
        a = figures.Panel(
            x0, y0, pw, ph, (factors[0], factors[-1]), (0, top), f"{case} → {target}"
        )
        a.frame(factors, [f"{f:g}" for f in factors])
        a.hline(floor, figures.GREY, "4 3")
        for c, th in enumerate(ths):
            part = g[g["th_jump"] == th]
            if part.empty:  # a partial grid draws the series it has
                continue
            sel = part.groupby("w_syn_factor")["rate"]
            med, lo, hi = sel.median(), sel.min(), sel.max()
            col = colours[c % len(colours)]
            a.band(factors, [lo[f] for f in factors], [hi[f] for f in factors], col)
            a.line(factors, [med[f] for f in factors], col)
        drawn.append(a)
    key = figures.Panel(60, 30, 10, 10, (0, 1), (0, 1))
    key.legend(
        [(f"th_jump {th:g} mV", colours[c % len(colours)]) for c, th in enumerate(ths)]
        + [(f"v4 floor ({r['holds_min_spikes']} spikes = {floor:g} Hz)", figures.GREY)],
        x=60,
        y=40,
    )
    drawn.append(key)
    width = 60 + cols * (pw + 60)
    height = 100 + rows_n * (ph + 60)
    return figures.document(
        width,
        height,
        "Target rate (Hz) against the w_syn factor; line = median over seeds, band = "
        "seed range. A report, not a score.",
        drawn,
    )
