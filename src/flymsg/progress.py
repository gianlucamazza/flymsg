"""Progress and resumable steps for long locked runs.

Floats are written as their shortest repr and read back with the round-trip parser, so
a resumed table equals the computed one bit for bit. `Progress` prints the measured rate and the remaining time after each unit of work, so a
run's ETA is measured, not guessed. `Steps` stores each finished step's tables under the
run's directory, bound to the lock's content hash, so an interrupted run resumes with the
steps it already finished and never mixes steps of two different locks. The simulations
are deterministic given the lock, so a resumed run equals an uninterrupted one.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd


class Progress:
    def __init__(self, total: int, label: str, stream=None):
        self.total, self.label, self.done = total, label, 0
        self.stream = sys.stderr if stream is None else stream
        self.started = time.monotonic()

    def step(self, n: int = 1, note: str = "") -> None:
        self.done += n
        elapsed = time.monotonic() - self.started
        rate = self.done / elapsed if elapsed > 0 else 0.0
        eta = (self.total - self.done) / rate if rate > 0 else float("nan")
        print(
            f"[{self.label}] {self.done}/{self.total} in {elapsed / 60:.1f} min, "
            f"eta {eta / 60:.1f} min{f' ({note})' if note else ''}",
            file=self.stream,
            flush=True,
        )


class Steps:
    """Finished steps of one locked run, stored as CSV tables in `root/<step>/`."""

    def __init__(self, root: Path | None, lock_sha256: str):
        self.root, self.lock = root, lock_sha256
        # steps read back instead of computed, recorded in the manifest
        self.resumed: list[str] = []
        if root is None:
            return
        root.mkdir(parents=True, exist_ok=True)
        marker = root / "lock.json"
        if marker.exists():
            if json.loads(marker.read_text())["content_sha256"] != lock_sha256:
                raise ValueError(f"{root} holds steps of another lock")
        else:
            marker.write_text(json.dumps({"content_sha256": lock_sha256}) + "\n")

    def done(self, step: str) -> bool:
        return self.root is not None and (self.root / step / "done").exists()

    def get(
        self, step: str, compute: Callable[[], dict[str, pd.DataFrame]]
    ) -> tuple[dict[str, pd.DataFrame], bool]:
        """The step's tables, and whether they were computed now (False: resumed)."""
        if self.done(step):
            d = self.root / step
            self.resumed.append(step)
            return {
                f.stem: pd.read_csv(f, float_precision="round_trip")
                for f in sorted(d.glob("*.csv"))
            }, False
        tables = compute()
        if self.root is not None:
            d = self.root / step
            d.mkdir(exist_ok=True)
            for name, table in tables.items():
                table.to_csv(d / f"{name}.csv", index=False)
            (d / "done").write_text("")
        return tables, True
