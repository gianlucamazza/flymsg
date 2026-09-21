"""Do simulated responses run through sexually dimorphic neurons more than expected?

For each validation case, the responders (neurons other than the stimulated ones that fire
during the stimulus in at least MIN_SEED_SHARE of the seeds) are compared with random neuron
sets of the same size and superclass mix, drawn from all non-stimulated neurons. The null
matches superclass because responders of a visual stimulus are mostly visual neurons, and
dimorphic neurons are not spread evenly across superclasses.
"""

import numpy as np
import pandas as pd

from flymsg import sim, validate

# MaleCNS annotations; "potentially ..." counts, the field is a best current call
CATEGORIES = {
    "fru/dsx+": lambda n: n["fruDsx"].notna(),
    "male-specific": lambda n: n["dimorphism"].fillna("").str.contains("male-specific"),
    "dimorphic": lambda n: n["dimorphism"].fillna("").str.contains("dimorphic"),
}


def responders(results: list[sim.Result], stim: np.ndarray) -> np.ndarray:
    """Neurons firing during the stimulus in >= MIN_SEED_SHARE of the seeds, minus `stim`."""
    fired = np.stack([r.rate(0, r.stim_ms) > 0 for r in results])
    need = int(np.ceil(validate.MIN_SEED_SHARE * len(results)))
    idx = np.flatnonzero(fired.sum(axis=0) >= need)
    return np.setdiff1d(idx, stim)


def enrichment(
    neurons: pd.DataFrame, resp: np.ndarray, stim: np.ndarray, rng, n_null: int = 1000
) -> pd.DataFrame:
    """Per category: observed share among responders, null mean share, ratio, and the
    empirical one-sided p (share of null sets at least as high, with +1 smoothing)."""
    sc = neurons["superclass"].fillna("none").to_numpy()
    pool = np.ones(len(neurons), dtype=bool)
    pool[stim] = False
    by_class = {c: np.flatnonzero((sc == c) & pool) for c in np.unique(sc[resp])}
    counts = dict(zip(*np.unique(sc[resp], return_counts=True), strict=True))
    flags = {k: f(neurons).to_numpy() for k, f in CATEGORIES.items()}
    null = {k: np.empty(n_null) for k in flags}
    for i in range(n_null):
        pick = np.concatenate(
            [rng.choice(by_class[c], size=k, replace=False) for c, k in counts.items()]
        )
        for k, f in flags.items():
            null[k][i] = f[pick].mean()
    rows = []
    for k, f in flags.items():
        obs = f[resp].mean()
        rows.append(
            {
                "category": k,
                "responders": int(f[resp].sum()),
                "share": obs,
                "null_share": null[k].mean(),
                "ratio": obs / null[k].mean() if null[k].mean() else np.nan,
                "p": (1 + (null[k] >= obs).sum()) / (1 + n_null),
            }
        )
    return pd.DataFrame(rows)


def run(
    neurons: pd.DataFrame, edges: pd.DataFrame, p: sim.Params, seeds: int = 3
) -> pd.DataFrame:
    """Enrichment for every validation case, at the validation protocol's stimulus."""
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)
    rng = np.random.default_rng(0)
    out = []
    for case in validate.CASES:
        stim = case.stim_idx(neurons)
        results = [
            sim.run(
                W,
                stim,
                validate.RATE_HZ,
                validate.DURATION_MS,
                validate.STIM_MS,
                p,
                s,
            )
            for s in range(seeds)
        ]
        resp = responders(results, stim)
        table = enrichment(neurons, resp, stim, rng)
        table.insert(0, "case", case.name)
        table.insert(1, "n_responders", resp.size)
        out.append(table)
    return pd.concat(out, ignore_index=True)
