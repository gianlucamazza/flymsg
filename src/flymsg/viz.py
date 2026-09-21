"""Export neurons, neuropils and simulated activity as a static three.js bundle.

Skeletons and neuropil meshes come from the public MaleCNS precomputed volumes (neuroglancer
formats, nm coordinates). They are cached under data/cache/ and written, together with a
scene table and optional per-bin spike counts, next to the page in viz_static/.
"""

import json
import shutil
import struct
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, sim

GS = "https://storage.googleapis.com/flyem-male-cns"
SKELETONS = f"{GS}/v1.0/segmentation/skeletons-malecns/skeletons-precomputed"
NEUROPILS = {
    "brain": f"{GS}/rois/fullbrain-roi-v4",
    "vnc": f"{GS}/rois/malecns-vnc-neuropil-roi-v0",
}
# Centre of the 8 nm segmentation volume (94088 x 78317 x 134576 voxels), so every
# export shares one coordinate frame.
CENTER_NM = np.array([94088, 78317, 134576]) * 8 / 2
STATIC = Path(__file__).parent / "viz_static"


def parse_skeleton(buf: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Neuroglancer precomputed skeleton: uint32 nv, ne; float32 xyz[nv]; uint32 edges[ne]."""
    nv, ne = struct.unpack_from("<II", buf)
    verts = np.frombuffer(buf, "<f4", 3 * nv, 8).reshape(nv, 3)
    edges = np.frombuffer(buf, "<u4", 2 * ne, 8 + 12 * nv).reshape(ne, 2)
    return verts, edges


def parse_ngmesh(buf: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Neuroglancer legacy mesh fragment: uint32 nv; float32 xyz[nv]; uint32 triangles[...]."""
    (nv,) = struct.unpack_from("<I", buf)
    verts = np.frombuffer(buf, "<f4", 3 * nv, 4).reshape(nv, 3)
    tris = np.frombuffer(buf, "<u4", offset=4 + 12 * nv).reshape(-1, 3)
    return verts, tris


def simplify(
    verts: np.ndarray, tris: np.ndarray, cell: float
) -> tuple[np.ndarray, np.ndarray]:
    """Vertex-clustering decimation: merge vertices sharing a grid cell of size `cell`."""
    keys = np.floor((verts - verts.min(axis=0)) / cell).astype(np.int64)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.ravel()
    counts = np.bincount(inv)
    merged = np.zeros((counts.size, 3))
    np.add.at(merged, inv, verts)
    merged /= counts[:, None]
    t = inv[tris]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    _, first = np.unique(
        np.sort(t, axis=1), axis=0, return_index=True
    )  # drop duplicates
    return merged.astype(np.float32), t[np.sort(first)].astype(np.uint32)


def simplify_skeleton(
    verts: np.ndarray, edges: np.ndarray, cell: float
) -> tuple[np.ndarray, np.ndarray]:
    """Merge skeleton nodes sharing a grid cell; drop collapsed and duplicate edges."""
    keys = np.floor((verts - verts.min(axis=0)) / cell).astype(np.int64)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.ravel()
    counts = np.bincount(inv)
    merged = np.zeros((counts.size, 3))
    np.add.at(merged, inv, verts)
    merged /= counts[:, None]
    e = inv[edges]
    e = np.unique(np.sort(e[e[:, 0] != e[:, 1]], axis=1), axis=0)
    return merged.astype(np.float32), e.astype(np.uint32)


def _get(url: str, dest: Path) -> bytes | None:
    """Cached download; None if the server has no such object (404)."""
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            data.download(url, dest)
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            raise
    return dest.read_bytes()


def fetch_skeletons(
    body_ids, cache: Path, threads: int = 16
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    def one(b):
        buf = _get(f"{SKELETONS}/{b}", cache / "skeletons" / str(b))
        return b, None if buf is None else parse_skeleton(buf)

    with ThreadPoolExecutor(threads) as pool:
        got = dict(pool.map(one, [int(b) for b in body_ids]))
    missing = [b for b, s in got.items() if s is None]
    if missing:
        print(
            f"  no skeleton for {len(missing)} bodies, skipped: {missing[:5]}{'...' if len(missing) > 5 else ''}"
        )
    return {b: s for b, s in got.items() if s is not None}


def fetch_neuropils(
    cache: Path, cell_nm: float = 5000.0, threads: int = 16
) -> list[tuple[str, str, np.ndarray, np.ndarray]]:
    """(name, region, verts, tris) per neuropil, simplified to `cell_nm` grid cells and cached."""
    items = []
    for region, base in NEUROPILS.items():
        with urllib.request.urlopen(f"{base}/segment_properties/info", timeout=60) as r:
            props = json.load(r)["inline"]
        names = props["properties"][0]["values"]
        items += [
            (region, base, seg, name)
            for seg, name in zip(props["ids"], names, strict=True)
        ]

    def one(item):
        region, base, seg, name = item
        folder = cache / "neuropils" / region
        simplified = folder / f"{seg}.s{cell_nm:g}.npz"
        if simplified.exists():
            z = np.load(simplified)
            return name, region, z["verts"], z["tris"]
        manifest = _get(f"{base}/mesh/{seg}:0", folder / f"{seg}.json")
        if manifest is None:
            return None
        parts = []
        for frag in json.loads(manifest)["fragments"]:
            buf = _get(f"{base}/mesh/{urllib.parse.quote(frag)}", folder / frag)
            if buf is not None:
                parts.append(parse_ngmesh(buf))
        if not parts:
            return None
        offsets = np.cumsum([0] + [len(v) for v, _ in parts[:-1]])
        verts = np.concatenate([v for v, _ in parts])
        tris = np.concatenate([t + o for (_, t), o in zip(parts, offsets, strict=True)])
        verts, tris = simplify(verts, tris, cell_nm)
        np.savez(simplified, verts=verts, tris=tris)
        return name, region, verts, tris

    with ThreadPoolExecutor(threads) as pool:
        return [x for x in pool.map(one, items) if x is not None]


def select_from_result(
    result: sim.Result, stim: np.ndarray, max_neurons: int
) -> np.ndarray:
    """Stimulated neurons plus the most active others (stimulus-window rate), capped."""
    rates = result.rate(0, result.stim_ms)
    rates[stim] = -1  # already included
    order = np.argsort(-rates, kind="stable")
    others = order[rates[order] > 0][: max(0, max_neurons - stim.size)]
    return np.concatenate([np.unique(stim), others])


def export(
    out: Path,
    neurons: pd.DataFrame,
    idx: np.ndarray,
    groups: list[str],
    cache: Path,
    result: sim.Result | None = None,
    neuropils: bool = True,
    skeleton_nm: float = 2000.0,
) -> dict:
    """Write scene.json, skeletons.bin, neuropils.bin, activity.bin and the page into `out`."""
    out.mkdir(parents=True, exist_ok=True)
    skel = fetch_skeletons(neurons["bodyId"].to_numpy()[idx], cache)
    rates = result.rate(0, result.stim_ms) if result is not None else None

    table, verts, edges, kept = [], [], [], []
    nv = ne = 0
    for i, group in zip(idx, groups, strict=True):
        r = neurons.iloc[i]
        if int(r["bodyId"]) not in skel:
            continue
        v, e = simplify_skeleton(*skel[int(r["bodyId"])], skeleton_nm)
        table.append(
            {
                "bodyId": int(r["bodyId"]),
                "type": r["type"] if pd.notna(r["type"]) else "untyped",
                "instance": r["instance"] if pd.notna(r["instance"]) else "",
                "nt": r["nt"] if pd.notna(r["nt"]) else "unknown",
                "superclass": r["superclass"] if pd.notna(r["superclass"]) else "",
                "group": group,
                "v0": nv,
                "nv": len(v),
                "rate": None if rates is None else round(float(rates[i]), 1),
            }
        )
        verts.append((v - CENTER_NM) / 1000.0)  # nm -> um, centred
        edges.append(e + nv)
        kept.append(i)
        nv += len(v)
        ne += len(e)
    if not table:
        raise FileNotFoundError("none of the selected neurons has a skeleton")
    np.concatenate(verts).astype("<f4").tofile(out / "skeletons.bin")
    with open(out / "skeletons.bin", "ab") as f:
        np.concatenate(edges).astype("<u4").tofile(f)

    shells = []
    if neuropils:
        pv, pt, n0, t0 = [], [], 0, 0
        for name, region, v, t in fetch_neuropils(cache):
            shells.append(
                {
                    "name": name,
                    "region": region,
                    "v0": n0,
                    "nv": len(v),
                    "t0": t0,
                    "nt": len(t),
                }
            )
            pv.append((v - CENTER_NM) / 1000.0)
            pt.append(t + n0)
            n0, t0 = n0 + len(v), t0 + len(t)
        np.concatenate(pv).astype("<f4").tofile(out / "neuropils.bin")
        with open(out / "neuropils.bin", "ab") as f:
            np.concatenate(pt).astype("<u4").tofile(f)

    scene = {"neurons": table, "vertices": nv, "edges": ne, "neuropils": shells}
    if result is not None:
        counts = np.minimum(result.counts[:, kept], 255).astype(np.uint8)
        counts.tofile(out / "activity.bin")
        scene["activity"] = {
            "bins": counts.shape[0],
            "bin_ms": result.bin_ms,
            "stim_ms": result.stim_ms,
        }
    (out / "scene.json").write_text(json.dumps(scene))
    for f in ("index.html", "main.js"):
        shutil.copy(STATIC / f, out / f)
    return scene
