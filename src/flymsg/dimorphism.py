"""Do simulated responses run through sexually dimorphic neurons more than expected?

For each validation case, the responders (neurons other than the stimulated ones that fire
during the stimulus in at least MIN_SEED_SHARE of the seeds) are compared with random neuron
sets of the same size and superclass mix, drawn from all non-stimulated neurons. The null
matches superclass because responders of a visual stimulus are mostly visual neurons, and
dimorphic neurons are not spread evenly across superclasses.
"""

import json
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, parallel, sim, validate

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


def _silencing_job(job: tuple[str, str]) -> list[dict]:
    (neurons, W, p, seeds, n_null), checkpoint, meta = parallel.context()
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
             "null_drop_mean": np.nan, "null_drop_min": np.nan, "null_drop_max": np.nan,
             "p_drop": np.nan, "p_rise": np.nan}
            for j, t in enumerate(case.targets)
        ]  # fmt: skip
    obs = target_rates(silenced)
    # null: as many neurons outside the category, same superclass mix, never stimulus or
    # targets: silencing N category neurons vs N others
    sc = neurons["superclass"].fillna("none").to_numpy()
    rng = np.random.default_rng(
        zlib.crc32(f"{case_name}/{category}".encode())
    )  # stable
    null = _null_rates(
        f"{case_name} / {category}",
        n_null,
        lambda: _matched_draw(rng, sc, ~keep_on & ~flag, silenced),
        target_rates,
        _partial(checkpoint, job),
        meta,
    )
    return _rows(case_name, category, silenced.size, case.targets, base, obs, null)


