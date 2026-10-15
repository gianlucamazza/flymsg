import os

from flymsg import parallel


def _job(j):
    return parallel.context()["base"] + j, os.getpid()


def test_workers_receive_the_context_and_run_in_other_processes():
    out = dict(parallel.imap(_job, [1, 2, 3, 4], 2, {"base": 10}))
    assert {j: v for j, (v, _) in out.items()} == {1: 11, 2: 12, 3: 13, 4: 14}
    assert os.getpid() not in {pid for _, pid in out.values()}


def test_serial_path_runs_here_with_the_same_context():
    out = dict(parallel.imap(_job, [1], 4, {"base": 0}))
    assert out[1] == (1, os.getpid())


def _lane_job(j):
    import time

    ctx = parallel.context()
    time.sleep(0.05)
    if ctx.get("fail") == j:
        raise RuntimeError(f"lane failed on {j}")
    return ctx["name"], os.getpid()


def test_a_shared_queue_feeds_the_workers_and_a_lane_here():
    jobs = list(range(12))
    out = dict(
        parallel.imap_shared(_lane_job, jobs, 2, {"name": "cpu"}, {"name": "lane"})
    )
    assert sorted(out) == jobs  # every job once
    names = {name for name, _ in out.values()}
    assert names == {"cpu", "lane"}  # both took work
    here = {pid for name, pid in out.values() if name == "lane"}
    assert here == {os.getpid()}


def test_a_failing_lane_stops_the_batch():
    import pytest

    with pytest.raises(RuntimeError, match="lane failed"):
        list(
            parallel.imap_shared(
                _lane_job,
                list(range(8)),
                1,
                {"name": "cpu"},
                {"name": "lane", "fail": 0},
            )
        )


def test_map_jobs_records_a_shared_run_like_any_other(tmp_path):
    from flymsg import draws

    rows = draws.map_jobs(
        _rows,
        [(k,) for k in range(6)],
        2,
        {"name": "cpu"},
        tmp_path / "ck.jsonl",
        {"v": 1},
        lane_ctx={"name": "lane"},
    )
    assert [r["k"] for r in rows] == list(range(6))  # in the order of the jobs
    again = draws.map_jobs(
        _rows,
        [(k,) for k in range(6)],
        2,
        {"name": "cpu"},
        tmp_path / "ck.jsonl",
        {"v": 1},
    )
    assert again == rows  # resumed from the checkpoint whatever lane ran them


def _rows(job):
    ctx, _checkpoint, _meta = parallel.context()
    return [{"k": job[0], "lane": ctx["name"]}]
