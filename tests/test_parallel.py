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
