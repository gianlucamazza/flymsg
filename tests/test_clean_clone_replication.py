"""Pure comparison and input guard tests; never execute the reproduction harness."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "clean_clone_replication",
    Path(__file__).resolve().parents[1] / "scripts/clean_clone_replication.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_comparison_detects_hash_verdict_and_inventory_mismatch(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    (output / "report.txt").write_text("negative\n")
    entry = {
        "outputs_sha256": {"report.txt": MODULE.sha256(output / "report.txt")},
        "verdict": "none",
        "config": {"seed": 1},
        "seeds": {"all": [1]},
        "source_commit": "abc",
    }
    manifest = {
        "extra": {"verdict": "none"},
        "config": entry["config"],
        "seeds": entry["seeds"],
        "git": {"commit": "abc", "dirty": False},
    }
    (output / "manifest.json").write_text(json.dumps(manifest))
    assert all(
        v
        for k, v in MODULE.compare(entry, output).items()
        if k.endswith(("match", "matches"))
    )
    (output / "extra").write_text("unexpected")
    assert not MODULE.compare(entry, output)["hashes_match"]
    manifest["extra"]["verdict"] = "pass"
    (output / "manifest.json").write_text(json.dumps(manifest))
    assert not MODULE.compare(entry, output)["verdict_matches"]


def test_guard_refuses_heldout_open_but_allows_presence_check(tmp_path):
    heldout = tmp_path / "raw" / "recording.mat"
    heldout.parent.mkdir()
    heldout.write_bytes(b"synthetic forbidden data")
    code = (
        MODULE.GUARD
        + """
p = root / "raw/recording.mat"
assert p.is_file()
try:
    p.read_bytes()
except PermissionError:
    pass
else:
    raise AssertionError("held-out open was accepted")
"""
    )
    import os

    subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "SF5_INPUT_ROOT": str(tmp_path)},
        check=True,
    )


def test_only_selected_clean_unscored_or_preholdout_results_are_exposed():
    index = json.loads(
        (MODULE.ROOT / "docs/evidence/replication-index.json").read_text()
    )["results"]
    for name in MODULE.CHOICES.values():
        entry = next(e for e in index if e["result"] == name)
        assert entry["dirty"] is False
        assert set(entry["inputs_sha256"]) == {"neurons.parquet", "edges.parquet"}
    assert MODULE.CHOICES["no-go"] == "results/gf_looming/v1"
