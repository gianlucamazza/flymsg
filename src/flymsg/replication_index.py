"""Build the replication index from archived manifests."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from flymsg import gf_looming, managed, song
from flymsg.archive_results import DIRS

SCHEMA = "flymsg.replication_index/v1"
PROTOCOLS = {**managed.PROTOCOLS, "gf-looming": gf_looming, "song": song}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock_of(command: str, protocols: dict, root: Path) -> str | None:
    module = protocols.get(command.split()[0])
    path = getattr(module, "PATH", None)
    return str(path.relative_to(root)) if path is not None else None


def _config(m: dict, suffix: str):
    """The experiment lock's version or hash as a historical command recorded it."""
    found = [v for k, v in (m.get("config") or {}).items() if k.endswith(suffix)]
    return found[0] if len(found) == 1 else None


def entry(rel: str, *, results: Path, protocols: dict, root: Path) -> dict:
    folder = results / rel
    m = json.loads((folder / "manifest.json").read_text())
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
        "lock": lock_of(m.get("command") or "", protocols, root),
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
            for p in sorted(folder.iterdir())
            if p.is_file() and p.name != "manifest.json"
        },
    }


def build(
    *,
    results: Path,
    protocols: dict,
    root: Path,
    dirs: tuple[str, ...] = DIRS,
    schema: str = SCHEMA,
) -> dict:
    return {
        "schema": schema,
        "results": [
            entry(rel, results=results, protocols=protocols, root=root) for rel in dirs
        ],
    }


def main(
    argv: list[str],
    *,
    results: Path,
    protocols: dict,
    root: Path,
    index: Path,
    dirs: tuple[str, ...] = DIRS,
    schema: str = SCHEMA,
) -> None:
    text = (
        json.dumps(
            build(
                results=results,
                protocols=protocols,
                root=root,
                dirs=dirs,
                schema=schema,
            ),
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )
    if "--check" in argv:
        if not index.is_file() or index.read_text() != text:
            sys.exit(
                f"{index.relative_to(root)} is stale; rerun scripts/replication_index.py"
            )
        return print(f"{index.relative_to(root)} matches results/")
    index.write_text(text)
    print(f"{len(dirs)} results -> {index.relative_to(root)}")
