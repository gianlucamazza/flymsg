"""Validation battery: stimulate known circuits and check the expected outcome.

positive   the known downstream types reach MIN_HZ (best neuron of the type, mean over seeds)
control    the same number of random neurons from the same superclasses, excluding direct
           inputs of the targets, must leave the targets below MIN_HZ: responses need the
           specific wiring, not just any drive of that size
stability  at most MAX_PERSISTENT neurons still fire from 100 ms after the stimulus ends

`calibrate` grid-searches w_syn x th_jump and ranks parameter sets by checks passed.
"""

import multiprocessing as mp
import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from flymsg import data, sim

MIN_HZ = 20.0
MAX_PERSISTENT = 100
RATE_HZ, STIM_MS, DURATION_MS = 100.0, 300.0, 600.0


def p1(neurons: pd.DataFrame) -> np.ndarray:
    """P1 courtship neurons: the pC1 subtypes matching pMP4/pMP-e (Yu 2010, Cachero 2010)."""
    is_pc1 = neurons["type"].fillna("").str.startswith("pC1")
    return np.flatnonzero(is_pc1 & neurons["synonyms"].fillna("").str.contains("pMP4"))


@dataclass
class Case:
    name: str
    stim: str | Callable[[pd.DataFrame], np.ndarray]
    targets: list[str]
    reference: str

    def stim_idx(self, neurons: pd.DataFrame) -> np.ndarray:
        return (
            data.resolve(neurons, self.stim)
            if isinstance(self.stim, str)
            else self.stim(neurons)
        )


CASES = [
    Case("looming escape", "LC4_R", ["DNp01", "TTMn"], "von Reyn 2014, Ache 2019"),
    # GF -> PSI -> DLMn is not tested: it runs mostly through gap junctions, which the
    # connectome does not contain (the chemical GF -> PSI link has only ~23 synapses).
    Case("giant fiber output", "DNp01", ["TTMn"], "King & Wyman 1980"),
    Case("P1 courtship drive", p1, ["pIP10", "dPR1"], "von Philipsborn 2011"),
    Case("pIP10 song pathway", "pIP10", ["dPR1"], "von Philipsborn 2011"),
]


def control_idx(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    stim: np.ndarray,
    targets: np.ndarray,
    rng,
) -> np.ndarray:
    """Random neurons matching the stimulus' superclass mix, minus targets and their inputs."""
    strong = edges[(edges["weight"] >= 5) & np.isin(edges["post"], targets)]
    excluded = np.zeros(len(neurons), dtype=bool)
    excluded[np.concatenate([stim, targets, strong["pre"].to_numpy()])] = True
    sc = neurons["superclass"].fillna("none").to_numpy()
    picks = []
    for cls, k in zip(*np.unique(sc[stim], return_counts=True), strict=True):
        pool = np.flatnonzero((sc == cls) & ~excluded)
        picks.append(rng.choice(pool, size=min(k, pool.size), replace=False))
    return np.concatenate(picks)


def respond(W, neurons, stim, targets, p, seeds) -> tuple[dict[str, float], float]:
    """Best-neuron stimulus-window rate per target type (mean over seeds), mean persistence."""
    results = [
        sim.run(W, stim, RATE_HZ, DURATION_MS, STIM_MS, p, seed)
        for seed in range(seeds)
    ]
    rates = np.mean([r.rate(0, STIM_MS) for r in results], axis=0)
    types = neurons["type"].to_numpy()
    best = {t: float(rates[types == t].max()) for t in targets}
    return best, float(np.mean([r.persistent().size for r in results]))


def run(
    neurons: pd.DataFrame, edges: pd.DataFrame, p: sim.Params, seeds: int = 3
) -> pd.DataFrame:
    """One row per check: case, kind, subject, value, passed."""
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)
    rng = np.random.default_rng(0)
    rows = []
    for case in CASES:
        stim = case.stim_idx(neurons)
        target_idx = np.concatenate([data.resolve(neurons, t) for t in case.targets])
        best, persistent = respond(W, neurons, stim, case.targets, p, seeds)
        rows += [(case.name, "positive", t, hz, hz >= MIN_HZ) for t, hz in best.items()]
        rows.append(
            (
                case.name,
                "stability",
                "self-sustained neurons",
                persistent,
                persistent <= MAX_PERSISTENT,
            )
        )
        ctrl = control_idx(neurons, edges, stim, target_idx, rng)
        best, _ = respond(W, neurons, ctrl, case.targets, p, seeds)
        rows += [(case.name, "control", t, hz, hz < MIN_HZ) for t, hz in best.items()]
    return pd.DataFrame(rows, columns=["case", "kind", "subject", "value", "passed"])


_shared: tuple[pd.DataFrame, pd.DataFrame, int] | None = (
    None  # inherited by forked workers
)


def _run_point(point: tuple[float, float]) -> dict:
    neurons, edges, seeds = _shared
    w_syn, th_jump = point
    t = time.monotonic()
    report = run(neurons, edges, sim.Params(w_syn=w_syn, th_jump=th_jump), seeds)
    failed = report[~report["passed"]]
    print(
        f"  w_syn={w_syn} th_jump={th_jump}: {int(report['passed'].sum())}/{len(report)} "
        f"({time.monotonic() - t:.0f} s)",
        flush=True,
    )
    return {
        "w_syn": w_syn,
        "th_jump": th_jump,
        "passed": int(report["passed"].sum()),
        "total": len(report),
        "failed": "; ".join(
            f"{r.case}/{r.kind}/{r.subject}={r.value:.0f}" for r in failed.itertuples()
        ),
    }


def calibrate(
    neurons, edges, w_syns, th_jumps, seeds: int = 3, workers: int = 4
) -> pd.DataFrame:
    """Run the battery on every (w_syn, th_jump); best first.

    Ties on checks passed go to the set closest to the published Shiu model
    (w_syn nearest 0.275, then the smallest th_jump).
    """
    global _shared
    _shared = (neurons, edges, seeds)
    grid = list(product(w_syns, th_jumps))
    with mp.get_context("fork").Pool(
        min(workers, len(grid))
    ) as pool:  # fork shares the tables
        rows = pool.map(_run_point, grid, chunksize=1)
    out = pd.DataFrame(rows)
    out["shiu_dist"] = (out["w_syn"] - sim.Params.w_syn).abs()
    return out.sort_values(
        ["passed", "shiu_dist", "th_jump"], ascending=[False, True, True]
    ).drop(columns="shiu_dist")
