"""Index every archived result for external reproduction (SF5, #151).

Usage: uv run python scripts/replication_index.py [--check]

For each directory of scripts/archive_results.py DIRS the index records what an operator
needs to rerun it and to compare: the command, the source commit, the lock (file, version
and content hash), the dataset release and the sha256 of its compact tables, every other
hashed input, the seeds, the recorded verdict, the Python and flymsg versions, and the
sha256 of every archived output file except the manifest (local paths are cleaned from it
when archived). `--check` fails when the committed index differs from the archive.
"""

import sys
from pathlib import Path

from flymsg import replication_index as _package

DIRS, PROTOCOLS, SCHEMA = _package.DIRS, _package.PROTOCOLS, _package.SCHEMA
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
INDEX = ROOT / "docs" / "evidence" / "replication-index.json"


def sha256(path: Path) -> str:
    return _package.sha256(path)


def lock_of(command: str) -> str | None:
    return _package.lock_of(command, PROTOCOLS, ROOT)


def _config(m: dict, suffix: str):
    """The experiment lock's version or hash as a historical command recorded it."""
    return _package._config(m, suffix)


def entry(rel: str) -> dict:
    return _package.entry(rel, results=RESULTS, protocols=PROTOCOLS, root=ROOT)


def build() -> dict:
    return _package.build(
        results=RESULTS, protocols=PROTOCOLS, root=ROOT, dirs=DIRS, schema=SCHEMA
    )


def main(argv: list[str]) -> None:
    _package.main(
        argv,
        results=RESULTS,
        protocols=PROTOCOLS,
        root=ROOT,
        index=INDEX,
        dirs=DIRS,
        schema=SCHEMA,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
