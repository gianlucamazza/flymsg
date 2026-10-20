"""Post-verdict exploratory layer tally for DN-arena v2 (docs/result/dn-arena.md); not scored.

Usage: uv run python scripts/dn_arena_v2_layers.py DATA_DIR OUT_DIR

Where left/right asymmetry is lost. One open-loop second on the intact graph,
steps = duration_us // clock.neural_us, at lamina-to-medulla gains 4 and 16.
Drives are the locked sphere, that sphere mirrored to the right, and zero drive.
Photoreceptors are the arena inputs, split by column side; other classes use
somaSide. A somaSide other than L or R is reported as other and stays out of the
asymmetry. Spikes are the second's total over spiking members. graded_mV is the
mean of Result.graded_v over that second (equal bins), then over graded members:
absolute membrane potential in mV as the kernel records v, not v minus rest.
Spike asymmetry is (L - R) / (L + R) when L + R > 0. left_minus_mirrored is the
locked sphere minus the mirrored sphere on each side.
"""

import json
import sys
from pathlib import Path

import numpy as np
from dn_arena_v2_exploratory import coverages

from flymsg import data, dn_arena, sim

GAINS = (4.0, 16.0)
DRIVES = (
    "sphere left (locked)",
    "sphere right (mirrored)",
    "dark (zero drive)",
)


def _classes(setup) -> list[tuple[str, np.ndarray, np.ndarray]]:
    neurons = setup.neurons
    types = neurons["type"].fillna("").astype(str)
    soma = np.asarray(neurons["somaSide"].fillna("").astype(str).to_numpy(), dtype=str)
    found: list[tuple[str, np.ndarray, np.ndarray]] = []

    def add(name: str, mask: np.ndarray) -> None:
        rows = np.flatnonzero(mask)
        found.append((name, rows, soma[rows]))

    pr = np.asarray(setup.input_rows, dtype=np.int64)
    pr_side = np.asarray(setup.sides, dtype=str)[setup.column_of_input]
    found.append(("photoreceptors", pr, pr_side))
    add("lamina L1-L5", types.isin(("L1", "L2", "L3", "L4", "L5")).to_numpy())
    add("Mi / Tm / TmY", types.str.startswith(("Mi", "Tm")).to_numpy())
    add("T4 / T5", types.str.startswith(("T4", "T5")).to_numpy())
    add("LC / LPLC", types.str.startswith(("LC", "LPLC")).to_numpy())
    add("DN*", types.str.startswith(("DN",)).to_numpy())
    decoder = np.asarray(setup.traced_rows, dtype=np.int64)
    found.append(("decoder six", decoder, soma[decoder]))
    return found


def _pack(rows, labels, spikes, g_at, is_graded) -> dict:
    labels = np.asarray(labels, dtype=str)
    masks = {
        "L": labels == "L",
        "R": labels == "R",
        "other": (labels != "L") & (labels != "R"),
    }
    out: dict = {}
    totals = {}
    for label, mask in masks.items():
        member = rows[mask]
        graded_m = is_graded[member]
        graded = member[graded_m]
        spiking = member[~graded_m]
        if graded.size == 0:
            mv = None
        else:
            mv = float(g_at[graded].mean())
        total = int(spikes[spiking].sum())
        totals[label] = total
        out[label] = {
            "neurons": int(member.size),
            "spiking_members": int(spiking.size),
            "spikes": total,
            "graded_members": int(graded.size),
            "graded_mV": mv,
        }
    total_lr = totals["L"] + totals["R"]
    if total_lr == 0:
        out["spike_asymmetry"] = None
    else:
        out["spike_asymmetry"] = (totals["L"] - totals["R"]) / total_lr
    return out


def _run(setup, built, kicks, classes) -> dict:
    res = sim.run(
        built.W,
        setup.input_rows,
        duration_ms=kicks.shape[0] * setup.params.dt,
        p=setup.params,
        kicks=kicks,
        graded=built.graded,
        membrane=built.membrane,
    )
    spikes = np.asarray(res.counts.sum(axis=0, dtype=np.int64))
    # Result.graded_v columns follow sorted Graded.idx.
    order = np.sort(np.asarray(built.graded.idx, dtype=np.int64))
    graded_v = res.graded_v
    if graded_v is None or graded_v.shape[1] != order.size:
        raise SystemExit("graded_v does not match sorted graded.idx")
    means = np.asarray(graded_v.mean(axis=0), dtype=np.float64)
    del res, graded_v
    g_at = np.full(spikes.shape[0], np.nan)
    g_at[order] = means
    del means
    is_graded = np.zeros(spikes.shape[0], dtype=bool)
    is_graded[order] = True
    out = {}
    for name, rows, labels in classes:
        out[name] = _pack(rows, labels, spikes, g_at, is_graded)
    return out


def _kicks(name: str, cov, setup, gain: float, steps: int) -> np.ndarray:
    if name == "dark (zero drive)":
        return np.zeros((steps, setup.input_rows.size), np.float32)
    return dn_arena.drive(cov[name], setup.column_of_input, gain, steps)


def _contrast(left: dict, right: dict) -> dict:
    out = {}
    for name, block in left.items():
        sides = {}
        for side in ("L", "R"):
            a, b = block[side], right[name][side]
            if a["graded_mV"] is None or b["graded_mV"] is None:
                mv = None
            else:
                mv = a["graded_mV"] - b["graded_mV"]
            sides[side] = {
                "spikes": a["spikes"] - b["spikes"],
                "graded_mV": mv,
            }
        out[name] = sides
    return out


def main(data_dir: Path, out: Path) -> dict:
    doc = dn_arena.assert_matches_code()
    neurons, edges = data.load(data_dir)
    setup = dn_arena.build(doc, neurons, edges, data_dir, out, "exploratory")
    classes = _classes(setup)
    steps = setup.duration_us // setup.clock.neural_us
    cov = coverages(setup, data_dir)
    result = {
        "graded_mV": "absolute mV of v, not v - rest; mean over second then members",
    }
    for cfg in dn_arena.configurations(doc):
        gain = cfg["lamina_medulla_gain"]
        if gain not in GAINS:
            continue
        _, built = dn_arena.pathway(
            setup.W,
            setup.neurons,
            cfg,
            setup.input_rows,
            setup.proto,
            setup.params,
        )
        drives = {}
        for name in DRIVES:
            kicks = _kicks(name, cov, setup, built.gain, steps)
            drives[name] = _run(setup, built, kicks, classes)
            del kicks
        drives["left_minus_mirrored"] = _contrast(
            drives["sphere left (locked)"],
            drives["sphere right (mirrored)"],
        )
        result[f"gain {gain:g}"] = drives
        del built
        print(json.dumps(result, indent=1), flush=True)
    return result


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
