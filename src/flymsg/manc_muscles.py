"""The muscle MANC published for each MaleCNS motor neuron (Phase C of the motor map).

Cheong, Eichler, Stürner et al. 2024 (eLife 13:RP96084, doi:10.7554/eLife.96084, CC BY 4.0),
Supplementary file 3, lists every MANC motor and efferent neuron with its type, its target and,
for a light-microscopy match, a certainty from 1 to 5. `fetch` downloads it into data/raw/manc
and checks the pinned sha256. `by_type` keeps one row per MANC type. `join` gives each
MaleCNS `vnc_motor` neuron the row of its `mancType`, the MaleCNS annotation naming the MANC
type it was matched to. A target that names a body part (`abdomen`, `hind leg` ...) is not a
muscle; a type with no target or several stays without one. Nothing here names a body
actuator: `motor_map.command` still refuses every row.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from flymsg import data

SUPP3_NAME = "elife-96084-supp3-v1.csv"
SUPP3_URL = f"https://cdn.elifesciences.org/articles/96084/{SUPP3_NAME}"
SUPP3_SHA256 = "c46e3cec1a5114b8d981d5f0383012c8e7fcdebd6c4e3eaffe4ac3ba1def2e94"
LICENSE = "CC BY 4.0"
SOURCE = (
    "Cheong, Eichler, Stürner et al. 2024, eLife 13:RP96084, "
    "doi:10.7554/eLife.96084, Supplementary file 3"
)
CERTAINTY = "match_certainty(1-5)"
# Supplementary file 3 targets that name a body part or several muscles, not one muscle
REGIONS = frozenset(
    {
        "abdomen",
        "abdomen A1",
        "abdomen A2",
        "front leg",
        "middle leg",
        "hind leg",
        "neck",
        "wing",
        "haltere",
        "multi",
    }
)


class MancError(ValueError):
    """The fetched file is not the pinned one."""


def raw_dir(data_dir: Path) -> Path:
    return data_dir / "raw" / "manc"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(data_dir: Path) -> Path:
    """Download Supplementary file 3 on first use; refuse a file with another hash."""
    out = raw_dir(data_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / SUPP3_NAME
    if dest.exists():
        print(f"ok      manc/{SUPP3_NAME}")
    else:
        print(f"fetch   manc/{SUPP3_NAME}")
        data.download(SUPP3_URL, dest)
    digest = sha256(dest)
    if digest != SUPP3_SHA256:
        raise MancError(f"{dest} has sha256 {digest}, expected {SUPP3_SHA256}")
    return dest


def _joined(values: pd.Series) -> str | None:
    kept = sorted({str(v) for v in values.dropna()})
    return " | ".join(kept) if kept else None


def by_type(supp3: pd.DataFrame) -> pd.DataFrame:
    """One row per MANC type: its targets, the muscle when there is exactly one and it is
    not a body part, and the range of the published match certainty."""
    rows = []
    for manc_type, g in supp3.groupby("type", sort=True):
        targets = sorted(set(g["target"].dropna()))
        certainty = g[CERTAINTY].dropna()
        if not targets:
            status = "no_target"
        elif all(t in REGIONS for t in targets):
            status = "region"
        elif len(targets) == 1:
            status = "muscle"
        else:
            status = "several_targets"
        rows.append(
            {
                "manc_type": manc_type,
                "manc_neurons": len(g),
                "target": " | ".join(targets) if targets else None,
                "muscle": targets[0] if status == "muscle" else None,
                "status": status,
                "certainty_min": certainty.min() if len(certainty) else None,
                "certainty_max": certainty.max() if len(certainty) else None,
                "publication_match": _joined(g["publication_match"]),
                "match_notes": _joined(g["match_notes"]),
                "source": SOURCE,
            }
        )
    table = pd.DataFrame(rows)
    for col in ("certainty_min", "certainty_max"):
        table[col] = table[col].astype("Int64")
    return table


def join(motor: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """Each MaleCNS motor neuron (`bodyId`, `type`, `mancType`) with its MANC type's row.
    A neuron with no `mancType`, a merged one (`MNad18,MNad27`) or one absent from the
    file keeps no muscle, with that reason as its status."""
    out = motor[["bodyId", "type", "mancType"]].merge(
        table, left_on="mancType", right_on="manc_type", how="left"
    )
    missing = out["manc_type"].isna()
    compound = out["mancType"].fillna("").str.contains(",")
    out.loc[missing, "status"] = "not_in_manc"
    out.loc[missing & compound, "status"] = "compound_type"
    out.loc[out["mancType"].isna(), "status"] = "untyped"
    return out.drop(columns="manc_type")


def neuron_agreement(
    joined: pd.DataFrame, manc_body: pd.Series, supp3: pd.DataFrame
) -> pd.DataFrame:
    """Add the type of the MANC neuron each MaleCNS neuron was individually matched to
    (`mancBodyid`, aligned with `joined`) and whether it agrees with the type-level join.
    The type-level muscle stays the one used: `mancType` is curated per type, while
    individual pairings in serially repeated leg types can land on a neighbouring type.
    `neuron_match_agrees` is None when the neuron has no resolvable MANC neuron."""
    types = supp3.drop_duplicates("bodyid").set_index("bodyid")["type"]
    ids = pd.to_numeric(manc_body, errors="coerce")
    out = joined.copy()
    out["manc_neuron_type"] = ids.map(types).to_numpy()
    agrees = out["manc_neuron_type"] == out["mancType"]
    out["neuron_match_agrees"] = agrees.astype(object).where(
        out["manc_neuron_type"].notna(), None
    )
    return out


def summary(joined: pd.DataFrame) -> pd.DataFrame:
    """Neurons and MaleCNS types per status."""
    return (
        joined.groupby("status")
        .agg(neurons=("bodyId", "size"), types=("type", "nunique"))
        .sort_values("neurons", ascending=False)
    )
