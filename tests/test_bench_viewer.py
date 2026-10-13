"""The viewer benchmark judges a pass by the CPU other processes used, not by the load its own
browser makes (issue #24)."""

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "bench_viewer", ROOT / "scripts" / "bench_viewer.py"
)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_proc_lines_are_parsed():
    stat = "cpu  100 5 50 9000 30 7 3 2 0 0\ncpu0 1 2 3 4 5 6 7 8 0 0\n"
    assert bench.busy_ticks(stat) == 100 + 5 + 50 + 7 + 3 + 2
    # a command with spaces and parentheses; session is field 6, utime/stime 14/15
    line = "4242 (Web Content (x)) S 1 4242 4200 0 -1 0 0 0 0 0 31 9 0 0 20 0 1 0 0"
    assert bench.session_and_ticks(line) == (4200, 40)


def test_foreign_cores_subtracts_the_benchmark_and_never_goes_negative():
    tick = bench.TICK
    assert bench.foreign_cores(busy=3 * tick * 10, own=2 * tick * 10, elapsed_s=10) == 1
    assert bench.foreign_cores(busy=tick, own=2 * tick, elapsed_s=1) == 0


def test_a_busy_process_in_the_session_counts_as_own():
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time\nt=time.time()\nwhile time.time()-t<30: pass",
        ],
        start_new_session=True,
    )
    # poll: a loaded host may give the child CPU slowly
    deadline, own = time.monotonic() + 20, {}
    try:
        while time.monotonic() < deadline:
            own = bench.session_cpu(child.pid)
            if sum(own.values()) >= 0.2 * bench.TICK:
                break
            time.sleep(0.1)
    finally:
        child.kill()
        child.wait()
    assert own and sum(own.values()) >= 0.2 * bench.TICK
    assert os.getpid() not in own
