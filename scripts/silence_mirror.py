"""Exploratory: the scan arms mirrored. LC4_L -> TTMn_L next to LC4_R -> TTMn_R, seeds 0-2.

Run on 2026-10-12 after scan v3 and before the partner follow-up lock (issue #76), which
discloses it. Per side: intact, both DNp01 silenced, DNp01 with DNp02 or DNp06 (both
sides of each type), and DNp01 with the DNp02 + DNp06 pair of one side only. Decides
nothing.

    uv run python scripts/silence_mirror.py
"""

from pathlib import Path

import numpy as np

from flymsg import data, sim

ROOT = Path(__file__).resolve().parents[1]
SEEDS = range(3)


def main() -> None:
    neurons, edges = data.load(ROOT / "data")
    p = sim.Params()
    W = sim.network(neurons, edges, p)

    def R(q):
        return data.resolve(neurons, q)

    gf = R("DNp01")
    for side, other in (("R", "L"), ("L", "R")):
        stim, motor = R(f"LC4_{side}"), R(f"TTMn_{side}")
        arms = {
            "intact": None,
            "DNp01": gf,
            "DNp01+DNp02": np.r_[gf, R("DNp02")],
            "DNp01+DNp06": np.r_[gf, R("DNp06")],
            f"DNp01+DNp02_{side}+DNp06_{side}": np.r_[
                gf, R(f"DNp02_{side}"), R(f"DNp06_{side}")
            ],
            f"DNp01+DNp02_{other}+DNp06_{other}": np.r_[
                gf, R(f"DNp02_{other}"), R(f"DNp06_{other}")
            ],
        }
        for name, silence in arms.items():
            counts = [
                int(
                    sim.run(W, stim, 100.0, 300.0, 300.0, p, s, silence=silence)
                    .counts[:, motor]
                    .sum()
                )
                for s in SEEDS
            ]
            print(f"{side} {name:32s} TTMn_{side} {counts}", flush=True)


if __name__ == "__main__":
    main()
