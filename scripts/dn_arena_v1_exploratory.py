"""Post-verdict exploratory count for DN-arena v1 (docs/result/dn-arena.md); not scored.

Usage: uv run python scripts/dn_arena_v1_exploratory.py DATA_DIR OUT_DIR

One open-loop second, every arena input photoreceptor at full light (100 Hz, the upper
bound: the sphere only lowers rates), Poisson seed and input dead time from the lock.
Prints spikes per neuron class, the sign of the inputs' output synapses, and the
shortest synaptic path from the inputs to each decoder neuron.
"""

import json
import sys
from collections import deque
from pathlib import Path

import numpy as np

from flymsg import data, dn_arena, sim, stimulus

CLASSES = {
    "lamina L1-L5": ("L1", "L2", "L3", "L4", "L5"),
    "Mi / Tm / TmY": ("Mi", "Tm"),
    "T4 / T5": ("T4", "T5"),
    "LC / LPLC": ("LC", "LPLC"),
    "DN* types": ("DN",),
}


def main(data_dir: Path, out: Path) -> dict:
    doc = dn_arena.assert_matches_code()
    neurons, edges = data.load(data_dir)
    setup = dn_arena.build(doc, neurons, edges, data_dir, out, "exploratory")
    p = setup.params
    steps = round(1000.0 / p.dt)
    kicks = sim.poisson_kicks(doc["seed"], 100.0, p.dt, steps, len(setup.input_rows))
    kicks = stimulus.dead_time(kicks, doc["model"]["input_gap_steps"])
    total = sim.run(setup.W, setup.input_rows, duration_ms=1000.0, p=p, kicks=kicks)
    total = total.counts.sum(axis=0)
    types = neurons["type"].fillna("").astype(str)
    groups = {"input photoreceptors": setup.input_rows}
    for name, prefixes in CLASSES.items():
        exact = name == "lamina L1-L5"
        hit = types.isin(prefixes) if exact else types.str.startswith(prefixes)
        groups[name] = np.flatnonzero(hit.to_numpy())
    groups["decoder six"] = setup.traced_rows
    groups["whole brain"] = np.arange(len(types))
    W = setup.W.tocsc()
    out_w = np.concatenate(
        [W.data[W.indptr[j] : W.indptr[j + 1]] for j in setup.input_rows]
    )
    dist = np.full(W.shape[0], -1)
    dist[setup.input_rows] = 0
    queue = deque(setup.input_rows.tolist())
    while queue:
        j = queue.popleft()
        for i in W.indices[W.indptr[j] : W.indptr[j + 1]]:
            if dist[i] < 0:
                dist[i] = dist[j] + 1
                queue.append(i)
    return {
        "classes": {
            k: {
                "neurons": int(v.size),
                "active": int((total[v] > 0).sum()),
                "spikes": int(total[v].sum()),
            }
            for k, v in groups.items()
        },
        "input_synapses": {
            "negative": int((out_w < 0).sum()),
            "positive": int((out_w > 0).sum()),
        },
        "hops_from_inputs": {
            str(b): int(dist[r]) for b, r in zip(setup.traced_ids, setup.traced_rows)
        },
    }


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2])), indent=1))
