"""Matched null draws and checkpointed batches, shared by the silencing tests.

`dimorphism` (T1–T4) and `silence_scan` build their nulls here: a draw matches a set on a
key (superclass, or superclass and sign), each draw's pick is hashed and saved with its
result, and a rerun replays the saved picks before it continues. Names and file layout are
those of v0.8.27; new records are checksummed. Legacy records remain readable for
progress inspection but cannot be resumed as newly verified scientific computation.
"""

import hashlib
import inspect
import json
import os
import sys
import time
import zlib
from functools import wraps
from pathlib import Path

import numpy as np

from flymsg import parallel, runstore


class CheckpointMismatch(ValueError):
    """A checkpoint file written with other parameters than the current run."""


def _exclusive(argument):
    def decorate(fn):
        signature = inspect.signature(fn)

        @wraps(fn)
        def run(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            path = bound.arguments[argument]
            if path is None:
                return fn(*args, **kwargs)
            path.parent.mkdir(parents=True, exist_ok=True)
            with runstore.writer_lock(path.with_name(path.name + ".data-writer.lock")):
                return fn(*args, **kwargs)

        return run

    return decorate


def _record_hash(payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=float
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_checked(stream, payload):
    record = {
        "_record_schema": "flymsg.draw-record/v1",
        **payload,
        "_record_sha256": _record_hash(payload),
    }
    stream.write(json.dumps(record, default=float) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _read_checked(path):
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    fragment = lines.pop() if lines and not lines[-1].endswith(b"\n") else b""
    records = []
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
            schema = record.pop("_record_schema", None)
            checksum = record.pop("_record_sha256", None)
        except (ValueError, AttributeError) as exc:
            raise CheckpointMismatch(
                f"checkpoint integrity mismatch at record {index}: {path}"
            ) from exc
        if schema != "flymsg.draw-record/v1":
            raise CheckpointMismatch(
                f"legacy checkpoint cannot be resumed with verified semantics: {path}"
            )
        if checksum != _record_hash(record):
            raise CheckpointMismatch(
                f"checkpoint integrity mismatch at record {index}: {path}"
            )
        records.append(record)
    if fragment:
        header = b'{"_record_schema": "flymsg.draw-record/v1"'
        # A kill during the first write leaves a prefix of that header. It is this
        # format's torn record, so it is discarded. Anything else is not resumed.
        if not records and not (
            fragment.startswith(header) or header.startswith(fragment)
        ):
            raise CheckpointMismatch(
                f"unidentified legacy/incomplete checkpoint: {path}"
            )
        with path.open("r+b") as stream:
            stream.truncate(sum(map(len, lines)))
            stream.flush()
            os.fsync(stream.fileno())
    return records


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


@_exclusive("partial")
def null_rates(
    label: str, n_null: int, pick, rates, partial: Path | None = None, meta=None
) -> np.ndarray:
    """`rates(pick())` n_null times, reporting progress and a measured ETA on stderr about
    every 10 % (null runs take hours on the full CNS). With `partial`, every draw is
    appended to that file as it finishes; a rerun replays the saved draws (`pick()` only,
    to advance the generator, checked against the saved hash of each pick) and continues."""
    saved = []
    if partial and partial.exists():
        records = _read_checked(partial)
        if records and records[0] != meta:
            raise CheckpointMismatch(f"{partial} was written with other parameters")
        saved = records[1:]
    out = []
    for i, rec in enumerate(saved[:n_null]):
        if pick_hash(pick()) != rec["pick"]:
            raise CheckpointMismatch(f"{partial}: draw {i} is not the one saved")
        out.append(rec["rates"])
    f = None
    if partial:
        f = partial.open("a")
        if not partial.stat().st_size:
            _write_checked(f, meta)
    t0, start = time.monotonic(), len(out)
    step = max(1, n_null // 10)
    try:
        for i in range(start + 1, n_null + 1):
            idx = pick()
            r = [float(x) for x in rates(idx)]
            out.append(r)
            if f:
                _write_checked(f, {"pick": pick_hash(idx), "rates": r})
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


@_exclusive("checkpoint")
def map_jobs(
    fn,
    jobs: list,
    workers: int,
    ctx,
    checkpoint: Path | None,
    meta: dict,
    first=(),
    lane_ctx=None,
):
    """Run `fn` over `jobs` (each returns a list of rows) with job context `ctx`, in worker
    processes if workers > 1, collecting results as they finish. With `checkpoint`, every
    finished job is appended to that JSON-lines file and jobs already there are skipped, so
    an interrupted run resumes (a running job's null draws are saved too, see `null_rates`);
    a checkpoint written with other parameters is refused. Jobs in `first` are submitted
    before the others (the confirmatory tests, so that an interrupted run has them);
    rows come back in the order of `jobs`. With `lane_ctx`, a lane in this process takes
    jobs from the same queue as the workers, with that context (another backend)."""
    done: dict[tuple, list] = {}
    if checkpoint and checkpoint.exists():
        for rec in _read_checked(checkpoint):
            if rec["meta"] != meta:
                raise CheckpointMismatch(
                    f"{checkpoint} was written with {rec['meta']}, not {meta}"
                )
            done[tuple(rec["job"])] = rec["rows"]
    runstore.record_work("resumed_jobs", [list(j) for j in done])
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
        runstore.record_work("computed_jobs", [list(job)])
        print(f"job {len(done)}/{len(jobs)} done: {job}", file=sys.stderr, flush=True)
        if checkpoint:
            rec = {
                "meta": meta,
                "job": list(job),
                "rows": rows,
                "producer_attempt": runstore.producer_attempt(),
            }
            with checkpoint.open("a") as f:
                _write_checked(f, rec)
            partial_path(checkpoint, job).unlink(missing_ok=True)

    batches = (
        parallel.imap(fn, todo, workers, (ctx, checkpoint, meta))
        if lane_ctx is None
        else parallel.imap_shared(
            fn, todo, workers, (ctx, checkpoint, meta), (lane_ctx, checkpoint, meta)
        )
    )
    for j, rows in batches:
        record(j, rows)
    return [r for j in jobs for r in done[tuple(j)]]
