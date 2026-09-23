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


def _category(name: str):
    """The category test; a KeyError listing the categories if the name is unknown."""
    try:
        return CATEGORIES[name]
    except KeyError:
        raise KeyError(
            f"unknown category {name!r}; categories: {', '.join(CATEGORIES)}"
        ) from None


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
    W = sim.network(neurons, edges, p)
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
# pre-registered confirmatory tests (docs/dimorphism.md, T1); the rest is descriptive
T1_CONFIRMATORY = [
    (c, k)
    for c in ("P1 courtship drive", "pIP10 song pathway")
    for k in ("fru/dsx+", "dimorphic")
]


def _case_rates(W, neurons, case, stim, p, seeds):
    """A function giving the targets' rates (and, on request, their per-seed rates) under a
    silencing. Runs stop at the end of the stimulus: the rates there are identical to those
    of the full protocol run (docs/dimorphism.md)."""

    def rates(silence=None, per_seed: bool = False):
        out, _ = validate.respond(
            W,
            neurons,
            stim,
            case.targets,
            p,
            seeds,
            silence=silence,
            duration_ms=validate.STIM_MS,
        )
        mean = np.array([out[t]["rate"] for t in case.targets])
        if not per_seed:
            return mean
        return mean, np.array([out[t]["seed_rates"] for t in case.targets])

    return rates


def _category_draw(neurons, case, which, keep_on, *_):
    """What a category test silences and what its null draws from: every neuron of the
    category (except stimulus and targets), against as many neurons outside it with the same
    superclass mix."""
    flag = _category(which)(neurons).to_numpy() & ~keep_on
    key = neurons["superclass"].fillna("none").to_numpy()
    return np.flatnonzero(flag), key, ~keep_on & ~flag, f"{case.name}/{which}"


def _set_draw(neurons, case, which, keep_on, sets, W, p, seeds, stim):
    """What a cell-type test silences and what its null draws from: the named types, against
    as many of the case's own responders matched on superclass and transmitter sign. Drawing
    from responders asks whether these neurons matter more than other active neurons of the
    same kind, not whether silencing active neurons does anything."""
    tested = np.concatenate([data.resolve(neurons, t) for t in sets[which]])
    all_tested = np.concatenate(
        [data.resolve(neurons, t) for ts in sets.values() for t in ts]
    )
    results = [  # responders read the stimulus window only
        sim.run(W, stim, validate.RATE_HZ, validate.STIM_MS, validate.STIM_MS, p, s)
        for s in range(seeds)
    ]
    pool = np.zeros(len(neurons), dtype=bool)
    pool[responders(results, stim)] = True
    pool[np.concatenate([np.flatnonzero(keep_on), all_tested])] = False
    key = (
        neurons["superclass"].fillna("none").astype(str)
        + "/"
        + neurons["sign"].astype(str)
    ).to_numpy()
    return tested, key, pool, f"loop/{case.name}/{which}"


def _job(job: tuple[str, str]) -> list[dict]:
    """One silencing test: silence a category (`sets` is None) or a named set of cell types,
    then compare each target's change with `n_null` matched random silencings."""
    (neurons, W, p, seeds, n_null, sets), checkpoint, meta = parallel.context()
    case_name, which = job
    case = validate.case_by_name(case_name)
    stim = case.stim_idx(neurons)
    keep_on = np.zeros(len(neurons), dtype=bool)
    keep_on[np.concatenate([stim, case.target_idx(neurons)])] = True
    rates = _case_rates(W, neurons, case, stim, p, seeds)
    silenced, key, pool, label = (
        _category_draw(neurons, case, which, keep_on)
        if sets is None
        else _set_draw(neurons, case, which, keep_on, sets, W, p, seeds, stim)
    )
    base, base_seeds = rates(per_seed=True)
    if not silenced.size:  # nothing of this category outside stimulus and targets
        return _rows(case_name, which, 0, case.targets, base, base, np.empty((0, 0)),
                     base_seeds, base_seeds)  # fmt: skip
    obs, obs_seeds = rates(silenced, per_seed=True)
    rng = np.random.default_rng(zlib.crc32(label.encode()))  # stable across runs
    null = _null_rates(
        f"{case_name} / {which}",
        n_null,
        lambda: _matched_draw(rng, key, pool, silenced),
        rates,
        _partial(checkpoint, job),
        meta,
    )
    return _rows(
        case_name, which, silenced.size, case.targets, base, obs, null,
        base_seeds, obs_seeds,
    )  # fmt: skip


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


