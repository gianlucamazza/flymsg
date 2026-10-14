"""Index every archived result for external reproduction (SF5, #151).

Usage: uv run python scripts/replication_index.py [--check]

For each directory of scripts/archive_results.py DIRS the index records what an operator
needs to rerun it and to compare: the command, the source commit, the lock (file, version
and content hash), the dataset release and the sha256 of its compact tables, every other
hashed input, the seeds, the recorded verdict, the Python and flymsg versions, and the
sha256 of every archived output file except the manifest (local paths are cleaned from it
when archived). `--check` fails when the committed index differs from the archive.
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from flymsg import managed

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "archive_results", ROOT / "scripts" / "archive_results.py"
)
_archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_archive)
DIRS, RESULTS = _archive.DIRS, _archive.RESULTS

INDEX = ROOT / "docs" / "evidence" / "replication-index.json"
SCHEMA = "flymsg.replication_index/v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock_of(command: str) -> str | None:
    module = managed.PROTOCOLS.get(command.split()[0])
    path = getattr(module, "PATH", None)
    return str(path.relative_to(ROOT)) if path is not None else None


def _config(m: dict, suffix: str):
    """The experiment lock's version or hash as a historical command recorded it."""
    found = [v for k, v in (m.get("config") or {}).items() if k.endswith(suffix)]
    return found[0] if len(found) == 1 else None


def entry(rel: str) -> dict:
    root = RESULTS / rel
    m = json.loads((root / "manifest.json").read_text())
    extra = m.get("extra") or {}
    execution = extra.get("execution") or {}
    prereg = m.get("preregistration") or {}
    dataset = m.get("dataset") or {}
    inputs = {
        k: v["sha256"]
        for k, v in (execution.get("inputs") or dataset.get("files") or {}).items()
    }
    return {
        "result": f"results/{rel}",
        "command": m.get("command"),
        "source_commit": (m.get("git") or {}).get("commit"),
        "dirty": (m.get("git") or {}).get("dirty"),
        "lock": lock_of(m.get("command") or ""),
        # managed executions record the experiment lock as the preregistration; historical
        # runs record the battery lock there and the experiment lock in their config
        "lock_version": prereg.get("version") if execution else _config(m, "_version"),
        "lock_sha256": prereg.get("content_sha256")
        if execution
        else _config(m, "_sha256"),
        "dataset": {"name": dataset.get("name"), "release": dataset.get("release")},
        "inputs_sha256": dict(sorted(inputs.items())),
        "config": m.get("config"),
        "seeds": m.get("seeds"),
        "verdict": extra.get("verdict"),
        "other_results": {k: extra[k] for k in ("drive", "left") if k in extra} or None,
        "python": (m.get("platform") or {}).get("python"),
        "flymsg": (m.get("packages") or {}).get("flymsg"),
        "execution_sha256": extra.get("execution_sha256"),
        "outputs_sha256": {
            p.name: sha256(p)
            for p in sorted(root.iterdir())
            if p.is_file() and p.name != "manifest.json"
        },
    }


def build() -> dict:
    return {"schema": SCHEMA, "results": [entry(rel) for rel in DIRS]}


def main(argv: list[str]) -> None:
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    if "--check" in argv:
        if not INDEX.is_file() or INDEX.read_text() != text:
            sys.exit(
                f"{INDEX.relative_to(ROOT)} is stale; rerun scripts/replication_index.py"
            )
        return print(f"{INDEX.relative_to(ROOT)} matches results/")
    INDEX.write_text(text)
    print(f"{len(DIRS)} results -> {INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
