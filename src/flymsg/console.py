"""The console worker as a backend: Device Portal access and batch jobs (#40).

A batch (`native.export_batch`) carries one network and its runs; the worker on the console
runs them on its GPU and returns one output per run, bit for bit with the CPU oracle
(qualified in docs/evidence/series-s-*.json). Device Portal settings come from the
environment only: `XBOX_IP`, `XBOX_USER`, `XBOX_PASS` and, to pin the device's TLS key,
`FLYMSG_DEVICE_PIN` (curl's `--pinnedpubkey` form). Nothing private is written anywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import numpy as np

from flymsg import native, sim
from flymsg.runtime import CpuRuntime

STOPPED = ("completed", "failed", "cancelled", "suspended", "awaiting_recovery")
ADAPTER = "SraKmd_arden"  # Xbox Series S, as the FloppyLM trainer's evidence records
PACKAGE_ENV = "FLYMSG_WORKER_PACKAGE"  # the installed worker's PackageFullName
SHADER_ENV = "FLYMSG_WORKER_SHADER"  # a local copy of that package's lif.cso


class Portal:
    """The few Device Portal calls a job needs, through curl."""

    def __init__(self) -> None:
        self.base = f"https://{os.environ['XBOX_IP']}:11443"
        # given to curl on stdin (-K -), never on its command line where ps shows it
        self.config = f'user = "{os.environ["XBOX_USER"]}:{os.environ["XBOX_PASS"]}"\n'
        fd, self.jar = tempfile.mkstemp(prefix="wdp")
        os.close(fd)
        self.pin = os.environ.get("FLYMSG_DEVICE_PIN")
        self.curl("GET", "/", out=os.devnull)
        token = [
            line.split("\t")[6]
            for line in Path(self.jar).read_text().splitlines()
            if "\tCSRF-Token\t" in line
        ]
        self.token = token[0] if token else ""

    def curl(self, method, path, out=None, upload=None) -> str:
        # an upload of a whole network can take minutes over a local network
        limit = "1800" if upload else "120"
        cmd = ["curl", "-sS", "-k", "--fail", "-m", limit, "-K", "-"]
        if self.pin:  # -k skips the CA chain only; curl still enforces the pinned key
            cmd += ["--pinnedpubkey", self.pin]
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
            [*cmd, self.base + path],
            input=self.config,
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode:
            raise RuntimeError(f"{method} {path.split('?')[0]} failed ({r.returncode})")
        return r.stdout

    def close(self) -> None:
        """Remove the session's cookie jar."""
        Path(self.jar).unlink(missing_ok=True)

    def __del__(self):
        self.close()

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
            f"&packagefullname={package}&path={path}&extract=false",
            upload=str(local),
        )

    def delete(self, package: str, rel: str, name: str) -> None:
        path = "%5CLocalState%5C" + rel.replace("\\", "%5C")
        self.curl(
            "DELETE",
            f"/api/filesystem/apps/file?knownfolderid=LocalAppData"
            f"&packagefullname={package}&path={path}&filename={name}",
        )

    def get(self, package: str, rel: str, name: str, local: Path) -> None:
        path = "%5CLocalState%5C" + rel.replace("\\", "%5C")
        self.curl(
            "GET",
            f"/api/filesystem/apps/file?knownfolderid=LocalAppData"
            f"&packagefullname={package}&path={path}&filename={name}",
            out=str(local),
        )


def lineage(backend: str) -> dict:
    """What a manifest records of the backend: the worker package and the shader's
    hash for the console (never an address or a credential), nothing for the CPU."""
    if backend not in ("console", "hybrid"):
        return {}
    shader = Path(os.environ[SHADER_ENV])
    return {
        "backend": backend,
        "worker_package": os.environ[PACKAGE_ENV],
        "worker_shader_sha256": hashlib.sha256(shader.read_bytes()).hexdigest(),
        "worker_adapter": ADAPTER,
    }


_DEVICE = None


