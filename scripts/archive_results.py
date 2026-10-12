"""Copy the small run outputs the docs cite from runs/ (ignored) into results/ (tracked).

Usage: uv run python scripts/archive_results.py

Each listed directory is copied whole, so its manifest travels with its numbers. Local
paths are dropped from manifests: `cwd`, and an absolute `extra.data_dir` becomes relative to
the repository (or its last part). An archived directory is never overwritten: a rerun
belongs in a new version, so a directory that already exists and differs is an error.
"""

import filecmp
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS, RESULTS = ROOT / "runs", ROOT / "results"
DIRS = (
    "behavior",
    "silence-scan/v1",
    "silence-scan/v2",
    "jump/intact",
    "jump/dnp01",
    "loop",
    "sensitivity/v1",
)
MAX_BYTES = 200_000  # a guard: results/ holds tables, not raw activity


def clean_manifest(doc: dict) -> dict:
    doc.pop("cwd", None)
    extra = doc.get("extra") or {}
    d = extra.get("data_dir")
    if d and Path(d).is_absolute():
        p = Path(d)
        extra["data_dir"] = (
            str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name
        )
    return doc


def archive(rel: str) -> Path:
    src, dst = RUNS / rel, RESULTS / rel
    if not (src / "manifest.json").is_file():
        sys.exit(f"{src} has no manifest.json")
    files = sorted(p for p in src.iterdir() if p.is_file() and ".ckpt" not in p.name)
    size = sum(p.stat().st_size for p in files)
    if size > MAX_BYTES:
        sys.exit(f"{src} is {size} bytes, over the {MAX_BYTES} byte guard")
    staged = RESULTS / ".staging" / rel
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir(parents=True)
    for f in files:
        shutil.copy2(f, staged / f.name)
    m = staged / "manifest.json"
    m.write_text(json.dumps(clean_manifest(json.loads(m.read_text())), indent=2) + "\n")
    if dst.exists():
        cmp = filecmp.dircmp(staged, dst)
        if cmp.left_only or cmp.right_only or cmp.diff_files:
            sys.exit(f"{dst} exists and differs; a rerun needs a new version")
        shutil.rmtree(staged)
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    staged.rename(dst)
    return dst


def main(dirs=DIRS) -> None:
    for rel in dirs:
        print(f"{archive(rel).relative_to(ROOT)}")
    shutil.rmtree(RESULTS / ".staging", ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1:] or DIRS)
