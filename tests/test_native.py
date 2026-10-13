import json
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

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
