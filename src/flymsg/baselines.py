"""Simple baselines for the battery: the measured wiring against degree-preserving
shuffles (SF2, #148).

The YAML file is the lock. The battery's eight responses run on the measured connectome
and on each locked shuffle (N1's configuration-model permutation of `post`) with the same
seeds and default parameters. Per response, the seed-median rate of the target's best
neuron gives an empirical p against the shuffles, upper tail for positive cases and lower
for the negative one, Holm-corrected over the battery. A response is specific when the
shuffles do not reproduce it. Nothing is chosen from the result and the defaults in
`sim.Params` do not change.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import console, draws, locks, nulls, parallel, sensitivity, sim, validate

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "baselines.yaml"

VERSION_HASHES = {
    1: "bff97462896375970c2573fee37f1cca1a14c165033418691f743267d50c07f9",
}

REAL = -1  # the `shuffle` column of the measured connectome's rows


class BaselineError(ValueError):
    """The baseline protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return locks.prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, BaselineError, "baseline protocol")


def assert_matches_code(doc: dict | None = None) -> dict:
    """The battery protocol, cases and holds rule are the sensitivity grid's, the family
    is the one the code draws, and the draws can reach Holm's first threshold."""
    doc = assert_locked() if doc is None else doc
    b, base, s = doc["battery"], doc["baseline"], doc["statistic"]
    if (b["rate_hz"], b["stim_ms"], b["duration_ms"]) != (
        validate.RATE_HZ,
        validate.STIM_MS,
        validate.DURATION_MS,
    ):
        raise BaselineError("the battery does not use the validation protocol")
    grid = sensitivity.load()
    if doc["cases"] != grid["cases"]:
        raise BaselineError("the cases are not the sensitivity grid's")
    if doc["holds"] != {
        k: grid["report"][k]
        for k in ("holds_min_spikes", "holds_seed_share_num", "holds_seed_share_den")
    }:
        raise BaselineError("the holds rule is not the v4 floor")
    if base["family"] != "degree_preserving":
        raise BaselineError("only the degree-preserving family is implemented")
    if 1.0 / (1 + base["draws"]) > s["alpha"] / len(responses(doc)):
        raise BaselineError("too few draws to reach Holm's first threshold")
    if doc["claim"]["scored"] is not False:
        raise BaselineError("a baseline report is not a score")
    return doc


def responses(doc: dict) -> list[tuple[str, str]]:
    """(case, target) for every response of the battery, positive cases first."""
    c = doc["cases"]
    out = []
    for case in [*c["positive"], *c["negative"]]:
        out += [(case, t) for t in sensitivity.case_targets(case)]
    return out


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    base = doc["baseline"]
    first = base["shuffle_seed0"]
    return (
        f"baselines v{doc['version']} (issue #{doc['issue']}): {len(responses(doc))} "
        f"responses, measured connectome against {base['draws']} {base['family']} "
        f"shuffles (seeds {first}-{first + base['draws'] - 1}), battery seeds "
        f"{doc['battery']['seed0']}-{doc['battery']['seed0'] + doc['battery']['seeds'] - 1}; "
        "a report, not a score"
    )


def _job(job: tuple) -> list[dict]:
    """One graph: the measured connectome (`("real",)`) or one shuffle
    (`("shuffle", seed)`), every case."""
    (neurons, edges, doc, backend), _checkpoint, _meta = parallel.context()
    b = doc["battery"]
    shuffle = REAL if job[0] == "real" else int(job[1])
    e = edges if shuffle == REAL else nulls.shuffle_degree_preserving(edges, shuffle)
    p = sim.Params()
    W = sim.network(neurons, e, p)
    c = doc["cases"]
    cases = [*c["positive"], *c["negative"]]
    seeds = range(b["seed0"], b["seed0"] + b["seeds"])
    computed = {}
    if backend == "console":
        # every case and seed of this graph as one batch: the network goes up once
        specs = [
            (
                sensitivity.case_inputs(case, neurons)[0],
                b["rate_hz"],
                b["duration_ms"],
                b["stim_ms"],
                s,
            )
            for case in cases
            for s in seeds
        ]
        results, _ = console.sim_runs(
            console.Device(),
            W,
            specs,
            p,
            Path("runs/console"),
            dataset="malecns-v1.0",
            seed=b["seed0"],
            scope=f"baselines graph {job}",
        )
        for k, case in enumerate(cases):
            computed[case] = results[k * len(seeds) : (k + 1) * len(seeds)]
    rows = []
    for case in cases:
        stim, targets = sensitivity.case_inputs(case, neurons)
        for row in sensitivity.measure(
            W,
            neurons,
            stim,
            targets,
            p,
            seed0=b["seed0"],
            seeds=b["seeds"],
            rate_hz=b["rate_hz"],
            stim_ms=b["stim_ms"],
            duration_ms=b["duration_ms"],
            results=computed.get(case),
        ):
            row.update(shuffle=shuffle, case=case)
            rows.append(row)
    return rows