def progress(checkpoint: Path) -> pd.DataFrame:
    """How far a checkpointed silencing run has got: one row per job with the null draws it
    has (finished jobs from the checkpoint, started ones from their `.partial` files; a
    started job is not necessarily running now).
    Read-only, so it can be called while the run continues."""
    meta = None
    if checkpoint.exists():
        lines = checkpoint.read_text().splitlines()
        if lines:
            meta = json.loads(lines[0])["meta"]
    parts = sorted(checkpoint.parent.glob(f"{checkpoint.name}.*.partial"))
    if meta is None and parts:
        meta = json.loads(parts[0].read_text().splitlines()[0])
    if meta is None:
        raise OSError(f"no checkpoint or partial file for {checkpoint}")
    if meta["kind"] == "by-type":
        jobs, first = [tuple(j) for j in meta["jobs"]], []
    elif meta["kind"] == "loop":
        jobs = [(c, k) for c in LOOP_CASES for k in meta["sets"]]
        first = confirmatory_jobs(meta["sets"])
    else:
        jobs = [(c, k) for c in SILENCING_CASES for k in CATEGORIES]
        first = T1_CONFIRMATORY
    n_null = meta.get("n_null", 0)  # a by-type scan has no null draws
    done = set()
    if checkpoint.exists():
        done = {
            tuple(json.loads(line)["job"])
            for line in checkpoint.read_text().splitlines()
        }
    rows = []
    for job in jobs:
        part = _partial(checkpoint, job)
        if tuple(job) in done:
            draws, state = n_null, "done"
        elif part.exists():
            draws, state = max(0, len(part.read_text().splitlines()) - 1), "started"
        else:
            draws, state = 0, "waiting"
        rows.append(
            {
                "case": job[0],
                "silenced": job[1],
                "confirmatory": tuple(job) in {tuple(j) for j in first},
                "draws": draws,
                "of": n_null,
                "state": state,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["confirmatory", "draws"], ascending=[False, False]
    )


class CheckpointMismatch(ValueError):
    """A checkpoint file written with other parameters than the current run."""


def _map_jobs(
    fn,
    jobs: list,
    workers: int,
    ctx,
    checkpoint: Path | None,
    meta: dict,
    first=(),
):
    """Run `fn` over `jobs` (each returns a list of rows) with job context `ctx`, in worker
    processes if workers > 1, collecting results as they finish. With `checkpoint`, every
    finished job is appended to that JSON-lines file and jobs already there are skipped, so
    an interrupted run resumes (a running job's null draws are saved too, see `_null_rates`);
    a checkpoint written with other parameters is refused. Jobs in `first` are submitted
    before the others (the confirmatory tests, so that an interrupted run has them);
    rows come back in the order of `jobs`."""
    done: dict[tuple, list] = {}
    if checkpoint and checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            rec = json.loads(line)
            if rec["meta"] != meta:
                raise CheckpointMismatch(
                    f"{checkpoint} was written with {rec['meta']}, not {meta}"
                )
            done[tuple(rec["job"])] = rec["rows"]
    first = {tuple(j) for j in first}
    todo = sorted(
        (j for j in jobs if tuple(j) not in done), key=lambda j: tuple(j) not in first
    )
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


def _rows(
    case_name, silenced, n_silenced, targets, base, obs, null, base_seeds, obs_seeds
) -> list[dict]:
    """One row per target: drop (negative: the response rises) against the null draws, with
    empirical one-sided p for a drop and for a rise (+1 smoothing). The per-seed rates are
    kept so that two silencings can later be compared with a bootstrap."""
    n_null = len(null)
    rows = []
    for j, t in enumerate(targets):
        # with a silent target there is nothing to drop, and a scan without null draws has
        # nothing to compare against: those rows carry NaN rather than a computed number
        drop = 1 - obs[j] / base[j] if base[j] else np.nan
        null_drop = 1 - null[:, j] / base[j] if (n_null and base[j]) else None
        stats = (
            {
                "null_drop_mean": float(null_drop.mean()),
                "null_drop_min": float(null_drop.min()),
                "null_drop_max": float(null_drop.max()),
                "p_drop": (1 + int((null_drop >= drop).sum())) / (1 + n_null),
                "p_rise": (1 + int((null_drop <= drop).sum())) / (1 + n_null),
            }
            if null_drop is not None
            else dict.fromkeys(
                (
                    "null_drop_mean",
                    "null_drop_min",
                    "null_drop_max",
                    "p_drop",
                    "p_rise",
                ),
                np.nan,
            )
        )
        rows.append(
            {
                "case": case_name,
                "silenced": silenced,
                "n_silenced": n_silenced,
                "target": t,
                "base_hz": base[j],
                "silenced_hz": obs[j],
                "drop": drop,
                **stats,
                "base_seed_hz": [float(x) for x in base_seeds[j]],
                "silenced_seed_hz": [float(x) for x in obs_seeds[j]],
            }
        )
    return rows


def silencing(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    p: sim.Params,
    seeds: int = 3,
    n_null: int = 1000,
    workers: int = 4,
    cases=SILENCING_CASES,
    checkpoint: Path | None = None,
) -> pd.DataFrame:
    """Silence every neuron of a category (except the stimulus and the targets) and measure
    how much each target's response drops, against silencing as many neurons outside the
    category with the same superclass mix. Empirical one-sided p for a drop and for a rise,
    with +1 smoothing (smallest 1 / (n_null + 1))."""
    W = sim.network(neurons, edges, p)
    ctx = (neurons, W, p, seeds, n_null, None)
    jobs = [(c, k) for c in cases for k in CATEGORIES]
    meta = {"kind": "silencing", "seeds": seeds, "n_null": n_null, **_param_meta(p)}
    rows = _map_jobs(_job, jobs, workers, ctx, checkpoint, meta, T1_CONFIRMATORY)
    return pd.DataFrame(rows)


def _param_meta(p: sim.Params) -> dict:
    return {"w_syn": p.w_syn, "th_jump": p.th_jump}


# the predicted feedback loop dPR1 -> dMS9 -> vPR9_a / IN00A038 -> dPR1 (docs/dimorphism.md)
LOOP_CASES = ("pIP10 song pathway", "P1 courtship drive")
# T2 (v0.5's predicted loop dPR1 -> dMS9 -> vPR9_a / IN00A038 -> dPR1) and T3 (the route the
# T2 result pointed to, dMS9 -> vMS12 -> IN03B024 -> dPR1). Both are pre-registered in
# docs/dimorphism.md; the sets not named as confirmatory there are descriptive.
LOOP_SETS = {
    "dMS9": ("dMS9",),
    "inhibitory feedback": ("vPR9_a", "IN00A038"),
    "both": ("dMS9", "vPR9_a", "IN00A038"),
}
T3_SETS = {
    "IN03B024": ("IN03B024",),
    "vMS12": ("vMS12_a", "vMS12_b", "vMS12_c"),
    "dMS9 + IN03B024": ("dMS9", "IN03B024"),
}
LOOP_PRESETS = {"t2": LOOP_SETS, "t3": T3_SETS}
CONFIRMATORY_SETS = {"t2": ("dMS9", "inhibitory feedback"), "t3": ("IN03B024", "vMS12")}


def confirmatory_jobs(sets: dict) -> list[tuple[str, str]]:
    """The pre-registered confirmatory (case, set) pairs of whichever preset `sets` is; an
    unknown set of sets has none, and every job is then treated alike."""
    for preset, names in CONFIRMATORY_SETS.items():
        if set(sets) == set(LOOP_PRESETS[preset]):
            return [(c, k) for c in LOOP_CASES for k in names]
    return []


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
    W = sim.network(neurons, edges, p)
    ctx = (neurons, W, p, seeds, n_null, sets)
    jobs = [(c, k) for c in cases for k in sets]
    meta = {
        "kind": "loop",
        "seeds": seeds,
        "n_null": n_null,
        "sets": {k: list(v) for k, v in sets.items()},
        **_param_meta(p),
    }
    rows = _map_jobs(
        _job, jobs, workers, ctx, checkpoint, meta, confirmatory_jobs(sets)
    )
    return pd.DataFrame(rows)


def _type_job(job: tuple[str, str]) -> list[dict]:
    (neurons, W, p, seeds, case_name, base, silenced_by_type), _, _ = parallel.context()
    t = job[1]
    case = validate.case_by_name(case_name)
    out, _ = validate.respond(
        W,
        neurons,
        case.stim_idx(neurons),
        case.targets,
        p,
        seeds,
        silence=silenced_by_type[t],
        duration_ms=validate.STIM_MS,
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
    checkpoint: Path | None = None,
) -> pd.DataFrame:
    """Silence, one cell type at a time, the responders of `case_name` that belong to
    `category`, and report each target's drop (negative: the response rises). Only types
    that fire in the case are tried, since silencing a silent type changes nothing."""
    case = validate.case_by_name(case_name)
    stim = case.stim_idx(neurons)
    targets = case.target_idx(neurons)
    W = sim.network(neurons, edges, p)
    results = [
        sim.run(W, stim, validate.RATE_HZ, validate.STIM_MS, validate.STIM_MS, p, s)
        for s in range(seeds)
    ]
    resp = np.setdiff1d(responders(results, stim), targets)
    resp = resp[_category(category)(neurons).to_numpy()[resp]]
    types = neurons["type"].fillna(neurons["bodyId"].astype(str)).to_numpy()
    by_type = {t: resp[types[resp] == t] for t in np.unique(types[resp])}
    base_out, _ = validate.respond(
        W, neurons, stim, case.targets, p, seeds, duration_ms=validate.STIM_MS
    )
    base = np.array([base_out[t]["rate"] for t in case.targets])
    ctx = (neurons, W, p, seeds, case_name, base, by_type)
    jobs = [(case_name, t) for t in by_type]
    # `jobs` goes into the meta because the types come from the run itself: `progress` has
    # no other way to name them. The other kinds keep their meta as it is, so that runs
    # started before this can still resume.
    meta = {
        "kind": "by-type",
        "seeds": seeds,
        "category": category,
        "jobs": [list(j) for j in jobs],
        **_param_meta(p),
    }
    return pd.DataFrame(_map_jobs(_type_job, jobs, workers, ctx, checkpoint, meta))
