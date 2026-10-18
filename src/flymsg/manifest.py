"""Run manifests written next to command outputs."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from flymsg import lock_codec

ROOT = Path(__file__).resolve().parents[2]
PREREG_PATH = ROOT / "validation" / "preregistration.yaml"

SCHEMA = "flymsg.run_manifest/v1"
PACKAGES = ("flymsg", "numpy", "pandas", "numba", "scipy", "pyarrow")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_info(root: Path | None = None) -> dict:
    root = root or ROOT
    info = {"commit": None, "dirty": None}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        info["commit"] = commit
        info["dirty"] = bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        pass
    return info


def package_versions() -> dict[str, str | None]:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def dataset_info(
    name: str,
    data_dir: Path | None = None,
    neurons=None,
    edges=None,
) -> dict:
    info = {
        "name": name,
        "release": "v1.0" if name == "malecns" else name,
        "n_neurons": None if neurons is None else len(neurons),
        "n_edges": None if edges is None else len(edges),
        "files": {},
    }
    if data_dir is not None:
        base = data_dir / "fafb" if name == "fafb" else data_dir
        for fn in ("neurons.parquet", "edges.parquet"):
            path = base / fn
            if path.is_file():
                info["files"][fn] = {
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
    return info


# git state when the command started; a long run must not record a checkout made while it ran
_START_GIT: dict | None = None


def mark_start() -> None:
    """Record the git state now; `write` uses it instead of the state at the end."""
    global _START_GIT
    _START_GIT = git_info()


def write(
    out: Path,
    *,
    command: str,
    config: dict,
    seeds: dict,
    dataset: dict,
    started_at: datetime,
    finished_at: datetime | None = None,
    extra: dict | None = None,
    provenance: dict | None = None,
) -> Path:
    """Write `manifest.json` next to a run's outputs and return its path."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    finished = finished_at or datetime.now(UTC)
    try:
        doc = lock_codec.load_yaml(PREREG_PATH.read_text(encoding="utf-8"))
        prereg_info = {
            "version": doc["version"],
            "content_sha256": doc["content_sha256"],
        }
    except (OSError, lock_codec.PreregistrationError):
        prereg_info = None
    payload = {
        "schema": SCHEMA,
        "command": command,
        "git": _START_GIT if _START_GIT is not None else git_info(),
        "dataset": dataset,
        "config": config,
        "seeds": seeds,
        "preregistration": prereg_info,
        "packages": package_versions(),
        "platform": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "timestamps": {
            "started_at": started_at.astimezone(UTC).isoformat(),
            "finished_at": finished.astimezone(UTC).isoformat(),
        },
        "cwd": os.fspath(Path.cwd()),
    }
    if provenance:
        payload.update(provenance)
    if extra:
        payload["extra"] = extra
    path = out / "manifest.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def required_keys(doc: dict) -> list[str]:
    missing = []
    for key in (
        "schema",
        "command",
        "git",
        "dataset",
        "config",
        "seeds",
        "packages",
        "platform",
        "timestamps",
    ):
        if key not in doc:
            missing.append(key)
    if "timestamps" in doc:
        for key in ("started_at", "finished_at"):
            if key not in doc["timestamps"]:
                missing.append(f"timestamps.{key}")
    if "git" in doc and "commit" not in doc["git"]:
        missing.append("git.commit")
    if "dataset" in doc:
        for key in ("name", "files"):
            if key not in doc["dataset"]:
                missing.append(f"dataset.{key}")
    return missing