def device() -> Device:
    """This process's Device, made once from the environment: one Device Portal session
    and cookie jar for a whole run, not one per graph."""
    global _DEVICE
    if _DEVICE is None:
        _DEVICE = Device()
    return _DEVICE


class Device:
    """The installed worker: where its inbox is and which shader it runs."""

    def __init__(
        self,
        package: str | None = None,
        shader: Path | None = None,
        adapter: str = ADAPTER,
        portal: Portal | None = None,
    ):
        self.package = package or os.environ[PACKAGE_ENV]
        shader = Path(shader or os.environ[SHADER_ENV])
        self.shader_sha = hashlib.sha256(shader.read_bytes()).hexdigest()
        self.adapter = adapter
        self.portal = portal or Portal()

    def status(self, rel: str, local: Path) -> dict:
        try:
            self.portal.get(self.package, rel, "status.json", local)
            return json.loads(local.read_text())
        except (RuntimeError, json.JSONDecodeError):
            return {}  # not written yet, or caught mid-replacement


def run_batch(
    device: Device,
    runtimes: list[CpuRuntime],
    out: Path,
    *,
    dataset: str,
    seed: int,
    scope: str,
    timeout_s: float = 7200.0,
    output: str = "state",
) -> tuple[list[Path], list[Path], dict]:
    """Run fresh runtimes of one network on the console: each run's output file, the
    fixture it decodes against, and the job's result. `output` is "state" (the whole
    state, `native.read_output`) or "counts" (counts and first spikes,
    `native.read_counts`)."""
    if output not in ("state", "counts"):
        raise ValueError(f"unknown batch output {output!r}")
    job_id = str(uuid.uuid4())
    folder = out / job_id
    folder.mkdir(parents=True)
    base, batch = folder / "fixture.bin", folder / "batch.bin"
    metas = native.export_batch(runtimes, base, batch)
    job = {
        "schema": "flymsg.neural_job/v1",
        "job_id": job_id,
        "semantics": "flymsg.lif/ordered-f32-v1",
        "backend": "dx12",
        "fixture_sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
        "batch": {
            "sha256": hashlib.sha256(batch.read_bytes()).hexdigest(),
            "runs": len(runtimes),
            # "counts": sparse counts and first spikes per run instead of whole states
            "output": output,
        },
        "shader_sha256": device.shader_sha,
        "expected_adapter": device.adapter,
        "dataset": dataset,
        "seed": seed,
        "neural_tick_us": runtimes[0].tick_us,
        "fixture": metas[0],
        "scope": scope,
    }
    (folder / "job.json").write_text(json.dumps(job, sort_keys=True, indent=2) + "\n")
    rel = f"inbox\\{job_id}"
    p = device.portal
    remote = ["fixture.bin", "batch.bin"]
    outputs, fixtures = [], []
    try:
        p.mkdir(device.package, rel)
        p.put(device.package, rel, base)
        p.put(device.package, rel, batch)
        p.put(device.package, rel, folder / "job.json")  # last: the worker starts on it
        start, status = time.time(), {}
        while time.time() - start < timeout_s:
            time.sleep(2)
            status = device.status(rel, folder / "status.json")
            # a parked job (suspended, awaiting_recovery) waits for a resume.json this
            # backend never writes: stop instead of waiting out the timeout
            if status.get("state") in STOPPED:
                break
        if status.get("state") != "completed":
            raise RuntimeError(
                f"console batch {job_id}: {status.get('state', 'timeout')} "
                f"{status.get('error', '')}".strip()
            )
        p.get(device.package, rel, "result.json", folder / "result.json")
        for k in range(len(runtimes)):
            name = f"{'counts' if output == 'counts' else 'output'}_{k}.bin"
            out_path, fixture = folder / name, folder / f"fixture_{k}.bin"
            remote.append(name)
            p.get(device.package, rel, name, out_path)
            # a version-1 output decodes against its fixture's header alone
            fixture.write_bytes(
                native.batch_fixture(base, batch, k)[: native.HEADER_WORDS].tobytes()
            )
            outputs.append(out_path)
            fixtures.append(fixture)
        return outputs, fixtures, json.loads((folder / "result.json").read_text())
    except BaseException:
        for path in [*outputs, *fixtures]:
            path.unlink(missing_ok=True)
        raise
    finally:
        # the console keeps the small records (job, status, results); its copies of
        # the network and the outputs would fill its storage over a long run
        for name in remote:
            try:
                p.delete(device.package, rel, name)
            except RuntimeError:
                pass  # cleanup only: a file left behind costs space, not correctness
        base.unlink(missing_ok=True)
        batch.unlink(missing_ok=True)


