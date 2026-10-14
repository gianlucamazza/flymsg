"""Export a 3D view: neuron metadata and simulated activity for the three.js page.

Geometry is not exported. The page (viz_static/) streams the real neuron surfaces
(multi-resolution Draco meshes), skeletons and neuropil meshes straight from the public
MaleCNS volumes on Google Cloud Storage, choosing the level of detail on screen.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import graph, sim

STATIC = Path(__file__).parent / "viz_static"
# The bundle the page reads (scene.json, activity.bin, graded.bin, partners.json); the page
# checks it.
SCENE_SCHEMA = "flymsg.scene/v1"
# graded.bin: signed potential relative to each neuron's reference, in steps of scale/127
GRADED_STEPS = 127


def page_files() -> list[Path]:
    """The page and every module beside it (vendor/ is copied as a tree). Collected rather
    than listed, so that a new module cannot be left out of an export."""
    return [STATIC / "index.html", *sorted(STATIC.glob("*.js"))]


def select_from_result(
    result: sim.Result,
    stim: np.ndarray,
    min_rate: float = 0.0,
    keep: np.ndarray | None = None,
) -> np.ndarray:
    """Stimulated neurons, then every neuron firing above `min_rate` Hz during the stimulus,
    most active first, then any `keep` neuron not already listed, even if silent, so that
    a comparison can show it at zero rather than "not exported"."""
    rates = result.rate(0, result.stim_ms)
    stim = np.unique(stim)
    rates[stim] = -np.inf  # listed first, separately
    order = np.argsort(-rates, kind="stable")
    responders = order[rates[order] > min_rate]
    idx = np.concatenate([stim, responders])
    if keep is not None:
        idx = np.concatenate([idx, np.setdiff1d(np.unique(keep), idx)])
    return idx


def _text(value, missing: str) -> str:
    return value if pd.notna(value) else missing


def export(
    out: Path,
    neurons: pd.DataFrame,
    idx: np.ndarray,
    groups: list[str],
    result: sim.Result | None = None,
    edges: pd.DataFrame | None = None,
    top: int = 10,
    graded: dict | None = None,
) -> dict:
    """Write scene.json, activity.bin (replays only), graded.bin (with `graded`),
    partners.json (with `edges`) and the page into `out`. partners.json holds each neuron's
    `top` partner types, as `flymsg info` lists them, its totals, and its partners inside the
    scene. `graded` = {"rows": neuron rows in `idx`, "mv": (bins, rows) potential relative to
    each neuron's reference, "scale_mv": (rows,) the potential that reads as full glow,
    "reference": what 0 mV stands for}; non-spiking neurons glow by that potential."""
    out.mkdir(parents=True, exist_ok=True)
    rates = result.rate(0, result.stim_ms) if result is not None else None
    rows = neurons.iloc[idx]
    scene = {
        "schema": SCENE_SCHEMA,
        "neurons": [
            {
                "bodyId": int(r.bodyId),
                "type": _text(r.type, "untyped"),
                "instance": _text(r.instance, ""),
                "nt": _text(r.nt, "unknown"),
                "superclass": _text(r.superclass, ""),
                "dimorphism": _text(r.dimorphism, ""),
                "fruDsx": _text(r.fruDsx, ""),
                "group": group,
                "rate": None if rates is None else round(float(rates[i]), 1),
            }
            for i, r, group in zip(idx, rows.itertuples(), groups, strict=True)
        ],
    }
    replay = out / "activity.bin"
    if result is not None:
        counts = np.minimum(result.counts[:, idx], 255).astype(np.uint8)
        counts.tofile(replay)
        scene["activity"] = {
            "bins": counts.shape[0],
            "bin_ms": result.bin_ms,
            "stim_ms": result.stim_ms,
        }
    else:
        replay.unlink(
            missing_ok=True
        )  # an anatomy export must not pick up an old replay
    graded_file = out / "graded.bin"
    if graded is not None:
        if result is None:
            raise ValueError("graded potentials need the replay they come from")
        position = {int(n): k for k, n in enumerate(idx)}
        rows = [position[int(n)] for n in graded["rows"]]
        mv = np.asarray(graded["mv"], dtype=float)
        scale = np.asarray(graded["scale_mv"], dtype=float)
        if mv.shape != (counts.shape[0], len(rows)) or scale.shape != (len(rows),):
            raise ValueError(
                "graded potentials must be (bins, rows) with one scale per row"
            )
        steps = np.clip(np.rint(mv / scale * GRADED_STEPS), -GRADED_STEPS, GRADED_STEPS)
        steps.astype(np.int8).tofile(graded_file)
        scene["graded"] = {
            "k": rows,
            "scale_mv": [round(float(s), 2) for s in scale],
            "reference": graded["reference"],
        }
    else:
        graded_file.unlink(missing_ok=True)
    (out / "scene.json").write_text(json.dumps(scene))
    table = out / "partners.json"
    if edges is not None:
        table.write_text(
            json.dumps(
                {
                    "source": "chemical synapse counts of the exported dataset",
                    "top": top,
                    "neurons": graph.partner_table(neurons, edges, idx, top),
                }
            )
        )
    else:
        table.unlink(missing_ok=True)  # never pair a scene with another scene's table
    copy_page(out)
    return scene


def copy_page(out: Path) -> None:
    """Copy the page, its modules and vendor/ into `out`, next to a scene."""
    out.mkdir(parents=True, exist_ok=True)
    for f in page_files():
        shutil.copy(f, out / f.name)
    shutil.copytree(STATIC / "vendor", out / "vendor", dirs_exist_ok=True)


COMPARE_STATUSES = ("validated", "exploratory", "failed")


def _bundle(path: Path) -> dict:
    path = Path(path)
    scene = json.loads((path / "scene.json").read_text())
    if scene.get("schema") != SCENE_SCHEMA:
        raise ValueError(f"{path}: scene is {scene.get('schema')}, not {SCENE_SCHEMA}")
    if "activity" not in scene:
        raise ValueError(f"{path}: an anatomy view has no replay to compare")
    if "comparison" in scene:
        raise ValueError(f"{path}: already a comparison")
    act = scene["activity"]
    spikes = np.fromfile(path / "activity.bin", np.uint8).reshape(
        act["bins"], len(scene["neurons"])
    )
    manifest = json.loads((path / "manifest.json").read_text())
    partners = path / "partners.json"
    table = json.loads(partners.read_text()) if partners.exists() else None
    return {"scene": scene, "spikes": spikes, "manifest": manifest, "partners": table}


def _differences(a: dict, b: dict) -> list[dict]:
    """Config, seed and code keys whose values differ between two run manifests."""
    out = []
    for section in ("config", "seeds"):
        keys = sorted(set(a.get(section, {})) | set(b.get(section, {})))
        for k in keys:
            va, vb = a.get(section, {}).get(k), b.get(section, {}).get(k)
            if va != vb:
                out.append({"key": f"{section}.{k}", "a": va, "b": vb})
    if a.get("git") != b.get("git"):
        out.append({"key": "git", "a": a.get("git"), "b": b.get("git")})
    return out


def compare_bundles(
    a_dir: Path,
    b_dir: Path,
    out: Path,
    labels: tuple[str, str],
    statuses: tuple[str, str],
    notes: tuple[str, str] = ("", ""),
) -> dict:
    """Pair two replay exports for the page, without simulating anything.

    The two runs must share the dataset (name, release, file hashes) and the time base
    (bins, bin width, stimulus window). The neuron set is the union, in the order of `a`
    then the neurons only `b` exported; `in` says which export holds each neuron, and a
    neuron missing from one export is "not exported" there, not silent.
    """
    for s in statuses:
        if s not in COMPARE_STATUSES:
            raise ValueError(
                f"status {s!r} is not one of {', '.join(COMPARE_STATUSES)}"
            )
    a, b = _bundle(a_dir), _bundle(b_dir)
    da, db = a["manifest"]["dataset"], b["manifest"]["dataset"]
    for key in ("name", "release", "files"):
        if da.get(key) != db.get(key):
            raise ValueError(f"not comparable: the datasets differ in {key}")
    if a["scene"]["activity"] != b["scene"]["activity"]:
        raise ValueError(
            "not comparable: time bases differ "
            f"({a['scene']['activity']} vs {b['scene']['activity']})"
        )
    rows_a = {n["bodyId"]: i for i, n in enumerate(a["scene"]["neurons"])}
    rows_b = {n["bodyId"]: i for i, n in enumerate(b["scene"]["neurons"])}
    order = list(rows_a) + [bid for bid in rows_b if bid not in rows_a]
    bins = a["scene"]["activity"]["bins"]
    spikes = [np.zeros((bins, len(order)), np.uint8) for _ in range(2)]
    neurons = []
    for k, bid in enumerate(order):
        ia, ib = rows_a.get(bid), rows_b.get(bid)
        base = dict(
            a["scene"]["neurons"][ia] if ia is not None else b["scene"]["neurons"][ib]
        )
        base["rate"] = None if ia is None else a["scene"]["neurons"][ia]["rate"]
        base["rate_b"] = None if ib is None else b["scene"]["neurons"][ib]["rate"]
        base["in"] = [ia is not None, ib is not None]
        neurons.append(base)
        if ia is not None:
            spikes[0][:, k] = a["spikes"][:, ia]
        if ib is not None:
            spikes[1][:, k] = b["spikes"][:, ib]
    runs = []
    for bundle, label, status, note in zip(
        (a, b), labels, statuses, notes, strict=True
    ):
        m = bundle["manifest"]
        runs.append(
            {
                "label": label,
                "status": status,
                "note": note,
                "command": m.get("command"),
                "config": m.get("config"),
                "seeds": m.get("seeds"),
                "git": m.get("git"),
            }
        )
    scene = {
        "schema": SCENE_SCHEMA,
        "neurons": neurons,
        "activity": a["scene"]["activity"],
        "comparison": {
            "runs": runs,
            "differences": _differences(a["manifest"], b["manifest"]),
            "dataset": {k: da.get(k) for k in ("name", "release")},
        },
    }
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scene.json").write_text(json.dumps(scene))
    spikes[0].tofile(out / "activity.bin")
    spikes[1].tofile(out / "activity_b.bin")
    for name, bundle in (("a", a), ("b", b)):  # the two runs' own manifests, unchanged
        (out / f"manifest_{name}.json").write_text(
            json.dumps(bundle["manifest"], indent=2)
        )
    _merge_partners(out, order, a, b)
    copy_page(out)
    return scene


def _merge_partners(out: Path, order: list, a: dict, b: dict) -> None:
    """One partner table for the union, with in-scene rows renumbered to it and the in-scene
    partners of a neuron that both exports hold merged."""
    tables = [(x, x["partners"]) for x in (a, b) if x["partners"] is not None]
    if not tables:
        (out / "partners.json").unlink(missing_ok=True)
        return
    row = {bid: k for k, bid in enumerate(order)}
    dirs = ("upstream", "downstream")
    merged = {}
    for bundle, table in tables:
        old = [n["bodyId"] for n in bundle["scene"]["neurons"]]
        for key, entry in table["neurons"].items():
            if key not in merged:
                merged[key] = {d: {**entry[d], "in_scene": {}} for d in dirs}
            for d in dirs:
                for r, w in entry[d]["in_scene"]:
                    merged[key][d]["in_scene"][row[old[r]]] = w
    for entry in merged.values():
        for d in dirs:
            entry[d]["in_scene"] = sorted(
                ([r, w] for r, w in entry[d]["in_scene"].items()),
                key=lambda x: (-x[1], x[0]),
            )
    first = tables[0][1]
    (out / "partners.json").write_text(
        json.dumps({"source": first["source"], "top": first["top"], "neurons": merged})
    )
