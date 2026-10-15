"""GPU parity of the native lane on a console through Windows Device Portal (#39, #40).

Builds the 12 version-1 acceptance fixtures of `scripts/native_acceptance.py` and their CPU
oracles, writes one `flymsg.neural_job/v1` per fixture bound to the installed package's shader
and the expected adapter, uploads them to the running worker's `LocalState/inbox` (fixture
first, job last), waits for each, fetches `output.bin` and checks it bit for bit against the
oracle. The worker must already be installed and running.

Device Portal settings come from the environment only: `XBOX_IP`, `XBOX_USER`, `XBOX_PASS`
and, to pin the device's TLS certificate, `FLYMSG_DEVICE_PIN` (its SHA-256; without it the
certificate is not checked). The report holds no address or credential.

Usage: uv run python scripts/console_gpu_parity.py --package PFN --shader lif.cso --out DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_acceptance import check  # the acceptance comparator, unchanged

from flymsg import sim
from flymsg.native import export_fixture, read_output
from flymsg.runtime import CpuRuntime

ADAPTER = "SraKmd_arden"  # Xbox Series S, as the FloppyLM trainer's evidence records


class Portal:
    """The few Device Portal calls a job needs, through curl."""

    def __init__(self) -> None:
        self.base = f"https://{os.environ['XBOX_IP']}:11443"
        self.auth = f"{os.environ['XBOX_USER']}:{os.environ['XBOX_PASS']}"
        fd, self.jar = tempfile.mkstemp(prefix="wdp")
        os.close(fd)
        pin = os.environ.get("FLYMSG_DEVICE_PIN")
        if pin:
            cert = ssl.get_server_certificate((os.environ["XBOX_IP"], 11443))
            der = ssl.PEM_cert_to_DER_cert(cert)
            if hashlib.sha256(der).hexdigest() != pin.lower():
                raise SystemExit("device certificate does not match FLYMSG_DEVICE_PIN")
        self.curl("GET", "/", out=os.devnull)
        token = [
            line.split("\t")[6]
            for line in Path(self.jar).read_text().splitlines()
            if "\tCSRF-Token\t" in line
        ]
        self.token = token[0] if token else ""

    def curl(self, method, path, out=None, upload=None) -> str:
        cmd = ["curl", "-sS", "-k", "--fail", "-m", "120", "-u", self.auth]
        cmd += ["-b", self.jar, "-c", self.jar, "-X", method]
        if method != "GET":
            cmd += ["-H", f"X-CSRF-Token:{getattr(self, 'token', '')}"]
        if upload:
            name = Path(upload).name
            cmd += [
                "-F",
                f"file=@{upload};type=application/octet-stream;filename={name}",
            ]
        elif method == "POST":
            cmd += ["-d", ""]
        if out:
            cmd += ["-o", out]
        r = subprocess.run(
            [*cmd, self.base + path], capture_output=True, text=True, check=False
        )
        if r.returncode:
            raise RuntimeError(f"{method} {path.split('?')[0]} failed ({r.returncode})")
        return r.stdout

    def mkdir(self, package: str, rel: str) -> None:
        parent = "%5CLocalState"
        for part in rel.split("\\"):
            try:
                self.curl(
                    "POST",
                    f"/api/filesystem/apps/folder?knownfolderid=LocalAppData"
                    f"&packagefullname={package}&path={parent}&newfoldername={part}",
                )
            except RuntimeError:
                pass  # it exists
            parent += "%5C" + part

    def put(self, package: str, rel: str, local: Path) -> None:
        path = "%5CLocalState%5C" + rel.replace("\\", "%5C")
        self.curl(
            "POST",
            f"/api/filesystem/apps/file?knownfolderid=LocalAppData"
            f"&packagefullname={package}&path={path}",
            upload=str(local),
        )

    def get(self, package: str, rel: str, name: str, local: Path) -> None:
        path = "%5CLocalState%5C" + rel.replace("\\", "%5C")
        self.curl(
            "GET",
            f"/api/filesystem/apps/file?knownfolderid=LocalAppData"
            f"&packagefullname={package}&path={path}&filename={name}",
            out=str(local),
        )


def fixtures():
    for seed in (3, 7, 19):
        for adapt in (0.0, 2.0):
            for silent in (False, True):
                p = sim.Params(th_jump=adapt, delay=0.3 if seed == 3 else 1.8)
                rng = np.random.default_rng(seed)
                W = sparse.csc_matrix(rng.integers(-20, 80, (8, 8)).astype(np.float32))
                oracle = CpuRuntime(
                    W,
                    np.array([0, 1]),
                    steps=1000,
                    kicks=sim.poisson_kicks(seed, 700, p.dt, 700, 2),
                    p=p,
                    per_bin=100,
                    trace=np.arange(8),
                    silence=np.array([3]) if silent else None,
                )
                yield (seed, adapt, silent), oracle


def run(package: str, shader: Path, out: Path, timeout_s: float = 600.0) -> dict:
    portal = Portal()
    shader_sha = hashlib.sha256(shader.read_bytes()).hexdigest()
    cases = []
    for (seed, adapt, silent), oracle in fixtures():
        job_id = str(uuid.uuid4())
        folder = out / job_id
        folder.mkdir(parents=True)
        fixture = folder / "fixture.bin"
        meta = export_fixture(oracle, fixture)
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
            except RuntimeError:
                continue
            status = json.loads((folder / "status.json").read_text())
            if status.get("state") in ("completed", "failed", "cancelled"):
                break
        case = {
            "seed": seed,
            "adaptation": adapt,
            "silenced": silent,
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
                    for k in ("seed", "adaptation", "silenced", "state", "parity")
                }
            )
        )
    report = {
        "schema": "flymsg.console_gpu_parity/v1",
        "adapter": ADAPTER,
        "package": package,
        "shader_sha256": shader_sha,
        "cases": cases,
        "passed": sum(c["parity"] for c in cases),
        "scope": "12 version-1 synthetic fixtures on the console GPU; not full-connectome "
        "throughput, lifecycle or biological validation",
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
    a = parser.parse_args()
    r = run(a.package, a.shader, a.out)
    print(f"passed {r['passed']} of {len(r['cases'])}")
