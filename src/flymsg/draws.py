"""Matched null draws and checkpointed batches, shared by the silencing tests.

`dimorphism` (T1–T4) and `silence_scan` build their nulls here: a draw matches a set on a
key (superclass, or superclass and sign), each draw's pick is hashed and saved with its
result, and a rerun replays the saved picks before it continues. Names and file layout are
those of v0.8.27, so existing checkpoints resume.
"""

import json
import sys
import time
import zlib
from pathlib import Path

import numpy as np

from flymsg import parallel


class CheckpointMismatch(ValueError):
    """A checkpoint file written with other parameters than the current run."""


def matched_pool_shortfall(key, pool, like) -> list[tuple[str, int, int]]:
    """Groups where `pool` has fewer neurons of that key than `like` requires."""
    groups, counts = np.unique(key[like], return_counts=True)
    short = []
    for g, k in zip(groups, counts, strict=True):
        have = int(np.count_nonzero(pool & (key == g)))
        if have < int(k):
            short.append((str(g), have, int(k)))
    return short


def matched_draw(
    rng, key: np.ndarray, pool: np.ndarray, like: np.ndarray
) -> np.ndarray:
    """As many neurons from `pool` as `like` has, with the same count per `key` value."""
    short = matched_pool_shortfall(key, pool, like)
    if short:
        g, have, need = short[0]
        raise ValueError(f"null pool has {have} neurons of {g!r}, need {need}")
    groups, counts = np.unique(key[like], return_counts=True)
    pick = []
    for g, k in zip(groups, counts, strict=True):
        cand = np.flatnonzero(pool & (key == g))
        pick.append(rng.choice(cand, size=k, replace=False))
    return np.concatenate(pick)


def pick_hash(idx) -> int:
    return zlib.crc32(np.sort(np.asarray(idx, dtype=np.int64)).tobytes())


def partial_path(checkpoint: Path | None, job) -> Path | None:
    """Where a job's null draws are saved while it runs."""
    if checkpoint is None:
        return None
    return checkpoint.with_name(
        f"{checkpoint.name}.{zlib.crc32(repr(tuple(job)).encode()):08x}.partial"
    )


def null_rates(
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
        if pick_hash(pick()) != rec["pick"]:
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
                f.write(json.dumps({"pick": pick_hash(idx), "rates": r}) + "\n")
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


def map_jobs(
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
    an interrupted run resumes (a running job's null draws are saved too, see `null_rates`);
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
            partial_path(checkpoint, job).unlink(missing_ok=True)

    for j, rows in parallel.imap(fn, todo, workers, (ctx, checkpoint, meta)):
        record(j, rows)
    return [r for j in jobs for r in done[tuple(j)]]
