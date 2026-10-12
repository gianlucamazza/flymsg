"""Write the whole-CNS soma layer of the 3D view. Usage: uv run python scripts/build_somata.py

Reads `somaLocation` from the MaleCNS v1.0 body annotations (data/raw, from `flymsg fetch`)
for every neuron in data/neurons.parquet and writes docs/live/cns/:
  somata.bin   float32 x, y, z per soma in segmentation voxels (scale 0), then one uint8
               region code per soma
  somata.json  count, region names and counts, source file and its sha256
Neurons without a soma in the volume (most sensory neurons, whose cell bodies are in the
periphery) are counted, not drawn. Nothing here enters a simulation.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
OUT = ROOT / "docs" / "live" / "cns"
# superclass prefix -> region; order is the region code
REGIONS = (
    ("optic lobe", ("ol_", "visual_")),
    ("central brain", ("cb_",)),
    ("ventral nerve cord", ("vnc_",)),
    ("descending", ("descending", "sensory_descending", "efferent_descending")),
    ("ascending", ("ascending", "sensory_ascending", "efferent_ascending")),
    ("other", ("",)),
)


def region(superclass) -> int:
    s = superclass if isinstance(superclass, str) else ""
    for code, (_, prefixes) in enumerate(REGIONS):
        if any(s.startswith(p) for p in prefixes):
            return code
    return len(REGIONS) - 1


def main() -> None:
    neurons = pd.read_parquet(
        ROOT / "data" / "neurons.parquet", columns=["bodyId", "superclass"]
    )
    ann = pd.read_feather(SOURCE, columns=["bodyId", "somaLocation"]).set_index(
        "bodyId"
    )
    loc = ann["somaLocation"].reindex(neurons["bodyId"]).to_numpy()
    has = np.array([isinstance(x, np.ndarray) and x.size == 3 for x in loc])
    xyz = np.stack(loc[has]).astype(np.float32)
    codes = np.array([region(s) for s in neurons["superclass"][has]], dtype=np.uint8)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "somata.bin").write_bytes(xyz.tobytes() + codes.tobytes())
    no_soma = neurons.loc[~has, "superclass"].fillna("none").value_counts()
    meta = {
        "count": int(has.sum()),
        "neurons": len(neurons),
        "units": "segmentation voxels, scale 0",
        "regions": [name for name, _ in REGIONS],
        "region_counts": np.bincount(codes, minlength=len(REGIONS)).tolist(),
        "without_soma": int((~has).sum()),
        "without_soma_by_superclass": {k: int(v) for k, v in no_soma.head(8).items()},
        "source": SOURCE.name,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    }
    (OUT / "somata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(
        f"{meta['count']} somata of {meta['neurons']} neurons -> {OUT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
