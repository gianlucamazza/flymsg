"""Measure the 3D viewer on the live scenes (issue #24). Usage:

    GL=gl uv run python scripts/bench_viewer.py [--seconds 30] [--max-load 1.0] [SCENE ...]

Builds the site into a temporary directory, serves it on localhost, opens each scene with
`?bench=<seconds>` through scripts/shoot.mjs (a fresh browser profile, then a reload in the same profile for warm-cache coverage) and
appends the page's BENCH summary, with the host, the GL backend and the load average before and
after, to runs/viewer-bench/<UTC time>.jsonl. A baseline needs an idle machine: the script
refuses to start when the 1-minute load average is above --max-load. GL=swiftshader is
software rendering and is recorded, but it is not a performance measurement.
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
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from flymsg import pages

ROOT = Path(__file__).resolve().parents[1]

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


def shoot(
    args: list[str], timeout: float, env: dict | None = None
) -> tuple[str, str | None]:
    """Run shoot.mjs in its own process group, so a timeout also ends its browser."""
    proc = subprocess.Popen(
        ["node", str(ROOT / "scripts" / "shoot.mjs"), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env=env,
    )
    try:
        out, error = proc.communicate(timeout=timeout)[0], None
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        return proc.communicate()[0], f"timeout after {timeout:.0f} s"
    if proc.returncode:
        error = f"shoot.mjs exited with {proc.returncode}"
    try:  # a failed shoot.mjs can leave its browser behind
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return out, error


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*", default=SCENES)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--max-load", type=float, default=1.0)
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
    load0 = os.getloadavg()
    if load0[0] > a.max_load:
        sys.exit(f"load average {load0[0]:.1f} > {a.max_load}: not an idle machine")
    gl = os.environ.get("GL", "swiftshader")
    out = ROOT / "runs" / "viewer-bench"
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
            load_before = os.getloadavg()
            url = f"http://127.0.0.1:{port}/live/{scene}/?bench={a.seconds}"
            if load_before[0] > a.max_load:
                sys.exit(
                    f"load average {load_before[0]:.1f} > {a.max_load}: interrupted before {scene}"
                )
            stdout, error = shoot(
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
                    and max(rec["load_before"][0], rec["load_after"][0]) <= a.max_load
                )
                with path.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
                b = rec["bench"] or {}
                print(
                    f"{scene} {cache}: eligible {rec['eligible']}, fps p50 {b.get('fps', {}).get('p50')}"
                )
        server.shutdown()
    print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
