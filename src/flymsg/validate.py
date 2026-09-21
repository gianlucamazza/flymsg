"""Validation battery: stimulate known circuits and check the expected outcome.

positive   reliable: the best neuron of each target type fires >= MIN_SPIKES during the
           stimulus in at least MIN_SEED_SHARE of the seeds
specific   its rate beats the control by SPECIFICITY x + MARGIN_HZ; the control stimulates
           the same number of random neurons from the same superclasses, excluding direct
           inputs of the targets, so the response must need the specific wiring
stability  at most MAX_PERSISTENT neurons still fire from 100 ms after the stimulus ends

Positive checks count spikes rather than requiring a rate: the adaptive threshold caps
steady rates (about (drive - 7 mV) / (th_jump * tau_th)), so an absolute rate threshold
would penalise adaptation itself instead of testing the wiring.

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

MIN_SPIKES = 3  # in the 300 ms stimulus window
MIN_SEED_SHARE = 2 / 3
SPECIFICITY, MARGIN_HZ = 3.0, 2.0
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


def respond(W, neurons, stim, targets, p, seeds) -> tuple[dict[str, dict], float]:
    """Per target type, its best neuron (highest mean rate over seeds): rate, reliable seeds
    and median first-spike latency. Also the mean number of self-sustained neurons."""
    results = [
        sim.run(W, stim, RATE_HZ, DURATION_MS, STIM_MS, p, seed)
        for seed in range(seeds)
    ]
    stim_bins = round(STIM_MS / results[0].bin_ms)
    spikes = np.stack([r.counts[:stim_bins].sum(axis=0) for r in results])  # seeds x n
    rates = spikes.mean(axis=0) / (STIM_MS / 1000.0)
    latency = np.stack([r.first_spike_ms for r in results])
    types = neurons["type"].to_numpy()
    out = {}
    for t in targets:
        idx = np.flatnonzero(types == t)
        best = idx[np.argmax(rates[idx])]
        lat = latency[:, best]
        out[t] = {
            "rate": float(rates[best]),
            "reliable": int((spikes[:, best] >= MIN_SPIKES).sum()),
            "latency": float(np.median(lat[np.isfinite(lat)]))
            if np.isfinite(lat).any()
            else np.nan,
        }
    return out, float(np.mean([r.persistent().size for r in results]))


def run(
    neurons: pd.DataFrame, edges: pd.DataFrame, p: sim.Params, seeds: int = 3
) -> pd.DataFrame:
    """One row per check: case, kind, subject, value, note, latency_ms, passed."""
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)
    rng = np.random.default_rng(0)
    need = int(np.ceil(MIN_SEED_SHARE * seeds))
    rows = []
    for case in CASES:
        stim = case.stim_idx(neurons)
        target_idx = np.concatenate([data.resolve(neurons, t) for t in case.targets])
        pos, persistent = respond(W, neurons, stim, case.targets, p, seeds)
        ctrl, _ = respond(
            W,
            neurons,
            control_idx(neurons, edges, stim, target_idx, rng),
            case.targets,
            p,
            seeds,
        )
        for t in case.targets:
            r, c = pos[t], ctrl[t]
            rows.append(
                (
                    case.name,
                    "positive",
                    t,
                    r["rate"],
                    f"{r['reliable']}/{seeds} seeds >= {MIN_SPIKES} spikes",
                    r["latency"],
                    r["reliable"] >= need,
                )
            )
            rows.append(
                (
                    case.name,
                    "specific",
                    t,
                    c["rate"],
                    f"control; needs <= {(r['rate'] - MARGIN_HZ) / SPECIFICITY:.1f} Hz",
                    np.nan,
                    r["rate"] >= SPECIFICITY * c["rate"] + MARGIN_HZ,
                )
            )
        rows.append(
            (
                case.name,
                "stability",
                "self-sustained neurons",
                persistent,
                f"<= {MAX_PERSISTENT}",
                np.nan,
                persistent <= MAX_PERSISTENT,
            )
        )
    return pd.DataFrame(
        rows,
        columns=["case", "kind", "subject", "value", "note", "latency_ms", "passed"],
    )


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
