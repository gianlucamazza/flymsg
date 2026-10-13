"""Execution-bound, process-exclusive experiment outputs on a local filesystem."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from flymsg import electrical, manifest

SCHEMA = "flymsg.execution/v1"
_active = ContextVar("flymsg_execution", default=None)


def record_work(kind: str, names) -> None:
    run = _active.get()
    if run is not None:
        run.attempts[-1].setdefault(kind, []).extend(names)


def producer_attempt():
    run = _active.get()
    return run.attempts[-1]["id"] if run is not None else None


@contextmanager
def checkpoint_owner(path: Path, identity: dict):
    """Honor an explicit checkpoint path, with identity and exclusive ownership."""
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = path.with_name(path.name + ".execution.json")
    with writer_lock(path.with_name(path.name + ".execution-owner.lock")):
        if marker.exists():
            if json.loads(marker.read_text()) != identity:
                raise ValueError("checkpoint belongs to another execution identity")
        else:
            existing = [
                p
                for p in path.parent.glob(path.name + "*")
                if p != path.with_name(path.name + ".execution-owner.lock")
            ]
            if existing:
                raise ValueError(
                    "legacy/external checkpoint has no execution identity; use a new path"
                )
            atomic_json(marker, identity)
        yield


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path: Path, value) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        sync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def writer_lock(path: Path):
    if sys.platform != "linux":
        raise ValueError(
            "managed experiment writes require qualified Linux file locking"
        )
    import fcntl

    with path.open("ab") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f"another process owns {path.parent}") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def inventory(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"artifact symlinks are unsupported: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "sha256": manifest.sha256_file(path),
                "bytes": path.stat().st_size,
            }
    return result


def verify_inventory(root: Path, expected: dict) -> None:
    if not root.is_dir() or inventory(root) != expected:
        raise ValueError(f"artifact integrity mismatch: {root}")


def verify_completed(root: Path) -> dict:
    """Validate a published execution for indexing/export, without opening it for writes."""
    try:
        identity = json.loads((root / "execution.json").read_text())["identity"]
        complete = json.loads((root / "complete.json").read_text())
        if complete["execution_sha256"] != digest(identity) or root.name != digest(
            identity
        ):
            raise ValueError("completed execution identity mismatch")
        verify_inventory(root / "output", complete["artifacts"])
        return complete
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"missing or invalid completion record: {root}") from exc


def sync_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        sync_dir(path)
    sync_dir(root)


def environment() -> dict:
    # Capture before computation; include optional consumers such as FlyGym/rdata too.
    packages = {d.metadata["Name"].lower(): d.version for d in metadata.distributions()}
    cpu = {}
    if sys.platform == "linux":
        for line in Path("/proc/cpuinfo").read_text().split("\n\n", 1)[0].splitlines():
            key, _, value = line.partition(":")
            if key.strip() in {
                "vendor_id",
                "model name",
                "cpu family",
                "model",
                "stepping",
                "microcode",
                "flags",
            }:
                cpu[key.strip()] = value.strip()
    return {
        "cpu": cpu,
        "packages": dict(sorted(packages.items())),
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
        "numerical_threads": {
            name: os.environ.get(name)
            for name in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMBA_NUM_THREADS",
            )
        },
    }


def files(paths: dict[str, Path]) -> dict:
    result = {}
    for name, path in sorted(paths.items()):
        if not path.is_file() or path.is_symlink():
            raise ValueError(
                f"required input is missing or a symlink: {path}; run flymsg fetch/build"
            )
        before = path.stat()
        checksum = manifest.sha256_file(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"input changed while hashing: {path}")
        result[name] = {"sha256": checksum, "bytes": after.st_size}
    return result


def execution(
    command: str, config: dict, protocol: dict, paths: dict[str, Path]
) -> dict:
    source = manifest.git_info()
    if source["dirty"] is not False or not source["commit"]:
        raise ValueError(
            "managed runs require clean committed source; use a clean worktree"
        )
    return {
        "schema": SCHEMA,
        "command": command,
        "config": config,
        "protocol": protocol,
        "source": source,
        "environment": environment(),
        "inputs": files(paths),
        "electrical_semantics": electrical.SEMANTICS,
    }


def verify_execution(identity: dict, paths: dict[str, Path]) -> None:
    if (
        manifest.git_info() != identity["source"]
        or environment() != identity["environment"]
        or files(paths) != identity["inputs"]
    ):
        raise ValueError(
            "execution inputs, source or environment changed during the run"
        )


class Run:
    """One execution identity, immutable final output, and an attempt history."""

    def __init__(self, base: Path, identity: dict):
        self.identity = json.loads(canonical(identity))
        self.id = digest(self.identity)
        # A historical version directory itself is never modified.
        self.root = base.parent / f"{base.name}.executions" / self.id
        self.output = self.root / ".output"
        self.completed = False
        self.exit_code = 0
        self.attempts = []

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self._owner = writer_lock(self.root / ".writer.lock")
        self._owner.__enter__()
        try:
            record = self.root / "execution.json"
            if record.exists():
                original = json.loads(record.read_text())
                if original["identity"] != self.identity:
                    raise ValueError("execution identity mismatch")
            else:
                if {p.name for p in self.root.iterdir()} != {".writer.lock"}:
                    raise ValueError(
                        "unidentified execution directory; refusing legacy artifacts"
                    )
                original = {"identity": self.identity, "started_at": now()}
                atomic_json(record, original)
            self.started = datetime.fromisoformat(original["started_at"])
            complete = self.root / "complete.json"
            publication = self.root / "publication.json"
            final = self.root / "output"
            if complete.exists():
                record = json.loads(complete.read_text())
                self._verify_complete(record)
                self.exit_code = record.get("exit_code", 0)
                self.output, self.completed = final, True
                return self
            # Recovery after the atomic output rename, before the completion record.
            if final.exists():
                if not publication.is_file():
                    raise ValueError("unidentified final output")
                published = json.loads(publication.read_text())
                self._verify_complete(published)
                self._recover_attempts(final)
                atomic_json(complete, published)
                self.exit_code = published.get("exit_code", 0)
                self.output, self.completed = final, True
                return self
            if publication.exists():
                # Prepared but not renamed: validate and finish without recomputing.
                published = json.loads(publication.read_text())
                if published.get("execution_sha256") != self.id:
                    raise ValueError("publication identity mismatch")
                verify_inventory(self.output, published["artifacts"])
                self.output.rename(final)
                sync_dir(self.root)
                self._recover_attempts(final)
                atomic_json(complete, published)
                self.exit_code = published.get("exit_code", 0)
                self.output, self.completed = final, True
                return self
            attempts = self.root / "attempts.json"
            self.attempts = (
                json.loads(attempts.read_text()) if attempts.exists() else []
            )
            for attempt in self.attempts:
                if attempt["status"] == "running":
                    attempt.update(status="interrupted", detected_at=now())
            self.attempts.append(
                {"id": uuid.uuid4().hex, "started_at": now(), "status": "running"}
            )
            atomic_json(attempts, self.attempts)
            # This is explicitly uncommitted output; never touch a finalized output.
            if self.output.exists():
                shutil.rmtree(self.output)
            self.output.mkdir()
            self._token = _active.set(self)
            return self
        except BaseException:
            self._owner.__exit__(*sys.exc_info())
            raise

    def _verify_complete(self, record: dict):
        if record.get("execution_sha256") != self.id:
            raise ValueError("completion identity mismatch")
        verify_inventory(self.root / "output", record["artifacts"])

    def _recover_attempts(self, final):
        doc = json.loads((final / "manifest.json").read_text())
        atomic_json(self.root / "attempts.json", doc["extra"]["attempts"])

    def finalize(self, *, exit_code=0):
        if self.completed:
            return
        if not (self.output / "manifest.json").is_file():
            raise ValueError("cannot complete a run without a manifest")
        self.attempts[-1].update(status="completed", finished_at=now())
        doc = json.loads((self.output / "manifest.json").read_text())
        doc.setdefault("extra", {}).update(
            execution_sha256=self.id, execution=self.identity, attempts=self.attempts
        )
        atomic_json(self.output / "manifest.json", doc)
        sync_tree(self.output)
        published = {
            "execution_sha256": self.id,
            "artifacts": inventory(self.output),
            "exit_code": exit_code,
        }
        atomic_json(self.root / "publication.json", published)
        self.output.rename(self.root / "output")
        sync_dir(self.root)
        atomic_json(self.root / "attempts.json", self.attempts)
        atomic_json(self.root / "complete.json", published)
        self.output, self.completed = self.root / "output", True

    def __exit__(self, kind, value, tb):
        try:
            if not self.completed and self.attempts:
                self.attempts[-1].update(
                    status="interrupted" if kind else "incomplete", finished_at=now()
                )
                atomic_json(self.root / "attempts.json", self.attempts)
        finally:
            if hasattr(self, "_token"):
                _active.reset(self._token)
            self._owner.__exit__(kind, value, tb)

    def stamp(self, *, command, config, seeds, dataset, extra):
        # Public references must point at final output, not its staging name.
        def final_refs(value):
            if isinstance(value, dict):
                return {k: final_refs(v) for k, v in value.items()}
            if isinstance(value, list):
                return [final_refs(v) for v in value]
            if isinstance(value, str) and value.startswith(str(self.output)):
                return str(self.root / "output") + value[len(str(self.output)) :]
            return value

        extra = final_refs(extra)
        manifest.write(
            self.output,
            command=command,
            config=config,
            seeds=seeds,
            dataset=dataset,
            started_at=self.started,
            extra=extra,
            provenance={
                "git": self.identity["source"],
                "packages": self.identity["environment"]["packages"],
                "preregistration": self.identity["protocol"],
            },
        )