def jobs(doc: dict) -> list[tuple]:
    """Tuples, as draws.map_jobs keys its checkpoint: the measured graph, then each
    shuffle."""
    base = doc["baseline"]
    first = base["shuffle_seed0"]
    return [("real",), *(("shuffle", s) for s in range(first, first + base["draws"]))]


BACKENDS = ("cpu", "console")


def run(
    neurons,
    edges,
    workers: int = 1,
    checkpoint: Path | None = None,
    backend: str = "cpu",
) -> pd.DataFrame:
    """`backend="console"` runs each graph's battery as one batch on the console worker
    (`flymsg.console`, bit for bit with `sim.run`), one graph at a time."""
    if backend not in BACKENDS:
        raise BaselineError(f"unknown backend {backend!r}")
    doc = assert_matches_code()
    meta = {"version": doc["version"], "sha256": doc["content_sha256"]}
    rows = draws.map_jobs(
        _job,
        jobs(doc),
        1 if backend == "console" else workers,  # one console, one batch at a time
        (neurons, edges, doc, backend),
        checkpoint,
        meta,
    )
    return pd.DataFrame(rows)


def holm(p: np.ndarray) -> np.ndarray:
    """Holm's step-down adjusted p values (monotone, capped at 1)."""
    order = np.argsort(p, kind="mergesort")
    m = p.size
    adjusted = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adjusted[i] = min(1.0, running)
    return adjusted


def judge(cells: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Per response: the measured seed median, the shuffles' quantiles, the empirical p
    in the locked tail, Holm's adjustment and whether the response is specific."""
    h, s = doc["holds"], doc["statistic"]
    stim_s = doc["battery"]["stim_ms"] / 1000.0
    need = h["holds_seed_share_num"] / h["holds_seed_share_den"]
    cells = cells.assign(
        at_floor=cells["rate"] * stim_s >= h["holds_min_spikes"] - 1e-9
    )
    per_graph = (
        cells.groupby(["case", "target", "shuffle"], sort=False)
        .agg(
            rate=("rate", "median"),
            latency=("latency", "median"),
            recruited=("recruited", "median"),
            persistent=("persistent", "median"),
            holds=("at_floor", lambda x: bool(x.mean() >= need - 1e-9)),
        )
        .sort_index()
    )
    negative = set(doc["cases"]["negative"])
    rows = []
    for case, target in responses(doc):
        g = per_graph.loc[(case, target)]
        real = g.loc[REAL]
        null = g.drop(index=REAL)
        if case in negative:
            extreme = int((null["rate"] <= real["rate"] + 1e-9).sum())
        else:
            extreme = int((null["rate"] >= real["rate"] - 1e-9).sum())
        q05, q50, q95 = np.percentile(null["rate"], [5, 50, 95])
        rows.append(
            {
                "case": case,
                "target": target,
                "tail": "lower" if case in negative else "upper",
                "rate_measured": float(real["rate"]),
                "null_q05": float(q05),
                "null_q50": float(q50),
                "null_q95": float(q95),
                "p": (1 + extreme) / (1 + len(null)),
                "holds_measured": bool(real["holds"]),
                "holds_share_null": float(null["holds"].mean()),
                "latency_measured": float(real["latency"]),
                "latency_null_median": float(null["latency"].median()),
                "recruited_measured": float(real["recruited"]),
                "recruited_null_median": float(null["recruited"].median()),
                "persistent_measured": float(real["persistent"]),
                "persistent_null_median": float(null["persistent"].median()),
            }
        )
    judged = pd.DataFrame(rows)
    judged["p_holm"] = holm(judged["p"].to_numpy())
    judged["specific"] = judged["p_holm"] <= s["alpha"] + 1e-12
    return judged


def verdict(judged: pd.DataFrame) -> str:
    """The specific and not specific responses; no overall pass or fail."""

    def names(d):
        return ", ".join(f"{c}/{t}" for c, t in zip(d.case, d.target)) or "none"

    return (
        f"specific: {names(judged[judged.specific])}; "
        f"not specific: {names(judged[~judged.specific])}"
    )
