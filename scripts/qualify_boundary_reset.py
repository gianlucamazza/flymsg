"""Qualify the boundary reset against the continuous clamp on the Kenyon cell coupling (KC
sparseness v7, docs/adr-gap-refractory.md). Usage:

    FLYMSG_DATA=data uv run python scripts/qualify_boundary_reset.py OUT.json

Arm E of the lLN2T eLN set (the coupled arm with the measured eLN-PN and sister-PN junctions),
3-octanol at the lock's DoOR rates for 50 ms, seed 0 (used by no lock), spikelets of 0 and
1 ms. Runs each case under both refractory modes and compares spike counts per neuron and
first-spike times. An engineering qualification, not a scored run; the continuous clamp takes
minutes per 50 ms on this component (issue #155).
"""

import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from flymsg import data, electrical, kc_sparseness, odors, sim

MS = 50.0
ODOR = "3-octanol"
SET = "lLN2T"


def setup(data_dir: Path):
    """The weight matrix of arm E for the set and the indices the v7 run would use."""
    neurons, edges = data.load(data_dir)
    captured = {}
    run_protocol = kc_sparseness.protocol

    def capture(W, idx, doc, steps, report):
        captured.update(W=W, idx=idx)

    kc_sparseness.protocol = capture
    try:
        kc_sparseness.run(neurons, edges, data_dir)
    finally:
        kc_sparseness.protocol = run_protocol
    W, idx = captured["W"], captured["idx"]
    own = idx["sets"][SET]
    return kc_sparseness.arms(W, {**idx, **own}, ["E"])["E"], idx, own, len(neurons)


def main() -> None:
    out = Path(sys.argv[1])
    Wx, idx, own, n = setup(Path(os.environ.get("FLYMSG_DATA", "data")))
    p = sim.Params()
    cells, rates = idx["stimuli"][ODOR]
    kicks = odors.kicks(rates, 0, p.dt, round(MS / p.dt))
    rows = []
    for width in (0.0, 1.0):
        res = {}
        for mode in ("boundary", "continuous"):
            gap = kc_sparseness.measured_gap(
                own["eln"], idx["sisters"], n, own["ACH_LN"], width
            )
            started = time.monotonic()
            r = sim.run(
                Wx,
                cells,
                duration_ms=MS,
                p=p,
                kicks=kicks,
                gap=replace(gap, refractory_mode=mode),
            )
            res[mode] = (r, time.monotonic() - started)
            print(width, mode, f"{res[mode][1]:.0f} s", electrical.cache_info())
        a, b = (res[m][0].counts.sum(axis=0) for m in ("boundary", "continuous"))
        first = [
            np.nan_to_num(res[m][0].first_spike_ms, nan=-1.0)
            for m in ("boundary", "continuous")
        ]
        rows.append(
            {
                "spike_ms": width,
                "seconds": {m: round(v[1], 1) for m, v in res.items()},
                "spikes": {"boundary": int(a.sum()), "continuous": int(b.sum())},
                "neurons_differing": int((a != b).sum()),
                "kc_spikes": {
                    "boundary": int(a[idx["KC"]].sum()),
                    "continuous": int(b[idx["KC"]].sum()),
                },
                "pn_spikes": {
                    "boundary": int(a[idx["PN"]].sum()),
                    "continuous": int(b[idx["PN"]].sum()),
                },
                "first_spike_equal": bool(np.array_equal(*first)),
            }
        )
    out.write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main()