def sim_runtime(
    W, stim, rate_hz: float, duration_ms: float, stim_ms: float | None, p, seed: int
) -> CpuRuntime:
    """The fresh runtime `sim.run(W, stim, rate_hz, duration_ms, stim_ms, p, seed)` steps
    (10 ms count bins): the same draw, the same masks (tests/test_runtime.py)."""
    stim = np.unique(stim)
    steps = int(duration_ms / p.dt)
    stim_steps = steps if stim_ms is None else int(stim_ms / p.dt)
    kicks = sim.poisson_kicks(seed, rate_hz, p.dt, stim_steps, int(stim.size))
    per_bin = max(1, round(10.0 / p.dt))
    if steps % per_bin:
        raise ValueError("duration_ms must be a multiple of the 10 ms bin")
    return CpuRuntime(W, stim, steps=steps, kicks=kicks, p=p, per_bin=per_bin)


def sim_runs(
    device: Device,
    W,
    specs: list[tuple],
    p,
    out: Path,
    *,
    dataset: str,
    seed: int,
    scope: str,
) -> tuple[Results, dict]:
    """`sim.run(W, stim, rate_hz, duration_ms, stim_ms, p, seed)` for each spec
    `(stim, rate_hz, duration_ms, stim_ms, seed)`, as one batch on the console. The runs
    must share a horizon; the results are `sim.run`'s, bit for bit."""
    runtimes = [sim_runtime(W, *spec[:4], p, spec[4]) for spec in specs]
    # a sim.Result needs only the counts and first spikes: the sparse output, a few
    # kilobytes per run instead of the whole state (tens of megabytes)
    outputs, fixtures, result = run_batch(
        device, runtimes, out, dataset=dataset, seed=seed, scope=scope, output="counts"
    )
    stim_ms = [
        (spec[2] if spec[3] is None else int(spec[3] / p.dt) * p.dt) for spec in specs
    ]
    return as_results(outputs, fixtures, p.dt, stim_ms), result


class Results:
    """Runs' outputs read as `sim.Result`s on demand: a whole-CNS run's counts are tens of
    megabytes, so a batch is decoded one run, or one slice, at a time."""

    def __init__(
        self, outputs: list[Path], fixtures: list[Path], dt_ms: float, stim_ms
    ):
        self.outputs, self.fixtures, self.dt, self.stim_ms = (
            outputs,
            fixtures,
            dt_ms,
            stim_ms,
        )

    def close(self) -> None:
        """Remove the local outputs and fixtures once the results have been read."""
        for path in [*self.outputs, *self.fixtures]:
            path.unlink(missing_ok=True)

    def __len__(self) -> int:
        return len(self.outputs)

    def __getitem__(self, k):
        if isinstance(k, slice):
            return [self[i] for i in range(*k.indices(len(self)))]
        path = self.outputs[k]
        out = (
            native.read_counts(path, self.fixtures[k])
            if path.name.startswith("counts_")
            else native.read_output(path, self.fixtures[k])
        )
        return native.as_result(out, self.fixtures[k], self.dt, self.stim_ms[k])


def as_results(
    outputs: list[Path], fixtures: list[Path], dt_ms: float, stim_ms: list[float]
) -> Results:
    """The runs' outputs as `sim.Result`s, decoded on demand."""
    return Results(outputs, fixtures, dt_ms, stim_ms)
