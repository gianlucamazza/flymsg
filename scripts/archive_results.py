"""Copy the small run outputs the docs cite from runs/ (ignored) into results/ (tracked).

Usage: uv run python scripts/archive_results.py

Each listed directory is copied whole, so its manifest travels with its numbers. Local
paths are dropped from manifests: `cwd`, and an absolute `extra.data_dir` becomes relative to
the repository (or its last part). An archived directory is never overwritten: a rerun
belongs in a new version, so a directory that already exists and differs is an error.
"""

import sys
from pathlib import Path

from flymsg import archive_results as _package

DIRS, MAX_BYTES = _package.DIRS, _package.MAX_BYTES
ROOT = Path(__file__).resolve().parents[1]
RUNS, RESULTS = ROOT / "runs", ROOT / "results"


def clean_manifest(doc: dict) -> dict:
    return _package.clean_manifest(doc, ROOT)


def archive(rel: str) -> Path:
    return _package.archive(
        rel, root=ROOT, runs=RUNS, results=RESULTS, max_bytes=MAX_BYTES
    )


def main(dirs=DIRS) -> None:
    _package.main(dirs, root=ROOT, runs=RUNS, results=RESULTS, max_bytes=MAX_BYTES)


if __name__ == "__main__":
    main(sys.argv[1:] or DIRS)
