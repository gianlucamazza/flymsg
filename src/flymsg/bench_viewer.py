"""Measure the 3D viewer on the live scenes (issue #24). Usage:

    GL=gl uv run python scripts/bench_viewer.py [--seconds 30] [--max-load 1.0] [SCENE ...]

Builds the site into a temporary directory, serves it on localhost, opens each scene with
`?bench=<seconds>` through scripts/shoot.mjs (a fresh browser profile, then a reload in the same profile for warm-cache coverage) and
appends the page's BENCH summary, with the host, the GL backend and the load average before and
after, to runs/viewer-bench/<UTC time>.jsonl. A baseline needs an idle machine: before each
scene the script waits (up to --cooldown seconds) for the 1-minute load average to fall to
--max-load. The load the benchmark itself makes (its browser decodes millions of triangles)
does not disqualify it: a pass is eligible when the CPU used by every other process during it,
the machine's busy time from /proc/stat minus the CPU of the benchmark's own session sampled
from /proc, averages at most --max-load cores. CPU the sampling misses counts as foreign, so
the error makes a pass ineligible, never eligible. GL=swiftshader is software rendering and is
recorded, but it is not a performance measurement.
"""

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from flymsg import pages
from flymsg.paths import repository_root, require_repository_path

ROOT = repository_root()

# the gallery scenes and the heaviest comparison pages
SCENES = (
    "looming",
    "song",
    "anatomy",
    "looming-bilateral",
    "dnp01-vs-dnp02",
    "right-vs-left",
)


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def bench_line(output: str) -> dict | None:
    """The page's BENCH summary from the shoot.mjs console output."""
    for line in output.splitlines():
        _, sep, rest = line.partition("BENCH ")
        if sep:
            return json.loads(rest)
    return None


def cache_passes(output: str) -> list[dict]:
    return [
        json.loads(line.removeprefix("CACHE_PASS "))
        for line in output.splitlines()
        if line.startswith("CACHE_PASS ")
    ]


TICK = os.sysconf("SC_CLK_TCK")


def busy_ticks(proc_stat: str) -> int:
    """Busy CPU time of the whole machine from /proc/stat: user, nice, system, irq, softirq
    and steal of the aggregate `cpu` line (idle and iowait excluded)."""
    fields = proc_stat.splitlines()[0].split()
    if fields[0] != "cpu":
        raise ValueError("not a /proc/stat aggregate line")
    user, nice, system, _idle, _iowait, irq, softirq, steal = map(int, fields[1:9])
    return user + nice + system + irq + softirq + steal


def session_and_ticks(pid_stat: str) -> tuple[int, int]:
    """Session id and utime + stime of one process from its /proc/<pid>/stat line."""
    rest = pid_stat[pid_stat.rindex(")") + 2 :].split()
    # after the command: state ppid pgrp session ... utime stime (fields 14 and 15)
    return int(rest[3]), int(rest[11]) + int(rest[12])


def session_cpu(session: int) -> dict[int, int]:
    """CPU ticks so far of every live process in `session`."""
    out = {}
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            sid, ticks = session_and_ticks(stat.read_text())
        except (OSError, ValueError, IndexError):
            continue  # gone, or not readable
        if sid == session:
            out[int(stat.parent.name)] = ticks
    return out


def foreign_cores(busy: int, own: int, elapsed_s: float) -> float:
    """Mean cores used by processes outside the benchmark, from ticks over `elapsed_s`."""
    return max(busy - own, 0) / TICK / elapsed_s


def wait_idle(max_load: float, timeout_s: float, step_s: float = 10.0) -> bool:
    """Wait until the 1-minute load average is at most `max_load`; False on timeout."""
    deadline = time.monotonic() + timeout_s
    while os.getloadavg()[0] > max_load:
        if time.monotonic() >= deadline:
            return False
        time.sleep(step_s)
    return True


