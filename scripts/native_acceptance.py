"""Run native fixture qualification; GPU claims require explicit --shader."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy import sparse

from flymsg import sim
from flymsg.native import NativeCapabilityError, export_fixture, read_output
from flymsg.runtime import CpuRuntime

# version 2 fixtures: graded neurons (tonic: half release at rest) and electrically
# coupled groups, alone and together
EXTENSIONS = {
    "none": {},
    "graded": {
        "graded": sim.Graded(
            idx=np.array([5, 6]), v_lo=-62.0, span=20.0, rate_hz=[150.0, 300.0]
        )
    },
    "gap": {
        "gap": sim.Gap(
            i=np.array([2, 3, 6]),
            j=np.array([3, 4, 7]),
            coupling=[0.3, 1.5, 0.8],
            refractory_mode="boundary",
        )
    },
    "spikelets": {
        "gap": sim.Gap(
            i=np.array([1, 2, 3]),
            j=np.array([2, 3, 4]),
            coupling=[0.2, 1.0, 0.4],
            coupling_back=[0.6, 0.3, 0.9],
            spike_mv=np.array([0.0, 40.0, 0.0, 25.0, 40.0, 0.0, 0.0, 0.0]),
            spike_ms=1.0,
            refractory_mode="boundary",
        )
    },
    "both": {
        "graded": sim.Graded(idx=np.array([5]), v_lo=-62.0, span=20.0, rate_hz=200.0),
        "gap": sim.Gap(
            i=np.array([2, 5]),
            j=np.array([3, 6]),
            coupling=[0.5, 2.0],
            spike_mv=40.0,
            spike_ms=0.5,
            refractory_mode="boundary",
        ),
    },
}


# Explicitly separate all-free qualification from the original refractory fixtures.
EXTENSIONS["gap-continuous-refractory"] = {
    "gap": sim.Gap(
        i=np.array([2, 3, 6]), j=np.array([3, 4, 7]), coupling=[0.3, 1.5, 0.8]
    ),
}
EXTENSIONS["gap-all-free"] = {
    "gap": sim.Gap(i=np.array([2, 3]), j=np.array([3, 4]), coupling=[0.3, 1.5]),
    "graded": sim.Graded(idx=np.array([2, 3, 4]), v_lo=-62.0, span=20.0, rate_hz=150.0),
}


def run(executable: Path, out: Path, shader: Path | None = None) -> dict:
    cases, unsupported = [], []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for seed, adapt, silent, ext in (
            (seed, adapt, silent, ext)
            for seed in (3, 7, 19)
            for adapt in (0.0, 2.0)
            for silent in (False, True)
            for ext in EXTENSIONS
        ):
            if shader and ext != "none":
                continue  # the GPU lane runs version 1 fixtures only
            p = sim.Params(th_jump=adapt, delay=0.3 if seed == 3 else 1.8)
            rng = np.random.default_rng(seed)
            W = sparse.csc_matrix(rng.integers(-20, 80, (8, 8)).astype(np.float32))
            kicks = sim.poisson_kicks(seed, 700, p.dt, 700, 2)
            kwargs = {
                "steps": 1000,
                "kicks": kicks,
                "p": p,
                "per_bin": 100,
                "trace": np.arange(8),
                "silence": np.array([3]) if silent else None,
                **EXTENSIONS[ext],
            }
            oracle = CpuRuntime(W, np.array([0, 1]), **kwargs)
            fixture, result, checkpoint = (
                root / "fixture.bin",
                root / "output.bin",
                root / "checkpoint.bin",
            )
            try:
                export_fixture(oracle, fixture)
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
            extra = ["--gpu", str(shader.resolve())] if shader else []
            base = [
                str(executable.resolve()),
                "--fixture",
                str(fixture),
                "--output",
                str(result),
            ]
            subprocess.run(
                [
                    *base,
                    "--advance",
                    "217",
                    "--checkpoint",
                    str(checkpoint),
                    *extra,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            oracle.advance_to(217)
            check(oracle, read_output(result, fixture))
            subprocess.run(
                [
                    *base,
                    "--resume",
                    str(checkpoint),
                    "--advance",
                    "1000",
                    *extra,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            oracle.advance_to(1000)
            check(oracle, read_output(result, fixture))
            cases.append(
                {
                    "seed": seed,
                    "adaptation": adapt,
                    "silenced": silent,
                    "extension": ext,
                    "electrical_mode": getattr(
                        EXTENSIONS[ext].get("gap"), "refractory_mode", "none"
                    ),
                    "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                    "passed": True,
                }
            )
        # Corruption and incompatible assets must fail before producing a new result.
        raw = bytearray(checkpoint.read_bytes())
        raw[-1] ^= 1
        checkpoint.write_bytes(raw)
        result.unlink()
        bad = subprocess.run(
            [*base, "--resume", str(checkpoint), *extra],
            check=False,
            capture_output=True,
            text=True,
        )
        if bad.returncode == 0 or result.exists():
            raise AssertionError("corrupt checkpoint accepted")
    report = {
        "schema": "flymsg.native_acceptance/v1",
        "backend": "dx12" if shader else "cpu",
        "unsupported": unsupported,
        "dynamic_electrical_clamp_qualified": False,
        "cases": cases,
        "passed": len(cases),
        "corrupt_checkpoint_rejected": True,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "shader_sha256": hashlib.sha256(shader.read_bytes()).hexdigest()
        if shader
        else None,
        "scope": "synthetic fixtures; not full-connectome performance or Xbox qualification",
    }
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def check(oracle: CpuRuntime, actual: dict) -> None:
    expected = oracle.snapshot()
    if actual["step"] != oracle.step:
        raise AssertionError("wrong cursor")
    for name in ("v", "g", "th", "ref_until", "counts", "first"):
        np.testing.assert_array_equal(actual[name], expected[name], err_msg=name)
    # the runtime keeps one placeholder column when nothing is traced; compare the
    # traced neurons only
    width = oracle.traced_spikes(0, 0).shape[1]
    np.testing.assert_array_equal(
        actual["traced"], expected["traced"][:, :width], err_msg="traced"
    )
    ring_mask = np.zeros_like(actual["ring_mask"])
    for slot, length in enumerate(expected["ring_len"]):
        ring_mask[slot, expected["ring"][slot, :length]] = 1
    np.testing.assert_array_equal(actual["ring_mask"], ring_mask)
    for name in ("graded_ring", "graded_vsum", "gap_pulse"):
        if name in expected:
            got = actual[name]
            np.testing.assert_array_equal(
                got.view(np.uint8), expected[name].view(np.uint8), err_msg=name
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--shader", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.exe, args.out, args.shader), indent=2))
