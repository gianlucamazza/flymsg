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

from flymsg import sim

STATIC = Path(__file__).parent / "viz_static"


def page_files() -> list[Path]:
    """The page and every module beside it (vendor/ is copied as a tree). Collected rather
    than listed, so that a new module cannot be left out of an export."""
    return [STATIC / "index.html", *sorted(STATIC.glob("*.js"))]


def select_from_result(
    result: sim.Result, stim: np.ndarray, min_rate: float = 0.0
) -> np.ndarray:
    """Stimulated neurons, then every neuron firing above `min_rate` Hz during the stimulus,
    most active first."""
    rates = result.rate(0, result.stim_ms)
    stim = np.unique(stim)
    rates[stim] = -np.inf  # listed first, separately
    order = np.argsort(-rates, kind="stable")
    responders = order[rates[order] > min_rate]
    return np.concatenate([stim, responders])


def _text(value, missing: str) -> str:
    return value if pd.notna(value) else missing


def export(
    out: Path,
    neurons: pd.DataFrame,
    idx: np.ndarray,
    groups: list[str],
    result: sim.Result | None = None,
) -> dict:
    """Write scene.json, activity.bin (replays only) and the page into `out`."""
    out.mkdir(parents=True, exist_ok=True)
    rates = result.rate(0, result.stim_ms) if result is not None else None
    rows = neurons.iloc[idx]
    scene = {
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
        ]
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
    (out / "scene.json").write_text(json.dumps(scene))
    for f in page_files():
        shutil.copy(f, out / f.name)
    shutil.copytree(STATIC / "vendor", out / "vendor", dirs_exist_ok=True)
    return scene
