"""Physical Series S qualification of the bounded continuous-input protocol.

Requires an already running worker built from --source-commit, plus the usual
XBOX_* and FLYMSG_WORKER_PACKAGE/SHADER environment. No credentials enter reports.
This is engineering parity, not a scored biological experiment or a DN lock.
"""

import argparse
import itertools
import json
import time
from pathlib import Path

import numpy as np
from scipy import sparse

from flymsg import sim
from flymsg.console import Device
from flymsg.console_runtime import ConsoleRuntime
from flymsg.native_acceptance import EXTENSIONS, check
from flymsg.runtime import CpuRuntime


def run(device, out, source_commit):
    cases = []
    extensions = (
        "none",
        "graded",
        "gap",
        "spikelets",
        "both",
        "gap-all-free",
        "membrane",
    )
    expected = list(
        itertools.product((3, 19), ("counts", "kick_equivalent"), extensions)
    )
    report = {
        "schema": "flymsg.console_stream_qualification/v1",
        "source_commit": source_commit,
        "package": device.package,
        "shader_sha256": device.shader_sha,
        "adapter": device.adapter,
        "scope": "synthetic engineering parity; no biological score or real-time claim",
        "expected_cases": len(expected),
        "cases": cases,
        "qualified": False,
    }
    out.mkdir(parents=True, exist_ok=True)
    try:
        for seed, encoding, extension in expected:
            began = time.perf_counter()
            rng = np.random.default_rng(seed)
            W = sparse.csc_matrix(rng.integers(-20, 80, (8, 8)).astype(np.float32))
            dtype = np.float32 if encoding == "kick_equivalent" else np.int64

            def fresh(W=W, dtype=dtype, encoding=encoding, extension=extension):
                return CpuRuntime(
                    W,
                    np.array([0, 1]),
                    steps=100,
                    per_bin=10,
                    kicks=np.zeros((0, 2), dtype),
                    input_encoding=encoding,
                    trace=np.arange(8),
                    p=sim.Params(th_jump=2, delay=0.3),
                    **EXTENSIONS[extension],
                )

            oracle = fresh()
            remote = ConsoleRuntime(
                fresh(), device, out, window_steps=17, source_commit=source_commit
            )
            for stop in (20, 40, 60, 80, 100):
                feedback = int(
                    oracle.traced_spikes(max(0, oracle.step - 20), oracle.step).sum()
                )
                values = rng.integers(0, 5, (20, 2)).astype(dtype)
                if encoding == "kick_equivalent":
                    values *= np.float32(0.375)
                    values[0, 0] = np.nextafter(np.float32(0), np.float32(1))
                    values += np.float32(feedback / 8)
                else:
                    values += feedback // 8
                oracle.schedule_inputs(values)
                remote.schedule_inputs(values)
                oracle.advance_to(stop)
                remote.advance_to(stop)
                check(oracle, remote.snapshot())
                if stop == 40:
                    saved = out / "checkpoint.npz"
                    remote.checkpoint(saved)
                    remote.close()
                    remote = ConsoleRuntime(
                        fresh(),
                        device,
                        out,
                        window_steps=17,
                        source_commit=source_commit,
                    )
                    remote.restore(saved)
                    check(oracle, remote.snapshot())
            remote.close()
            cases.append(
                {
                    "seed": seed,
                    "encoding": encoding,
                    "extension": extension,
                    "passed": True,
                    "wall_s": time.perf_counter() - began,
                }
            )
    except Exception as exc:
        # PortalError messages are sanitized by the transport; do not dump environment.
        report["error"] = str(exc)
        raise
    finally:
        report["qualified"] = len(cases) == len(expected)
        (out / "qualification.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run(Device(), args.out, args.source_commit)
    print(
        json.dumps({"qualified": report["qualified"], "passed": len(report["cases"])})
    )


if __name__ == "__main__":
    main()
