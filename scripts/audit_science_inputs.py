"""Read-only source and assignment diagnostics; no physiological scoring."""

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

from flymsg import data, eye, medulla


def audit(root):
    sources = {}
    for name, (file_id, expected) in medulla.FILES.items():
        path = medulla.raw_dir(root) / f"fig3_{name}.npy"
        actual = medulla.sha256(path) if path.exists() else None
        sources[name] = {
            "url": f"{medulla.EDMOND}/{file_id}",
            "expected_sha256": expected,
            "actual_sha256": actual,
            "status": "missing"
            if actual is None
            else "verified"
            if actual == expected
            else "corrupt",
        }
    neurons, edges = data.load(root)
    ann = pd.read_feather(root / "raw" / data.RAW["annotations"])
    candidates = eye.assignment_candidates(neurons, edges, ann)
    cols = pd.read_parquet(root / "eye/columns.parquet")
    assigned = eye.photoreceptors(neurons, edges, ann)
    missing = assigned.merge(cols[["side", "hex1", "hex2"]], how="left", indicator=True)
    return (
        sources,
        candidates,
        missing[missing._merge == "left_only"].drop(columns="_merge"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sources, candidates, missing = audit(args.data)
    args.out.mkdir(parents=True, exist_ok=False)
    candidates.to_parquet(args.out / "assignment-candidates.parquet", index=False)
    missing.to_csv(args.out / "missing-columns.csv", index=False)
    report = {
        "schema": "flymsg.science-inputs/v1",
        "sources": sources,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"], text=True
            ).strip()
        ),
        "assignment_uncertainty": "UNKNOWN",
        "registration": "UNKNOWN",
        "holdout_opened": False,
        "candidate_rows": len(candidates),
    }
    if all(row["status"] == "verified" for row in sources.values()):
        report["ranges"] = medulla.ranges(args.data).to_dict(orient="records")
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