def shoot(
    args: list[str], timeout: float, env: dict | None = None
) -> tuple[str, str | None, float | None]:
    """Run shoot.mjs in its own session, so a timeout also ends its browser. Returns the
    output, an error or None, and the mean cores used outside that session meanwhile."""
    busy0, t0 = busy_ticks(Path("/proc/stat").read_text()), time.monotonic()
    proc = subprocess.Popen(
        ["node", str(require_repository_path(ROOT) / "scripts" / "shoot.mjs"), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env=env,
    )
    # cumulative CPU per process of the session, kept at its last sampled value after exit
    own: dict[int, int] = {}
    done = threading.Event()

    def sample():
        while not done.is_set():
            own.update(session_cpu(proc.pid))
            done.wait(0.5)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        out, error = proc.communicate(timeout=timeout)[0], None
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        done.set()
        sampler.join()
        return proc.communicate()[0], f"timeout after {timeout:.0f} s", None
    if proc.returncode:
        error = f"shoot.mjs exited with {proc.returncode}"
    own.update(session_cpu(proc.pid))  # survivors' last ticks
    done.set()
    sampler.join()
    foreign = foreign_cores(
        busy_ticks(Path("/proc/stat").read_text()) - busy0,
        sum(own.values()),
        time.monotonic() - t0,
    )
    try:  # a failed shoot.mjs can leave its browser behind
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return out, error, foreign


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*", default=SCENES)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--max-load", type=float, default=1.0)
    ap.add_argument(
        "--cooldown",
        type=float,
        default=600.0,
        help="seconds to wait for the load to settle before each scene",
    )
    ap.add_argument(
        "--viewport",
        nargs=2,
        type=int,
        default=[1400, 900],
        metavar=("WIDTH", "HEIGHT"),
    )
    ap.add_argument(
        "--mobile-emulation",
        action="store_true",
        help="desktop browser emulation, not a physical mobile result",
    )
    a = ap.parse_args()
    if a.seconds <= 0 or min(a.viewport) <= 0 or a.max_load <= 0:
        ap.error("duration, viewport and load bound must be positive")
    if not wait_idle(a.max_load, a.cooldown):
        sys.exit(
            f"load average {os.getloadavg()[0]:.1f} > {a.max_load} after "
            f"{a.cooldown:.0f} s: not an idle machine"
        )
    gl = os.environ.get("GL", "swiftshader")
    out = require_repository_path(ROOT) / "runs" / "viewer-bench"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl"
    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp) / "site"
        pages.build(site)
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(Quiet, directory=str(site))
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for scene in a.scenes:
            if not wait_idle(a.max_load, a.cooldown):
                sys.exit(
                    f"load average {os.getloadavg()[0]:.1f} > {a.max_load} after "
                    f"{a.cooldown:.0f} s: interrupted before {scene}"
                )
            load_before = os.getloadavg()
            url = f"http://127.0.0.1:{port}/live/{scene}/?bench={a.seconds}"
            stdout, error, foreign = shoot(
                [
                    url,
                    str(Path(tmp) / f"{scene}.png"),
                    str(a.seconds + 5),
                    *map(str, a.viewport),
                ],
                2 * (a.seconds * 10 + 120),
                {
                    **os.environ,
                    "BENCH_WARM": "1",
                    "MOBILE": "1" if a.mobile_emulation else "0",
                },
            )
            passes = cache_passes(stdout)
            for cache in ("cold", "warm"):
                measured = next((p for p in passes if p["cache"] == cache), {})
                rec = {
                    "scene": scene,
                    "gl": gl,
                    "seconds": a.seconds,
                    "cache": cache,
                    "viewport": a.viewport,
                    "device_kind": "emulated-mobile"
                    if a.mobile_emulation
                    else "desktop",
                    "commit": commit,
                    "host": platform.node(),
                    "cpu_count": os.cpu_count(),
                    "load_before": measured.get("load_before", load_before),
                    "load_after": measured.get("load_after", os.getloadavg()),
                    # both passes run in one browser session: the same measurement
                    "foreign_cores": None if foreign is None else round(foreign, 3),
                    "bench": measured.get("bench"),
                    "network": measured.get("network"),
                    "gpu": measured.get("gpu"),
                    "error": error,
                }
                if rec["bench"] is None and rec["error"] is None:
                    rec["error"] = "no BENCH summary (page failed to load or run)"
                renderer = str((rec["gpu"] or {}).get("renderer", "")).lower()
                hardware = bool(renderer) and not any(
                    s in renderer
                    for s in (
                        "swiftshader",
                        "llvmpipe",
                        "softpipe",
                        "software",
                        "warp",
                        "basic render",
                        "webkit webgl",
                    )
                )
                rec["eligible"] = (
                    hardware
                    and rec["error"] is None
                    and gl in {"gl", "vulkan"}
                    and load_before[0] <= a.max_load
                    and foreign is not None
                    and foreign <= a.max_load
                )
                with path.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
                b = rec["bench"] or {}
                print(
                    f"{scene} {cache}: eligible {rec['eligible']}, fps p50 "
                    f"{b.get('fps', {}).get('p50')}, other processes {rec['foreign_cores']} cores"
                )
        server.shutdown()
    print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
