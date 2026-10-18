"""Prospective #224 process-local device removal; test hardware only.

Requalify the new binary with the full GPU parity matrix before invoking this.
Credentials are environment-only. Every attempt preserves artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console_hardstop import (
    DONE,
    FAULTS,
    complete_checkpoint,
    failure,
    now,
    processes,
    resolve_pid,
    sample,
    snapshot,
    wait,
)
from console_lifecycle import (
    INPUTS,
    SEED,
    STEPS,
    Job,
    N,
    Portal,
    TrialEpoch,
    app_call,
    oracle,
)

from flymsg import runstore

SCHEMA = "flymsg.console_gpufault/v1"
RECOVERY_SECONDS = 60
EXIT_SECONDS = 60


def checkpoint_hashes(job, evidence, phase):
    return {
        name: hashlib.sha256((job.folder / phase / name).read_bytes()).hexdigest()
        for name in ("checkpoint.bin", "checkpoint.json")
        if name in evidence["files"]
    }


def run_case(portal, args, sha, epoch, name, record):
    epoch.check(f"{name}-before-submit")
    job = Job(portal, args.package, sha, args.out, rt=oracle())
    record.update(
        job_id=job.id,
        source_commit=args.lineage["worker_source_commit"],
        trial_epoch=epoch.expected,
    )
    before_hashes = {}
    step = 200_000
    if name == "F2":
        job.submit()
        running = wait(job, record, "initial", {"running"}, after=0)
        if running.get("state") != "running" or not 0 < running["step"] < STEPS:
            return "indeterminate"
        app_call(portal, "DELETE", args.package, args.aumid)
        parked = wait(job, record, "suspend", {"suspended"})
        saved_step = parked.get("step", 0)
        before = snapshot(job, record, "published")
        if parked.get("state") != "suspended" or not 0 < saved_step < STEPS:
            return "indeterminate"
        if not complete_checkpoint(before, job, record["source_commit"]):
            return "fail"
        before_hashes = checkpoint_hashes(job, before, "published")
        step = saved_step + 200_000
        if step >= STEPS:
            return "indeterminate"
        record["checkpoint_step"] = saved_step
        epoch.check("F2-after-suspend")
        job.control("fault.json", "flymsg.worker_fault/v1", step=step)
        app_call(portal, "POST", args.package, args.aumid)
        ready = wait(job, record, "parked", {"awaiting_recovery"})
        if ready.get("state") != "awaiting_recovery":
            return "indeterminate"
    record["processes_before"] = processes(portal, args.worker_image)
    pid = resolve_pid(record["processes_before"])
    record["fault_step"] = step
    # Fault occurs after this action and before terminal status. A Portal cannot
    # timestamp RemoveDevice itself: retain a conservative elapsed upper bound,
    # plus the separately measured terminal-observation-to-exit interval.
    began = time.monotonic()
    record["fault_window_start_utc"] = now()
    if name == "F1":
        job.submit(fault_step=step)
    else:
        job.control("resume.json", "flymsg.worker_resume/v1")
    terminal = wait(job, record, "fault", DONE, timeout=120)
    observed = time.monotonic()
    record["terminal_observed_utc"] = now()
    after = snapshot(job, record, "after-fault")
    epoch.check(f"{name}-after-fault")
    if terminal.get("fault_injection_unavailable"):
        return "blocked" if terminal.get("state") == "failed" else "fail"
    if terminal.get("state") != "failed":
        return "fail"
    hr = terminal.get("device_removed_hresult", "")
    if not hr or not int(hr, 16) & 0x80000000:
        return "fail"
    record["device_removed_hresult"] = hr
    if "fault.json" not in after["files"]:
        return "indeterminate"
    if any(n == "result.json" or n.startswith("output") for n in after["files"]):
        return "fail"
    if name == "F1" and any(n.startswith("checkpoint") for n in after["files"]):
        return "fail"
    if name == "F2" and checkpoint_hashes(job, after, "after-fault") != before_hashes:
        return "fail"
    deadline = observed + EXIT_SECONDS
    while True:
        matches = processes(portal, args.worker_image)
        record["processes_after"] = matches
        if not matches and time.monotonic() <= deadline:
            break
        if time.monotonic() >= deadline:
            return "fail"
        time.sleep(0.25)
    record["fault_pid"] = pid
    record["exit_observed_utc"] = now()
    record["fault_to_exit_seconds"] = {
        "lower": 0,
        "upper": time.monotonic() - began,
        "method": "submit/resume-to-exit upper bound; no synchronized device clock",
    }
    record["terminal_observation_to_exit_seconds"] = time.monotonic() - observed
    epoch.check(f"{name}-before-restart")
    # Prepare a fresh job, then include app start and submission in the
    # predeclared deadline for its first identity-checked worker status.
    fresh = Job(portal, args.package, sha, args.out, rt=oracle())
    recovery = {"source_commit": record["source_commit"], "job_id": fresh.id}
    record["recovery"] = recovery
    restart = time.monotonic()
    app_call(portal, "POST", args.package, args.aumid)
    fresh.submit()
    deadline = restart + RECOVERY_SECONDS
    while True:
        status = sample(fresh, recovery, "restart")
        if status:
            break
        if time.monotonic() >= deadline:
            return "fail"
        time.sleep(0.25)
    record["restart_to_first_status_seconds"] = time.monotonic() - restart
    if time.monotonic() > deadline:
        return "fail"
    final = wait(fresh, recovery, "fresh-completion", DONE, timeout=900)
    epoch.check(f"{name}-after-recovery")
    if final.get("state") != "completed" or final.get("step") != STEPS:
        return "fail"
    record["oracle_parity"] = fresh.parity()
    return "pass" if record["oracle_parity"] else "fail"


def run(args):
    # Existing directory is always refused, before contact.
    args.out.mkdir(parents=True)
    report = {
        "schema": SCHEMA,
        "protocol": "GPU device removal — protocol 2026-10-18",
        "platform": "Xbox Series S, Dev Mode",
        "started_utc": now(),
        "verdict": "indeterminate",
        "fixture": {
            "neurons": N,
            "inputs": INPUTS,
            "seed": SEED,
            "steps": STEPS,
            "extension": "none",
            "synthetic": True,
        },
        "cases": [],
        "deadlines_seconds": {
            "pid_exit": EXIT_SECONDS,
            "restart_status": RECOVERY_SECONDS,
        },
        "hygiene": "process-local removal; restore by process restart; no persistent device setting changed",
    }
    portal = None
    try:
        source = args.lineage.get("worker_source_commit", "")
        if not isinstance(source, str) or not re.fullmatch(
            r"[0-9a-fA-F]{7,40}", source
        ):
            raise ValueError("declared worker source commit required")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.exe", args.worker_image, re.IGNORECASE):
            raise ValueError("worker image must be an executable basename")
        # Retain provenance without copying arbitrary input metadata into output.
        report["lineage_sha256"] = hashlib.sha256(
            json.dumps(args.lineage, sort_keys=True).encode()
        ).hexdigest()
        args.lineage = {"worker_source_commit": source}
        sha = hashlib.sha256(args.shader.read_bytes()).hexdigest()
        report["shader_sha256"] = sha
        portal = Portal()
        epoch = TrialEpoch(portal, args.package, args.out, args.lineage, sha)
        report["trial_epoch"] = epoch.expected
        app_call(portal, "POST", args.package, args.aumid)
        for name in ("F1", "F2"):
            record = {"case": name, "verdict": "indeterminate"}
            report["cases"].append(record)
            try:
                record["verdict"] = run_case(portal, args, sha, epoch, name, record)
            except TimeoutError as exc:
                record["verdict"] = "fail"
                record["failure"] = failure(exc)
            except (*FAULTS, KeyboardInterrupt) as exc:
                record["failure"] = failure(exc)
            runstore.atomic_json(args.out / "report.json", report)
            if record["verdict"] != "pass":
                break
        verdicts = [c["verdict"] for c in report["cases"]]
        report["verdict"] = "pass" if verdicts == ["pass", "pass"] else verdicts[-1]
    except (*FAULTS, KeyboardInterrupt) as exc:
        report["failure"] = failure(exc)
    finally:
        if portal is not None:
            try:
                app_call(portal, "DELETE", args.package, args.aumid)
                time.sleep(2)
                report["cleanup"] = {
                    "app_stop_requested": True,
                    "processes": processes(portal, args.worker_image),
                }
                if report["cleanup"]["processes"]:
                    report["verdict"] = "indeterminate"
            except (*FAULTS, KeyboardInterrupt) as exc:
                report["cleanup"] = failure(exc)
                report["verdict"] = "indeterminate"
            try:
                portal.close()
            except FAULTS as exc:
                report["session_cleanup"] = failure(exc)
                report["verdict"] = "indeterminate"
        report["finished_utc"] = now()
        runstore.atomic_json(args.out / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--aumid", required=True)
    parser.add_argument(
        "--worker-image", required=True, help="exact worker executable basename"
    )
    parser.add_argument("--shader", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.lineage = json.loads(args.lineage.read_text())
        report = run(args)
    except (OSError, ValueError, KeyboardInterrupt):
        sys.exit(
            "GPU fault trial not started; check inputs and use a new output directory"
        )
    print(json.dumps({"schema": SCHEMA, "verdict": report["verdict"]}))
    sys.exit(0 if report["verdict"] == "pass" else 1)
