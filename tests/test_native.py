import json
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse
from test_core import chain

from flymsg.native import export_fixture, read_output
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


def test_the_console_parity_script_builds_the_twelve_version_one_fixtures(tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "console_gpu_parity.py"
    spec = importlib.util.spec_from_file_location("console_gpu_parity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = list(module.fixtures())
    assert len(cases) == 12
    for (seed, _, _), oracle in cases:
        fixture = tmp_path / f"{seed}.bin"
        export_fixture(oracle, fixture)
        header = np.frombuffer(fixture.read_bytes(), dtype="<u4")
        assert int(header[1]) == 1  # the DX12 lane runs version-1 fixtures only


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
    assert int(header[1]) == 1  # the DX12 lane runs version-1 fixtures only
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
    from flymsg import sim

    rng = np.random.default_rng(5)
    W = sparse.random(60, 60, density=0.15, random_state=rng, format="csc")
    W.data = rng.integers(-20, 80, W.data.size).astype(np.float32)
    W = W.astype(np.float32)
    p = sim.Params()
    runs = []
    for k, (stim, stim_steps) in enumerate(
        [([0, 1, 2], 300), ([5], 300), ([7, 9], 120), ([0, 1, 2], 300)]
    ):
        runs.append(
            CpuRuntime(
                W,
                np.array(stim),
                steps=400,
                kicks=sim.poisson_kicks(30 + k, 300.0, p.dt, stim_steps, len(stim)),
                p=p,
                per_bin=100,
                trace=np.arange(4),
            )
        )
    return runs


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
    outputs, fixtures = [], []
    for k in range(len(specs)):
        out, fixture = tmp_path / f"output_{k}.bin", tmp_path / f"fixture_{k}.bin"
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
            ],
            check=True,
            capture_output=True,
        )
        fixture.write_bytes(native.batch_fixture(base, batch, k).tobytes())
        outputs.append(out)
        fixtures.append(fixture)
    results = console.as_results(outputs, fixtures, p.dt, [30.0, 60.0])
    assert len(results) == 2 and len(results[0:2]) == 2
    for s, r in zip(specs, results[:], strict=True):
        expected = sim.run(W, np.array(s[0]), s[1], s[2], s[3], p, s[4])
        assert np.array_equal(r.counts, expected.counts)
        assert np.array_equal(r.first_spike_ms, expected.first_spike_ms, equal_nan=True)
        assert r.bin_ms == expected.bin_ms and r.stim_ms == expected.stim_ms
