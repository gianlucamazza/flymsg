"""Read-only scientific/run-integrity diagnostics; scratch files live in a temporary dir.

Run from a FlyMSG environment: python scripts/audit_integrity.py
These probes describe current behavior, not accepted scientific results. No dataset needed.
"""

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy import sparse

from flymsg import manifest, progress, sim
from flymsg.runtime import CpuRuntime


def main():
    p, coupling = sim.Params(), 5.0
    rt = CpuRuntime(
        sparse.csc_matrix((2, 2), dtype=np.float32),
        np.array([], dtype=int),
        steps=1,
        kicks=np.zeros((0, 0), dtype=np.int32),
        p=p,
        per_bin=1,
        gap=sim.Gap(np.array([0]), np.array([1]), coupling),
        input_encoding="counts",
    )
    # Cell 1 is clamped at rest for this entire step. Cell 0 is below threshold.
    rt._state["v"][0] = p.v_rest + 5
    rt._state["ref_until"][1] = 100
    rt.advance_to(1)
    actual = float(rt.snapshot()["v"][0])
    expected = float(p.v_rest + 5 * np.exp(-(1 + coupling) * p.dt / p.tau_m))
    findings = {
        "source": manifest.git_info(),
        "gap_refractory": {
            "actual_mv": actual,
            "analytic_mv": expected,
            "absolute_error_mv": abs(actual - expected),
        },
    }
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        identity = {
            "schema": "flymsg.execution/v1",
            "source": "probe-v1",
            "lock": "same-lock",
        }
        progress.Steps(root, identity).get(
            "arm", lambda: {"t": pd.DataFrame({"value": [1]})}
        )
        try:
            progress.Steps(root, {**identity, "source": "probe-v2"})
        except ValueError as exc:
            findings["changed_computation"] = {"refused": True, "reason": str(exc)}
        pd.DataFrame({"value": [999]}).to_parquet(
            root / "arm" / "t.parquet", index=True
        )
        try:
            progress.Steps(root, identity).get(
                "arm", lambda: {"t": pd.DataFrame({"value": [2]})}
            )
        except ValueError as exc:
            findings["tampered_checkpoint"] = {"refused": True, "reason": str(exc)}
    stream = io.StringIO()
    with patch("flymsg.progress.time.monotonic", side_effect=[0.0, 0.001, 60.0]):
        report = progress.Progress(100, "resumed", stream=stream)
        report.step(50, note="resumed", resumed=True)
        report.step(1, note="computed")
    findings["eta_after_resume"] = {
        "reported": stream.getvalue().splitlines()[-1],
        "expected_remaining_minutes_from_fresh_work": 49,
    }
    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
