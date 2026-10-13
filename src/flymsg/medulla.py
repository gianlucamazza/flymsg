"""Measured voltages of T4's medulla inputs (issue #140): Groschner, Malis, Zuidinga & Borst
2022, Nature 603:119, doi:10.1038/s41586-022-04428-3, Fig 3a. Per-cell whole-cell traces of
Mi1, Tm3, Mi4, Mi9 and C3 to 30 deg/s ON and OFF edges, deposited on Edmond
(doi:10.17617/3.8G, version 1.0, CC BY 4.0): 1 kHz, 8 s, -1 pA holding current. The ON sweep
starts in darkness, the OFF sweep in light; the photodiode trace (fig3_led.npy) changes
between 3.5 and 4.5 s, and the mean traces start to move from about 1.5 s.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data

EDMOND = "https://edmond.mpg.de/api/access/datafile"
# file: (Edmond datafile id, sha256 of the version 1.0 file; Edmond lists its MD5)
FILES = {
    "Mi1": (104811, "351e9e791a30d1c5bac329165934fbc05dbcfbb038b4b6e940e2531de1d61cce"),
    "Tm3": (104816, "07797ccd2ce72d3ea89c9ca01ba641c7c92d3d6dd198d6324596f2cf16b0fb82"),
    "Mi4": (104812, "9309bb6deadcb8bf5c9a52267ef6564c314a04212af81c129b0754cf4de1f791"),
    "Mi9": (104813, "3d5909c9b6c42776ff5e56d7219eacd002758a24b3cf5b7cecf30a07b8bf5c83"),
    "C3": (104809, "b9118e32cfb0d22acd4da41aee6931923ea33e4dda258df2abd26fd252e21be6"),
}
DARK_MS = 1000  # the first second of the ON sweep, before the edge, is darkness


def raw_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "raw" / "groschner2022"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(data_dir: Path) -> None:
    out = raw_dir(data_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, (file_id, digest) in FILES.items():
        dest = out / f"fig3_{name}.npy"
        if not dest.exists():
            print(f"fetch   groschner2022/{dest.name}")
            data.download(f"{EDMOND}/{file_id}", dest)
        if sha256(dest) != digest:
            dest.unlink()  # the next fetch downloads it again
            raise ValueError(f"{dest} is not the deposited file (sha256)")


def ranges_of(traces: np.ndarray) -> dict:
    """From one type's (2 sweeps: ON, OFF; cells; 8000 samples) traces in mV: the cell count,
    the mean dark potential (first second of the ON sweep) and the lowest and highest values
    of the cell-mean ON and OFF traces, rounded to 0.1 mV."""
    mean = np.nanmean(traces, axis=1)
    return {
        "n": int(traces.shape[1]),
        "dark_mv": round(float(mean[0, :DARK_MS].mean()), 1),
        "lowest_mv": round(float(mean.min()), 1),
        "highest_mv": round(float(mean.max()), 1),
    }


def ranges(data_dir: Path) -> pd.DataFrame:
    fetch(data_dir)
    rows = []
    for name in FILES:
        traces = np.load(raw_dir(data_dir) / f"fig3_{name}.npy", allow_pickle=False)
        rows.append({"type": name, **ranges_of(traces)})
    return pd.DataFrame(rows)
