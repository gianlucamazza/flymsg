"""Worker lifecycle on a console through Windows Device Portal (#40).

Three runs of one synthetic version-1 fixture, long enough to be interrupted, each as a dx12
job to the installed worker:

- throughput: run to completion; steps per second over the advance, timed by the worker
  (`result.json`), output checked bit for bit against the CPU oracle;
- cancel: a `flymsg.worker_cancel/v1` while running must end in `cancelled` before the end;
- stop and resume: the app is stopped through Device Portal while the job runs and started
  again; the job must be parked, `suspended` with a checkpoint when the platform suspended
  the app before ending it, `awaiting_recovery` when it ended without one, and after a
  `flymsg.worker_resume/v1` complete with the oracle's output.

Settings as `console_gpu_parity.py` (environment only); the report holds no address or
credential. Exits nonzero unless all three behave.

Usage: uv run python scripts/console_lifecycle.py --package PFN --aumid AUMID \
    --shader lif.cso --out DIR
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console_gpu_parity import ADAPTER, Portal
from native_acceptance import check  # the acceptance comparator, unchanged

from flymsg import sim
from flymsg.native import export_fixture, read_output
from flymsg.runtime import CpuRuntime

# synthetic; about 23 s of advance at the measured 44k steps/s, so a cancel or a stop sent
# after a 1 s status poll lands mid-run
N, STEPS, SEED, INPUTS = 2048, 1_000_000, 40, 2


def oracle() -> CpuRuntime:
    p = sim.Params()
    rng = np.random.default_rng(SEED)
    W = sparse.random(N, N, density=0.01, random_state=rng, format="csc")
    W.data = rng.integers(-20, 80, W.data.size).astype(np.float32)
    return CpuRuntime(
        W.astype(np.float32),
        np.arange(INPUTS),
        steps=STEPS,
        kicks=sim.poisson_kicks(SEED, 200, p.dt, STEPS, INPUTS),
        p=p,
        per_bin=1000,
        trace=np.arange(8),
    )


class Job:
    """One dx12 job on the console: its fixture, oracle, upload, status and output."""

    def __init__(
        self,
        portal: Portal,
        package: str,
        shader_sha: str,
        out: Path,
        rt: CpuRuntime | None = None,
        *,
        dataset: str = "synthetic",
        seed: int = SEED,
        scope: str = "lifecycle qualification fixture, not biological validation",
    ):
        self.portal, self.package = portal, package
        self.id = str(uuid.uuid4())
        self.folder = out / self.id
        self.folder.mkdir(parents=True)
        self.rel = f"inbox\\{self.id}"
        self.rt = oracle() if rt is None else rt
        fixture = self.folder / "fixture.bin"
        meta = export_fixture(self.rt, fixture)
        self.steps = int(meta["steps"])
        self.fixture = fixture
        self.job = {
            "schema": "flymsg.neural_job/v1",
            "job_id": self.id,
            "semantics": "flymsg.lif/ordered-f32-v1",
            "backend": "dx12",
            "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "shader_sha256": shader_sha,
            "expected_adapter": ADAPTER,
            "dataset": dataset,
            "seed": seed,
            "neural_tick_us": 100,
            "fixture": meta,
            "scope": scope,
        }

    def control(self, name: str, schema: str) -> None:
        path = self.folder / name
        path.write_text(json.dumps({"schema": schema, "job_id": self.id}) + "\n")
        self.portal.put(self.package, self.rel, path)

    def submit(self) -> float:
        (self.folder / "job.json").write_text(
            json.dumps(self.job, sort_keys=True, indent=2) + "\n"
        )
        self.portal.mkdir(self.package, self.rel)
        self.portal.put(self.package, self.rel, self.fixture)
        self.portal.put(self.package, self.rel, self.folder / "job.json")
        return time.time()

    def status(self) -> dict:
        try:
            self.portal.get(
                self.package, self.rel, "status.json", self.folder / "status.json"
            )
            return json.loads((self.folder / "status.json").read_text())
        except (RuntimeError, json.JSONDecodeError):
            return {}  # not written yet, or caught mid-replacement

    def wait(self, states: set, timeout_s: float = 900.0) -> dict:
        start = time.time()
        while time.time() - start < timeout_s:
            s = self.status()
            if s.get("state") in states:
                return s
            time.sleep(1.0)
        return {"state": "timeout"}

    def result(self) -> dict:
        self.portal.get(
            self.package, self.rel, "result.json", self.folder / "result.json"
        )
        return json.loads((self.folder / "result.json").read_text())

    def parity(self) -> bool:
        self.portal.get(
            self.package, self.rel, "output.bin", self.folder / "output.bin"
        )
        self.rt.advance_to(self.steps)
        try:
            check(self.rt, read_output(self.folder / "output.bin", self.fixture))
            return True
        except AssertionError:
            return False


def app_call(portal: Portal, method: str, package: str, aumid: str) -> None:
    pkg = base64.b64encode(package.encode()).decode()
    if method == "DELETE":
        portal.curl("DELETE", f"/api/taskmanager/app?package={pkg}")
    else:
        app = base64.b64encode(aumid.encode()).decode()
        portal.curl("POST", f"/api/taskmanager/app?appid={app}&package={pkg}")


def run(package: str, aumid: str, shader: Path, out: Path, lineage: dict) -> dict:
    portal = Portal()
    sha = hashlib.sha256(shader.read_bytes()).hexdigest()
    done = {"completed", "failed", "cancelled"}

    job = Job(portal, package, sha, out)
    job.submit()
    final = job.wait(done)
    # FLYMSG_COMMIT baked into the worker, as its status reports it
    lineage = {**lineage, "worker_source_commit": final.get("source_commit")}
    rate = None
    if final.get("state") == "completed":
        result = job.result()
        rate = result["advance_steps"] / (result["advance_ms"] / 1000.0)
    throughput = {
        "state": final.get("state"),
        "error": final.get("error", ""),
        "steps": STEPS,
        "neurons": N,
        "steps_per_s": rate,  # the worker's own clock over the advance
        "app_memory_bytes": final.get("app_memory_bytes"),
        "app_memory_limit_bytes": final.get("app_memory_limit_bytes"),
        "parity": final.get("state") == "completed" and job.parity(),
    }

    job = Job(portal, package, sha, out)
    job.submit()
    first = job.wait({"running"} | done)
    job.control("cancel.json", "flymsg.worker_cancel/v1")
    final = job.wait(done)
    cancel = {
        "seen_running": first.get("state") == "running",
        "state": final.get("state"),
        "step": final.get("step"),
        "ok": first.get("state") == "running"
        and final.get("state") == "cancelled"
        and 0 < final.get("step", 0) < STEPS,
    }

    job = Job(portal, package, sha, out)
    job.submit()
    first = job.wait({"running"} | done)
    app_call(portal, "DELETE", package, aumid)
    time.sleep(5)
    app_call(portal, "POST", package, aumid)
    waiting = job.wait({"suspended", "awaiting_recovery"} | done, timeout_s=120)
    job.control("resume.json", "flymsg.worker_resume/v1")
    final = job.wait(done)
    recovery = {
        "seen_running": first.get("state") == "running",
        "parked_as": waiting.get("state"),
        "parked_at_step": waiting.get("step"),
        "state": final.get("state"),
        "how": "Device Portal stop of the running app, restart, then a "
        "flymsg.worker_resume/v1",
        "parity": final.get("state") == "completed" and job.parity(),
    }
    if final.get("state") == "completed":
        # a resume from the checkpoint advances only the remaining steps
        recovery["resumed_advance_steps"] = job.result()["advance_steps"]
    recovery["ok"] = (
        recovery["seen_running"]
        and recovery["parked_as"] in ("suspended", "awaiting_recovery")
        and recovery["parity"]
    )

    report = {
        "schema": "flymsg.console_lifecycle/v1",
        "date": time.strftime("%Y-%m-%d"),
        "platform": "Xbox Series S, Dev Mode",
        "script": "scripts/console_lifecycle.py",
        "oracle": "the CPU runtime on the same fixture, compared with "
        "scripts/native_acceptance.py check() after the last step",
        "package_lineage": lineage,
        "adapter": ADAPTER,
        "package": package,
        "shader_sha256": sha,
        "fixture": {
            "neurons": N,
            "steps": STEPS,
            "inputs": INPUTS,
            "seed": SEED,
            "synthetic": True,
        },
        "throughput": throughput,
        "cancel": cancel,
        "stop_and_resume": recovery,
        "passed": bool(throughput["parity"] and cancel["ok"] and recovery["ok"]),
        "scope": "one synthetic version-1 fixture; not full-connectome throughput or "
        "biological validation",
    }
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, help="installed PackageFullName")
    parser.add_argument("--aumid", required=True, help="the worker's AppUserModelId")
    parser.add_argument(
        "--shader", type=Path, required=True, help="the package's lif.cso"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--lineage",
        type=Path,
        required=True,
        help="JSON of the installed package's lineage (CI run, source commit, msix hashes)",
    )
    a = parser.parse_args()
    r = run(a.package, a.aumid, a.shader, a.out, json.loads(a.lineage.read_text()))
    keys = ("throughput", "cancel", "stop_and_resume", "passed")
    print(json.dumps({k: r[k] for k in keys}))
    sys.exit(0 if r["passed"] else 1)
