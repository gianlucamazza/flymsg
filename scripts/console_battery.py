"""The battery of one graph as one console batch, against sim.run on the host (#40).

Every case and seed of the locked battery (validation/baselines.yaml's protocol) on the
measured MaleCNS connectome runs as one batch job on the console worker; each run's spike
counts and first spikes are checked against `sim.run` on the host, run by run. The report
records the console's wall time (upload included) and the host's. Settings from the
environment only (see flymsg.console); the report holds no address or credential. Exits
nonzero unless every run matches.

Usage: uv run python scripts/console_battery.py --out DIR [--seeds 5]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from flymsg import baselines, console, data, sensitivity, sim


def run(out: Path, seeds: int) -> dict:
    doc = baselines.assert_matches_code()
    b = doc["battery"]
    neurons, edges = data.load(Path(os.environ.get("FLYMSG_DATA", "data")))
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    cases = [*doc["cases"]["positive"], *doc["cases"]["negative"]]
    specs = [
        (
            sensitivity.case_inputs(case, neurons)[0],
            b["rate_hz"],
            b["duration_ms"],
            b["stim_ms"],
            s,
        )
        for case in cases
        for s in range(b["seed0"], b["seed0"] + seeds)
    ]
    start = time.perf_counter()
    got, result = console.sim_runs(
        console.Device(),
        W,
        specs,
        p,
        out,
        dataset="malecns-v1.0",
        seed=b["seed0"],
        scope="battery qualification, not a baseline result",
    )
    console_s = time.perf_counter() - start
    start = time.perf_counter()
    expected = [sim.run(W, spec[0], *spec[1:4], p, spec[4]) for spec in specs]
    host_s = time.perf_counter() - start
    mismatches = [
        k
        for k, (g, e) in enumerate(zip(got, expected, strict=True))
        if not (
            np.array_equal(g.counts, e.counts)
            and np.array_equal(g.first_spike_ms, e.first_spike_ms, equal_nan=True)
        )
    ]
    report = {
        "schema": "flymsg.console_battery/v1",
        "date": time.strftime("%Y-%m-%d"),
        "platform": "Xbox Series S, Dev Mode",
        "script": "scripts/console_battery.py",
        "battery": {
            "cases": cases,
            "seeds": seeds,
            "duration_ms": b["duration_ms"],
            "runs": len(specs),
        },
        "network": {"neurons": int(W.shape[0]), "synapses": int(W.nnz)},
        **console.lineage("console"),
        "console": {
            "wall_s": console_s,
            "advance_ms": result["advance_ms"],
            "advance_steps": result["advance_steps"],
        },
        "host_sim_run_s": host_s,
        "host_load_average": list(os.getloadavg()),
        "mismatched_runs": mismatches,
        "passed": not mismatches,
        "scope": "one graph's battery; equality of counts and first spikes per run",
    }
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=5)
    a = parser.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    r = run(a.out, a.seeds)
    keys = ("battery", "console", "host_sim_run_s", "mismatched_runs", "passed")
    print(json.dumps({k: r[k] for k in keys}))
    sys.exit(0 if r["passed"] else 1)
