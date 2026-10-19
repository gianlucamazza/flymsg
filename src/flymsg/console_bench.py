"""Full-connectome throughput of the GPU lane on a console, against the host CPU (#40).

The default MaleCNS model (version-1 fixture: no graded or coupled neurons) with the
battery's looming stimulus at its rate runs as one dx12 job on the installed worker; its
output is checked bit for bit against the CPU oracle and its throughput is the worker's own
timing of the advance (`result.json`). The same fixture's host baselines are the Python
oracle and, if given, the native CPU executor. Settings as `console_gpu_parity.py`
(environment only); the report holds no address or credential. Exits nonzero unless the
console output matches.

Usage: uv run python scripts/console_bench.py --package PFN --shader lif.cso --out DIR \
    --lineage lineage.json [--native build/native/flymsg_native] [--steps 2000]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from flymsg import data, sensitivity, sim, validate
from flymsg.console import ADAPTER, Portal
from flymsg.console_lifecycle import Job
from flymsg.runtime import CpuRuntime

CASE, SEED = "looming escape", 500  # one battery stimulus; a seed no lock uses


def oracle(data_dir: Path, steps: int) -> CpuRuntime:
    """The default model with the case's stimulus at the battery rate."""
    neurons, edges = data.load(data_dir)
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    stim, _ = sensitivity.case_inputs(CASE, neurons)
    stim = np.sort(stim)
    kicks = sim.poisson_kicks(SEED, validate.RATE_HZ, p.dt, steps, stim.size)
    return CpuRuntime(
        W,
        stim,
        steps=steps,
        kicks=kicks,
        p=p,
        per_bin=100,
        input_encoding="counts",
    )


def host_python(data_dir: Path, steps: int) -> float:
    """Steps per second of the Python oracle on this host, over the whole horizon."""
    rt = oracle(data_dir, steps)
    start = time.perf_counter()
    rt.advance_to(steps)
    return steps / (time.perf_counter() - start)


def host_native(exe: Path, fixture: Path, steps: int) -> float:
    """Steps per second of the native CPU executor on the same fixture (process time
    includes reading the fixture)."""
    out = fixture.with_name("native-output.bin")
    start = time.perf_counter()
    subprocess.run(
        [str(exe), "--fixture", str(fixture), "--output", str(out)],
        check=True,
        capture_output=True,
    )
    return steps / (time.perf_counter() - start)


def run(args) -> dict:
    data_dir = Path(os.environ.get("FLYMSG_DATA", "data"))
    portal = Portal()
    sha = hashlib.sha256(args.shader.read_bytes()).hexdigest()
    job = Job(
        portal,
        args.package,
        sha,
        args.out,
        oracle(data_dir, args.steps),
        dataset="malecns-v1.0",
        seed=SEED,
        scope="full-connectome throughput qualification, not biological validation",
    )
    job.submit()
    final = job.wait({"completed", "failed", "cancelled"}, timeout_s=3600)
    console = {"state": final.get("state"), "error": final.get("error", "")}
    if final.get("state") == "completed":
        result = job.result()
        console |= {
            "steps_per_s": result["advance_steps"] / (result["advance_ms"] / 1000.0),
            "app_memory_bytes": final.get("app_memory_bytes"),
            "parity": job.parity(),
        }
    host = {"python_steps_per_s": host_python(data_dir, args.steps)}
    if args.native:
        host["native_cpu_steps_per_s"] = host_native(
            args.native, job.fixture, args.steps
        )
    host["load_average"] = list(os.getloadavg())  # a busy host slows its baselines
    # flymsg.native_fixture header: word 2 the neuron count, word 16 the offset of
    # the incoming CSR's row pointers
    words = np.frombuffer(job.fixture.read_bytes(), "<u4")
    report = {
        "schema": "flymsg.console_bench/v1",
        "date": time.strftime("%Y-%m-%d"),
        "platform": "Xbox Series S, Dev Mode",
        "script": "scripts/console_bench.py",
        "package_lineage": json.loads(args.lineage.read_text())
        | {"worker_source_commit": final.get("source_commit")},
        "adapter": ADAPTER,
        "package": args.package,
        "shader_sha256": sha,
        "fixture": {
            "dataset": "MaleCNS v1.0, default model",
            "neurons": int(words[2]),
            "synapses": int(words[words[16] + words[2]]),  # the incoming CSR's end
            "state_bytes": job.job["fixture"]["state_bytes"],
            "steps": args.steps,
            "stimulus": f"{CASE} at {validate.RATE_HZ:g} Hz, seed {SEED}",
            "bytes": job.fixture.stat().st_size,
        },
        "console": console,
        "host": host,
        "passed": bool(console.get("parity")),
        "scope": "one stimulus, a short horizon; throughput of the version-1 lane only",
    }
    (args.out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, help="installed PackageFullName")
    parser.add_argument(
        "--shader", type=Path, required=True, help="the package's lif.cso"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--native", type=Path, help="native CPU executor, optional")
    parser.add_argument("--steps", type=int, default=2000)
    a = parser.parse_args()
    r = run(a)
    print(json.dumps({k: r[k] for k in ("fixture", "console", "host", "passed")}))
    sys.exit(0 if r["passed"] else 1)


if __name__ == "__main__":
    main()
