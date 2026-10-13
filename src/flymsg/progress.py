"""Measured progress and atomic, execution-bound typed step tables."""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from flymsg import runstore


class Progress:
    def __init__(self, total: int, label: str, stream=None):
        self.total, self.label, self.done = total, label, 0
        self.resumed, self.computed, self.compute_seconds = 0, 0, 0.0
        self.stream = sys.stderr if stream is None else stream
        self.started = self.last = time.monotonic()

    def step(self, n: int = 1, note: str = "", *, resumed: bool = False) -> None:
        if n < 0 or self.done + n > self.total:
            raise ValueError("progress exceeds its workload")
        current = time.monotonic()
        self.done += n
        if resumed:
            self.resumed += n
        else:
            self.computed += n
            self.compute_seconds += current - self.last
        self.last = current
        eta = (
            f"{(self.total - self.done) * self.compute_seconds / self.computed / 60:.1f} min"
            if self.computed
            else "unknown"
        )
        print(
            f"[{self.label}] {self.done}/{self.total} in {(current - self.started) / 60:.1f} min, "
            f"eta {eta}, computed {self.computed}, resumed {self.resumed}"
            f"{f' ({note})' if note else ''}",
            file=self.stream,
            flush=True,
        )


class Steps:
    """Finished tables, published atomically and verified before reuse.

    Persistent callers supply the full execution identity, never a protocol hash alone.
    Parquet preserves typed strings, missing values, indices and exact IEEE floats.
    """

    def __init__(self, root: Path | None, identity: dict | str):
        self.root, self.resumed = root, []
        self.computed = []
        if root is None:
            self.id = None
            return
        if not isinstance(identity, dict):
            raise TypeError(
                "persistent steps require a full execution identity, not a lock hash"
            )
        self.id = runstore.digest(identity)
        root.mkdir(parents=True, exist_ok=True)
        with runstore.writer_lock(root / ".writer.lock"):
            marker = root / "execution.json"
            if marker.exists():
                if json.loads(marker.read_text()) != identity:
                    raise ValueError(
                        f"{root} holds steps of another execution identity"
                    )
            else:
                if {p.name for p in root.iterdir()} != {".writer.lock"}:
                    raise ValueError(f"{root} contains unidentified legacy steps")
                runstore.atomic_json(marker, identity)

    def done(self, step: str) -> bool:
        return self.root is not None and (self.root / step).exists()

    def get(
        self, step: str, compute: Callable[[], dict[str, pd.DataFrame]]
    ) -> tuple[dict[str, pd.DataFrame], bool]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+\-]*", step) or step in {
            "execution.json"
        }:
            raise ValueError("invalid step name")
        if self.root is None:
            self.computed.append(step)
            return compute(), True
        with runstore.writer_lock(self.root / ".writer.lock"):
            dest = self.root / step
            if dest.exists():
                record = dest / "step.json"
                if not record.is_file():
                    raise ValueError(f"incomplete or legacy completed step: {dest}")
                meta = json.loads(record.read_text())
                if (
                    meta.get("schema") != "flymsg.step/v1"
                    or meta.get("execution_sha256") != self.id
                ):
                    raise ValueError(f"step identity mismatch: {dest}")
                expected = meta["files"]
                actual = runstore.inventory(dest)
                actual.pop("step.json", None)
                if actual != expected:
                    raise ValueError(f"step integrity mismatch: {dest}")
                tables = {}
                for name, schema in meta["tables"].items():
                    table = pd.read_parquet(dest / f"{name}.parquet")
                    if self._schema(table) != schema:
                        raise ValueError(f"step schema mismatch: {dest}")
                    tables[name] = table
                if set(expected) != {f"{name}.parquet" for name in tables}:
                    raise ValueError(f"step inventory mismatch: {dest}")
                self.resumed.append(step)
                runstore.record_work("resumed_steps", [step])
                return tables, False
            for abandoned in self.root.glob(f".{step}.*.tmp"):
                token = abandoned.name[len(step) + 2 : -4]
                if (
                    re.fullmatch(r"[0-9a-f]{32}", token)
                    and abandoned.is_dir()
                    and not abandoned.is_symlink()
                ):
                    shutil.rmtree(abandoned)
            tables = compute()
            staging = self.root / f".{step}.{uuid.uuid4().hex}.tmp"
            staging.mkdir()
            try:
                schemas = {}
                for name, table in tables.items():
                    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]*", name):
                        raise ValueError("invalid table name")
                    table.to_parquet(staging / f"{name}.parquet", index=True)
                    schemas[name] = self._schema(table)
                runstore.atomic_json(
                    staging / "step.json",
                    {
                        "schema": "flymsg.step/v1",
                        "execution_sha256": self.id,
                        "producer_attempt": runstore.producer_attempt(),
                        "tables": schemas,
                        "files": runstore.inventory(staging),
                    },
                )
                runstore.sync_tree(staging)
                staging.rename(dest)
                runstore.sync_dir(self.root)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            self.computed.append(step)
            runstore.record_work("computed_steps", [step])
            return tables, True

    @staticmethod
    def _schema(table):
        return {
            "rows": len(table),
            "columns": list(table.columns),
            "dtypes": [str(d) for d in table.dtypes],
        }
