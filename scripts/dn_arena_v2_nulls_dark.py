"""Post-verdict exploratory dark test for DN-arena v2 wiring nulls; not scored.

Usage: uv run python scripts/dn_arena_v2_nulls_dark.py DATA_DIR OUT_DIR

At the locked lamina-to-medulla gain 4, run one open-loop second in darkness
and under the locked sphere at the reset pose for six turning and six silent
wiring nulls. Compare decoder spikes with the archived index 1 counts to check
whether the null band is tonic. Each shuffled pathway uses the intact rate and
drive gain, as in the lock.
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
from dn_arena_v2_exploratory import coverages, decoder_spikes

from flymsg import data, dn_arena, sim, wiring

TURNING_SEEDS = (7308, 7316, 7317, 7323, 7327, 7333)
# First six all-zero decoder counts at index 1 in the results.csv below.
SILENT_SEEDS = (7300, 7301, 7303, 7306, 7309, 7311)
RESULTS_CSV = (
    Path(__file__).resolve().parents[1]
    / "results/dn-arena/v2.executions"
    / "edd21a61d587947dd98ebef882219f74a335c6e6ed75d7f5dd980fc3a5bb8785"
    / "output/results.csv"
)


def main(data_dir: Path, out: Path) -> dict:
    with RESULTS_CSV.open(newline="") as source:
        archived = {
            int(float(row["seed"])): json.loads(row["spikes"])
            for row in csv.DictReader(source)
            if row["kind"] == "wiring-null" and float(row["index"]) == 1
        }
    doc = dn_arena.assert_matches_code()
    neurons, edges = data.load(data_dir)
    setup = dn_arena.build(doc, neurons, edges, data_dir, out, "exploratory")
    cfg = next(
        cfg for cfg in dn_arena.configurations(doc) if cfg["lamina_medulla_gain"] == 4
    )
    _, intact = dn_arena.pathway(
        setup.W, neurons, cfg, setup.input_rows, setup.proto, setup.params
    )
    steps = setup.duration_us // setup.clock.neural_us
    coverage = coverages(setup, data_dir)["sphere left (locked)"]
    sphere = dn_arena.drive(coverage, setup.column_of_input, intact.gain, steps)
    dark = np.zeros_like(sphere)
    names = dn_arena.neurons(doc)
    result = {}
    for seed in TURNING_SEEDS + SILENT_SEEDS:
        shuffled, _ = wiring.shuffle_targets(edges, seed)
        w_null = sim.network(neurons, shuffled, setup.params)
        del shuffled
        static, null = dn_arena.pathway(
            w_null,
            neurons,
            cfg,
            setup.input_rows,
            setup.proto,
            setup.params,
            rate=(intact.rate_hz, intact.receiving),
        )
        del static
        result[str(seed)] = {
            "dark (zero drive)": decoder_spikes(setup, null, dark),
            "sphere left (locked)": decoder_spikes(setup, null, sphere),
            "archived index 1": {
                " ".join(names[b]): archived[seed][str(b)] for b in setup.traced_ids
            },
        }
        del null, w_null
        print(json.dumps(result, indent=1), flush=True)
    return result


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
