"""Download and compact the connectomes.

malecns  MaleCNS v1.0, male brain + VNC (Janelia FlyEM + Google, CC-BY 4.0), in `data/`
fafb     FlyWire FAFB v783, female brain only, as used by the Shiu et al. (2024) model, in
         `data/fafb/`: connectivity and neuron list from that model's repository (MIT),
         annotations from flyconnectome/flywire_annotations (cite Berg 2025, Schlegel 2024,
         Matsliah 2024, Dorkenwald 2024). Both sources are pinned to a commit.
"""

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
SHIU_REPO = "https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/91bdd1e7dcf193f3e7ca5a8933497fcef63b7960"
FW_ANN_REPO = "https://raw.githubusercontent.com/flyconnectome/flywire_annotations/8587524c1748ce5ef2080822a2fc890fc03bf597"
FAFB_RAW = {
    "connectivity": f"{SHIU_REPO}/Connectivity_783.parquet",  # ~100 MB
    "completeness": f"{SHIU_REPO}/Completeness_783.csv",  # the model's neurons
    "annotations": f"{FW_ANN_REPO}/supplemental_files/Supplemental_file1_neuron_annotations.tsv",
}
ANN_COLS = [
    "bodyId",
    "type",
    "instance",
    "superclass",
    "class",
    "subclass",
    "somaSide",
    "entryNerve",
    "receptorType",
    "flywireType",
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


def fetch(data_dir: Path, dataset: str = "malecns") -> None:
    if dataset == "fafb":
        files = {Path(url).name: url for url in FAFB_RAW.values()}
        raw = data_dir / "fafb" / "raw"
    else:
        files = {name: f"{BASE}/{name}" for name in RAW.values()}
        raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for name, url in files.items():
        dest = raw / name
        if dest.exists():
            print(f"ok      {name}")
            continue
        print(f"fetch   {name}")
        download(url, dest)


def build(data_dir: Path, dataset: str = "malecns", min_weight: int = 1) -> None:
    """Write neurons.parquet (row index = neuron idx) and edges.parquet (pre, post, weight)."""
    if dataset == "fafb":
        build_fafb(data_dir / "fafb")
        return
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


def build_fafb(out: Path) -> None:
    """FAFB v783 in the MaleCNS schema. Neurons are those of the Shiu model; `sign` follows
    SIGN like MaleCNS, and `shiu_sign` keeps the model's own sign (+1/-1 for every neuron)
    for reproducing it exactly."""
    raw = out / "raw"
    ids = np.sort(
        pd.read_csv(
            raw / Path(FAFB_RAW["completeness"]).name, index_col=0
        ).index.to_numpy()
    )
    ann = pd.read_csv(
        raw / Path(FAFB_RAW["annotations"]).name, sep="\t", low_memory=False
    ).set_index("root_id")
    ann = ann.reindex(ids)
    side = ann["side"].map({"left": "L", "right": "R"})
    neurons = pd.DataFrame(
        {
            "bodyId": ids,
            "type": ann["cell_type"].to_numpy(),
            "instance": (ann["cell_type"] + "_" + side).to_numpy(),
            "superclass": ann["super_class"].to_numpy(),
            "class": ann["cell_class"].to_numpy(),
            "subclass": ann["cell_sub_class"].to_numpy(),
            "somaSide": side.to_numpy(),
            "entryNerve": ann["nerve"].to_numpy(),
            "receptorType": None,
            "flywireType": ann["cell_type"].to_numpy(),
            "dimorphism": ann["dimorphism"].to_numpy(),
            "fruDsx": ann["fru_dsx"].to_numpy(),
            "synonyms": ann["synonyms"].to_numpy(),
            "nt": ann["top_nt"].to_numpy(),
        }
    )
    neurons["sign"] = neurons["nt"].map(SIGN).fillna(0).astype(np.int8)
    c = pd.read_parquet(
        raw / Path(FAFB_RAW["connectivity"]).name,
        columns=["Presynaptic_ID", "Postsynaptic_ID", "Connectivity", "Excitatory"],
    )
    pre = np.searchsorted(ids, c["Presynaptic_ID"].to_numpy())
    post = np.searchsorted(ids, c["Postsynaptic_ID"].to_numpy())
    # searchsorted returns len(ids) for an id above them all, so clip before checking
    for idx, col in ((pre, "Presynaptic_ID"), (post, "Postsynaptic_ID")):
        if not np.array_equal(ids[np.minimum(idx, len(ids) - 1)], c[col]):
            raise ValueError(
                f"{col}: connectivity references neurons outside the completeness list"
            )
    shiu = np.zeros(len(ids), dtype=np.int8)
    shiu[pre] = c["Excitatory"].to_numpy()
    neurons["shiu_sign"] = shiu
    edges = pd.DataFrame(
        {
            "pre": pre.astype(np.int32),
            "post": post.astype(np.int32),
            "weight": c["Connectivity"].to_numpy().astype(np.int32),
        }
    )
    neurons.to_parquet(out / "neurons.parquet")
    edges.to_parquet(out / "edges.parquet")
    print(
        f"FAFB: {len(neurons):,} neurons, {len(edges):,} edges, {edges['weight'].sum():,} synapses"
    )


def load(data_dir: Path, dataset: str = "malecns") -> tuple[pd.DataFrame, pd.DataFrame]:
    if dataset == "fafb":
        data_dir = data_dir / "fafb"
    if not (data_dir / "edges.parquet").exists():
        flag = " --dataset fafb" if dataset == "fafb" else ""
        raise FileNotFoundError(
            f"no compact data in {data_dir}/: run `flymsg fetch{flag}` and `flymsg build{flag}`"
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
