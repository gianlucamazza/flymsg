"""Compare a viewer benchmark run with the baseline (issue #24). Usage:

    uv run python scripts/bench_check.py runs/viewer-bench/<time>.jsonl [--baseline FILE ...]

Only eligible warm-cache passes count, on both sides. For each scene the baseline range is
the minimum and maximum over its passes; there is no tolerance beyond it, since the spread
between passes on one idle machine is the only measure of noise there is. A candidate is
reported worse when its fps p50 falls below the range or a load mark (first_surface,
all_represented) lands after it, and the script exits 1. The range comes from a handful of
passes: falling outside it is a reason to look, not proof of a regression. fps is compared
only where every baseline pass drew a distribution of frames (p5 below p50): a scene that
redraws only on change, like anatomy, yields one interval, not a frame rate. A run on another
GPU, viewport or GL backend has no baseline here and is refused.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = sorted(
    (ROOT / "docs" / "evidence" / "viewer-bench-2026-10-13").glob("*.jsonl")
)
MARKS = ("first_surface", "all_represented")


def passes(paths) -> list[dict]:
    """Eligible warm passes of the given JSONL files."""
    out = []
    for path in paths:
        for line in Path(path).read_text().splitlines():
            rec = json.loads(line)
            if rec["eligible"] and rec["cache"] == "warm":
                out.append(rec)
    return out


def setup(rec: dict) -> tuple:
    return (rec["gpu"]["renderer"], tuple(rec["viewport"]), rec["gl"])


def metrics(rec: dict) -> dict:
    b = rec["bench"]
    out = {m: b["marks"].get(m) for m in MARKS}
    out["fps"] = b["fps"]["p50"]
    out["frames"] = b["fps"]["p5"] is not None and b["fps"]["p5"] < b["fps"]["p50"]
    return out


def ranges(baseline: list[dict]) -> dict:
    """Per scene and metric: (min, max, n) over the baseline passes that have it."""
    by_scene: dict[str, list[dict]] = {}
    for rec in baseline:
        by_scene.setdefault(rec["scene"], []).append(metrics(rec))
    out = {}
    for scene, ms in by_scene.items():
        out[scene] = {}
        names = list(MARKS) + (["fps"] if all(m["frames"] for m in ms) else [])
        for name in names:
            values = [m[name] for m in ms if m[name] is not None]
            if values:
                out[scene][name] = (min(values), max(values), len(values))
    return out


def compare(candidate: list[dict], baseline: list[dict]) -> list[tuple]:
    """(scene, metric, value, low, high, n, verdict) for each comparable value."""
    setups = {setup(r) for r in baseline}
    rows = []
    table = ranges(baseline)
    for rec in candidate:
        if setup(rec) not in setups:
            raise ValueError(f"{rec['scene']}: no baseline for {setup(rec)}")
        for name, value in metrics(rec).items():
            if name not in table.get(rec["scene"], {}) or value is None:
                continue
            low, high, n = table[rec["scene"]][name]
            worse = value < low if name == "fps" else value > high
            better = value > high if name == "fps" else value < low
            verdict = "worse" if worse else "better" if better else "inside"
            rows.append((rec["scene"], name, value, low, high, n, verdict))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--baseline", nargs="+", type=Path, default=BASELINE)
    a = ap.parse_args()
    candidate = passes([a.run])
    if not candidate:
        sys.exit(f"{a.run}: no eligible warm pass")
    try:
        rows = compare(candidate, passes(a.baseline))
    except ValueError as e:
        sys.exit(str(e))
    for scene, name, value, low, high, n, verdict in rows:
        print(f"{scene:18} {name:16} {value:7} [{low} .. {high}, n={n}] {verdict}")
    if any(r[-1] == "worse" for r in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
