"""Do simulated responses run through sexually dimorphic neurons more than expected?

For each validation case, the responders (neurons other than the stimulated ones that fire
during the stimulus in at least MIN_SEED_SHARE of the seeds) are compared with random neuron
sets of the same size and superclass mix, drawn from all non-stimulated neurons. The null
matches superclass because responders of a visual stimulus are mostly visual neurons, and
dimorphic neurons are not spread evenly across superclasses.
"""

import multiprocessing as mp
import zlib

import numpy as np
import pandas as pd

from flymsg import data, sim, validate

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


SILENCING_CASES = ("P1 courtship drive", "pIP10 song pathway", "looming escape")
_shared = None  # job context, inherited by forked workers


def _silencing_job(job: tuple[str, str]) -> list[dict]:
    neurons, W, p, seeds, n_null = _shared
    case_name, category = job
    case = next(c for c in validate.CASES if c.name == case_name)
    stim = case.stim_idx(neurons)
    targets = np.concatenate([data.resolve(neurons, t) for t in case.targets])
    keep_on = np.zeros(len(neurons), dtype=bool)
    keep_on[np.concatenate([stim, targets])] = True
    flag = CATEGORIES[category](neurons).to_numpy() & ~keep_on
    silenced = np.flatnonzero(flag)

    def target_rates(silence):
        out, _ = validate.respond(
            W, neurons, stim, case.targets, p, seeds, silence=silence
        )
        return np.array([out[t]["rate"] for t in case.targets])

    base = target_rates(None)
    if not silenced.size:  # nothing of this category outside stimulus and targets
        return [
            {"case": case_name, "silenced": category, "n_silenced": 0, "target": t,
             "base_hz": base[j], "silenced_hz": base[j], "drop": np.nan,
             "null_drop_mean": np.nan, "null_drop_max": np.nan, "p": np.nan}
            for j, t in enumerate(case.targets)
        ]  # fmt: skip
    obs = target_rates(silenced)
    # null: as many neurons outside the category, same superclass mix, never stimulus or
    # targets: silencing N category neurons vs N others
    sc = neurons["superclass"].fillna("none").to_numpy()
    rng = np.random.default_rng(
        zlib.crc32(f"{case_name}/{category}".encode())
    )  # stable
    null = []
    for _ in range(n_null):
        pick = np.concatenate(
            [
                rng.choice(
                    np.flatnonzero((sc == c) & ~keep_on & ~flag), size=k, replace=False
                )
                for c, k in zip(
                    *np.unique(sc[silenced], return_counts=True), strict=True
                )
            ]
        )
        null.append(target_rates(pick))
    null = np.array(null)
    rows = []
    for j, t in enumerate(case.targets):
        drop = 1 - obs[j] / base[j] if base[j] else np.nan
        null_drop = 1 - null[:, j] / base[j] if base[j] else np.full(n_null, np.nan)
        rows.append(
            {
                "case": case_name,
                "silenced": category,
                "n_silenced": silenced.size,
                "target": t,
                "base_hz": base[j],
                "silenced_hz": obs[j],
                "drop": drop,
                "null_drop_mean": float(np.nanmean(null_drop)),
                "null_drop_max": float(np.nanmax(null_drop)),
                "p": (1 + int((null_drop >= drop).sum())) / (1 + n_null),
            }
        )
    return rows


def silencing(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    p: sim.Params,
    seeds: int = 3,
    n_null: int = 20,
    workers: int = 4,
    cases=SILENCING_CASES,
) -> pd.DataFrame:
    """Silence every neuron of a category (except the stimulus and the targets) and measure
    how much each target's response drops, against silencing as many neurons outside the
    category with the same superclass mix. Empirical one-sided p with +1 smoothing (smallest 1 / (n_null + 1))."""
    global _shared
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)
    _shared = (neurons, W, p, seeds, n_null)
    jobs = [(c, k) for c in cases for k in CATEGORIES]
    if workers <= 1:
        rows = [_silencing_job(j) for j in jobs]
    else:
        with mp.get_context("fork").Pool(min(workers, len(jobs))) as pool:
            rows = pool.map(_silencing_job, jobs, chunksize=1)
    return pd.DataFrame([r for chunk in rows for r in chunk])


def _type_job(job: tuple[str, str]) -> dict:
    neurons, W, p, seeds, case_name, base, silenced_by_type = _shared
    t = job[1]
    case = next(c for c in validate.CASES if c.name == case_name)
    out, _ = validate.respond(
        W,
        neurons,
        case.stim_idx(neurons),
        case.targets,
        p,
        seeds,
        silence=silenced_by_type[t],
    )
    row = {"case": case_name, "type": t, "n": silenced_by_type[t].size}
    for j, tgt in enumerate(case.targets):
        row[f"{tgt}_drop"] = 1 - out[tgt]["rate"] / base[j] if base[j] else np.nan
    return row


def type_silencing(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    p: sim.Params,
    case_name: str,
    category: str,
    seeds: int = 3,
    workers: int = 4,
) -> pd.DataFrame:
    """Silence, one cell type at a time, the responders of `case_name` that belong to
    `category`, and report each target's drop (negative: the response rises). Only types
    that fire in the case are tried, since silencing a silent type changes nothing."""
    global _shared
    case = next(c for c in validate.CASES if c.name == case_name)
    stim = case.stim_idx(neurons)
    targets = np.concatenate([data.resolve(neurons, t) for t in case.targets])
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)
    results = [
        sim.run(W, stim, validate.RATE_HZ, validate.DURATION_MS, validate.STIM_MS, p, s)
        for s in range(seeds)
    ]
    resp = np.setdiff1d(responders(results, stim), targets)
    resp = resp[CATEGORIES[category](neurons).to_numpy()[resp]]
    types = neurons["type"].fillna(neurons["bodyId"].astype(str)).to_numpy()
    by_type = {t: resp[types[resp] == t] for t in np.unique(types[resp])}
    base_out, _ = validate.respond(W, neurons, stim, case.targets, p, seeds)
    base = np.array([base_out[t]["rate"] for t in case.targets])
    _shared = (neurons, W, p, seeds, case_name, base, by_type)
    jobs = [(case_name, t) for t in by_type]
    if workers <= 1:
        rows = [_type_job(j) for j in jobs]
    else:
        with mp.get_context("fork").Pool(min(workers, len(jobs))) as pool:
            rows = pool.map(_type_job, jobs, chunksize=4)
    return pd.DataFrame(rows)
