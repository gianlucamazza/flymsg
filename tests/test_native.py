import json
import os
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
    if installed := os.environ.get("FLYMSG_NATIVE_EXE"):
        exe = Path(installed).resolve(strict=True)
        return exe
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
    assert report["passed"] == 120
    assert report["qualification"] == {
        "qualified": True,
        "expected_cases": 120,
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
        input_encoding="counts",
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
        input_encoding="counts",
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
        input_encoding="counts",
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
    from flymsg import console_gpu_parity as module

    assert len(list(module.fixtures())) == 12
    versions = {1: 0, 2: 0, 3: 0, 4: 0}
    for (seed, _, _, ext), oracle in module.fixtures(tuple(module.EXTENSIONS)):
        fixture = tmp_path / f"{seed}.bin"
        try:
            export_fixture(oracle, fixture, input_encoding=module.encoding(ext))
        except NativeCapabilityError:
            continue  # the dynamic clamp, refused on every native lane
        header = np.frombuffer(fixture.read_bytes(), dtype="<u4")
        assert int(header[1]) == (
            4
            if "membrane" in ext
            else 3
            if ext.startswith("sparse")
            else 1
            if ext == "none"
            else 2
        )
        versions[int(header[1])] += 1
    # the acceptance's 60 version-2 cases, as the CPU executor runs them
    assert versions == {1: 12, 2: 60, 3: 24, 4: 24}


def test_the_console_lifecycle_fixture_is_version_one_and_long(tmp_path):
    from flymsg import console_lifecycle as module

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
    from flymsg import console_bench, sensitivity

    assert console_bench.CASE in sensitivity.load()["cases"]["positive"]


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
        input_encoding="counts",
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
    from flymsg import native_acceptance

    return native_acceptance


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
            input_encoding="counts",
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

    native.export_batch(lazy(), Path(os.devnull), Path(os.devnull))
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


@pytest.mark.parametrize(
    "extension", ["none", "graded", "both", "membrane", "membrane-mixed"]
)
def test_sparse_inputs_match_dense_bytes_and_resume(native_exe, tmp_path, extension):
    from flymsg import native, sim
    from flymsg.native_acceptance import EXTENSIONS, check

    options = EXTENSIONS.get(extension, {})
    if extension == "membrane-mixed":
        options = {
            "graded": sim.Graded(
                idx=np.array([7]), v_lo=-62.0, span=20.0, rate_hz=200.0
            ),
            "gap": EXTENSIONS["both"]["gap"],
            "membrane": sim.Membrane(np.array([0, 1, 7]), 13.0, 4.0, -58.0, -43.0),
        }
    rng = np.random.default_rng(5)
    kicks = np.zeros((1000, 2), dtype=np.int64)
    kicks[[0, 1, 63, 64, 216, 217, 900], :] = [
        [1, 2],
        [3, 0],
        [0, 4],
        [5, 6],
        [2, 1],
        [0, 8],
        [2**53, 1],
    ]
    W = sparse.csc_matrix(rng.integers(-20, 80, (8, 8)).astype(np.float32))
    rt = CpuRuntime(
        W,
        np.array([0, 1]),
        steps=1000,
        kicks=kicks,
        per_bin=100,
        trace=np.arange(8),
        input_encoding="counts",
        **options,
    )
    outputs = []
    for encoding in ("dense", "sparse"):
        fixture = tmp_path / f"{encoding}.bin"
        output = tmp_path / f"{encoding}.out"
        checkpoint = tmp_path / f"{encoding}.checkpoint"
        meta = export_fixture(rt, fixture, input_encoding=encoding)
        if encoding == "sparse":
            w = np.frombuffer(fixture.read_bytes(), dtype="<u4")
            events = w[int(w[24]) :].reshape(-1, 4)
            restored = np.zeros_like(kicks)
            restored[events[:, 0], events[:, 1]] = (
                events[:, 2:].copy().reshape(-1).view("<f8").astype(np.int64)
            )
            np.testing.assert_array_equal(restored, kicks)
            assert meta["input_encoding"] == "sparse"
            assert native.input_ms(fixture, 0.1) == 901 * 0.1
        base = [str(native_exe), "--fixture", str(fixture), "--output", str(output)]
        subprocess.run(
            [*base, "--advance", "217", "--checkpoint", str(checkpoint)],
            check=True,
            capture_output=True,
        )
        partial = output.read_bytes()
        subprocess.run(
            [*base, "--resume", str(checkpoint)], check=True, capture_output=True
        )
        outputs.append((partial, output.read_bytes()))
        rt.advance_to(1000)
        check(rt, read_output(output, fixture))
        # Restore a fresh Python oracle for the next export.
        rt = CpuRuntime(
            W,
            np.array([0, 1]),
            steps=1000,
            kicks=kicks,
            per_bin=100,
            trace=np.arange(8),
            input_encoding="counts",
            **options,
        )
    assert outputs[0] == outputs[1]


def test_sparse_export_over_dense_gpu_budget(tmp_path):
    from flymsg.native import MAX_BYTES

    n, steps = 1024, 70_000
    rt = CpuRuntime(
        sparse.csc_matrix((n, n), dtype=np.float32),
        np.arange(n),
        steps=1,
        kicks=np.zeros((1, n), dtype=np.int64),
        per_bin=1,
        input_encoding="counts",
    )
    # Exercise export sizing without allocating the hypothetical 547 MiB dense
    # input. A broadcast zero view represents exactly those input counts.
    rt._steps, rt._per_bin = steps, steps
    rt._kicks = np.broadcast_to(np.zeros((1, n), dtype=np.int64), (steps, n))
    assert steps * n * 8 > MAX_BYTES
    path = tmp_path / "long.bin"
    meta = export_fixture(rt, path, input_encoding="sparse")
    assert path.stat().st_size == meta["input_bytes"] < 64 * 1024
    assert meta["input_bytes"] + meta["state_bytes"] < MAX_BYTES
    with pytest.raises(ValueError, match="cap"):
        # Size rejection should precede dense serialization.
        export_fixture(rt, tmp_path / "dense.bin")


def test_uniform_membrane_keeps_legacy_fixture_bytes(tmp_path):
    from flymsg import sim

    p = sim.Params()
    kwargs = {"steps": 100, "kicks": np.ones((100, 1), dtype=np.int64), "per_bin": 100}
    W = sparse.eye(4, format="csc", dtype=np.float32)
    membrane = sim.Membrane(np.arange(4), p.tau_m, p.tau_syn, p.v_rest, p.v_th)
    paths = [tmp_path / "plain", tmp_path / "uniform"]
    for path, m in zip(paths, (None, membrane), strict=True):
        meta = export_fixture(
            CpuRuntime(W, np.array([0]), membrane=m, input_encoding="counts", **kwargs),
            path,
        )
        assert meta["schema"] == "flymsg.native_fixture/v1"
    assert paths[0].read_bytes() == paths[1].read_bytes()


@pytest.mark.parametrize(
    "field", ["descriptor", "flag", "count", "order", "column", "zero", "membrane"]
)
def test_native_rejects_corrupt_sparse_membrane(native_exe, tmp_path, field):
    from flymsg import sim

    rt = CpuRuntime(
        sparse.eye(3, format="csc"),
        np.array([0]),
        steps=10,
        per_bin=10,
        kicks=np.ones((10, 1), dtype=np.int64),
        membrane=sim.Membrane(np.array([1]), 10.0, 3.0, -60.0, -45.0),
        input_encoding="counts",
    )
    fixture, output = tmp_path / "fixture", tmp_path / "output"
    export_fixture(rt, fixture, input_encoding="sparse")
    w = np.frombuffer(fixture.read_bytes(), dtype="<u4").copy()
    desc, events = int(w[39]), int(w[24])
    at, value = {
        "descriptor": (39, 1),
        "flag": (desc, 2),
        "count": (desc + 1, 100),
        "order": (events + 4, 0),
        "column": (events + 1, 1),
        "zero": (events + 3, 0),
        "membrane": (desc + 3, 0x7F800000),
    }[field]
    w[at] = value
    fixture.write_bytes(w.tobytes())
    run = subprocess.run(
        [str(native_exe), "--fixture", str(fixture), "--output", str(output)],
        capture_output=True,
        check=False,
    )
    assert run.returncode != 0 and not output.exists()


@pytest.mark.parametrize("count", [1, 6, 8])
@pytest.mark.parametrize("encoding", ["dense", "sparse"])
def test_nonuniform_membrane_matches_sim_run(native_exe, tmp_path, count, encoding):
    from flymsg import sim

    n, steps = 8, 1000
    rng = np.random.default_rng(17)
    W = sparse.csc_matrix(rng.integers(-20, 80, (n, n)).astype(np.float32))
    membrane = sim.Membrane(
        np.arange(count),
        np.linspace(9.0, 23.0, count),
        np.linspace(2.0, 5.0, count),
        np.linspace(-66.0, -55.0, count),
        np.linspace(-49.0, -41.0, count),
    )
    kicks = sim.poisson_kicks(7, 700.0, 0.1, steps, 2)
    p = sim.Params(th_jump=2.0)
    rt = CpuRuntime(
        W,
        np.array([0, 1]),
        steps=steps,
        kicks=kicks,
        p=p,
        per_bin=100,
        membrane=membrane,
        input_encoding="counts",
    )
    fixture, output = tmp_path / "fixture", tmp_path / "output"
    export_fixture(rt, fixture, input_encoding=encoding)
    subprocess.run(
        [str(native_exe), "--fixture", str(fixture), "--output", str(output)],
        check=True,
        capture_output=True,
    )
    actual = read_output(output, fixture)
    expected = sim.run(
        W,
        np.array([0, 1]),
        700.0,
        steps * p.dt,
        p=p,
        kicks=kicks,
        membrane=membrane,
        bin_ms=10.0,
    )
    np.testing.assert_array_equal(actual["counts"], expected.counts)
    first = np.where(actual["first"] >= 0, actual["first"] * p.dt, np.nan)
    np.testing.assert_array_equal(first, expected.first_spike_ms)


def test_sparse_block_planning_preserves_steps_and_resume(native_exe, tmp_path):
    """Force tiny blocks through the same planner DX12 uses, including empty
    steps, a multi-column step, and a resumed cursor inside the input."""
    from flymsg import sim

    kicks = np.zeros((100, 2), dtype=np.int64)
    kicks[[0, 10, 30, 99]] = [[1, 2], [3, 0], [4, 5], [0, 6]]
    rt = CpuRuntime(
        sparse.eye(2, format="csc"),
        np.array([0, 1]),
        steps=100,
        kicks=kicks,
        per_bin=100,
        p=sim.Params(),
        input_encoding="counts",
    )
    fixture, expected, actual = (
        tmp_path / "fixture",
        tmp_path / "expected",
        tmp_path / "actual",
    )
    export_fixture(rt, fixture, input_encoding="sparse")
    subprocess.run(
        [str(native_exe), "--fixture", str(fixture), "--output", str(expected)],
        check=True,
        capture_output=True,
    )
    source, exe = tmp_path / "blocks.cpp", tmp_path / "blocks"
    source.write_text("""#include "lif.h"
int main(int argc, char **argv) {
  if (argc != 4) return 1;
  flymsg::Runtime r(flymsg::read_words(argv[1]));
  // A step with two events must never be split to satisfy capacity one.
  bool refused = false;
  try { r.input_block(0, r.input[3], 1); }
  catch (const std::runtime_error &) { refused = true; }
  flymsg::require(refused, "split input step accepted");
  r.advance_to(17);
  r.checkpoint(argv[3]);
  flymsg::Runtime resumed(r.input);
  resumed.restore(argv[3]);
  uint64_t consumed = resumed.event_lower_bound(resumed.step);
  unsigned blocks = 0;
  while (resumed.step < resumed.input[3]) {
    auto b = resumed.input_block(resumed.step, resumed.input[3], 2);
    flymsg::require(b.first == consumed && b.last - b.first <= 2, "bad block");
    for (auto k = b.first; k < b.last; ++k) {
      auto tick = resumed.input[resumed.input[24] + 4 * k];
      flymsg::require(tick >= resumed.step && tick < b.end, "bad event boundary");
    }
    consumed = b.last;
    resumed.advance_to(b.end);
    ++blocks;
  }
  flymsg::require(blocks > 1 && consumed == resumed.events, "missing events");
  resumed.snapshot(argv[2]);
}
""")
    subprocess.run(
        [
            shutil.which("g++"),
            "-std=c++20",
            "-O2",
            "-ffp-contract=off",
            "-I",
            str(ROOT / "native"),
            str(source),
            "-o",
            str(exe),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [str(exe), str(fixture), str(actual), str(tmp_path / "checkpoint")],
        check=True,
        capture_output=True,
    )
    assert actual.read_bytes() == expected.read_bytes()


@pytest.mark.parametrize("encoding", ["counts", "kick_equivalent"])
@pytest.mark.parametrize("window", [1, 7, 100])
def test_native_streamed_input_resume_parity(native_exe, tmp_path, encoding, window):
    from flymsg.native import input_block
    from flymsg.native_acceptance import check

    dtype = np.float32 if encoding == "kick_equivalent" else np.int64
    rng = np.random.default_rng(41)
    values = rng.integers(0, 5, (100, 2)).astype(dtype)
    if encoding == "kick_equivalent":
        values *= np.float32(0.375)
        values[0, 0] = np.nextafter(np.float32(0), np.float32(1))
    W = sparse.csc_matrix(np.array([[0, 2, 0], [-1, 0, 3], [1, 0, 0]], np.float32))
    oracle = CpuRuntime(
        W,
        np.array([0, 1]),
        steps=100,
        kicks=np.zeros((0, 2), dtype),
        input_encoding=encoding,
        per_bin=10,
        trace=np.arange(3),
    )
    fixture, output, checkpoint, block = [
        tmp_path / name
        for name in ("fixture.bin", "output.bin", "checkpoint.bin", "input.bin")
    ]
    export_fixture(oracle, fixture, window_steps=window)
    for start in range(0, 100, window):
        stop = min(100, start + window)
        block.write_bytes(
            input_block(values[start:stop], step=start, input_encoding=encoding)
        )
        args = [
            str(native_exe),
            "--fixture",
            str(fixture),
            "--output",
            str(output),
            "--input-block",
            str(block),
            "--advance",
            str(stop),
            "--checkpoint",
            str(checkpoint),
        ]
        if start:
            args += ["--resume", str(checkpoint)]
        subprocess.run(args, check=True, capture_output=True)
        oracle.schedule_inputs(values[start:stop])
        oracle.advance_to(stop)
        check(oracle, read_output(output, fixture))


@pytest.mark.parametrize("storage", ["dense", "sparse"])
def test_native_fractional_drive_parity(native_exe, tmp_path, storage):
    from flymsg.native_acceptance import check

    values = np.random.default_rng(62).uniform(0, 4, (100, 1)).astype(np.float32)
    oracle = CpuRuntime(
        sparse.eye(2, format="csc"),
        np.array([0]),
        steps=100,
        kicks=values,
        input_encoding="kick_equivalent",
        per_bin=10,
        trace=np.arange(2),
    )
    fixture, output = tmp_path / "fixture.bin", tmp_path / "output.bin"
    export_fixture(oracle, fixture, input_encoding=storage)
    subprocess.run(
        [str(native_exe), "--fixture", str(fixture), "--output", str(output)],
        check=True,
        capture_output=True,
    )
    oracle.advance_to(100)
    check(oracle, read_output(output, fixture))


class _NativeStreamPortal:
    """Transport double executing the real C++ engine, never Python LIF math."""

    def __init__(self, root, exe):
        self.root, self.exe = root, exe
        self.root.mkdir()
        self.receipts = {}

    def mkdir(self, package, rel):
        (self.root / rel.replace("\\", "/")).mkdir(parents=True)

    def put(self, package, rel, local):
        import hashlib

        folder = self.root / rel.replace("\\", "/")
        shutil.copyfile(local, folder / local.name)
        if not local.name.startswith("command_") or local.suffix != ".json":
            return
        cmd = json.loads(local.read_text())
        job = json.loads((folder / "job.json").read_text())
        previous = self.receipts.get(rel, job["fixture_sha256"])
        assert cmd["previous_receipt_sha256"] == previous
        seq, op = cmd["sequence"], cmd["operation"]
        result = folder / f"result_{seq}.bin"
        checkpoint = folder / "live.bin"
        fixture = folder / "fixture.bin"
        step = cmd.get("target", cmd["expected_step"])
        if op != "finish":
            args = [
                str(self.exe),
                "--fixture",
                str(fixture),
                "--output",
                str(result),
                "--advance",
                str(step),
                "--checkpoint",
                str(checkpoint),
            ]
            if op == "restore":
                shutil.copyfile(folder / f"command_{seq}.bin", checkpoint)
            if checkpoint.exists():
                args += ["--resume", str(checkpoint)]
            if op == "advance":
                args += ["--input-block", str(folder / f"command_{seq}.bin")]
            subprocess.run(args, check=True, capture_output=True)
            if op == "advance":
                actual = read_output(result, fixture)
                trace = actual["traced"][cmd["expected_step"] : step]
                result.write_bytes(
                    struct.pack(
                        "<4I", 0x31544D46, cmd["expected_step"], step, trace.shape[1]
                    )
                    + trace.astype("<u4").tobytes()
                )
            if op == "checkpoint":
                shutil.copyfile(checkpoint, result)
        ack = {
            "schema": "flymsg.stream_receipt/v1",
            "job_id": cmd["job_id"],
            "sequence": seq,
            "step": step,
            "source_commit": "a" * 40,
            "command_sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
            "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest()
            if op != "finish"
            else "",
        }
        path = folder / f"receipt_{seq}.json"
        path.write_text(json.dumps(ack))
        self.receipts[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    def get(self, package, rel, name, local):
        shutil.copyfile(self.root / rel.replace("\\", "/") / name, local)


def test_console_stream_feedback_checkpoint(native_exe, tmp_path):
    from types import SimpleNamespace

    from flymsg.console_runtime import ConsoleRuntime
    from flymsg.native_acceptance import check

    def fresh():
        return CpuRuntime(
            sparse.eye(3, format="csc"),
            np.array([0]),
            steps=100,
            kicks=np.zeros((0, 1), np.float32),
            input_encoding="kick_equivalent",
            per_bin=10,
            trace=np.arange(3),
        )

    portal = _NativeStreamPortal(tmp_path / "remote", native_exe)
    device = SimpleNamespace(
        portal=portal, package="qualified", shader_sha="s" * 64, adapter="test"
    )
    oracle = fresh()
    stream = ConsoleRuntime(
        fresh(), device, tmp_path / "host", window_steps=7, source_commit="a" * 40
    )
    for stop in (10, 20, 30, 40, 50):
        # Delayed neural feedback changes the next input block.
        feedback = oracle.traced_spikes(max(0, oracle.step - 10), oracle.step).sum()
        values = np.full((10, 1), 0.375 + float(feedback) * 0.125, np.float32)
        oracle.schedule_inputs(values)
        stream.schedule_inputs(values)
        oracle.advance_to(stop)
        stream.advance_to(stop)
        check(oracle, stream.snapshot())
    saved = tmp_path / "checkpoint.npz"
    stream.checkpoint(saved)
    stream.close()
    resumed = ConsoleRuntime(
        fresh(), device, tmp_path / "host", window_steps=7, source_commit="a" * 40
    )
    resumed.restore(saved)
    values = np.full((50, 1), 1.625, np.float32)
    oracle.schedule_inputs(values)
    resumed.schedule_inputs(values)
    oracle.advance_to(100)
    resumed.advance_to(100)
    check(oracle, resumed.snapshot())
    np.testing.assert_array_equal(
        resumed.traced_spikes(0, 100), oracle.traced_spikes(0, 100)
    )
    resumed.close()


@pytest.mark.parametrize(
    "fault",
    [
        "fractional-count",
        "non-float32-drive",
        "nan",
        "negative",
        "start",
        "width",
        "length",
        "encoding",
        "truncated",
    ],
)
def test_native_stream_rejects_invalid_block(native_exe, tmp_path, fault):
    from flymsg.native import input_block

    encoding = "counts" if fault == "fractional-count" else "kick_equivalent"
    dtype = np.int64 if encoding == "counts" else np.float32
    runtime = CpuRuntime(
        sparse.eye(2, format="csc"),
        np.array([0]),
        steps=10,
        kicks=np.zeros((0, 1), dtype),
        input_encoding=encoding,
        per_bin=10,
    )
    fixture, output, block = [
        tmp_path / name for name in ("fixture.bin", "output.bin", "block.bin")
    ]
    export_fixture(runtime, fixture, window_steps=3)
    raw = bytearray(
        input_block(np.ones((3, 1), dtype), step=0, input_encoding=encoding)
    )
    if fault in {"fractional-count", "non-float32-drive", "nan", "negative"}:
        value = {
            "fractional-count": 0.5,
            "non-float32-drive": 0.1,
            "nan": np.nan,
            "negative": -1,
        }[fault]
        struct.pack_into("<d", raw, 28, value)
    elif fault == "truncated":
        raw.pop()
    else:
        slot, value = {
            "start": (3, 1),
            "width": (5, 2),
            "length": (4, 4),
            "encoding": (2, 0),
        }[fault]
        struct.pack_into("<I", raw, slot * 4, value)
    block.write_bytes(raw)
    result = subprocess.run(
        [
            str(native_exe),
            "--fixture",
            str(fixture),
            "--input-block",
            str(block),
            "--output",
            str(output),
            "--advance",
            "3",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_console_rejects_receipt_before_committing_step(native_exe, tmp_path):
    from types import SimpleNamespace

    from flymsg.console_runtime import ConsoleRuntime

    class CorruptReceipt(_NativeStreamPortal):
        def get(self, package, rel, name, local):
            super().get(package, rel, name, local)
            if name.startswith("receipt_"):
                ack = json.loads(local.read_text())
                ack["source_commit"] = "b" * 40
                local.write_text(json.dumps(ack))

    portal = CorruptReceipt(tmp_path / "remote", native_exe)
    device = SimpleNamespace(
        portal=portal, package="qualified", shader_sha="s" * 64, adapter="test"
    )
    runtime = CpuRuntime(
        sparse.eye(2, format="csc"),
        np.array([0]),
        steps=10,
        kicks=np.zeros((0, 1), np.float32),
        input_encoding="kick_equivalent",
        per_bin=10,
    )
    stream = ConsoleRuntime(
        runtime, device, tmp_path / "host", window_steps=3, source_commit="a" * 40
    )
    stream.schedule_inputs(np.ones((3, 1), np.float32))
    with pytest.raises(RuntimeError, match="identity/order"):
        stream.advance_to(3)
    assert stream.step == 0
    with pytest.raises(RuntimeError, match="explicit recovery"):
        stream.advance_to(3)


def test_stream_qualification_matrix_with_native_engine(native_exe, tmp_path):
    from runpy import run_path
    from types import SimpleNamespace

    collector = run_path(str(ROOT / "scripts/console_stream_parity.py"))
    portal = _NativeStreamPortal(tmp_path / "remote", native_exe)
    device = SimpleNamespace(
        portal=portal, package="qualified", shader_sha="s" * 64, adapter="test"
    )
    report = collector["run"](device, tmp_path / "host", "a" * 40)
    assert report["qualified"]
    assert len(report["cases"]) == report["expected_cases"] == 28
