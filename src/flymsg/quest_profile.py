"""Read-only, bounded Quest GPU/process sampling; never adjusts device settings.

Run alongside the viewer's interval collector. Samples do not imply visible-page
or XR qualification. gpubusy is retained verbatim: its driver reset semantics are
not assumed to be cumulative or comparable to frame time.
"""

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from flymsg import manifest, runstore


def read(serial, *args):
    try:
        return subprocess.check_output(
            ["adb", "-s", serial, *args], text=True, stderr=subprocess.PIPE, timeout=10
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return {"unavailable": str(exc)}


def sample(serial):
    started = time.monotonic()
    processes = read(serial, "shell", "ps", "-A", "-o", "PID,NAME")
    memory = {}
    if isinstance(processes, str):
        for line in processes.splitlines()[1:]:
            fields = line.split(maxsplit=1)
            if len(fields) != 2 or not fields[0].isdigit():
                continue
            pid, name = fields
            if name == "com.oculus.browser" or name.startswith("com.oculus.browser:"):
                memory[pid] = {
                    "name": name,
                    "status": read(serial, "shell", "cat", f"/proc/{pid}/status"),
                }
    return {
        "at": datetime.now(UTC).isoformat(),
        "processes": processes,
        "browser_processes": memory,
        "gpu_busy_raw": read(
            serial, "shell", "cat", "/sys/class/kgsl/kgsl-3d0/gpubusy"
        ),
        "gpu_clock_hz": read(serial, "shell", "cat", "/sys/class/kgsl/kgsl-3d0/gpuclk"),
        "thermal": read(serial, "shell", "dumpsys", "thermalservice"),
        "sample_wall_s": time.monotonic() - started,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300 or not 1 <= args.interval <= 30:
        parser.error("seconds must be 1..300 and interval 1..30")
    if read(args.serial, "shell", "getprop", "ro.product.model") != "Quest 2":
        parser.error("explicit serial must identify Quest 2")
    args.out.mkdir(parents=True, exist_ok=False)
    runstore.atomic_json(
        args.out / "profile.json",
        {
            "schema": "flymsg.quest-profile/v1",
            "source": manifest.git_info(),
            "serial": args.serial,
            "seconds": args.seconds,
            "interval_s": args.interval,
            "qualification": "not-scored; correlate with visible-page/XR frame evidence",
            "fingerprint": read(
                args.serial, "shell", "getprop", "ro.build.fingerprint"
            ),
            "atrace_categories": read(
                args.serial, "shell", "atrace", "--list_categories"
            ),
        },
    )
    until = time.monotonic() + args.seconds
    with (args.out / "samples.jsonl").open("x") as stream:
        while time.monotonic() < until:
            stream.write(json.dumps(sample(args.serial), separators=(",", ":")) + "\n")
            stream.flush()
            remaining = until - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval, remaining))


if __name__ == "__main__":
    main()
