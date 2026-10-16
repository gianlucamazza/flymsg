"""GPU parity of the native lane on a console through Windows Device Portal (#39, #40).

Builds the acceptance fixtures of `scripts/native_acceptance.py` (12 version-1 ones and,
with `--v2`, the version-2 ones the exporter accepts: graded neurons, coupled groups,
spikelets) and their CPU oracles, writes one `flymsg.neural_job/v1` per fixture bound to the installed package's shader
and the expected adapter, uploads them to the running worker's `LocalState/inbox` (fixture
first, job last), waits for each, fetches `output.bin` and checks it bit for bit against the
oracle. The worker must already be installed and running.

Device Portal settings come from the environment only: `XBOX_IP`, `XBOX_USER`, `XBOX_PASS`
and, to pin the device's self-signed TLS key, `FLYMSG_DEVICE_PIN` (curl's `--pinnedpubkey`
form, `sha256//<base64>`, checked by curl on every connection; without it the key is not
checked). The report holds no address or credential. Exits nonzero unless every case passes.

Usage: uv run python scripts/console_gpu_parity.py --package PFN --shader lif.cso --out DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_acceptance import EXTENSIONS, check, qualification

from flymsg import sim
from flymsg.console import (  # the scripts beside this one import them here
    ADAPTER,
    Portal,
    PortalError,
)
from flymsg.native import NativeCapabilityError, export_fixture, read_output
from flymsg.runtime import CpuRuntime


def fixtures(extensions=("none",)):
    for ext in extensions:
        for seed in (3, 7, 19):
            for adapt in (0.0, 2.0):
                for silent in (False, True):
                    p = sim.Params(th_jump=adapt, delay=0.3 if seed == 3 else 1.8)
                    rng = np.random.default_rng(seed)
                    W = sparse.csc_matrix(
                        rng.integers(-20, 80, (8, 8)).astype(np.float32)
                    )
                    oracle = CpuRuntime(
                        W,
                        np.array([0, 1]),
                        steps=1000,
                        kicks=sim.poisson_kicks(seed, 700, p.dt, 700, 2),
                        p=p,
                        per_bin=100,
                        trace=np.arange(8),
                        silence=np.array([3]) if silent else None,
                        **EXTENSIONS[ext],
                    )
                    yield (seed, adapt, silent, ext), oracle


def run(
    package: str, shader: Path, out: Path, v2: bool = False, timeout_s: float = 600.0
) -> dict:
    portal = Portal()
    shader_sha = hashlib.sha256(shader.read_bytes()).hexdigest()
    cases, unsupported = [], []
    for (seed, adapt, silent, ext), oracle in fixtures(
        tuple(EXTENSIONS) if v2 else ("none",)
    ):
        job_id = str(uuid.uuid4())
        folder = out / job_id
        folder.mkdir(parents=True)
        fixture = folder / "fixture.bin"
        try:
            meta = export_fixture(oracle, fixture)
        except NativeCapabilityError as exc:
            unsupported.append(
                {
                    "seed": seed,
                    "adaptation": adapt,
                    "silenced": silent,
                    "extension": ext,
                    "reason": str(exc),
                }
            )
            continue
        job = {
            "schema": "flymsg.neural_job/v1",
            "job_id": job_id,
            "semantics": "flymsg.lif/ordered-f32-v1",
            "backend": "dx12",
            "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "shader_sha256": shader_sha,
            "expected_adapter": ADAPTER,
            "dataset": "synthetic",
            "seed": seed,
            "neural_tick_us": 100,
            "fixture": meta,
            "scope": "qualification fixture, not biological validation",
        }
        (folder / "job.json").write_text(
            json.dumps(job, sort_keys=True, indent=2) + "\n"
        )
        rel = f"inbox\\{job_id}"
        portal.mkdir(package, rel)
        portal.put(package, rel, fixture)
        portal.put(package, rel, folder / "job.json")  # last: the worker starts on it
        status, start = {}, time.time()
        while time.time() - start < timeout_s:
            time.sleep(5)
            try:
                portal.get(package, rel, "status.json", folder / "status.json")
            except PortalError as exc:
                if exc.http_status != 404:
                    raise
                continue
            status = json.loads((folder / "status.json").read_text())
            if status.get("state") in ("completed", "failed", "cancelled"):
                break
        case = {
            "seed": seed,
            "adaptation": adapt,
            "silenced": silent,
            "extension": ext,
            "fixture_sha256": job["fixture_sha256"],
            "state": status.get("state"),
            "error": status.get("error", ""),
            "app_memory_bytes": status.get("app_memory_bytes"),
            "source_commit": status.get("source_commit"),
            "parity": False,
        }
        if case["state"] == "completed":
            portal.get(package, rel, "output.bin", folder / "output.bin")
            portal.get(package, rel, "result.json", folder / "result.json")
            case["output_sha256"] = json.loads((folder / "result.json").read_text())[
                "output_sha256"
            ]
            actual_sha = hashlib.sha256(
                (folder / "output.bin").read_bytes()
            ).hexdigest()
            if actual_sha != case["output_sha256"]:
                case["mismatch"] = "downloaded output checksum differs from result"
            else:
                oracle.advance_to(1000)
                try:
                    check(oracle, read_output(folder / "output.bin", fixture))
                    case["parity"] = True
                except AssertionError as err:
                    case["mismatch"] = str(err)[:400]
        cases.append(case)
        print(
            json.dumps(
                {
                    k: case[k]
                    for k in (
                        "seed",
                        "adaptation",
                        "silenced",
                        "extension",
                        "state",
                        "parity",
                    )
                }
            )
        )
    report = {
        "schema": "flymsg.console_gpu_parity/v1",
        "adapter": ADAPTER,
        "package": package,
        "shader_sha256": shader_sha,
        "cases": cases,
        "unsupported_extensions": sorted({c["extension"] for c in unsupported}),
        "unsupported": unsupported,
        "qualification": qualification(
            cases, unsupported, v2=v2, success_field="parity"
        ),
        "passed": sum(c["parity"] for c in cases),
        "scope": "synthetic acceptance fixtures (version 1, and version 2 with --v2) on "
        "the console GPU; not full-connectome throughput, lifecycle or biological "
        "validation",
    }
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, help="installed PackageFullName")
    parser.add_argument(
        "--shader", type=Path, required=True, help="the package's lif.cso"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--v2", action="store_true", help="add the version-2 fixtures")
    a = parser.parse_args()
    r = run(a.package, a.shader, a.out, a.v2)
    print(f"passed {r['passed']} of {len(r['cases'])}")
    sys.exit(0 if r["qualification"]["qualified"] else 1)
