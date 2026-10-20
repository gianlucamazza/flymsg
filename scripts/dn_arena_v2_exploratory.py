"""Post-verdict exploratory drive test for DN-arena v2 (docs/result/dn-arena.md); not scored.

Usage: uv run python scripts/dn_arena_v2_exploratory.py DATA_DIR OUT_DIR

One open-loop second with the body held at its reset pose, on the lock's anchored
pathway at lamina-to-medulla gains 4 and 16, under four drives: the locked sphere
(the disconnected arm's input), the same sphere mirrored to the fly's right, no sphere
(full light) and zero drive (the dark anchor alone). The same four drives run on
wiring-null seed 7323, whose decoder sets the null minimum at every gain, with the
intact graph's rate and drive gain as in the lock. Prints the six decoder neurons'
spikes per run. If the counts do not follow the stimulus, the readout is not visual.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import closedloop, data, dn_arena, eye, optics, pose, sim, wiring

GAINS = (4.0, 16.0)
NULL_SEED = 7323


def coverages(setup, data_dir: Path) -> dict[str, np.ndarray]:
    """Per-column coverage at the reset pose: locked sphere, its mirror, none."""
    doc = setup.doc
    ann = pd.read_feather(
        data_dir / "raw" / data.RAW["annotations"],
        columns=["bodyId", "type", "instance", "assignedOlHex1", "assignedOlHex2"],
    )
    cols = eye.columns(ann, eye.lenses(data_dir))
    columns = optics.Columns.from_frame(cols, dn_arena._source_sha256(data_dir))
    state = dn_arena._body(doc).reset()
    mounts = pose.flygym_eye_mounts()
    z = float(np.mean([pose.eye_pose(state, m).position_m[2] for m in mounts]))
    x, y = (float(v) for v in doc["stimulus"]["center_xy_m"])
    registration = pose.Registration(
        pose.Pose("body", "eyemap", (0.0, 0.0, 0.0), pose.IDENTITY),
        doc["eye"]["registration"],
    )

    def at(cy: float) -> np.ndarray:
        sphere = optics.Sphere(
            doc["stimulus"]["sphere"], (x, cy, z), float(doc["stimulus"]["radius_m"])
        )
        stim, _ = closedloop.optical(
            columns,
            registration,
            mounts,
            (sphere,),
            float(doc["eye"]["acceptance_deg"]),
        )
        return np.asarray(stim(0, state))

    locked = at(y)
    if not np.array_equal(locked, np.asarray(setup.stimulus(0, state))):
        raise SystemExit("rebuilt stimulus differs from the lock's")
    return {
        "sphere left (locked)": locked,
        "sphere right (mirrored)": at(-y),
        "no sphere": np.zeros_like(locked),
    }


def decoder_spikes(setup, built, kicks) -> dict[str, int]:
    res = sim.run(
        built.W,
        setup.input_rows,
        duration_ms=kicks.shape[0] * setup.params.dt,
        p=setup.params,
        kicks=kicks,
        graded=built.graded,
        membrane=built.membrane,
        trace=setup.traced_rows,
    )
    names = dn_arena.neurons(setup.doc)
    total = res.traced.sum(axis=0)
    return {
        " ".join(names[b]): int(n) for b, n in zip(setup.traced_ids, total, strict=True)
    }


def main(data_dir: Path, out: Path) -> dict:
    doc = dn_arena.assert_matches_code()
    neurons, edges = data.load(data_dir)
    setup = dn_arena.build(doc, neurons, edges, data_dir, out, "exploratory")
    steps = setup.duration_us // setup.clock.neural_us
    cov = coverages(setup, data_dir)
    shuffled, _ = wiring.shuffle_targets(edges, NULL_SEED)
    w_null = sim.network(neurons, shuffled, setup.params)
    result = {}
    for cfg in dn_arena.configurations(doc):
        if cfg["lamina_medulla_gain"] not in GAINS:
            continue
        _, intact = dn_arena.pathway(
            setup.W, neurons, cfg, setup.input_rows, setup.proto, setup.params
        )
        _, null = dn_arena.pathway(
            w_null,
            neurons,
            cfg,
            setup.input_rows,
            setup.proto,
            setup.params,
            rate=(intact.rate_hz, intact.receiving),
        )
        kicks = {
            k: dn_arena.drive(c, setup.column_of_input, intact.gain, steps)
            for k, c in cov.items()
        }
        kicks["dark (zero drive)"] = np.zeros_like(kicks["no sphere"])
        result[f"gain {cfg['lamina_medulla_gain']:g}"] = {
            graph: {k: decoder_spikes(setup, built, v) for k, v in kicks.items()}
            for graph, built in (("intact", intact), (f"null {NULL_SEED}", null))
        }
        print(json.dumps(result, indent=1), flush=True)
    return result


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
