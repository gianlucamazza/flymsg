"""Re-read of the archived sensitivity grid (SF2, #148).

The YAML file is the lock. It names `results/sensitivity/v1` and a rule for when two
parameter cells are equivalent. The grid was already reported, so this is not a new
experiment and not a confirmatory claim. Parameters without a distribution in the
evidence table stay blocked: this module does not invent an interval for them.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flymsg import locks, sensitivity

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "identifiability.yaml"

VERSION_HASHES = {
    1: "7005af13b01014f69bc431ed4e5b4662f4f95fa02bff69afadbce17d3bf90f7c",
}


class IdentifiabilityError(ValueError):
    """The identifiability re-read drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return locks.prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(
        doc, VERSION_HASHES, IdentifiabilityError, "identifiability re-read"
    )


def check_parameters(doc: dict) -> None:
    """A blocked row has no interval. Any other row must name an evidence record."""
    for row in doc["parameters"]:
        if row["status"] == "blocked":
            continue
        if row["status"] != "sourced" or not row.get("evidence"):
            raise IdentifiabilityError(
                f"{row['name']} needs status blocked, or sourced with an evidence id"
            )


def assert_matches_code(doc: dict | None = None) -> dict:
    """The archive is the sensitivity lock's grid, and every parameter row is blocked
    unless it names a real evidence record."""
    doc = assert_locked() if doc is None else doc
    grid = sensitivity.assert_locked()
    if doc["archive"]["sensitivity_sha256"] != grid["content_sha256"]:
        raise IdentifiabilityError("the archive is not the locked sensitivity grid")
    if doc["archive"]["sensitivity_version"] != grid["version"]:
        raise IdentifiabilityError("the archive version is not the sensitivity lock")
    if doc["claim"]["scored"] is not False or doc["defaults_changed"] is not False:
        raise IdentifiabilityError("the re-read is not a score and changes no default")
    check_parameters(doc)
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    blocked = [row["name"] for row in doc["parameters"] if row["status"] == "blocked"]
    return (
        f"identifiability v{doc['version']} (issue #{doc['issue']}): "
        f"re-read {doc['archive']['cells']}; blocked parameters: {', '.join(blocked)}; "
        "not a new experiment"
    )


def _parent(parents: dict, cell: tuple) -> tuple:
    while parents[cell] != cell:
        parents[cell] = parents[parents[cell]]
        cell = parents[cell]
    return cell


def judge(cells: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Per response: equivalence classes of parameter cells, and whether the seed range
    already covers the whole grid."""
    grid = sensitivity.load()
    holds = sensitivity.holds(cells, grid)
    quantum = 1000.0 / grid["grid"]["stim_ms"]
    rows = []
    grouped = cells.groupby(["case", "target"], sort=False)
    for (case, target), group in grouped:
        medians = (
            group.groupby(["w_syn_factor", "th_jump"])["rate"].median().rename("median")
        )
        spans = (
            group.groupby(["w_syn_factor", "th_jump"])["rate"]
            .agg(lambda s: float(s.max() - s.min()))
            .rename("seed_range")
        )
        table = medians.to_frame().join(spans).reset_index()
        flags = holds[(holds["case"] == case) & (holds["target"] == target)]
        table = table.merge(
            flags[["w_syn_factor", "th_jump", "holds"]],
            on=["w_syn_factor", "th_jump"],
        )
        default = table[(table["w_syn_factor"] == 1.0) & (table["th_jump"] == 0.0)]
        if len(default) != 1:
            raise IdentifiabilityError(f"{case}/{target} has no single default cell")
        tolerance = max(float(default["seed_range"].iloc[0]), quantum)
        spread = float(table["median"].max() - table["median"].min())
        cells_ = [(float(r.w_syn_factor), float(r.th_jump)) for r in table.itertuples()]
        parents = {cell: cell for cell in cells_}
        lookup = {
            (float(r.w_syn_factor), float(r.th_jump)): r for r in table.itertuples()
        }
        for i, left in enumerate(cells_):
            for right in cells_[i + 1 :]:
                a, b = lookup[left], lookup[right]
                if bool(a.holds) == bool(b.holds) and abs(a.median - b.median) <= (
                    tolerance + 1e-9
                ):
                    ra, rb = _parent(parents, left), _parent(parents, right)
                    parents[rb] = ra
        classes: dict[tuple, list] = {}
        for cell in cells_:
            classes.setdefault(_parent(parents, cell), []).append(cell)
        default_median = float(default["median"].iloc[0])
        positive = case in grid["cases"]["positive"]
        rows.append(
            {
                "case": case,
                "target": target,
                "classes": len(classes),
                "default_class_size": len(classes[_parent(parents, (1.0, 0.0))]),
                "grid_cells": len(cells_),
                "undecidable": tolerance + 1e-9 >= spread,
                "matches_silent_null": positive and default_median <= quantum + 1e-9,
                "default_median_hz": default_median,
                "seed_range_hz": float(default["seed_range"].iloc[0]),
                "median_spread_hz": spread,
            }
        )
    return pd.DataFrame(rows)


def parameter_table(doc: dict) -> pd.DataFrame:
    """Blocked rows have no interval. Sourced rows only name an evidence id."""
    rows = []
    for row in doc["parameters"]:
        rows.append(
            {
                "parameter": row["name"],
                "status": row["status"],
                "interval": "none" if row["status"] == "blocked" else "evidence",
                "why": row["why"],
            }
        )
    return pd.DataFrame(rows)


def report(cells: pd.DataFrame, doc: dict) -> str:
    judged = judge(cells, doc)
    lines = [
        summary(doc),
        judged.to_string(index=False),
        "",
        parameter_table(doc).to_string(index=False),
    ]
    return "\n".join(lines)


def write_report(doc: dict | None = None, root: Path = ROOT) -> Path:
    doc = assert_matches_code() if doc is None else doc
    path = root / doc["archive"]["cells"]
    if not path.is_file():
        raise IdentifiabilityError(f"missing archive {path}")
    text = report(pd.read_csv(path), doc)
    out = root / "runs" / "identifiability" / f"v{doc['version']}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.txt").write_text(text + "\n")
    return out / "report.txt"
