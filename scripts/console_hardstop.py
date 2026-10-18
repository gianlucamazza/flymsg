"""Prospective #224 process termination protocol; never run implicitly.

Device Portal credentials come only from the environment, as in console_lifecycle.
Reports retain selected evidence fields only, never raw request errors or process tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console_lifecycle import (
    INPUTS,
    SEED,
    STEPS,
    Job,
    N,
    Portal,
    TrialEpoch,
    app_call,
    failure_record,
    oracle,
)

from flymsg import runstore
from flymsg.console import PortalError

SCHEMA = "flymsg.console_hardstop/v1"
DONE = {"completed", "failed", "cancelled"}
# Faults a trial can raise: portal/transport, files, malformed replies, epoch loss and
# the oracle comparison. Anything else is a harness bug and propagates.
FAULTS = (PortalError, OSError, RuntimeError, ValueError, KeyError, TypeError)


def now():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def failure(exc):
    # failure_record's free text can contain caller-controlled paths or server data.
    record = failure_record(exc)
    safe = {"error_type": record["error_type"], "state": record["state"]}
    if isinstance(exc, PortalError):
        safe.update(http_status=exc.http_status, curl_code=exc.curl_code)
    return safe


def processes(portal, image):
    table = json.loads(portal.curl("GET", "/api/resourcemanager/processes"))
    matches = []
    for row in table["Processes"]:
        name = row["ImageName"].replace("\\", "/").rsplit("/", 1)[-1]
        if name.casefold() == image.casefold():
            pid = row["ProcessId"]
            if type(pid) is not int or pid <= 0:
                raise ValueError("invalid process identity")
            matches.append({"image": image, "pid": pid})
    return matches


def resolve_pid(matches):
    if len(matches) != 1:
        raise ValueError("worker image must resolve to exactly one PID")
    return matches[0]["pid"]


def sample(job, record, phase):
    status = job.status()
    error = status.get("error", "")
    removed = re.search(r"device removed HRESULT (0x[0-9A-Fa-f]{8})", error)
    unavailable = error == "fault injection unavailable"
    status = {
        k: status[k]
        for k in (
            "schema",
            "state",
            "step",
            "source_commit",
            "job_id",
            "app_memory_bytes",
            "app_memory_limit_bytes",
            "batch_outputs",
        )
        if k in status
    }
    if removed:
        status["device_removed_hresult"] = removed[1].upper()
    if unavailable:
        status["fault_injection_unavailable"] = True
    record.setdefault("status_history", []).append(
        {"utc": now(), "phase": phase, "status": status}
    )
    runstore.atomic_json(job.folder / "observations.json", record)
    if status and (
        status.get("source_commit") != record["source_commit"]
        or status.get("job_id") != job.id
    ):
        raise ValueError("worker/job identity changed")
    return status


def wait(job, record, phase, states, timeout=120, after=-1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = sample(job, record, phase)
        if status.get("state") in states and status.get("step", -1) > after:
            return status
        if status.get("state") in DONE:
            return status
        time.sleep(0.25)
    raise TimeoutError("status deadline")


def snapshot(job, record, phase):
    path = "%5CLocalState%5C" + job.rel.replace("\\", "%5C")
    listing = json.loads(
        job.portal.curl(
            "GET",
            "/api/filesystem/apps/files?knownfolderid=LocalAppData"
            f"&packagefullname={job.package}&path={path}",
        )
    )
    # Keep every filename, including .tmp, but discard server paths and metadata.
    names = sorted(row["Name"] for row in listing["Items"])
    folder = job.folder / phase
    folder.mkdir()
    evidence = {"utc": now(), "files": names}
    record.setdefault("snapshots", {})[phase] = evidence
    runstore.atomic_json(job.folder / "observations.json", record)
    for name in ("status.json", "checkpoint.json", "checkpoint.bin"):
        if name in names:
            job.portal.get(job.package, job.rel, name, folder / name)
    if "checkpoint.bin" in names:
        evidence["checkpoint_sha256"] = hashlib.sha256(
            (folder / "checkpoint.bin").read_bytes()
        ).hexdigest()
    if "checkpoint.json" in names:
        saved = json.loads((folder / "checkpoint.json").read_text())
        evidence["checkpoint"] = saved
    runstore.atomic_json(job.folder / "observations.json", record)
    return evidence


def complete_checkpoint(evidence, job, source_commit):
    saved = evidence.get("checkpoint", {})
    return bool(
        {n for n in evidence["files"] if n.startswith("checkpoint")}
        == {"checkpoint.bin", "checkpoint.json"}
        and evidence.get("checkpoint_sha256")
        and evidence["checkpoint_sha256"] == saved.get("checkpoint_sha256")
        and saved.get("fixture_sha256") == job.job["fixture_sha256"]
        and saved.get("shader_sha256") == job.job["shader_sha256"]
        and saved.get("source_commit") == source_commit
        and saved.get("backend") == "dx12"
        and saved.get("package") == job.package
    )


def kill(portal, image, record):
    record["processes_before"] = processes(portal, image)
    try:
        pid = resolve_pid(record["processes_before"])
    except ValueError:
        return "blocked"
    record["kill_pid"] = pid
    try:
        portal.curl("DELETE", f"/api/taskmanager/process?pid={pid}")
    except PortalError as exc:
        record["kill_error"] = failure(exc)
        try:
            record["processes_after"] = processes(portal, image)
        except FAULTS as observation_error:
            record["process_observation_error"] = failure(observation_error)
        return "blocked"
    time.sleep(1)
    record["processes_after"] = processes(portal, image)
    return "indeterminate" if record["processes_after"] else None


def run_case(portal, args, sha, epoch, name, record):
    job = Job(portal, args.package, sha, args.out, rt=oracle())
    record.update(
        job_id=job.id,
        source_commit=args.lineage["worker_source_commit"],
        trial_epoch=epoch.expected,
    )
    job.submit()
    first = wait(job, record, "initial", {"running"}, after=0)
    if first.get("state") != "running" or not 0 < first["step"] < STEPS:
        return "indeterminate"
    saved_step = 0
    saved_sha = None
    if name == "B":
        epoch.check("B-before-suspend")
        app_call(portal, "DELETE", args.package, args.aumid)
        parked = wait(job, record, "suspend", {"suspended"})
        saved_step = parked.get("step", 0)
        checkpoint = snapshot(job, record, "published")
        if parked.get("state") != "suspended" or not 0 < saved_step < STEPS:
            return "indeterminate"
        if not complete_checkpoint(checkpoint, job, record["source_commit"]):
            return "fail"
        saved_sha = checkpoint["checkpoint_sha256"]
        record.update(checkpoint_step=saved_step, checkpoint_sha256=saved_sha)
        epoch.check("B-after-suspend")
        app_call(portal, "POST", args.package, args.aumid)
        job.control("resume.json", "flymsg.worker_resume/v1")
        wait(job, record, "first-resume", {"running"}, after=saved_step)
    epoch.check(f"{name}-before-kill")
    before = snapshot(job, record, "before-kill")
    if name == "A" and any(n.startswith("checkpoint") for n in before["files"]):
        return "indeterminate"
    if name == "B" and (
        not complete_checkpoint(before, job, record["source_commit"])
        or before["checkpoint_sha256"] != saved_sha
        or before.get("checkpoint") != checkpoint.get("checkpoint")
    ):
        return "indeterminate"
    latest = sample(job, record, "immediately-before-kill")
    if (
        latest.get("state") != "running"
        or not saved_step < latest.get("step", 0) < STEPS
    ):
        return "indeterminate"
    verdict = kill(portal, args.worker_image, record)
    if verdict:
        record["verdict"] = verdict
    after = snapshot(job, record, "after-kill")
    status = sample(job, record, "after-kill")
    epoch.check(f"{name}-after-kill")
    if verdict:
        return verdict
    if status.get("state") not in {"running", "awaiting_recovery"}:
        return "indeterminate"
    if name == "A" and any(n.startswith("checkpoint") for n in after["files"]):
        return "indeterminate"
    if name == "B" and (
        not complete_checkpoint(after, job, record["source_commit"])
        or after["checkpoint_sha256"] != saved_sha
        or after.get("checkpoint") != before.get("checkpoint")
    ):
        return "indeterminate"
    app_call(portal, "POST", args.package, args.aumid)
    epoch.check(f"{name}-after-restart")
    parked = wait(job, record, "recovery", {"awaiting_recovery", "suspended"})
    if parked.get("state") == "suspended":
        return "indeterminate"
    if parked.get("state") != "awaiting_recovery" or parked.get("step") != 0:
        return "fail"
    job.control("resume.json", "flymsg.worker_resume/v1")
    final = wait(job, record, "completion", DONE, timeout=900)
    epoch.check(f"{name}-after-completion")
    if final.get("state") != "completed" or final.get("step") != STEPS:
        return "fail"
    result = job.result()
    record["restoration_step"] = STEPS - result["advance_steps"]
    record["oracle_parity"] = job.parity()
    return (
        "pass"
        if record["oracle_parity"] and record["restoration_step"] == saved_step
        else "fail"
    )


def run(args):
    # Existing directory is always refused, before contact.
    args.out.mkdir(parents=True)
    report = {
        "schema": SCHEMA,
        "protocol": "Noncooperative termination — protocol 2026-10-18",
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
        for name in ("A", "B"):
            record = {"case": name, "verdict": "indeterminate"}
            report["cases"].append(record)
            try:
                record["verdict"] = run_case(portal, args, sha, epoch, name, record)
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
        sys.exit("Hardstop not started; check inputs and use a new output directory")
    print(json.dumps({"schema": SCHEMA, "verdict": report["verdict"]}))
    sys.exit(0 if report["verdict"] == "pass" else 1)
