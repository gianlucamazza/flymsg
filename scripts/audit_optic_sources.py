"""Inventory local optical evidence without scoring physiology or downloading data."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from flymsg import eye, medulla
from flymsg.paths import repository_root

ROOT = repository_root()


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def audit(data_dir):
    # Verify the source bytes even when the derived tables already exist.
    for name in eye.EYEMAP_FILES:
        eye._verify_source(eye.raw_dir(data_dir) / name)
    cols = pd.read_parquet(data_dir / "eye/columns.parquet")
    receptors = pd.read_parquet(data_dir / "eye/photoreceptors.parquet")
    neurons = pd.read_parquet(data_dir / "neurons.parquet")
    masks = eye.receptor_masks(neurons, cols, receptors)
    files = [
        *sorted((data_dir / "raw").glob("*.feather")),
        *sorted(eye.raw_dir(data_dir).glob("*.RData")),
        data_dir / "neurons.parquet",
        data_dir / "edges.parquet",
        data_dir / "eye/columns.parquet",
        data_dir / "eye/photoreceptors.parquet",
    ]
    physiology = {}
    for name, (_, expected) in medulla.FILES.items():
        path = medulla.raw_dir(data_dir) / f"fig3_{name}.npy"
        physiology[name] = {
            "expected_sha256": expected,
            "local_sha256": sha256(path) if path.exists() else None,
        }
    return {
        "schema": "flymsg.optic-source-audit/v1",
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "inputs_sha256": {str(p.relative_to(data_dir)): sha256(p) for p in files},
        "coverage": eye.check(cols, receptors),
        "receptor_masks": {
            "simulated": len(masks),
            "assigned": int(masks.has_assignment.sum()),
            "with_column": int(masks.has_column.sum()),
            "with_direction": int(masks.has_direction.sum()),
            "unknown_laterality": int(masks.laterality_matches.isna().sum()),
            "laterality_conflicts": int(masks.laterality_matches.eq(False).sum()),
        },
        "direction_transfer_status": "INFERRED",
        "registration_status": "UNKNOWN",
        "angular_uncertainty_status": "UNKNOWN",
        "physiology_status": "UNKNOWN",
        "physiology_local_sources": physiology,
        "historical_sha256": {
            str(p.relative_to(ROOT)): sha256(p)
            for p in [
                ROOT / "validation/t4t5.yaml",
                *sorted((ROOT / "results/t4t5").rglob("*")),
            ]
            if p.is_file()
        },
        "limitations": [
            "Masks cover simulated receptors only; untraced cells are not reconstructed.",
            "Source integrity and coverage do not validate physiology.",
            "Derived tables are hashed, not silently rebuilt; run flymsg eye first.",
            "No measured angular covariance or eye/body transform is supplied.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT
    ):
        parser.error("commit tracked changes before recording evidence")
    report = audit(args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(json.dumps(report["receptor_masks"]))
