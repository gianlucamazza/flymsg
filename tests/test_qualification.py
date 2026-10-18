"""Qualification must cover a fixed matrix, including deliberate native refusals."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def records(v2=True, success="passed"):
    # Explicit expected contract, not derived from the production fixture registry.
    extensions = ("none", "graded", "gap", "spikelets", "both", "gap-all-free")
    cases = [
        {
            "seed": seed,
            "adaptation": adapt,
            "silenced": silent,
            "extension": ext,
            success: True,
        }
        for seed in (3, 7, 19)
        for adapt in (0.0, 2.0)
        for silent in (False, True)
        for ext in (extensions if v2 else ("none",))
    ]
    refused = (
        [
            {
                "seed": seed,
                "adaptation": adapt,
                "silenced": silent,
                "extension": "gap-continuous-refractory",
                "reason": "native continuous-clamp electrical coupling with refractory cells is unqualified",
            }
            for seed in (3, 7, 19)
            for adapt in (0.0, 2.0)
            for silent in (False, True)
        ]
        if v2
        else []
    )
    return cases, refused


@pytest.mark.parametrize("v2", [False, True])
@pytest.mark.parametrize("success", ["passed", "parity"])
def test_complete_matrix_passes(monkeypatch, v2, success):
    module = load("native_acceptance", monkeypatch)
    cases, refused = records(v2, success)
    result = module.qualification(cases, refused, v2=v2, success_field=success)
    assert result["qualified"]
    assert result["expected_cases"] == (72 if v2 else 12)
    assert result["expected_refusals"] == (12 if v2 else 0)


@pytest.mark.parametrize(
    "damage",
    [
        "v1-only",
        "missing",
        "duplicate",
        "replacement",
        "unexpected-refusal",
        "missing-refusal",
        "duplicate-refusal",
        "reason",
        "failed",
        "empty",
    ],
)
def test_incomplete_or_changed_matrix_fails(monkeypatch, damage):
    module = load("native_acceptance", monkeypatch)
    cases, refused = records()
    if damage == "v1-only":
        cases = [c for c in cases if c["extension"] == "none"]
    elif damage == "missing":
        cases.pop()
    elif damage == "duplicate":
        cases.append(cases[0].copy())
    elif damage == "replacement":
        cases[-1] = cases[0].copy()  # same count, different coverage
    elif damage == "unexpected-refusal":
        refused.append({**cases.pop(), "reason": refused[0]["reason"]})
    elif damage == "missing-refusal":
        refused.pop()
    elif damage == "duplicate-refusal":
        refused.append(refused[0].copy())
    elif damage == "reason":
        refused[0]["reason"] = "a different capability was lost"
    elif damage == "failed":
        cases[0]["passed"] = False
    elif damage == "empty":
        cases, refused = [], []
    result = module.qualification(cases, refused)
    assert not result["qualified"]
    assert result["errors"]


@pytest.mark.parametrize(
    "damage",
    [
        "none",
        "v1-only",
        "unexpected-refusal",
        "bad-hash",
        "status-auth",
        "status-transport",
    ],
)
def test_console_report_checks_coverage_and_download(monkeypatch, tmp_path, damage):
    module = load("console_gpu_parity", monkeypatch)
    cases, refused = records(damage != "v1-only")
    matrix = cases + refused

    class Oracle:
        def __init__(self, case):
            self.case = case

        def advance_to(self, step):
            assert step == 1000

    class Portal:
        def mkdir(self, *args):
            pass

        def put(self, *args):
            pass

        def get(self, package, rel, name, path):
            if name == "status.json":
                if damage in ("status-auth", "status-transport"):
                    raise module.PortalError(
                        "GET",
                        "/api/files?private=query",
                        22 if damage == "status-auth" else 7,
                        401 if damage == "status-auth" else 0,
                    )
                path.write_text(json.dumps({"state": "completed"}))
            elif name == "result.json":
                path.write_text(
                    json.dumps(
                        {
                            "output_sha256": "bad"
                            if damage == "bad-hash"
                            else hashlib.sha256(b"gpu").hexdigest()
                        }
                    )
                )
            else:
                assert name == "output.bin"
                path.write_bytes(b"gpu")

    def export(oracle, path):
        if "reason" in oracle.case or (
            damage == "unexpected-refusal" and oracle.case["extension"] == "graded"
        ):
            raise module.NativeCapabilityError(refused[0]["reason"])
        path.write_bytes(b"fixture")
        return {}

    monkeypatch.setattr(module, "Portal", Portal)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        module,
        "fixtures",
        lambda extensions: (
            ((c["seed"], c["adaptation"], c["silenced"], c["extension"]), Oracle(c))
            for c in matrix
        ),
    )
    monkeypatch.setattr(module, "export_fixture", export)
    monkeypatch.setattr(module, "read_output", lambda *a: {})
    monkeypatch.setattr(module, "check", lambda *a: None)
    shader = tmp_path / "lif.cso"
    shader.write_bytes(b"shader")
    if damage in ("status-auth", "status-transport"):
        with pytest.raises(module.PortalError):
            module.run("mock-package", shader, tmp_path, v2=True)
        assert not (tmp_path / "report.json").exists()
        return
    report = module.run("mock-package", shader, tmp_path, v2=True)
    assert report["qualification"]["qualified"] is (damage == "none")
    assert json.loads((tmp_path / "report.json").read_text()) == report


@pytest.mark.parametrize(
    "extension", ["graded", "gap", "spikelets", "both", "gap-all-free"]
)
def test_lifecycle_can_export_supported_v2(monkeypatch, tmp_path, extension):
    module = load("console_lifecycle", monkeypatch)
    from flymsg.native import export_fixture

    monkeypatch.setattr(module, "N", 8)
    monkeypatch.setattr(module, "STEPS", 1000)
    rt = module.oracle(extension)
    meta = export_fixture(rt, tmp_path / "fixture.bin")
    assert meta["schema"] == "flymsg.native_fixture/v2"
    assert rt.step == 0


def test_parity_rejects_opposite_signed_zero(monkeypatch):
    import numpy as np

    module = load("native_acceptance", monkeypatch)
    state = {
        name: np.zeros(1, dtype=np.float32)
        for name in ("v", "g", "th", "ref_until", "counts", "first")
    }
    state.update(ring_len=np.zeros(1, dtype=int), ring=np.zeros((1, 1), dtype=int))
    state["traced"] = np.zeros((0, 1), dtype=bool)

    class Oracle:
        step = 0

        def snapshot(self):
            return state

        def traced_spikes(self, *args):
            return np.zeros((0, 1), dtype=bool)

    actual = {name: value.copy() for name, value in state.items()}
    actual.update(
        step=0,
        traced=np.zeros((0, 1), dtype=bool),
        ring_mask=np.zeros((1, 1), dtype=bool),
    )
    module.check(Oracle(), actual)
    actual["g"][0] = -0.0
    assert np.array_equal(actual["g"], state["g"])
    with pytest.raises(AssertionError, match="g"):
        module.check(Oracle(), actual)


def test_wait_timeout_keeps_the_last_status(monkeypatch, tmp_path):
    module = load("console_lifecycle", monkeypatch)
    job = object.__new__(module.Job)
    seen = {"state": "checkpointing", "step": 1_000_000, "source_commit": "90249e45"}
    job.status = lambda: dict(seen)
    now = {"t": 0.0}

    def clock():
        now["t"] += 500.0
        return now["t"]

    monkeypatch.setattr(module.time, "time", clock)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    got = job.wait({"completed", "failed", "cancelled"})
    assert got["state"] == "timeout"
    assert got["last_state"] == "checkpointing"
    assert got["step"] == 1_000_000
    assert got["source_commit"] == "90249e45"


@pytest.fixture(scope="module")
def publish_exe(tmp_path_factory):
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.fail("native publish tests require g++")
    exe = tmp_path_factory.mktemp("publish") / "flymsg_native"
    subprocess.run(
        [
            compiler,
            "-std=c++20",
            "-O2",
            "-ffp-contract=off",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(SCRIPTS.parent / "native/main.cpp"),
            "-o",
            str(exe),
        ],
        check=True,
    )
    return exe


def test_publish_records_failed_or_completed_from_the_temporary_size(
    publish_exe, tmp_path
):
    # Real start: the temporary file is absent. The byte count is an input to
    # the shipped publish, not a size reconstructed after the fact.
    idle = tmp_path / "idle"
    idle.mkdir()
    destination = idle / "checkpoint.bin"
    temporary = Path(str(destination) + ".tmp")
    assert not destination.exists()
    assert not temporary.exists()
    stalled = subprocess.run(
        [str(publish_exe), "--publish", str(destination), "--publish-bytes", "0"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert stalled.returncode == 0, stalled.stderr
    assert stalled.stdout.strip() == "failed"
    assert not destination.exists()
    assert temporary.is_file()
    assert temporary.stat().st_size == 0

    grown = tmp_path / "grown"
    grown.mkdir()
    replaced = grown / "checkpoint.bin"
    replaced_tmp = Path(str(replaced) + ".tmp")
    assert not replaced.exists()
    assert not replaced_tmp.exists()
    nbytes = "32"
    finished = subprocess.run(
        [
            str(publish_exe),
            "--publish",
            str(replaced),
            "--publish-bytes",
            nbytes,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip() == "completed"
    assert replaced.is_file()
    assert replaced.stat().st_size == int(nbytes)
    assert not replaced_tmp.exists()


def test_throughput_timeout_is_not_a_lineage_mismatch(monkeypatch, tmp_path):
    module = load("console_lifecycle", monkeypatch)

    class Job:
        def __init__(self, *args, **kwargs):
            pass

        def submit(self):
            pass

        def wait(self, states, timeout_s=900.0):
            return {
                "state": "timeout",
                "last_state": "checkpointing",
                "step": 1_000_000,
            }

    monkeypatch.setattr(module, "Portal", lambda: object())
    monkeypatch.setattr(
        module,
        "TrialEpoch",
        lambda *a: type("Epoch", (), {"check": lambda *a: None})(),
    )
    monkeypatch.setattr(module, "Job", Job)
    shader = tmp_path / "lif.cso"
    shader.write_bytes(b"shader")
    out = tmp_path / "trial"
    with pytest.raises(RuntimeError, match="timed out during throughput") as caught:
        module.run(
            "package",
            "app",
            shader,
            out,
            {"worker_source_commit": "90249e45"},
            "graded",
        )
    assert "lineage" not in str(caught.value)
    record = module.failure_record(caught.value)
    assert record == {
        "schema": "flymsg.console_lifecycle/v1",
        "state": "interrupted",
        "passed": False,
        "error_type": "RuntimeError",
        "error": str(caught.value),
    }
    assert not (out / "report.json").exists()


def test_lifecycle_rejects_download_corruption_before_advancing_oracle(
    monkeypatch, tmp_path
):
    module = load("console_lifecycle", monkeypatch)
    job = object.__new__(module.Job)
    job.folder, job.package, job.rel = tmp_path, "mock", "inbox"

    class Portal:
        def get(self, package, rel, name, path):
            path.write_bytes(b"corrupt")

    job.portal = Portal()
    job.result = lambda: {"output_sha256": hashlib.sha256(b"original").hexdigest()}
    assert job.parity() is False


def test_force_stop_is_explicit_and_scoped_to_one_package(monkeypatch):
    module = load("console_lifecycle", monkeypatch)
    calls = []

    class Portal:
        def curl(self, *args):
            calls.append(args)

    module.app_call(Portal(), "DELETE", "owned-package", "owned-app")
    module.app_call(Portal(), "DELETE", "owned-package", "owned-app", force=True)
    assert calls[1] == ("DELETE", calls[0][1] + "&forcestop=yes")
    assert calls[0][1].startswith("/api/taskmanager/app?package=")


@pytest.mark.parametrize(
    "failure,match",
    [
        ("transport", "injected transport"),
        ("source", "source changed"),
        ("timeout", "did not park"),
    ],
)
def test_lifecycle_preserves_progress_when_recovery_fails(
    monkeypatch, tmp_path, failure, match
):
    module = load("console_lifecycle", monkeypatch)
    created = []

    class Job:
        def __init__(self, *args, **kwargs):
            self.index, self.calls = len(created), 0
            self.id = str(self.index)
            created.append(self)

        def submit(self):
            pass

        def wait(self, *args, **kwargs):
            states = [
                ["completed"],
                ["running", "cancelled"],
                ["running", "awaiting_recovery"],
            ]
            state = states[self.index][self.calls]
            self.calls += 1
            if self.index == 2 and self.calls == 2 and failure == "timeout":
                state = "timeout"
            source = (
                "changed"
                if self.index == 2 and self.calls == 2 and failure == "source"
                else "fixture"
            )
            return {"state": state, "step": 123, "source_commit": source}

        def result(self):
            return {"advance_steps": 1000, "advance_ms": 100}

        def parity(self):
            return True

        def control(self, name, schema):
            if name == "resume.json":
                assert failure == "transport"
                raise RuntimeError("injected transport failure")

    monkeypatch.setattr(module, "Portal", lambda: object())
    monkeypatch.setattr(
        module, "TrialEpoch", lambda *a: type("Epoch", (), {"check": lambda *a: None})()
    )
    monkeypatch.setattr(module, "Job", Job)
    monkeypatch.setattr(module, "app_call", lambda *a, **kw: None)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    shader = tmp_path / "lif.cso"
    shader.write_bytes(b"shader")
    out = tmp_path / "trial"
    with pytest.raises(RuntimeError, match=match):
        module.run("package", "app", shader, out, {})
    progress = json.loads((out / "progress.json").read_text())
    assert progress["throughput"]["parity"]
    assert progress["cancel"]["ok"]
    assert progress["phase"] == "resume_upload"
    assert progress["passed"] is False
    assert not (out / "report.json").exists()
    with pytest.raises(ValueError, match="already exists"):
        module.run("package", "app", shader, out, {})


def test_remote_epoch_detects_replaced_app_context(monkeypatch, tmp_path):
    module = load("console_lifecycle", monkeypatch)
    remote = {}

    class Portal:
        def put(self, package, rel, path):
            remote[path.name] = path.read_bytes()

        def get(self, package, rel, name, path):
            path.write_bytes(remote[name])

    epoch = module.TrialEpoch(
        Portal(), "package", tmp_path, {"source": "pinned"}, "shader"
    )
    epoch.check("before-stop")
    remote[epoch.name] = b"{}"
    with pytest.raises(RuntimeError, match="epoch changed"):
        epoch.check("after-restart")


def test_sustained_windows_use_running_steps_only(monkeypatch):
    module = load("console_sustained", monkeypatch)
    samples = [{"t": 0.0, "state": "validating", "step": 0}]
    samples += [
        {"t": float(t), "state": "running", "step": 100 * t} for t in range(1, 131)
    ]
    samples.append({"t": 131.0, "state": "completed", "step": 13_100})
    assert module.windows(samples, 60.0) == [100.0, 100.0]
    assert module.summary([4.0, 2.0])["last_over_first"] == 0.5
    assert module.summary([]) == {}
    assert module.summary([0.0, 5.0])["last_over_first"] is None


@pytest.mark.parametrize(
    "damage", ["none", "other_output", "failed", "oracle", "upload", "cleanup"]
)
def test_sustained_case_fails_closed(monkeypatch, tmp_path, damage):
    module = load("console_sustained", monkeypatch)
    case = {
        "name": "c",
        "stimulus": "s",
        "seed": 1,
        "steps": 10,
        "jobs": 3,
        "per_bin": 1,
    }

    class FirstJob:
        pass

    def one_job(portal, args, sha, out, rt, case, index):
        failed = damage in ("failed", "upload") and index == 1
        record = {
            "index": index,
            "final_state": (
                {"failed": "failed", "upload": "upload_failed"}[damage]
                if failed
                else "completed"
            ),
            "reported_sha_matches": True,
            "output_sha256": "b" if damage == "other_output" and index == 2 else "a",
            "upload_s": 1.0,
            "first_running_s": 1.0,
            "samples": [{"app_memory_bytes": 1}],
            "window_steps_per_s": [],
        }
        if not failed:
            record["advance_steps_per_s"] = 2000.0
        if damage == "cleanup" and index == 2:
            record["cleanup_errors"] = ["DELETE failed"]
        return record, FirstJob()

    class Model:
        def runtime(self, case):
            return None

    monkeypatch.setattr(module, "one_job", one_job)
    monkeypatch.setattr(module, "parity", lambda job: damage != "oracle")
    args = type("A", (), {"out": tmp_path})()
    result = module.run_case(None, args, "sha", Model(), case)
    assert result["verdict"] == ("pass" if damage == "none" else "fail")
    if damage in ("failed", "upload"):
        assert len(result["jobs"]) == 2


@pytest.mark.parametrize("fault", ["result", "download", "hash"])
def test_sustained_readback_fault_is_recorded(monkeypatch, tmp_path, fault):
    module = load("console_sustained", monkeypatch)
    deleted = []

    class Portal:
        def curl(self, method, path):
            return json.dumps(
                {
                    "GPUData": {"AvailableAdapters": [{}]},
                    "CpuLoad": 1,
                    "AvailablePages": 1,
                    "PageSize": 4096,
                }
            )

        def get(self, package, rel, name, local):
            if fault == "download":
                raise module.PortalError("GET", "/x", 22, 500)
            local.write_bytes(b"output")

        def delete(self, package, rel, name):
            deleted.append(name)

    class Job:
        def __init__(self, portal, package, sha, out, rt, **kw):
            self.id, self.rel, self.folder = "j", "inbox\\j", tmp_path
            self.fixture = tmp_path / "fixture.bin"
            self.fixture.write_bytes(b"f")

        def submit(self):
            pass

        def status(self):
            return {"state": "completed", "step": 10, "app_memory_bytes": 1}

        def result(self):
            if fault == "result":
                raise module.PortalError("GET", "/r", 22, 404)
            sha = "0" * 64 if fault == "hash" else hashlib.sha256(b"output").hexdigest()
            return {"advance_steps": 10, "advance_ms": 5.0, "output_sha256": sha}

    monkeypatch.setattr(module, "Job", Job)
    args = type("A", (), {"package": "p"})()
    case = {"steps": 10, "seed": 1}
    record, _ = module.one_job(Portal(), args, "sha", tmp_path, None, case, 0)
    if fault == "hash":
        assert record["final_state"] == "completed"
        assert record["reported_sha_matches"] is False
    else:
        assert record["final_state"] == "readback_failed"
    assert deleted == []


@pytest.mark.parametrize("count", [0, 2])
def test_hardstop_pid_resolution_refuses_missing_or_ambiguous(monkeypatch, count):
    module = load("console_hardstop", monkeypatch)

    class FakePortal:
        def curl(self, method, path):
            assert (method, path) == ("GET", "/api/resourcemanager/processes")
            return json.dumps(
                {
                    "Processes": [
                        {"ImageName": "C:\\worker\\Worker.exe", "ProcessId": i + 1}
                        for i in range(count)
                    ]
                    + [{"ImageName": "Other.exe", "ProcessId": 99}]
                }
            )

    matches = module.processes(FakePortal(), "worker.exe")
    with pytest.raises(ValueError, match="exactly one"):
        module.resolve_pid(matches)


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("refused", "blocked"),
        ("survives", "indeterminate"),
        ("suspended", "indeterminate"),
        ("recovery", "pass"),
        ("mismatch", "fail"),
        ("checkpointing", "indeterminate"),
        ("wrong-restoration", "fail"),
    ],
)
@pytest.mark.parametrize("case", ["A", "B"])
def test_hardstop_fake_portal_paths(monkeypatch, tmp_path, scenario, expected, case):
    from types import SimpleNamespace

    module = load("console_hardstop", monkeypatch)
    lifecycle = __import__("console_lifecycle")
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        module, "oracle", lambda: SimpleNamespace(advance_to=lambda _: None)
    )
    monkeypatch.setattr(lifecycle, "read_output", lambda *args: object())

    def check(*args):
        if scenario == "mismatch":
            raise AssertionError("independent oracle mismatch")

    monkeypatch.setattr(lifecycle, "check", check)
    checkpoint = b"complete checkpoint"
    checkpoint_sha = hashlib.sha256(checkpoint).hexdigest()
    saved = {
        "fixture_sha256": "fixture",
        "shader_sha256": "shader",
        "backend": "dx12",
        "package": "package",
        "source_commit": "source",
        "checkpoint_sha256": checkpoint_sha,
    }

    class FakePortal:
        state = "running"
        alive = True
        killed = False
        checkpoint_exists = False
        resumed = False

        def __init__(self):
            self.calls = []

        def curl(self, method, path):
            self.calls.append((method, path))
            if path == "/api/resourcemanager/processes":
                return json.dumps(
                    {
                        "Processes": [{"ImageName": "Worker.exe", "ProcessId": 42}]
                        if self.alive
                        else []
                    }
                )
            if path.startswith("/api/filesystem/apps/files?"):
                names = ["job.json", "fixture.bin", "status.json", "unrelated.tmp"]
                if self.checkpoint_exists:
                    names += ["checkpoint.json", "checkpoint.bin"]
                return json.dumps({"Items": [{"Name": n} for n in names]})
            if path == "/api/taskmanager/process?pid=42":
                assert method == "DELETE"
                if scenario == "refused":
                    raise module.PortalError(method, path, 22, 403)
                self.killed = True
                self.alive = scenario == "survives"
                self.state = (
                    "suspended"
                    if scenario == "suspended"
                    else ("checkpointing" if scenario == "checkpointing" else "running")
                )
                return ""
            assert path.startswith("/api/taskmanager/app?")
            if method == "DELETE":
                self.checkpoint_exists = True
                self.state = "suspended"
                self.alive = False
            else:
                self.alive = True
                if self.killed:
                    self.state = "awaiting_recovery"
            return ""

        def get(self, package, rel, name, local):
            if name == "checkpoint.bin":
                local.write_bytes(checkpoint)
            elif name == "checkpoint.json":
                local.write_text(json.dumps(saved))
            elif name == "status.json":
                local.write_text(json.dumps({"state": self.state}))
            elif name == "output.bin":
                local.write_bytes(b"output")
            else:
                raise AssertionError(name)

    real_parity = module.Job.parity

    class FakeJob:
        id = "job"
        rel = "inbox\\job"
        steps = 1_000_000
        parity = real_parity

        def __init__(self, portal, package, sha, out, rt):
            self.portal, self.package, self.rt = portal, package, rt
            self.job = {"fixture_sha256": "fixture", "shader_sha256": "shader"}
            self.folder = out / self.id
            self.folder.mkdir()
            self.fixture = self.folder / "fixture.bin"

        def submit(self):
            return 0

        def status(self):
            state = self.portal.state
            step = {
                "running": 200 if self.portal.resumed else 100,
                "suspended": 100,
                "awaiting_recovery": 0,
                "checkpointing": 200,
                "completed": self.steps,
            }[state]
            return {
                "state": state,
                "step": step,
                "source_commit": "source",
                "job_id": self.id,
            }

        def control(self, name, schema):
            assert (name, schema) == ("resume.json", "flymsg.worker_resume/v1")
            self.portal.resumed = True
            self.portal.state = "completed" if self.portal.killed else "running"

        def result(self):
            restored = 100 if case == "B" else 0
            return {
                "advance_steps": self.steps
                - restored
                - (1 if scenario == "wrong-restoration" else 0),
                "output_sha256": hashlib.sha256(b"output").hexdigest(),
            }

    monkeypatch.setattr(module, "Job", FakeJob)
    epochs = []
    epoch = SimpleNamespace(check=epochs.append, expected={"epoch": "trial"})
    args = SimpleNamespace(
        package="package",
        aumid="app",
        out=tmp_path,
        worker_image="Worker.exe",
        lineage={"worker_source_commit": "source"},
    )
    record = {}
    portal = FakePortal()
    assert module.run_case(portal, args, "shader", epoch, case, record) == expected
    assert record["processes_before"] == [{"image": "Worker.exe", "pid": 42}]
    assert "unrelated.tmp" in record["snapshots"]["after-kill"]["files"]
    assert record["status_history"]
    assert f"{case}-after-kill" in epochs
    if expected == "pass":
        assert record["restoration_step"] == (100 if case == "B" else 0)
        assert record["oracle_parity"]
    if case == "B":
        assert record["checkpoint_sha256"] == checkpoint_sha


def test_hardstop_existing_output_refused_before_contact(monkeypatch, tmp_path):
    from types import SimpleNamespace

    module = load("console_hardstop", monkeypatch)

    def forbidden():
        raise AssertionError("Portal must not be constructed")

    monkeypatch.setattr(module, "Portal", forbidden)
    with pytest.raises(FileExistsError):
        module.run(SimpleNamespace(out=tmp_path))


@pytest.mark.parametrize("interrupted", [False, True])
def test_hardstop_always_stops_app_and_retains_safe_report(
    monkeypatch, tmp_path, interrupted
):
    from types import SimpleNamespace

    module = load("console_hardstop", monkeypatch)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    calls = []

    class FakePortal:
        def curl(self, method, path):
            calls.append((method, path))
            if path == "/api/resourcemanager/processes":
                return json.dumps({"Processes": []})
            assert path.startswith("/api/taskmanager/app?")
            return ""

        def close(self):
            calls.append(("close", ""))

    monkeypatch.setattr(module, "Portal", FakePortal)
    monkeypatch.setattr(
        module,
        "TrialEpoch",
        lambda *args: SimpleNamespace(expected={"epoch": "trial", "lineage": args[3]}),
    )

    def trial(*args):
        if interrupted:
            raise RuntimeError("https://private-address/ secret-credential")
        return "pass"

    monkeypatch.setattr(module, "run_case", trial)
    shader = tmp_path / "lif.cso"
    shader.write_bytes(b"shader")
    args = SimpleNamespace(
        out=tmp_path / "new",
        shader=shader,
        package="package",
        aumid="app",
        worker_image="Worker.exe",
        lineage={"worker_source_commit": "abcdef01", "private": "secret-credential"},
    )
    report = module.run(args)
    assert report["verdict"] == ("indeterminate" if interrupted else "pass")
    assert calls[-3][0] == "DELETE"
    assert calls[-2] == ("GET", "/api/resourcemanager/processes")
    assert calls[-1] == ("close", "")
    stored = (args.out / "report.json").read_text()
    assert "private-address" not in stored
    assert "secret-credential" not in stored
    assert json.loads(stored)["schema"] == "flymsg.console_hardstop/v1"
