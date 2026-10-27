"""Synthetic causal witness, not a physiological validation or fitted model."""

import runpy
from pathlib import Path


def test_locked_retinal_causal_and_numerical_gates(tmp_path):
    module = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/check_optic_causality.py")
    )
    report = module["run"](tmp_path)
    assert report["evidence_status"] == "SYNTHETIC"
    assert report["physiology_status"] == "UNKNOWN"
    assert all(report["gates"].values()), report
