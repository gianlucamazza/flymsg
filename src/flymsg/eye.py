"""Compound-eye geometry on the MaleCNS optic-lobe column grid (issue #84).

Every MaleCNS optic-lobe column has hex coordinates (`assignedOlHex1/2`, Nern et al. 2025).
The eye map of Zhao et al. 2025 gives a viewing direction for each lens on the same hex
grid (reiserlab/eyemap_T4, GPL-3.0: fetched into data/raw/eyemap, never redistributed;
outputs derived from it stay under data/). `columns` joins the two, one row per column with
its direction where a lens exists; `photoreceptors` assigns each simulated photoreceptor to
the column of its strongest output. Nothing here simulates.

Conventions: azimuth 0 is straight ahead and grows toward the fly's right; elevation grows
dorsally. The map is of one right eye (micro-CT of a female head); the left eye is its
mirror image, a named assumption (Zhao et al. assume left-right symmetry too).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rdata
from scipy import stats

from flymsg import data

EYEMAP_COMMIT = "99d2a43123db636cedb55af9ff31a59657e7d17e"
EYEMAP_BASE = (
    f"https://raw.githubusercontent.com/reiserlab/eyemap_T4/{EYEMAP_COMMIT}/data"
)
EYEMAP_FILES = {
    "eyemap.RData": f"{EYEMAP_BASE}/eyemap.RData",
    "20240701.RData": f"{EYEMAP_BASE}/microCT/20240701.RData",
}
HEX_ORIGIN = (18, 19)  # hex1, hex2 of the column p = q = 0 (Nern et al. 2025)
COLUMN_TYPE = "L1"  # one per column, every column assigned
RECEPTORS = {"R1-R6": r"^R1-R6$", "R7": r"^R7", "R8": r"^R8"}
DORSAL_RIM = ("R7d", "R8d")  # dorsal rim area photoreceptors


def raw_dir(data_dir: Path) -> Path:
    return data_dir / "raw" / "eyemap"


def fetch(data_dir: Path) -> None:
    out = raw_dir(data_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, url in EYEMAP_FILES.items():
        dest = out / name
        if dest.exists():
            print(f"ok      eyemap/{name}")
            continue
        print(f"fetch   eyemap/{name}")
        data.download(url, dest)


def pq(hex1, hex2) -> tuple[np.ndarray, np.ndarray]:
    """Zhao/Nern (p, q) of MaleCNS hex coordinates."""
    return (
        np.asarray(hex2, dtype=int) - HEX_ORIGIN[1],
        np.asarray(hex1, dtype=int) - HEX_ORIGIN[0],
    )


def lens_table(lens_ixy, i_match, ucl, left) -> pd.DataFrame:
    """Right-eye lenses with p, q and the unit viewing direction (x front, y the fly's
    left, z up), as proc_eyemap.R builds them: `ucl[order(i_match), ][!left, ]` has one
    row per lens index. `lens_ixy` rows are (lens index from 1, p, q)."""
    lens = np.asarray(lens_ixy).astype(int)
    order = np.argsort(np.asarray(i_match).astype(int), kind="stable")
    right = np.asarray(ucl, dtype=float)[order][~np.asarray(left).astype(bool)]
    xyz = right[lens[:, 0] - 1]
    return pd.DataFrame(
        {
            "p": lens[:, 1],
            "q": lens[:, 2],
            "x": xyz[:, 0],
            "y": xyz[:, 1],
            "z": xyz[:, 2],
        }
    )


def _as_read(obj, _attrs):
    """Keep an R object of a class flymsg does not use as rdata parsed it."""
    return obj


# R classes stored next to the eye map that flymsg reads past (a PCA and an assignment
# result); declared so they convert as parsed instead of warning on every read
CONSTRUCTORS = {
    **rdata.conversion.DEFAULT_CLASS_MAP,
    "prcomp": _as_read,
    "solve_LSAP": _as_read,
}


def lenses(data_dir: Path) -> pd.DataFrame:
    raw = raw_dir(data_dir)
    eyemap = rdata.read_rda(raw / "eyemap.RData", constructor_dict=CONSTRUCTORS)
    uct = rdata.read_rda(raw / "20240701.RData", constructor_dict=CONSTRUCTORS)
    return lens_table(
        eyemap["lens_ixy"], uct["i_match"], uct["ucl_rot_sm"], uct["ind_left_lens"]
    )


def side_of(instance) -> str | None:
    s = instance if isinstance(instance, str) else ""
    return s[-1] if s[-2:] in ("_L", "_R") else None


def columns(annotations: pd.DataFrame, lens: pd.DataFrame) -> pd.DataFrame:
    """One row per optic-lobe column (one L1 each): side, hex1, hex2, p, q, and azimuth and
    elevation in degrees where a lens has the same (p, q); NaN where none does. The left
    eye is the right eye mirrored."""
    l1 = annotations[
        (annotations["type"] == COLUMN_TYPE)
        & annotations["assignedOlHex1"].notna()
        & annotations["assignedOlHex2"].notna()
    ]
    cols = (
        pd.DataFrame(
            {
                "side": l1["instance"].map(side_of),
                "hex1": l1["assignedOlHex1"].astype(int),
                "hex2": l1["assignedOlHex2"].astype(int),
            }
        )
        .dropna(subset=["side"])
        .drop_duplicates()
        .sort_values(["side", "hex1", "hex2"])
        .reset_index(drop=True)
    )
    cols["p"], cols["q"] = pq(cols["hex1"], cols["hex2"])
    merged = cols.merge(lens, on=["p", "q"], how="left")
    # the map's +y is the fly's left, so azimuth toward the right is -atan2(y, x); the left
    # eye mirrors y
    y = np.where(merged["side"] == "L", -merged["y"], merged["y"])
    merged["azimuth_deg"] = np.degrees(-np.arctan2(y, merged["x"]))
    merged["elevation_deg"] = np.degrees(np.arcsin(merged["z"].clip(-1, 1)))
    return merged.drop(columns=["x", "y", "z"])


def photoreceptors(
    neurons: pd.DataFrame, edges: pd.DataFrame, annotations: pd.DataFrame
) -> pd.DataFrame:
    """Each simulated photoreceptor with the column (side, hex1, hex2) that receives most of
    its synapses among column-assigned neurons. Photoreceptors carry no hex label; their
    strongest output names their cartridge (R1-R6) or medulla column (R7, R8)."""
    ann = annotations.set_index("bodyId").reindex(neurons["bodyId"])
    hexed = np.flatnonzero(
        ann["assignedOlHex1"].notna().to_numpy()
        & ann["assignedOlHex2"].notna().to_numpy()
    )
    col = pd.DataFrame(
        {
            "side": neurons["instance"].iloc[hexed].map(side_of).to_numpy(),
            "hex1": ann["assignedOlHex1"].iloc[hexed].astype(int).to_numpy(),
            "hex2": ann["assignedOlHex2"].iloc[hexed].astype(int).to_numpy(),
        },
        index=hexed,
    )
    types = neurons["type"].fillna("")
    rows = []
    for kind, pattern in RECEPTORS.items():
        cells = np.flatnonzero(types.str.contains(pattern).to_numpy())
        e = edges[np.isin(edges["pre"], cells) & np.isin(edges["post"], hexed)]
        votes = (
            e.join(col, on="post")
            .groupby(["pre", "side", "hex1", "hex2"])["weight"]
            .sum()
            .reset_index()
        )
        best = votes.sort_values(["weight", "hex1", "hex2"]).groupby("pre").tail(1)
        best = best.assign(kind=kind, type=types.iloc[best["pre"]].to_numpy())
        rows.append(best.rename(columns={"pre": "neuron", "weight": "synapses"}))
    return pd.concat(rows, ignore_index=True)[
        ["neuron", "kind", "type", "side", "hex1", "hex2", "synapses"]
    ]


def check(cols: pd.DataFrame, receptors: pd.DataFrame) -> dict:
    """Coverage per side, and the dorsal-rim check: R7d/R8d photoreceptors should land on
    columns that look up. Neither number enters the map."""
    m = receptors.merge(cols, on=["side", "hex1", "hex2"], how="left")
    rim = m["type"].isin(DORSAL_RIM)
    rest = m["kind"].isin(["R7", "R8"]) & ~rim
    return {
        "columns": {s: int((cols["side"] == s).sum()) for s in "LR"},
        "with_direction": {
            s: int(cols.loc[cols["side"] == s, "azimuth_deg"].notna().sum())
            for s in "LR"
        },
        "receptors": {
            f"{k} {s}": int(n)
            for (k, s), n in receptors.groupby(["kind", "side"]).size().items()
        },
        "dorsal_rim_elevation_deg": float(m.loc[rim, "elevation_deg"].median()),
        "other_r7_r8_elevation_deg": float(m.loc[rest, "elevation_deg"].median()),
    }


def angular_distance_deg(az1, el1, az2, el2) -> np.ndarray:
    """Great-circle angle between directions given as azimuth and elevation in degrees."""
    a1, e1, a2, e2 = (
        np.radians(np.asarray(v, dtype=float)) for v in (az1, el1, az2, el2)
    )
    cos = np.sin(e1) * np.sin(e2) + np.cos(e1) * np.cos(e2) * np.cos(a1 - a2)
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


def disk_coverage(
    cols: pd.DataFrame,
    azimuth_deg: float,
    elevation_deg: float,
    radius_deg: float,
    acceptance_deg: float,
) -> np.ndarray:
    """Share of each column's acceptance profile covered by a dark disk of angular radius
    `radius_deg` centred at (azimuth, elevation). The profile is a circular Gaussian of
    full width at half maximum `acceptance_deg` around the column's direction; in the
    small-angle limit the covered share is the Rice CDF at the disk radius. NaN where a
    column has no direction."""
    sigma = acceptance_deg / (2 * np.sqrt(2 * np.log(2)))
    d = angular_distance_deg(
        cols["azimuth_deg"], cols["elevation_deg"], azimuth_deg, elevation_deg
    )
    if radius_deg <= 0:
        return np.where(np.isnan(d), np.nan, 0.0)
    return stats.rice.cdf(radius_deg / sigma, d / sigma)


def looming_radius_deg(t_ms, collision_ms: float, l_over_v_ms: float) -> np.ndarray:
    """Angular radius of an object approaching at constant speed: tan(theta/2) = l / (v t)
    before collision, with l/v the half-size over speed; the classic looming stimulus of
    von Reyn et al. 2014. Capped at 90 degrees from collision on."""
    to_go = collision_ms - np.asarray(t_ms, dtype=float)
    with np.errstate(divide="ignore"):
        half = np.degrees(np.arctan(l_over_v_ms / np.where(to_go > 0, to_go, np.nan)))
    return np.where(to_go > 0, np.minimum(half, 90.0), 90.0)


def photoreceptor_kicks(
    coverage: np.ndarray, receptor_columns: np.ndarray, gain: float
) -> np.ndarray:
    """Graded input for `sim.run(..., kicks=...)`: one column per photoreceptor, one row per
    step, in units of the Poisson kick (`Params.poisson_scale * w_syn` mV). `coverage` is
    (steps, columns), the share of each column's acceptance profile under the dark disk;
    `receptor_columns` gives each photoreceptor's column index into it (-1 for none, which
    receives nothing). The drive is `gain` times the light left, 1 - coverage: a dark disk
    lowers it. `gain` has no measured value; a lock states it."""
    cov = np.asarray(coverage, dtype=float)
    idx = np.asarray(receptor_columns, dtype=int)
    light = np.where(idx >= 0, 1.0 - cov[:, np.clip(idx, 0, None)], 0.0)
    return gain * np.nan_to_num(light, nan=0.0)
