"""Sustained full-connectome workload on the console's GPU lane (#224).

The protocol is declared in PROTOCOL before any measurement and written into the report
unchanged. Each case runs its jobs back to back on the installed worker: the default
MaleCNS model (version-1 fixture) with one battery stimulus. A job's GPU input carries its
kicks densely, so the 512 MiB budget of `native/lif.h` bounds one job's horizon; a
sustained run is a declared series of identical jobs. The first job of a case is checked
bit for bit against the CPU oracle; every later job must return the same output bytes.

While a job runs, the worker's status (state, step, app memory) is sampled every second
and the Device Portal's system performance (GPU engine utilisation and memory, CPU load,
available pages) every five seconds. Throughput comes from the worker's own advance timing
and, within a job, from step deltas over 60 s windows. Settings as `console_gpu_parity.py`
(environment only); the report holds no address or credential. A failed, cancelled or
timed-out job is recorded and ends its case; it is not retried.

Usage: uv run python scripts/console_sustained.py --package PFN --shader lif.cso \
    --lineage lineage.json --out NEW_DIR [--case NAME ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console_gpu_parity import ADAPTER, Portal
from console_lifecycle import Job
from native_acceptance import check

from flymsg import data, sensitivity, sim, validate
from flymsg.console import PortalError
from flymsg.native import read_output
from flymsg.runtime import CpuRuntime

PROTOCOL = {
    "schema": "flymsg.console_sustained_protocol/v1",
    "declared": "2026-10-16, before any sustained measurement",
    "revision": 4,
    "revision_reason": "attempt 1 (1d1fde5) kept each job's fixture, checkpoint and output on the console; the third 500k-step upload got HTTP 500 and the script stopped without a record. Revision 2 deletes a job's large files from the console once its output is downloaded and hashed, and records a Device Portal error as the job's final state",
    "revision_3": "cross-vendor review fixes, no change to cases or measures: a failed "
    "result or output read-back is recorded as `readback_failed`; the console copy is "
    "deleted only when the downloaded bytes match the worker's reported hash; a zero first "
    "window gives no last/first ratio instead of an exception",
    "revision_4": "2026-10-18, before measuring it: adds `long-looming-sparse`, one "
    "1,500,000-step looming job in the sparse kick encoding (fixture v3), beyond the "
    "~760k-step cap that dense kicks hit within the 512 MiB GPU input budget; existing "
    "cases unchanged and not rerun",
    "console_cleanup": ["fixture.bin", "checkpoint.bin", "output.bin"],
    "model": "MaleCNS v1.0 default model, version-1 fixture (no graded or coupled neurons)",
    "rate_hz": validate.RATE_HZ,
    "cases": [
        # cold: the first job after a fresh worker start; warm: the next one
        {
            "name": "setup-looming",
            "stimulus": "looming escape",
            "seed": 600,
            "steps": 20_000,
            "jobs": 2,
            "per_bin": 100,
        },
        {
            "name": "sustained-looming",
            "stimulus": "looming escape",
            "seed": 601,
            "steps": 500_000,
            "jobs": 4,
            "per_bin": 10_000,
        },
        {
            "name": "sustained-bitter",
            "stimulus": "bitter feeding",
            "seed": 602,
            "steps": 500_000,
            "jobs": 4,
            "per_bin": 10_000,
        },
        {
            "name": "long-looming-sparse",
            "stimulus": "looming escape",
            "seed": 603,
            "steps": 1_500_000,
            "jobs": 1,
            "per_bin": 10_000,
            "input_encoding": "sparse",
        },
    ],
    "activity": "looming escape drives DNp01 and TTMn (battery positive); bitter feeding "
    "is the battery negative that stays silent at MN9",
    "status_period_s": 1.0,
    "perf_period_s": 5.0,
    "window_s": 60.0,
    "job_timeout_factor": 4.0,  # of the advance time expected at 2,320 steps/s
    "v2_full_connectome": "not measured: no full-connectome version-2 configuration is "
    "exportable (per-neuron membranes are refused by flymsg.native), so only the synthetic "
    "graded lifecycle (scripts/console_lifecycle.py --extension graded) covers v2",
    "verdicts": "per case: pass when every job completes with the oracle's output; fail on "
    "any other final state or output; throttling is reported, not judged",
}
EXPECTED_STEPS_PER_S = 2_320.0


class Model:
    """The default network, loaded once; each job exports a fresh runtime of it."""

    def __init__(self, data_dir: Path):
        self.neurons, edges = data.load(data_dir)
        self.p = sim.Params()
        self.W = sim.network(self.neurons, edges, self.p)

    def runtime(self, case: dict) -> CpuRuntime:
        stim, _ = sensitivity.case_inputs(case["stimulus"], self.neurons)
        stim = np.sort(stim)
        kicks = sim.poisson_kicks(
            case["seed"], validate.RATE_HZ, self.p.dt, case["steps"], stim.size
        )
        return CpuRuntime(
            self.W,
            stim,
            steps=case["steps"],
            kicks=kicks,
            p=self.p,
            per_bin=case["per_bin"],
        )


def windows(samples: list[dict], width_s: float) -> list[float]:
    """Steps per second over consecutive windows of `width_s` while a job runs."""
    run = [s for s in samples if s.get("state") == "running" and "step" in s]
    rates, start = [], 0
    for i in range(1, len(run)):
        dt = run[i]["t"] - run[start]["t"]
        if dt >= width_s:
            rates.append((run[i]["step"] - run[start]["step"]) / dt)
            start = i
    return rates


def perf(portal: Portal) -> dict:
    d = json.loads(portal.curl("GET", "/api/resourcemanager/systemperf"))
    gpu = d["GPUData"]["AvailableAdapters"][0]
    return {
        "gpu_engines_utilization": gpu.get("EnginesUtilization"),
        "gpu_dedicated_used": gpu.get("DedicatedMemoryUsed"),
        "gpu_system_used": gpu.get("SystemMemoryUsed"),
        "cpu_load": d.get("CpuLoad"),
        "available_pages": d.get("AvailablePages"),
        "page_size": d.get("PageSize"),
    }


def one_job(portal, args, sha, out, rt, case, index) -> dict:
    job = Job(
        portal,
        args.package,
        sha,
        out,
        rt,
        dataset="malecns-v1.0",
        seed=case["seed"],
        scope="sustained workload qualification, not biological validation",
        input_encoding=case.get("input_encoding", "dense"),
    )
    t0 = time.time()
    try:
        job.submit()
    except PortalError as exc:
        return {
            "index": index,
            "job_id": job.id,
            "fixture_bytes": job.fixture.stat().st_size,
            "upload_s": time.time() - t0,
            "first_running_s": None,
            "final_state": "upload_failed",
            "error": str(exc),
            "samples": [],
            "perf": [],
            "window_steps_per_s": [],
        }, job
    upload_s = time.time() - t0
    timeout = (
        case["steps"] / EXPECTED_STEPS_PER_S * PROTOCOL["job_timeout_factor"] + 600
    )
    samples, perfs, last_perf, final = [], [], 0.0, {}
    portal_errors = []
    while time.time() - t0 < timeout:
        now = time.time()
        try:
            s = job.status()
            if now - last_perf >= PROTOCOL["perf_period_s"]:
                perfs.append({"t": now - t0} | perf(portal))
                last_perf = now
        except PortalError as exc:
            portal_errors.append({"t": now - t0, "error": str(exc)})
            time.sleep(PROTOCOL["status_period_s"])
            continue
        if s:
            samples.append(
                {
                    "t": now - t0,
                    "state": s.get("state"),
                    "step": s.get("step"),
                    "app_memory_bytes": s.get("app_memory_bytes"),
                }
            )
            if s.get("state") in {"completed", "failed", "cancelled"}:
                final = s
                break
        time.sleep(PROTOCOL["status_period_s"])
    record = {
        "index": index,
        "job_id": job.id,
        "fixture_bytes": job.fixture.stat().st_size,
        "upload_s": upload_s,
        "first_running_s": next(
            (x["t"] for x in samples if x["state"] == "running"), None
        ),
        "final_state": final.get("state", "timeout"),
        "error": final.get("error", ""),
        "source_commit": final.get("source_commit"),
        "samples": samples,
        "perf": perfs,
        "portal_errors": portal_errors,
        "window_steps_per_s": windows(samples, PROTOCOL["window_s"]),
    }
    if record["final_state"] == "completed":
        try:
            readback(portal, args, job, record)
        except (PortalError, KeyError, ValueError, OSError) as exc:
            # completed on the console but not read back: recorded, never a pass
            record["final_state"] = "readback_failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
    return record, job


def readback(portal, args, job: Job, record: dict) -> None:
    """Result, output download and hash; the console copy is deleted only once the local
    bytes match the hash the worker reported, so a transfer fault keeps its evidence."""
    result = job.result()
    record["advance_steps_per_s"] = result["advance_steps"] / (
        result["advance_ms"] / 1000.0
    )
    t1 = time.time()
    portal.get(args.package, job.rel, "output.bin", job.folder / "output.bin")
    record["download_s"] = time.time() - t1
    record["output_bytes"] = (job.folder / "output.bin").stat().st_size
    record["output_sha256"] = hashlib.sha256(
        (job.folder / "output.bin").read_bytes()
    ).hexdigest()
    record["reported_sha_matches"] = record["output_sha256"] == result["output_sha256"]
    if not record["reported_sha_matches"]:
        return
    for name in PROTOCOL["console_cleanup"]:
        try:
            portal.delete(args.package, job.rel, name)
        except PortalError as exc:
            record.setdefault("cleanup_errors", []).append(str(exc))


def parity(job: Job) -> bool:
    """The downloaded output against the CPU oracle, without fetching it again."""
    job.rt.advance_to(job.steps)
    try:
        check(job.rt, read_output(job.folder / "output.bin", job.fixture))
        return True
    except (AssertionError, ValueError):
        return False


def summary(values: list[float]) -> dict:
    if not values:
        return {}
    return {
        "n": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
        # a stalled first window has no ratio; the job's state records the stall
        "last_over_first": values[-1] / values[0] if values[0] else None,
    }


def run_case(portal, args, sha, model: Model, case) -> dict:
    out = args.out / case["name"]
    out.mkdir(parents=True)
    jobs, first_job = [], None
    for i in range(case["jobs"]):
        record, job = one_job(portal, args, sha, out, model.runtime(case), case, i)
        jobs.append(record)
        first_job = first_job or job
        if record["final_state"] != "completed":
            break
    # the oracle runs after the series, so the console's jobs follow each other
    if jobs[0]["final_state"] == "completed":
        t0 = time.time()
        jobs[0]["oracle_parity"] = parity(first_job)
        jobs[0]["oracle_s"] = time.time() - t0
    first = jobs[0].get("output_sha256")
    passed = (
        len(jobs) == case["jobs"]
        and all(
            j["final_state"] == "completed"
            and j["reported_sha_matches"]
            and not j.get("cleanup_errors")
            for j in jobs
        )
        and jobs[0].get("oracle_parity") is True
        and all(j["output_sha256"] == first for j in jobs)
    )
    within = [r for j in jobs for r in j["window_steps_per_s"]]
    return {
        "case": case,
        "verdict": "pass" if passed else "fail",
        "jobs": jobs,
        "advance_steps_per_s": summary(
            [j["advance_steps_per_s"] for j in jobs if "advance_steps_per_s" in j]
        ),
        "window_steps_per_s": summary(within),
        "upload_s": summary([j["upload_s"] for j in jobs]),
        "first_running_s": [j["first_running_s"] for j in jobs],
        "peak_app_memory_bytes": max(
            (s["app_memory_bytes"] or 0 for j in jobs for s in j["samples"]),
            default=None,
        ),
        "host_load_average": list(os.getloadavg()),
    }


if __name__ == "__main__":
    names = [c["name"] for c in PROTOCOL["cases"]]
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, help="installed PackageFullName")
    parser.add_argument(
        "--shader", type=Path, required=True, help="the package's lif.cso"
    )
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="a new directory")
    parser.add_argument("--case", choices=names, action="append", help="default: all")
    a = parser.parse_args()
    a.out.mkdir(parents=True)
    portal = Portal()
    model = Model(Path(os.environ.get("FLYMSG_DATA", "data")))
    sha = hashlib.sha256(a.shader.read_bytes()).hexdigest()
    report = {
        "schema": "flymsg.console_sustained/v1",
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": "Xbox Series S, Dev Mode",
        "script": "scripts/console_sustained.py",
        "protocol": PROTOCOL,
        "package": a.package,
        "package_lineage": json.loads(a.lineage.read_text()),
        "adapter": ADAPTER,
        "shader_sha256": sha,
        "cases": [],
    }
    for case in PROTOCOL["cases"]:
        if a.case and case["name"] not in a.case:
            continue
        report["cases"].append(run_case(portal, a, sha, model, case))
        (a.out / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
    report["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    (a.out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({c["case"]["name"]: c["verdict"] for c in report["cases"]}))
    sys.exit(0 if all(c["verdict"] == "pass" for c in report["cases"]) else 1)
