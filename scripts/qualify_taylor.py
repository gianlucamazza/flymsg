"""Qualify the Taylor solver of the continuous clamp against its dense maps on the Kenyon
cell coupling (issue #155, docs/adr-gap-refractory.md). Usage:

    FLYMSG_DATA=data uv run python scripts/qualify_taylor.py OUT.json

Arm E of both KC v7 eLN sets, 3-octanol at the lock's DoOR rates for 50 ms, seed 0 (used by
no lock), spikelets of 0 and 1 ms: spike counts per neuron and first-spike times under
flymsg.gap/continuous-clamp-v1 (dense map per refractory mask) and
flymsg.gap/continuous-clamp-taylor-v1. Then one full 1000 ms odor under the Taylor solver,
timed. An engineering qualification, not a scored run.
"""

import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from qualify_boundary_reset import ODOR, setup

from flymsg import electrical, kc_sparseness, odors, sim

MS = 50.0
FULL_MS = 1000.0


def main() -> None:
    out = Path(sys.argv[1])
    data_dir = Path(os.environ.get("FLYMSG_DATA", "data"))
    p = sim.Params()
    rows, full = [], None
    for name in ("lLN2T", "lLN2T+lLN1_bc"):
        Wx, idx, own, n = setup(data_dir, name)
        cells, rates = idx["stimuli"][ODOR]
        for width in (0.0, 1.0):
            gap = kc_sparseness.measured_gap(
                own["eln"], idx["sisters"], n, own["ACH_LN"], width
            )
            res = {}
            for solver in ("dense", "taylor"):
                kicks = odors.kicks(rates, 0, p.dt, round(MS / p.dt))
                started = time.monotonic()
                r = sim.run(
                    Wx,
                    cells,
                    duration_ms=MS,
                    p=p,
                    kicks=kicks,
                    gap=replace(gap, solver=solver),
                )
                res[solver] = (r, time.monotonic() - started)
                print(name, width, solver, f"{res[solver][1]:.0f} s", flush=True)
            a, b = (res[s][0].counts.sum(axis=0) for s in ("dense", "taylor"))
            first = [
                np.nan_to_num(res[s][0].first_spike_ms, nan=-1.0)
                for s in ("dense", "taylor")
            ]
            rows.append(
                {
                    "eln_set": name,
                    "spike_ms": width,
                    "seconds": {s: round(v[1], 1) for s, v in res.items()},
                    "spikes": {"dense": int(a.sum()), "taylor": int(b.sum())},
                    "neurons_differing": int((a != b).sum()),
                    "kc_spikes": {
                        "dense": int(a[idx["KC"]].sum()),
                        "taylor": int(b[idx["KC"]].sum()),
                    },
                    "first_spike_equal": bool(np.array_equal(*first)),
                }
            )
        if full is None:
            gap = kc_sparseness.measured_gap(
                own["eln"], idx["sisters"], n, own["ACH_LN"], 1.0
            )
            kicks = odors.kicks(rates, 0, p.dt, round(FULL_MS / p.dt))
            started = time.monotonic()
            sim.run(
                Wx,
                cells,
                duration_ms=FULL_MS,
                p=p,
                kicks=kicks,
                gap=replace(gap, solver="taylor"),
            )
            full = {
                "eln_set": name,
                "spike_ms": 1.0,
                "duration_ms": FULL_MS,
                "taylor_s": round(time.monotonic() - started, 1),
            }
            print(full, flush=True)
    G = electrical.generators(
        replace(gap, solver="taylor"), *sim.gap_arrays(gap, n, p)[:2], p
    )[2]
    out.write_text(
        json.dumps(
            {"taylor_terms": int(G[4]), "runs": rows, "full_odor": full}, indent=1
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
