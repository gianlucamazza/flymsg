"""Process pool for long simulation batches.

Workers start from a forkserver, not by forking the caller: after loading the tables the
caller holds pyarrow's thread pools, and forking a multi-threaded process can deadlock the
child. Each worker receives the shared job context (tables, weight matrix, parameters) once,
through the pool initializer, and reads it with `context()`.
"""

import multiprocessing as mp
import queue
import threading
from collections import deque
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

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


def _lane_job(fn_job):
    fn, job, ctx = fn_job
    _init(ctx)  # the lane's thread shares this process's context slot
    return job, fn(job)


def imap_shared(
    fn: Callable, jobs: list, workers: int, ctx, lane_ctx
) -> Iterator[tuple]:
    """Yield (job, fn(job)) as jobs finish, from one shared queue served by up to
    `workers` processes with context `ctx` and by a lane in this process with context
    `lane_ctx` (another backend, such as the console). Each takes its next job only when
    it is free, so the faster one runs more. A failure in either stops the batch."""
    todo, lock, finished = deque(jobs), threading.Lock(), queue.Queue()

    def take():
        with lock:
            return todo.popleft() if todo else None

    pool = mp.get_context("forkserver").Pool(
        max(1, workers), initializer=_init, initargs=(ctx,)
    )
    lane = ThreadPoolExecutor(1)

    def to_pool():
        job = take()
        if job is not None:
            pool.apply_async(
                _tagged,
                ((fn, job),),
                callback=lambda r: (finished.put((r, None)), to_pool()),
                error_callback=lambda exc: finished.put((None, exc)),
            )

    def to_lane():
        job = take()
        if job is not None:
            lane.submit(_lane_job, (fn, job, lane_ctx)).add_done_callback(done_lane)

    def done_lane(future):
        exc = future.exception()
        finished.put((None if exc else future.result(), exc))
        if exc is None:
            to_lane()

    with pool, lane:
        to_lane()
        for _ in range(max(1, workers)):
            to_pool()
        for _ in range(len(jobs)):
            result, exc = finished.get()
            if exc is not None:
                with lock:
                    todo.clear()  # nothing new starts
                raise exc
            yield result
