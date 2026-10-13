"""Odors as measured receptor response vectors (issue #96).

The Database of Odorant Responses (DoOR; Münch & Galizia 2016, Sci Rep 6:21841,
doi:10.1038/srep21841) merges published recordings into one consensus response per
odorant and receptor, normalised to [0, 1]. `ropensci/DoOR.data` is CC BY-SA 4.0: it is
fetched into data/raw/door and never redistributed. `vector` turns an odorant into a
response per MaleCNS ORN type through DoOR's receptor -> glomerulus map; `kicks` draws
Poisson input with one rate per stimulated neuron. Nothing here changes the engine.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data

DOOR_COMMIT = "db323a496577c4b4a72b5c2fcd1859e07521ffb5"
DOOR_BASE = f"https://raw.githubusercontent.com/ropensci/DoOR.data/{DOOR_COMMIT}/data"
DOOR_FILES = ("door_response_matrix.csv", "door_mappings.csv", "odor.csv")
# DoOR names in vivo recordings of an identified neuron by its sensillum code (ab4B, ac3A,
# pb2A ...) and heterologous receptor recordings by the receptor (Or33a ...)
NEURON_CODE = re.compile(r"^(ab|ac|at|ai|pb)\d")


def raw_dir(data_dir: Path) -> Path:
    return data_dir / "raw" / "door"


def fetch(data_dir: Path) -> None:
    out = raw_dir(data_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in DOOR_FILES:
        dest = out / name
        if dest.exists():
            print(f"ok      door/{name}")
            continue
        print(f"fetch   door/{name}")
        data.download(f"{DOOR_BASE}/{name}", dest)


def read_r_csv(path: Path) -> pd.DataFrame:
    """A table R wrote with row names (`write.csv2`): the header lacks the row-name
    column, fields are `;`-separated and missing values are `NA`."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f, delimiter=";"))
    frame = pd.DataFrame(
        [r[1:] for r in rows[1:]], index=[r[0] for r in rows[1:]], columns=rows[0]
    )
    return frame.replace("NA", np.nan)


def tables(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = raw_dir(data_dir)
    responses = read_r_csv(raw / "door_response_matrix.csv").astype(float)
    return (
        responses,
        read_r_csv(raw / "door_mappings.csv"),
        read_r_csv(raw / "odor.csv"),
    )


def inchikey(odor_table: pd.DataFrame, name: str) -> str:
    hit = odor_table[odor_table["Name"].str.lower() == name.lower()]
    if hit.empty:
        raise KeyError(f"no DoOR odorant named {name!r}")
    return str(hit["InChIKey"].iloc[0])


def vector(
    responses: pd.DataFrame,
    mappings: pd.DataFrame,
    odor_table: pd.DataFrame,
    name: str,
    orn_types,
) -> pd.DataFrame:
    """DoOR response of odorant `name` per MaleCNS ORN type: one row per receptor with a
    measured response whose glomerulus has an ORN type in `orn_types`. Receptors without
    data for this odorant, or without a glomerulus in the volume, are left out and counted
    by `coverage`."""
    row = responses.loc[inchikey(odor_table, name)]
    glom = mappings.set_index("receptor")["glomerulus"]
    known = set(orn_types)
    out = []
    for receptor, value in row.dropna().items():
        g = glom.get(receptor)
        t = f"ORN_{g}"
        if isinstance(g, str) and t in known:
            out.append(
                {
                    "receptor": receptor,
                    "glomerulus": g,
                    "type": t,
                    "response": float(value),
                }
            )
    return pd.DataFrame(out, columns=["receptor", "glomerulus", "type", "response"])


def coverage(responses: pd.DataFrame, odor_table: pd.DataFrame, name: str, v) -> dict:
    row = responses.loc[inchikey(odor_table, name)]
    return {
        "receptors": int(row.size),
        "measured": int(row.notna().sum()),
        "in_volume": len(v),
    }


def kicks(rates_hz: np.ndarray, seed: int, dt_ms: float, steps: int) -> np.ndarray:
    """Poisson input counts, one column per stimulated neuron with its own rate; one
    Generator, one call. Equal rates give exactly `sim.poisson_kicks`."""
    rng = np.random.default_rng(seed)
    lam = np.asarray(rates_hz, dtype=float) * dt_ms / 1000.0
    return rng.poisson(lam, (steps, lam.size))


def per_type(v: pd.DataFrame) -> pd.Series:
    """One response per ORN type. A neuron-level recording (sensillum code) is the
    neuron's own response and wins; otherwise the largest response among the receptors
    the type co-expresses, since either receptor can drive the neuron."""
    is_neuron = v["receptor"].map(lambda r: bool(NEURON_CODE.match(str(r))))
    neuron = v[is_neuron].groupby("type")["response"].max()
    receptor = v[~is_neuron].groupby("type")["response"].max()
    return neuron.combine_first(receptor).sort_index()


def stimulus(
    neurons: pd.DataFrame, responses_by_type: pd.Series, rate_max_hz: float
) -> tuple[np.ndarray, np.ndarray]:
    """Every neuron of each responding ORN type with its rate, `rate_max_hz` times the
    type's response."""
    types = neurons["type"].to_numpy()
    idx, rates = [], []
    for t, r in responses_by_type.items():
        members = np.flatnonzero(types == t)
        idx.append(members)
        rates.append(np.full(members.size, rate_max_hz * float(r)))
    order = np.argsort(np.concatenate(idx), kind="stable")
    return np.concatenate(idx)[order], np.concatenate(rates)[order]
