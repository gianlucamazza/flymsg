import json
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse
from test_core import chain

from flymsg.native import NativeCapabilityError, export_fixture, read_output
from flymsg.runtime import CpuRuntime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def native_exe(tmp_path_factory):
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip(
            "native reference tests require g++; dedicated native CI covers Windows"
        )
    exe = tmp_path_factory.mktemp("native") / "flymsg_native"
    subprocess.run(
        [
            compiler,
            "-std=c++20",
            "-O2",
            "-ffp-contract=off",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "native/main.cpp"),
            "-o",
            str(exe),
        ],
        check=True,
    )
    return exe


def test_native_full_acceptance(native_exe, tmp_path):
    subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/native_acceptance.py",
            "--exe",
            str(native_exe),
            "--out",
            str(tmp_path / "report.json"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["passed"] == 72
    assert report["qualification"] == {
        "qualified": True,
        "expected_cases": 72,
        "expected_refusals": 12,
        "errors": [],
    }
    assert len(report["unsupported"]) == 12
    assert {c["extension"] for c in report["unsupported"]} == {
        "gap-continuous-refractory"
    }
    assert {
        c["electrical_mode"]
        for c in report["cases"]
        if c["extension"] in {"gap", "spikelets", "both"}
    } == {"boundary"}


@pytest.mark.parametrize(
    "slot,value", [(0, 0), (1, 99), (16, 1), (25, 1), (35, 0xFFFFFFFF)]
)
def test_native_rejects_invalid_contract_before_output(
    native_exe, tmp_path, slot, value
):
    runtime = CpuRuntime(
        sparse.eye(2, format="csc"),
        np.array([0]),
        steps=100,
        kicks=np.ones((100, 1), dtype=np.int64),
        per_bin=100,
    )
    fixture, output = tmp_path / "fixture.bin", tmp_path / "out.bin"
    export_fixture(runtime, fixture)
    raw = bytearray(fixture.read_bytes())
    struct.pack_into("<I", raw, slot * 4, value)
    fixture.write_bytes(raw)
    result = subprocess.run(
        [str(native_exe), "--fixture", str(fixture), "--output", str(output)],
        check=False,
        capture_output=True,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_fixture_requires_fresh_state_and_valid_output(tmp_path):
    runtime = CpuRuntime(
        sparse.eye(2, format="csc"),
        np.array([0]),
        steps=100,
        kicks=np.ones((100, 1), dtype=np.int64),
        per_bin=100,
    )
    fixture = tmp_path / "fixture.bin"
    export_fixture(runtime, fixture)
    output = tmp_path / "bad.bin"
    output.write_bytes(b"bad")
    with pytest.raises(ValueError):
        read_output(output, fixture)
    runtime.advance_to(1)
    with pytest.raises(ValueError, match="fresh"):
        export_fixture(runtime, fixture)


@pytest.mark.parametrize("word", ["offset", "ng", "span", "width"])
def test_native_rejects_a_corrupt_version_2_extension(native_exe, tmp_path, word):
    from flymsg import sim

    W = sparse.csc_matrix(np.full((4, 4), 5.0, dtype=np.float32))
    runtime = CpuRuntime(
        W,
        np.array([0]),
        steps=100,
        kicks=np.ones((100, 1), dtype=np.int64),
        per_bin=100,
        # This corruption fixture needs an exportable all-free electrical component.
        graded=sim.Graded(
            idx=np.array([1, 2, 3]), v_lo=-60.0, span=10.0, rate_hz=[0.0, 100.0, 0.0]
        ),
        gap=sim.Gap(i=np.array([1]), j=np.array([3]), coupling=0.5),
    )
    fixture, output = tmp_path / "fixture.bin", tmp_path / "out.bin"
    export_fixture(runtime, fixture)
    raw = bytearray(fixture.read_bytes())
    ext = struct.unpack_from("<I", raw, 37 * 4)[0]
    # extension: 5 header words, then the graded column of each of the 4 neurons, v_lo,
    # span
    at = {
        "offset": 37 * 4,
        "ng": ext * 4,
        "span": (ext + 5 + 4 + 3) * 4,
        "width": (ext + 4) * 4,  # a spike term without any amplitude
    }[word]
    value = {"offset": ext + 1, "ng": 5, "span": 0, "width": 5}[word]
    struct.pack_into("<I", raw, at, value)
    fixture.write_bytes(raw)
    result = subprocess.run(
        [str(native_exe), "--fixture", str(fixture), "--output", str(output)],
        check=False,
        capture_output=True,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_the_console_parity_script_builds_version_one_and_two_fixtures(tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "console_gpu_parity.py"
    spec = importlib.util.spec_from_file_location("console_gpu_parity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # puts scripts/ on the path for its siblings
    assert len(list(module.fixtures())) == 12
    versions = {1: 0, 2: 0}
    for (seed, _, _, ext), oracle in module.fixtures(tuple(module.EXTENSIONS)):
        fixture = tmp_path / f"{seed}.bin"
        try:
            export_fixture(oracle, fixture)
        except NativeCapabilityError:
            continue  # the dynamic clamp, refused on every native lane
        header = np.frombuffer(fixture.read_bytes(), dtype="<u4")
        assert int(header[1]) == (1 if ext == "none" else 2)
        versions[int(header[1])] += 1
    # the acceptance's 60 version-2 cases, as the CPU executor runs them
    assert versions == {1: 12, 2: 60}


def test_the_console_lifecycle_fixture_is_version_one_and_long(tmp_path):
    import importlib.util
    import sys

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts))  # the script imports its siblings
    try:
        spec = importlib.util.spec_from_file_location(
            "console_lifecycle", scripts / "console_lifecycle.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(scripts))
    oracle = module.oracle()
    fixture = tmp_path / "lifecycle.bin"
    meta = export_fixture(oracle, fixture)
    header = np.frombuffer(fixture.read_bytes()[:64], dtype="<u4")
    assert int(header[1]) == 1  # the default lifecycle fixture remains version 1
    assert meta["steps"] == module.STEPS
    # at least 20 s of advance at the 44k steps/s measured on the console, so a cancel
    # or stop sent after a 1 s status poll lands mid-run
    assert module.STEPS >= 20 * 44_000


def test_the_console_bench_drives_a_battery_case():
    import importlib.util
    import sys

    from flymsg import sensitivity

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location(
            "console_bench", scripts / "console_bench.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(scripts))
    assert module.CASE in sensitivity.load()["cases"]["positive"]


def test_a_native_run_replays_as_a_simulation_result(tmp_path):
    from flymsg import native, sim

    edges, sign, n = chain([400, 400])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    p = sim.Params()
    oracle = CpuRuntime(
        W,
        np.array([0]),
        steps=600,
        kicks=sim.poisson_kicks(1, 200.0, p.dt, 600, 1),
        p=p,
        per_bin=100,
    )
    fixture = tmp_path / "fixture.bin"
    native.export_fixture(oracle, fixture)
    assert native.stimulated(fixture).tolist() == [0]
    assert native.input_ms(fixture, p.dt) <= 60.0  # kicks for 600 steps of 0.1 ms
    assert native.input_ms(fixture, p.dt) > 50.0
    oracle.advance_to(600)
    snap = oracle.snapshot()
    result = native.as_result(snap, fixture, p.dt, stim_ms=30.0)
    assert result.bin_ms == 10.0 and result.stim_ms == 30.0
    assert np.array_equal(result.counts, snap["counts"])
    fired = snap["first"] >= 0
    assert np.allclose(result.first_spike_ms[fired], snap["first"][fired] * p.dt)
    assert np.isnan(result.first_spike_ms[~fired]).all()


def _acceptance():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "native_acceptance", ROOT / "scripts" / "native_acceptance.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _battery_runs():
    """Runs of one network as a battery makes them: different stimulus sets, seeds and
    input lengths, the same horizon."""
    return list(_battery_runtimes())


def _battery_runtimes():
    """`_battery_runs`, built one at a time."""
    from flymsg import sim

    rng = np.random.default_rng(5)
    W = sparse.random(60, 60, density=0.15, random_state=rng, format="csc")
    W.data = rng.integers(-20, 80, W.data.size).astype(np.float32)
    W = W.astype(np.float32)
    p = sim.Params()
    for k, (stim, stim_steps) in enumerate(
        [([0, 1, 2], 300), ([5], 300), ([7, 9], 120), ([0, 1, 2], 300)]
    ):
        yield CpuRuntime(
            W,
            np.array(stim),
            steps=400,
            kicks=sim.poisson_kicks(30 + k, 300.0, p.dt, stim_steps, len(stim)),
            p=p,
            per_bin=100,
            trace=np.arange(4),
        )


def test_a_batch_rebuilds_every_run_word_for_word(tmp_path):
    from flymsg import native

    runs = _battery_runs()
    native.export_batch(runs, tmp_path / "base.bin", tmp_path / "batch.bin")
    for k, rt in enumerate(_battery_runs()):
        single = tmp_path / f"single{k}.bin"
        export_fixture(rt, single)
        expected = np.frombuffer(single.read_bytes(), dtype="<u4")
        rebuilt = native.batch_fixture(tmp_path / "base.bin", tmp_path / "batch.bin", k)
        assert np.array_equal(rebuilt, expected)
    with pytest.raises(ValueError, match="invalid batch or run"):
        native.batch_fixture(tmp_path / "base.bin", tmp_path / "batch.bin", 4)
    # the batch carries the network once
    assert (tmp_path / "batch.bin").stat().st_size < 4 * (
        tmp_path / "base.bin"
    ).stat().st_size


def test_a_batch_from_a_generator_is_the_batch_from_a_list(tmp_path):
    """Runs built one at a time, as the export asks, give the same bytes."""
    from flymsg import native

    listed, lazy = tmp_path / "listed", tmp_path / "lazy"
    listed.mkdir(), lazy.mkdir()
    native.export_batch(_battery_runs(), listed / "base.bin", listed / "batch.bin")
    native.export_batch(iter(_battery_runs()), lazy / "base.bin", lazy / "batch.bin")
    for name in ("base.bin", "batch.bin"):
        assert (listed / name).read_bytes() == (lazy / name).read_bytes()
    with pytest.raises(ValueError, match="at least one run"):
        native.export_batch(iter([]), lazy / "base.bin", lazy / "batch.bin")


def test_a_lazy_batch_holds_the_first_run_and_the_current_one():
    """While a run is built, only the base's runtime is alive besides it: a whole
    network copy each, so a battery's preparation does not grow with its runs."""
    import gc
    import weakref

    from flymsg import native

    alive = weakref.WeakSet()
    seen = []

    def lazy():
        for rt in _battery_runtimes():
            gc.collect()
            seen.append(len(alive))
            alive.add(rt)
            yield rt
            del rt

    native.export_batch(lazy(), Path("/dev/null"), Path("/dev/null"))
    assert seen == [0, 1, 1, 1]


def test_the_native_executor_runs_a_batch_bit_for_bit(native_exe, tmp_path):
    from flymsg import native

    native.export_batch(_battery_runs(), tmp_path / "base.bin", tmp_path / "batch.bin")
    for k, oracle in enumerate(_battery_runs()):
        out = tmp_path / f"out{k}.bin"
        subprocess.run(
            [
                str(native_exe),
                "--fixture",
                str(tmp_path / "base.bin"),
                "--batch",
                str(tmp_path / "batch.bin"),
                "--run",
                str(k),
                "--output",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        fixture = tmp_path / f"fixture{k}.bin"
        fixture.write_bytes(
            native.batch_fixture(
                tmp_path / "base.bin", tmp_path / "batch.bin", k
            ).tobytes()
        )
        oracle.advance_to(400)
        _acceptance().check(oracle, read_output(out, fixture))


def test_console_results_read_native_batch_outputs_as_sim_run(native_exe, tmp_path):
    """The console path end to end, with the native CPU executor standing in for the
    worker: a batch of sim.run calls, run by run, read back as sim.Results."""
    from flymsg import console, native, sim

    rng = np.random.default_rng(2)
    W = sparse.random(80, 80, density=0.12, random_state=rng, format="csc")
    W.data = rng.integers(-20, 80, W.data.size).astype(np.float32)
    W, p = W.astype(np.float32), sim.Params()
    specs = [([0, 3, 5], 300.0, 60.0, 30.0, 7), ([11], 300.0, 60.0, None, 8)]
    runtimes = [console.sim_runtime(W, np.array(s[0]), *s[1:4], p, s[4]) for s in specs]
    base, batch = tmp_path / "base.bin", tmp_path / "batch.bin"
    native.export_batch(runtimes, base, batch)
    outputs, counts, fixtures = [], [], []
    for k in range(len(specs)):
        out, fixture = tmp_path / f"output_{k}.bin", tmp_path / f"fixture_{k}.bin"
        sparse_out = tmp_path / f"counts_{k}.bin"
        subprocess.run(
            [
                str(native_exe),
                "--fixture",
                str(base),
                "--batch",
                str(batch),
                "--run",
                str(k),
                "--output",
                str(out),
                "--counts",
                str(sparse_out),
            ],
            check=True,
            capture_output=True,
        )
        fixture.write_bytes(native.batch_fixture(base, batch, k).tobytes())
        outputs.append(out)
        counts.append(sparse_out)
        fixtures.append(fixture)
    for files in (outputs, counts):
        results = console.as_results(files, fixtures, p.dt, [30.0, 60.0])
        assert len(results) == 2 and len(results[0:2]) == 2
        for s, r in zip(specs, results[:], strict=True):
            expected = sim.run(W, np.array(s[0]), s[1], s[2], s[3], p, s[4])
            assert np.array_equal(r.counts, expected.counts)
            assert np.array_equal(
                r.first_spike_ms, expected.first_spike_ms, equal_nan=True
            )
            assert r.bin_ms == expected.bin_ms and r.stim_ms == expected.stim_ms
    # a sparse output read against another run's horizon, or corrupted, is refused
    with pytest.raises(ValueError):
        native.read_counts(counts[0], base_with_steps(fixtures[0], tmp_path))
    words = np.frombuffer(counts[0].read_bytes(), dtype="<u4").copy()
    words[5] = 0xFFFFFFFF  # first nonzero count's index, out of range
    bad = tmp_path / "bad.bin"
    bad.write_bytes(words.tobytes())
    with pytest.raises(ValueError):
        native.read_counts(bad, fixtures[0])


def base_with_steps(fixture, tmp_path):
    """The fixture's header with twice its steps."""
    h = np.frombuffer(fixture.read_bytes(), dtype="<u4").copy()
    h[3] *= 2
    path = tmp_path / "longer.bin"
    path.write_bytes(h.tobytes())
    return path


def test_sparse_counts_decode_as_the_full_output(native_exe, tmp_path):
    from flymsg import native

    native.export_batch(_battery_runs(), tmp_path / "base.bin", tmp_path / "batch.bin")
    for k in range(4):
        out, counts = tmp_path / f"out{k}.bin", tmp_path / f"counts_{k}.bin"
        subprocess.run(
            [
                str(native_exe),
                "--fixture",
                str(tmp_path / "base.bin"),
                "--batch",
                str(tmp_path / "batch.bin"),
                "--run",
                str(k),
                "--output",
                str(out),
                "--counts",
                str(counts),
            ],
            check=True,
            capture_output=True,
        )
        fixture = tmp_path / f"fixture{k}.bin"
        fixture.write_bytes(
            native.batch_fixture(
                tmp_path / "base.bin", tmp_path / "batch.bin", k
            ).tobytes()
        )
        full, sparse = (
            native.read_output(out, fixture),
            native.read_counts(counts, fixture),
        )
        assert sparse["step"] == full["step"]
        assert np.array_equal(sparse["counts"], full["counts"])
        assert np.array_equal(sparse["first"], full["first"])
        assert counts.stat().st_size < out.stat().st_size


class FakeWorker:
    """A Device Portal over a local folder, with the native CPU executor as the worker:
    job.json runs the batch, and status.json lists the outputs `outputs` names."""

    def __init__(self, root, exe, outputs, finish=True):
        self.root, self.exe, self.outputs, self.finish = root, exe, outputs, finish
        self.uploads = []

    def mkdir(self, package, rel):
        (self.root / rel.replace("\\", "/")).mkdir(parents=True, exist_ok=True)

    def put(self, package, rel, local):
        folder = self.root / rel.replace("\\", "/")
        shutil.copy(local, folder / local.name)
        self.uploads.append(local.name)
        if local.name != "job.json":
            return
        job = json.loads(local.read_text())
        status = {"job_id": job["job_id"], "state": "running"}
        if self.outputs is not None:
            status["batch_outputs"] = self.outputs
        if self.finish:
            for k in range(job["batch"]["runs"]):
                subprocess.run(
                    [
                        str(self.exe),
                        "--fixture",
                        str(folder / "fixture.bin"),
                        "--batch",
                        str(folder / "batch.bin"),
                        "--run",
                        str(k),
                        "--output",
                        str(folder / f"output_{k}.bin"),
                        "--counts",
                        str(folder / f"counts_{k}.bin"),
                    ],
                    check=True,
                    capture_output=True,
                )
            status["state"] = "completed"
            (folder / "result.json").write_text(json.dumps({"advance_ms": 1.0}))
        (folder / "status.json").write_text(json.dumps(status))

    def get(self, package, rel, name, local):
        source = self.root / rel.replace("\\", "/") / name
        if not source.exists():
            raise RuntimeError(f"GET {name} failed")
        shutil.copy(source, local)

    def delete(self, package, rel, name):
        (self.root / rel.replace("\\", "/") / name).unlink(missing_ok=True)


def test_console_batches_need_a_worker_that_lists_their_output(
    native_exe, tmp_path, monkeypatch
):
    """sim_runs on a worker listing "counts" gives sim.run's results and the host's
    timing; on an older worker, which lists no outputs, it cancels at the first
    report instead of running the whole batch, and says why even when that worker
    finished before the first report."""
    from flymsg import console, sim

    monkeypatch.setattr(console.time, "sleep", lambda s: None)
    rng = np.random.default_rng(4)
    W = sparse.random(60, 60, density=0.15, random_state=rng, format="csc")
    W.data = rng.integers(-20, 80, W.data.size).astype(np.float32)
    W, p = W.astype(np.float32), sim.Params()
    specs = [(np.array([0, 2]), 300.0, 60.0, 30.0, 3)]
    shader = tmp_path / "lif.cso"
    shader.write_bytes(b"shader")
    for outputs, finish in ((["state", "counts"], True), (None, False), (None, True)):
        root = tmp_path / f"{outputs is None}{finish}"
        worker = FakeWorker(root, native_exe, outputs, finish)
        device = console.Device(package="pkg", shader=shader, portal=worker)
        out = root / "local"
        if outputs is None:
            with pytest.raises(RuntimeError, match="newer worker"):
                console.sim_runs(
                    device, W, specs, p, out, dataset="d", seed=0, scope="t"
                )
            # a running job is cancelled; a finished one leaves no output behind
            assert (worker.uploads[-1] == "cancel.json") != finish
            assert not list(root.rglob("output_*.bin"))
            continue
        results, result = console.sim_runs(
            device, W, specs, p, out, dataset="d", seed=0, scope="t"
        )
        expected = sim.run(W, *specs[0][:4], p, specs[0][4])
        assert np.array_equal(results[0].counts, expected.counts)
        assert set(result["host"]) == {
            "export_s",
            "upload_s",
            "console_s",
            "download_s",
        }
