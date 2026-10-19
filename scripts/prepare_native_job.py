"""Prepare a synthetic Xbox acceptance job; no deployment or console access."""

import argparse
import hashlib
import json
import uuid
from pathlib import Path

import numpy as np
from scipy import sparse

from flymsg import sim
from flymsg.native import export_fixture
from flymsg.runtime import CpuRuntime


def prepare(out: Path, *, shader: Path | None, adapter: str = "SraKmd_arden") -> Path:
    job_id = str(uuid.uuid4())
    folder = out / job_id
    folder.mkdir(parents=True, exist_ok=False)
    p = sim.Params()
    runtime = CpuRuntime(
        sparse.csc_matrix(
            np.array([[0, 0, -1], [50, 0, 0], [0, 40, 0]], dtype=np.float32)
        ),
        np.array([0]),
        steps=1000,
        per_bin=100,
        p=p,
        kicks=sim.poisson_kicks(7, 500, p.dt, 700, 1),
        trace=np.arange(3),
        input_encoding="counts",
    )
    fixture = folder / "fixture.bin"
    metadata = export_fixture(runtime, fixture)
    job = {
        "schema": "flymsg.neural_job/v1",
        "job_id": job_id,
        "semantics": "flymsg.lif/ordered-f32-v1",
        "backend": "dx12" if shader else "cpu",
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "shader_sha256": hashlib.sha256(shader.read_bytes()).hexdigest()
        if shader
        else "",
        "expected_adapter": adapter if shader else "",
        "dataset": "synthetic",
        "seed": 7,
        "neural_tick_us": 100,
        "fixture": metadata,
        "scope": "qualification fixture, not biological validation",
    }
    # Publish this file last when transferring the directory to Device Portal.
    (folder / "job.json").write_text(json.dumps(job, sort_keys=True, indent=2) + "\n")
    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--shader", type=Path)
    parser.add_argument("--adapter", default="SraKmd_arden")
    args = parser.parse_args()
    print(prepare(args.out, shader=args.shader, adapter=args.adapter))
