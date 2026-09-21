"""Download and compact the MaleCNS v1.0 connectome (Janelia FlyEM, CC-BY 4.0)."""

import shutil
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

BASE = (
    "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
)
RAW = {
    "annotations": "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "nt": "body-neurotransmitters-male-cns-v1.0.feather",
    "weights": "connectome-weights-male-cns-v1.0-minconf-0.5.feather",  # ~1 GB
}
# Fast-acting sign per transmitter. Glutamate (GluCl) and histamine (HisCl) are
# inhibitory in Drosophila; neuromodulators and "unclear" get no fast effect.
SIGN = {"acetylcholine": 1, "gaba": -1, "glutamate": -1, "histamine": -1}
ANN_COLS = [
    "bodyId",
    "type",
    "instance",
    "superclass",
    "class",
    "somaSide",
    "dimorphism",
    "fruDsx",
    "synonyms",
]


def download(url: str, dest: Path, retries: int = 3, timeout: float = 60) -> None:
    """Download to a .part file, check the size against Content-Length, then rename."""
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, retries + 1):
        try:
            with (
                urllib.request.urlopen(url, timeout=timeout) as r,
                open(tmp, "wb") as f,
            ):
                expected = int(r.headers.get("Content-Length", -1))
                shutil.copyfileobj(r, f, length=1 << 20)
            if expected >= 0 and tmp.stat().st_size != expected:
                raise OSError(f"size {tmp.stat().st_size} != {expected}")
            tmp.rename(dest)
            return
        except OSError as err:  # URLError and timeouts are OSError subclasses
            tmp.unlink(missing_ok=True)
            client_error = isinstance(err, urllib.error.HTTPError) and err.code < 500
            if client_error or attempt == retries:  # a 404 will not heal on retry
                raise
            print(f"  retry {attempt}/{retries - 1}: {err}")


def fetch(data_dir: Path) -> None:
    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for name in RAW.values():
        dest = raw / name
        if dest.exists():
            print(f"ok      {name}")
            continue
        print(f"fetch   {name}")
        download(f"{BASE}/{name}", dest)


def build(data_dir: Path, min_weight: int = 1) -> None:
    """Write neurons.parquet (row index = neuron idx) and edges.parquet (pre, post, weight)."""
    raw = data_dir / "raw"
    ann = pd.read_feather(raw / RAW["annotations"])
    ann = ann.loc[ann["status"] == "Traced", ANN_COLS]
    nt = pd.read_feather(raw / RAW["nt"], columns=["body", "consensus_nt"])
    neurons = (
        ann.merge(
            nt.rename(columns={"body": "bodyId", "consensus_nt": "nt"}),
            on="bodyId",
            how="left",
        )
        .sort_values("bodyId")
        .reset_index(drop=True)
    )
    neurons["sign"] = neurons["nt"].map(SIGN).fillna(0).astype(np.int8)

    ids = neurons["bodyId"].to_numpy()
    filt = (
        ds.field("body_pre").isin(ids)
        & ds.field("body_post").isin(ids)
        & (ds.field("weight") >= min_weight)
    )
    w = ds.dataset(raw / RAW["weights"], format="feather").to_table(filter=filt)
    edges = pd.DataFrame(
        {
            "pre": np.searchsorted(ids, w["body_pre"].to_numpy()).astype(np.int32),
            "post": np.searchsorted(ids, w["body_post"].to_numpy()).astype(np.int32),
            "weight": w["weight"].to_numpy().astype(np.int32),
        }
    )
    neurons.to_parquet(data_dir / "neurons.parquet")
    edges.to_parquet(data_dir / "edges.parquet")
    print(
        f"{len(neurons):,} neurons, {len(edges):,} edges, {edges['weight'].sum():,} synapses"
    )


def load(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not (data_dir / "edges.parquet").exists():
        raise FileNotFoundError(
            f"no compact data in {data_dir}/: run `flymsg fetch` and `flymsg build`"
        )
    return pd.read_parquet(data_dir / "neurons.parquet"), pd.read_parquet(
        data_dir / "edges.parquet"
    )


def resolve(neurons: pd.DataFrame, query: str) -> np.ndarray:
    """Neuron indices matching a cell type, an instance, or a bodyId."""
    for col in ("type", "instance"):
        idx = np.flatnonzero(neurons[col].to_numpy() == query)
        if idx.size:
            return idx
    if query.isdigit():
        idx = np.flatnonzero(neurons["bodyId"].to_numpy() == int(query))
        if idx.size:
            return idx
    raise KeyError(f"no neuron matches {query!r}")