def _null_rates(
    label: str, n_null: int, pick, rates, partial: Path | None = None, meta=None
) -> np.ndarray:
    """`rates(pick())` n_null times, reporting progress and a measured ETA on stderr about
    every 10 % (null runs take hours on the full CNS). With `partial`, every draw is
    appended to that file as it finishes; a rerun replays the saved draws (`pick()` only,
    to advance the generator, checked against the saved hash of each pick) and continues."""
    saved = []
    if partial and partial.exists():
        lines = partial.read_text().splitlines()
        try:
            json.loads(lines[-1])
        except (json.JSONDecodeError, IndexError):  # cut short while writing
            lines = lines[:-1]
            partial.write_text("".join(line + "\n" for line in lines))
        if lines and json.loads(lines[0]) != meta:
            raise CheckpointMismatch(f"{partial} was written with other parameters")
        saved = [json.loads(line) for line in lines[1:]]
    out = []
    for i, rec in enumerate(saved[:n_null]):
        if _pick_hash(pick()) != rec["pick"]:
            raise CheckpointMismatch(f"{partial}: draw {i} is not the one saved")
        out.append(rec["rates"])
    f = None
    if partial:
        f = partial.open("a")
        if not partial.stat().st_size:
            f.write(json.dumps(meta) + "\n")
    t0, start = time.monotonic(), len(out)
    step = max(1, n_null // 10)
    try:
        for i in range(start + 1, n_null + 1):
            idx = pick()
            r = [float(x) for x in rates(idx)]
            out.append(r)
            if f:
                f.write(json.dumps({"pick": _pick_hash(idx), "rates": r}) + "\n")
                f.flush()
            if i % step == 0 or i == n_null:
                el = time.monotonic() - t0
                eta = el / (i - start) * (n_null - i) / 60
                print(
                    f"  [{label}] null {i}/{n_null}, {el / 60:.0f} min, ETA {eta:.0f} min",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        if f:
            f.close()
    return np.array(out)


def _pick_hash(idx) -> int:
    return zlib.crc32(np.sort(np.asarray(idx, dtype=np.int64)).tobytes())


def _partial(checkpoint: Path | None, job) -> Path | None:
    """Where a job's null draws are saved while it runs."""
    if checkpoint is None:
        return None
    return checkpoint.with_name(
        f"{checkpoint.name}.{zlib.crc32(repr(tuple(job)).encode()):08x}.partial"
    )


class CheckpointMismatch(ValueError):
    """A checkpoint file written with other parameters than the current run."""


def _map_jobs(fn, jobs: list, workers: int, ctx, checkpoint: Path | None, meta: dict):
    """Run `fn` over `jobs` (each returns a list of rows) with job context `ctx`, in worker
    processes if workers > 1, collecting results as they finish. With `checkpoint`, every finished job
    is appended to that JSON-lines file and jobs already there are skipped, so an
    interrupted run resumes (a running job's null draws are saved too, see `_null_rates`);
    a checkpoint written with other parameters is refused."""
    done: dict[tuple, list] = {}
    if checkpoint and checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            rec = json.loads(line)
            if rec["meta"] != meta:
                raise CheckpointMismatch(
                    f"{checkpoint} was written with {rec['meta']}, not {meta}"
                )
            done[tuple(rec["job"])] = rec["rows"]
    todo = [j for j in jobs if tuple(j) not in done]
    if done:
        print(
            f"resuming: {len(done)} of {len(jobs)} jobs in {checkpoint}",
            file=sys.stderr,
        )

    def record(job, rows):
        done[tuple(job)] = rows
        print(f"job {len(done)}/{len(jobs)} done: {job}", file=sys.stderr, flush=True)
        if checkpoint:
            rec = {"meta": meta, "job": list(job), "rows": rows}
            with checkpoint.open("a") as f:
                f.write(json.dumps(rec, default=float) + "\n")
            _partial(checkpoint, job).unlink(missing_ok=True)

    for j, rows in parallel.imap(fn, todo, workers, (ctx, checkpoint, meta)):
        record(j, rows)
    return [r for j in jobs for r in done[tuple(j)]]


def _matched_draw(
    rng, key: np.ndarray, pool: np.ndarray, like: np.ndarray
) -> np.ndarray:
    """As many neurons from `pool` as `like` has, with the same count per `key` value."""
    groups, counts = np.unique(key[like], return_counts=True)
    pick = []
    for g, k in zip(groups, counts, strict=True):
        cand = np.flatnonzero(pool & (key == g))
        if cand.size < k:
            raise ValueError(f"null pool has {cand.size} neurons of {g!r}, need {k}")
        pick.append(rng.choice(cand, size=k, replace=False))
    return np.concatenate(pick)


def _rows(case_name, silenced, n_silenced, targets, base, obs, null) -> list[dict]:
    """One row per target: drop (negative: the response rises) against the null draws, with
    empirical one-sided p for a drop and for a rise (+1 smoothing)."""
    n_null = len(null)
    rows = []
    for j, t in enumerate(targets):
        drop = 1 - obs[j] / base[j] if base[j] else np.nan
        null_drop = 1 - null[:, j] / base[j] if base[j] else np.full(n_null, np.nan)
        rows.append(
            {
                "case": case_name,
                "silenced": silenced,
                "n_silenced": n_silenced,
                "target": t,
                "base_hz": base[j],
                "silenced_hz": obs[j],
                "drop": drop,
                "null_drop_mean": float(np.nanmean(null_drop)),
                "null_drop_min": float(np.nanmin(null_drop)),
                "null_drop_max": float(np.nanmax(null_drop)),
                "p_drop": (1 + int((null_drop >= drop).sum())) / (1 + n_null),
                "p_rise": (1 + int((null_drop <= drop).sum())) / (1 + n_null),
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
    checkpoint: Path | None = None,
) -> pd.DataFrame:
    """Silence every neuron of a category (except the stimulus and the targets) and measure
    how much each target's response drops, against silencing as many neurons outside the
    category with the same superclass mix. Empirical one-sided p for a drop and for a rise,
    with +1 smoothing (smallest 1 / (n_null + 1))."""
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)
    ctx = (neurons, W, p, seeds, n_null)
    jobs = [(c, k) for c in cases for k in CATEGORIES]
    meta = {"kind": "silencing", "seeds": seeds, "n_null": n_null, **_param_meta(p)}
    return pd.DataFrame(_map_jobs(_silencing_job, jobs, workers, ctx, checkpoint, meta))


def _param_meta(p: sim.Params) -> dict:
    return {"w_syn": p.w_syn, "th_jump": p.th_jump}


# the predicted feedback loop dPR1 -> dMS9 -> vPR9_a / IN00A038 -> dPR1 (docs/dimorphism.md)
LOOP_SETS = {
    "dMS9": ("dMS9",),
    "inhibitory feedback": ("vPR9_a", "IN00A038"),
    "both": ("dMS9", "vPR9_a", "IN00A038"),
}
LOOP_CASES = ("pIP10 song pathway", "P1 courtship drive")


def _loop_job(job: tuple[str, str]) -> list[dict]:
    (neurons, W, p, seeds, n_null, sets), checkpoint, meta = parallel.context()
    case_name, set_name = job
    case = next(c for c in validate.CASES if c.name == case_name)
    stim = case.stim_idx(neurons)
    targets = np.concatenate([data.resolve(neurons, t) for t in case.targets])
    tested = np.concatenate([data.resolve(neurons, t) for t in sets[set_name]])
    all_tested = np.concatenate(
        [data.resolve(neurons, t) for ts in sets.values() for t in ts]
    )
    results = [
        sim.run(W, stim, validate.RATE_HZ, validate.DURATION_MS, validate.STIM_MS, p, s)
        for s in range(seeds)
    ]
    pool = np.zeros(len(neurons), dtype=bool)
    pool[responders(results, stim)] = True
    pool[np.concatenate([stim, targets, all_tested])] = False
    key = (
        neurons["superclass"].fillna("none").astype(str)
        + "/"
        + neurons["sign"].astype(str)
    ).to_numpy()

    def target_rates(silence):
        out, _ = validate.respond(
            W, neurons, stim, case.targets, p, seeds, silence=silence
        )
        return np.array([out[t]["rate"] for t in case.targets])

    base, obs = target_rates(None), target_rates(tested)
    rng = np.random.default_rng(zlib.crc32(f"loop/{case_name}/{set_name}".encode()))
    null = _null_rates(
        f"{case_name} / {set_name}",
        n_null,
        lambda: _matched_draw(rng, key, pool, tested),
        target_rates,
        _partial(checkpoint, job),
        meta,
    )
    return _rows(case_name, set_name, tested.size, case.targets, base, obs, null)


def loop_silencing(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    p: sim.Params,
    seeds: int = 3,
    n_null: int = 1000,
    workers: int = 4,
    cases=LOOP_CASES,
    sets=LOOP_SETS,
    checkpoint: Path | None = None,
) -> pd.DataFrame:
    """Silence each set of cell types and compare each target's change with silencing as
    many of the case's own responders, matched on superclass and transmitter sign (never the
    stimulus, the targets or any tested neuron): do these neurons matter more than other
    active neurons of the same kind?"""
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)
    ctx = (neurons, W, p, seeds, n_null, sets)
    jobs = [(c, k) for c in cases for k in sets]
    meta = {
        "kind": "loop",
        "seeds": seeds,
        "n_null": n_null,
        "sets": {k: list(v) for k, v in sets.items()},
        **_param_meta(p),
    }
    return pd.DataFrame(_map_jobs(_loop_job, jobs, workers, ctx, checkpoint, meta))


def _type_job(job: tuple[str, str]) -> list[dict]:
    (neurons, W, p, seeds, case_name, base, silenced_by_type), _, _ = parallel.context()
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
    return [row]


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
    ctx = (neurons, W, p, seeds, case_name, base, by_type)
    jobs = [(case_name, t) for t in by_type]
    return pd.DataFrame(_map_jobs(_type_job, jobs, workers, ctx, None, {}))
