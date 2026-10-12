"""Post-hoc and exploratory: what reached 0 spikes in the null of silence-scan v1?

Regenerates the confirm-stage null picks of version 1 (they are seeded by the unit label,
so they are the draws that ran) and counts, per tested unit, how many draws contain the
neurons of the other unit that passed the screen. It does not change the v1 verdict.

    uv run python scripts/silence_scan_posthoc.py
"""

import json
import zlib
from pathlib import Path

import numpy as np

from flymsg import data, dimorphism, sim

UNITS = ("DNp02", "DNp06")
CONFIRM_SEEDS = range(10, 13)  # silence-scan v1


def main() -> None:
    neurons, edges = data.load(Path("data"))
    stim = data.resolve(neurons, "LC4_R")
    motor = int(data.resolve(neurons, "TTMn_R")[0])
    base = data.resolve(neurons, "DNp01")
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    runs = [
        sim.run(W, stim, 100.0, 300.0, 300.0, p, s, silence=base) for s in CONFIRM_SEEDS
    ]
    pool = np.zeros(len(neurons), dtype=bool)
    pool[dimorphism.responders(runs, stim)] = True
    pool[np.concatenate([stim, [motor], base])] = False
    key = (
        neurons["superclass"].fillna("none").astype(str)
        + "/"
        + neurons["sign"].astype(str)
    ).to_numpy()
    units = {u: data.resolve(neurons, u) for u in UNITS}
    recorded = {}
    for line in Path("runs/silence-scan.ckpt.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec["meta"].get("stage") == "confirm":
            recorded[rec["job"][0]] = rec["rows"][0]
    names = neurons["instance"].fillna("").to_numpy()
    print(f"null pool: {int(pool.sum())} responders on seeds 10-12")
    for unit, tested in units.items():
        other = next(u for u in units if u != unit)
        upool = pool.copy()
        upool[tested] = False
        rng = np.random.default_rng(zlib.crc32(f"silence-scan/v1/{unit}".encode()))
        picks = [dimorphism._matched_draw(rng, key, upool, tested) for _ in range(1000)]
        at_zero = round(recorded[unit]["p"] * 1001) - 1
        print(
            f"{unit}: {at_zero} of 1000 draws reached 0 spikes (p {recorded[unit]['p']:.4f})"
        )
        for i in units[other]:
            hits = sum(int(i in pick) for pick in picks)
            print(
                f"  draws containing {names[i]} ({neurons['bodyId'].iat[i]}): {hits}"
                f" (in the pool: {bool(upool[i])})"
            )


if __name__ == "__main__":
    main()
