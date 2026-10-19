"""The locked comparison of two synapse-weight rules on Liu et al. 2022's measured PN -> LHN
unitary EPSPs (issue #139): synapse count against synapse density (count over the
postsynaptic surface area). No simulation: the model is linear in the weight at one synapse,
so a rank statistic only needs each pair's count and each type's area."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import locks
from flymsg.paths import repository_root

ROOT = repository_root()
PATH = ROOT / "validation" / "weight_rule.yaml"
AREAS = "weight_rule/areas.csv"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "87a33e5fbc589f4445386618275c46bf88c18d7f97d46e1b02e82ff4535ef79d",  # Liu 2022 Table S3, six matched LHN types, Spearman, paired bootstrap seed 139
}


class WeightRuleError(ValueError):
    """The weight-rule protocol drifted from the locked version, or an input is missing."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, WeightRuleError, "weight-rule protocol")


def summary(doc: dict | None = None) -> str:
    doc = assert_locked() if doc is None else doc
    return (
        f"weight-rule v{doc['version']} (issue #139): {len(doc['pairs'])} pairs of "
        f"{len(doc['matched_types'])} matched LHN types, Spearman per rule, "
        f"paired bootstrap seed {doc['protocol']['seed']}"
    )


def lhn_types(doc: dict, sensitivity: bool = False) -> dict[str, list[str]]:
    types = dict(doc["matched_types"])
    if sensitivity:
        types.update(doc["partial_types"])
    return types


def pn_type(doc: dict, glom: str) -> str:
    hits = [t for t in doc["protocol"]["pn_types"] if t.split("_")[0] == glom]
    if len(hits) != 1:
        raise WeightRuleError(f"no single PN type for glomerulus {glom}")
    return hits[0]


def area_bodies(doc: dict, neurons: pd.DataFrame) -> pd.DataFrame:
    """Every MaleCNS neuron of the matched and partial LHN types: the meshes to measure."""
    rows = []
    for liu, types in lhn_types(doc, sensitivity=True).items():
        for t in types:
            for body in neurons.loc[neurons["type"] == t, "bodyId"]:
                rows.append({"liu_type": liu, "type": t, "bodyId": int(body)})
    return pd.DataFrame(rows)


def fetch_areas(doc: dict, neurons: pd.DataFrame, data_dir: Path) -> Path:
    """Measure the meshes with scripts/mesh_area.mjs into data/weight_rule/areas.csv, an input
    frozen before the locked run. A body without a mesh is written with an empty area."""
    bodies = area_bodies(doc, neurons)
    out = data_dir / AREAS
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["node", str(ROOT / "scripts" / "mesh_area.mjs"), *map(str, bodies["bodyId"])],
        capture_output=True,
        text=True,
        check=False,  # the error is reported with Node's stderr below
    )
    if proc.returncode:
        raise WeightRuleError(f"mesh_area.mjs failed:\n{proc.stderr.strip()}")
    measured = {int(r["bodyId"]): r for r in map(json.loads, proc.stdout.splitlines())}
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bodyId", "type", "area_um2", "fragments", "triangles"])
        for b in bodies.itertuples():
            r = measured.get(b.bodyId, {})
            w.writerow(
                [
                    b.bodyId,
                    b.type,
                    r.get("area_um2", ""),
                    r.get("fragments", ""),
                    r.get("triangles", ""),
                ]
            )
    return out


