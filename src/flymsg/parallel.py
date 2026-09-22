"""Process pool for long simulation batches.

Workers start from a forkserver, not by forking the caller: after loading the tables the
caller holds pyarrow's thread pools, and forking a multi-threaded process can deadlock the
child. Each worker receives the shared job context (tables, weight matrix, parameters) once,
through the pool initializer, and reads it with `context()`.
"""

import multiprocessing as mp
from collections.abc import Callable, Iterator

_context = None


def _init(ctx) -> None:
    global _context
    _context = ctx


def context():
    """The job context of the current batch (in a worker or in the serial path)."""
    return _context


def _tagged(fn_job):
    fn, job = fn_job
    return job, fn(job)


def imap(fn: Callable, jobs: list, workers: int, ctx) -> Iterator[tuple]:
    """Yield (job, fn(job)) as each job finishes, in up to `workers` processes; serially in
    this process when workers <= 1 or there is a single job. `fn` must be a module-level
    function."""
    if workers <= 1 or len(jobs) <= 1:
        _init(ctx)
        for j in jobs:
            yield j, fn(j)
        return
    pool = mp.get_context("forkserver").Pool(
        min(workers, len(jobs)), initializer=_init, initargs=(ctx,)
    )
    with pool:
        yield from pool.imap_unordered(_tagged, [(fn, j) for j in jobs])
