"""Read-only source and assignment diagnostics; no physiological scoring."""

import argparse
import hashlib
import json
import subprocess
import tempfile
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


REPOSITORY = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def publish(root, destination):
    root, destination = Path(root), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    provenance = {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=REPOSITORY,
                text=True,
            ).strip()
        ),
    }
    inputs = [
        root / "neurons.parquet",
        root / "edges.parquet",
        root / "raw" / data.RAW["annotations"],
        root / "eye/columns.parquet",
    ]
    inputs += [medulla.raw_dir(root) / f"fig3_{name}.npy" for name in medulla.FILES]
    hashes = {str(p.relative_to(root)): digest(p) for p in inputs if p.exists()}
    sources, candidates, missing = audit(root)
    report = {
        "schema": "flymsg.science-inputs/v1",
        **provenance,
        "sources": sources,
        "inputs_sha256": hashes,
        "assignment_uncertainty": "UNKNOWN",
        "registration": "UNKNOWN",
        "holdout_opened": False,
        "candidate_rows": len(candidates),
    }
    if all(row["status"] == "verified" for row in sources.values()):
        report["ranges"] = medulla.ranges(root).to_dict(orient="records")
    if hashes != {str(p.relative_to(root)): digest(p) for p in inputs if p.exists()}:
        raise ValueError("source files changed during audit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".audit-", dir=destination.parent) as tmp:
        staged = Path(tmp) / "output"
        staged.mkdir()
        candidates.to_parquet(staged / "assignment-candidates.parquet", index=False)
        missing.to_csv(staged / "missing-columns.csv", index=False)
        report["outputs_sha256"] = {p.name: digest(p) for p in staged.iterdir()}
        (staged / "report.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n"
        )
        if destination.exists():
            raise FileExistsError(destination)
        staged.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    publish(args.data, args.out)