def pair_counts(
    doc: dict, neurons: pd.DataFrame, edges: pd.DataFrame, pairs: list[dict]
) -> pd.DataFrame:
    """Per pair: the mean over LHN neurons of the summed count from the glomerulus's PN on
    the same side, then the mean over the sides that have both."""
    types = lhn_types(doc, sensitivity=True)
    side = neurons["somaSide"].fillna("")
    all_pns = np.flatnonzero(
        neurons["type"].isin(doc["protocol"]["pn_types"]).to_numpy()
    )
    edges = edges[edges["pre"].isin(all_pns)]  # once, not per pair
    rows = []
    for p in pairs:
        glom, liu = p["pair"].split("/")
        pns = neurons["type"] == pn_type(doc, glom)
        lhns = neurons["type"].isin(types[liu])
        per_side = []
        for s in ("L", "R"):
            pre = np.flatnonzero((pns & (side == s)).to_numpy())
            post = np.flatnonzero((lhns & (side == s)).to_numpy())
            if pre.size == 0 or post.size == 0:
                continue
            e = edges[edges["pre"].isin(pre) & edges["post"].isin(post)]
            per_post = e.groupby("post")["weight"].sum().reindex(post, fill_value=0)
            per_side.append(float(per_post.mean()))
        rows.append(
            {
                "pair": p["pair"],
                "liu_type": liu,
                "uepsp_mv": float(p["uepsp_mv"]),
                "sides": len(per_side),
                "count": float(np.mean(per_side)) if per_side else np.nan,
            }
        )
    return pd.DataFrame(rows)


def type_areas(doc: dict, areas: pd.DataFrame) -> dict[str, float]:
    """Mean mesh area per Liu LHN type over all its MaleCNS neurons; NaN if any has none."""
    out = {}
    for liu, types in lhn_types(doc, sensitivity=True).items():
        a = areas.loc[areas["type"].isin(types), "area_um2"]
        out[liu] = float(a.mean()) if len(a) and a.notna().all() else np.nan
    return out


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def compare(table: pd.DataFrame, seed: int, n_boot: int = 10000) -> dict:
    """Spearman per rule, their difference and its paired bootstrap 95% interval."""
    u = table["uepsp_mv"].to_numpy()
    c = table["count"].to_numpy()
    d = table["density"].to_numpy()
    rho_c, rho_d = spearman(c, u), spearman(d, u)
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(n_boot):
        i = rng.integers(0, len(u), len(u))
        delta = spearman(d[i], u[i]) - spearman(c[i], u[i])
        if np.isfinite(delta):
            deltas.append(delta)
    lo, hi = np.percentile(deltas, [2.5, 97.5]) if deltas else (np.nan, np.nan)
    return {
        "pairs": len(u),
        "rho_count": rho_c,
        "rho_density": rho_d,
        "delta": rho_d - rho_c,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "boot_valid": len(deltas),
    }


def verdict(stats: dict, n_types: int) -> str:
    if stats["pairs"] < 10 or n_types < 4:
        return "not_testable"
    if stats["ci_low"] > 0:
        return "density"
    if stats["ci_high"] < 0:
        return "count"
    return "undecided"


def run(
    doc: dict, neurons: pd.DataFrame, edges: pd.DataFrame, areas: pd.DataFrame
) -> dict:
    seed = doc["protocol"]["seed"]
    area = type_areas(doc, areas)
    out = {}
    for name, pairs in (
        ("primary", doc["pairs"]),
        ("sensitivity", doc["pairs"] + doc["sensitivity_pairs"]),
    ):
        t = pair_counts(doc, neurons, edges, pairs)
        t["area_um2"] = t["liu_type"].map(area)
        t["density"] = t["count"] / t["area_um2"]
        out[f"{name}_table"] = t
        usable = t.dropna(subset=["count", "density"])
        out[name] = compare(usable, seed)
        out[f"{name}_types"] = int(usable["liu_type"].nunique())
        if name == "primary":
            measured = usable[usable["uepsp_mv"] > 0]
            out["measured_only"] = compare(measured, seed)
            dens, amp = usable["density"].to_numpy(), usable["uepsp_mv"].to_numpy()
            out["density_fit_r2"] = (
                float(np.corrcoef(dens, amp)[0, 1] ** 2) if dens.std() > 0 else np.nan
            )
    missing = [liu for liu in doc["matched_types"] if not np.isfinite(area[liu])]
    out["verdict"] = (
        "not_testable" if missing else verdict(out["primary"], out["primary_types"])
    )
    out["missing_areas"] = missing
    return out
