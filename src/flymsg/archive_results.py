"""Archive cited run directories from runs/ into results/."""

from __future__ import annotations

import filecmp
import json
import shutil
import sys
from pathlib import Path

from flymsg import runstore

DIRS = (
    "behavior",
    "silence-scan/v1",
    "silence-scan/v2",
    "silence-scan/v3",
    "mb-plasticity/v1",
    "kc-sparseness/v1",
    "kc-sparseness/v2",
    "kc-sparseness/v3",
    "kc-sparseness/v4",
    "kc-sparseness/v5",
    "kc-sparseness/v7.executions/f8549bf7414656b26cf37dcf99811142bb3b1b3a7743b79d5ebeda941457c3a5/output",
    "kc-sparseness/v8.executions/c714d0a3035c6d0842295f3e8057367fe9adbebb6e12fee4ac09eed6b31aee24/output",
    "t4t5/v1",
    "t4t5/v2",
    "t4t5/v3.executions/d85c3913d5894b5c1f6ffedcfd5b77cc7357cffd81f1e79b8d6bef1db6f04644/output",
    "t4t5/v4.executions/7a550844a1d00d7d1ace0ddad24055859d9aae944e8048e273adfd0c99dc952d/output",
    "weight-rule/v1.executions/beb2fccf6b8094ee842de39deba87da17448ac37fab0626e1fa15db517762f4f/output",
    "jump3d/v1",
    "partner-followup/v1",
    "jump/intact",
    "jump/dnp01",
    "loop",
    "sensitivity/v1",
    "convergence/v1.executions/be1ac2741e08d8f0432fd49fed5ebd74fab5062d79cb280a39637f49ae31997c/output",
    "path-metrics/v1.executions/0c616b348fe32a245e22eade4fa6e8e54511d4d49a9e106044d1e47badfdc313/output",
    "gf_looming/v1",
    "gf_looming/v2",
    "song/v1",
    "baselines/v1.executions/f89ed1c350b97a63cb5bfa7c483f1837ad81d585bcea19742800f809674bb7f4/output",
    "apl-claws/v1.executions/b914035a1c1a364adec8e0a880373c104287b3e677f39521f76550e5dbadc0fd/output",
)
# A guard: results/ holds tables, not raw activity. 250 kB since t4t5 v3, whose per-type
# medulla table over 25 configurations brings its required artifacts to 202 kB; 450 kB since
# song v1, whose per-cell table (1,045 cells: conditions, rates, seeds, 99 shuffles, the
# evidence for its no-go) brings its artifacts to 421 kB.
MAX_BYTES = 450_000


def clean_manifest(doc: dict, root: Path) -> dict:
    doc.pop("cwd", None)
    extra = doc.get("extra") or {}

    def local(value):
        p = Path(value)
        return str(p.relative_to(root)) if p.is_relative_to(root) else p.name

    for key in ("data_dir", "out", "replay"):
        value = extra.get(key)
        if value and Path(value).is_absolute():
            extra[key] = local(value)
    for attempt in extra.get("attempts", []):
        value = attempt.get("checkpoint")
        if value and Path(value).is_absolute():
            attempt["checkpoint"] = local(value)
    return doc


def archive(
    rel: str, *, root: Path, runs: Path, results: Path, max_bytes: int = MAX_BYTES
) -> Path:
    src, dst = runs / rel, results / rel
    complete = None
    if src.name == "output" and src.parent.parent.name.endswith(".executions"):
        try:
            complete = runstore.verify_completed(src.parent)
        except ValueError as exc:
            sys.exit(str(exc))
    if not (src / "manifest.json").is_file():
        sys.exit(f"{src} has no manifest.json")
    files = sorted(p for p in src.iterdir() if p.is_file() and ".ckpt" not in p.name)
    size = sum(p.stat().st_size for p in files)
    if size > max_bytes:
        sys.exit(f"{src} is {size} bytes, over the {max_bytes} byte guard")
    staged = results / ".staging" / rel
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir(parents=True)
    for f in files:
        shutil.copy2(f, staged / f.name)
    if complete is not None:
        runstore.verify_inventory(staged, complete["artifacts"])
    manifest = staged / "manifest.json"
    manifest.write_text(
        json.dumps(clean_manifest(json.loads(manifest.read_text()), root), indent=2)
        + "\n"
    )
    if dst.exists():
        cmp = filecmp.dircmp(staged, dst)
        different, errors = filecmp.cmpfiles(
            staged, dst, cmp.common_files, shallow=False
        )[1:]
        if cmp.left_only or cmp.right_only or different or errors:
            sys.exit(f"{dst} exists and differs; a rerun needs a new version")
        shutil.rmtree(staged)
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    staged.rename(dst)
    return dst


def main(
    dirs, *, root: Path, runs: Path, results: Path, max_bytes: int = MAX_BYTES
) -> None:
    for rel in dirs:
        archived = archive(
            rel, root=root, runs=runs, results=results, max_bytes=max_bytes
        )
        print(f"{archived.relative_to(root)}")
    shutil.rmtree(results / ".staging", ignore_errors=True)
