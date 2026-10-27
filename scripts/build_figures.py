"""Draw the docs figures from archived run outputs. Usage: uv run python scripts/build_figures.py

Reads results/ (tracked; filled from runs/ by scripts/archive_results.py, manifests included):
  results/behavior/           flymsg behavior --run
  results/silence-scan/v{2,3}/  flymsg silence-scan --run (locks v2, v3)
  results/partner-followup/v1/  flymsg partner-followup --run
  results/jump/{intact,dnp01}/  flymsg jump --sim LC4_R [--silence DNp01]
  results/loop/               flymsg loop --sim LC4_R ...
  results/sensitivity/v1/     flymsg sensitivity --run
  results/kc-sparseness/v1/ … v5/  flymsg kc-sparseness --run
  results/jump3d/v1/          flymsg jump3d --run
  results/t4t5/v4.executions/  flymsg t4t5 --run (lock v4)
  results/dn-arena/v{1,2}.executions/  flymsg dn-arena --run (locks v1, v2)
  validation/homology/        flymsg homology
and reruns one exploratory simulation (the scored ORN_DM1 corner, seed 0) for the Kenyon
cell persistence figure, which needs the MaleCNS tables. The sparseness and jump figures
read the archives only. Writes docs/img/*.svg. Nothing here changes a result.
"""

import argparse
import ast
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import behavior, data, figures, locks, partner_followup, sensitivity, sim

ROOT = Path(__file__).resolve().parents[1]
RESULTS, IMG = ROOT / "results", ROOT / "docs" / "img"


def looming_jump() -> str:
    doc = behavior.load()
    endpoints = doc["protocol"]
    seeds = range(endpoints["seed0"], endpoints["seed0"] + endpoints["seeds"])
    replay = dict(np.load(RESULTS / "behavior" / "replay.npz"))
    return figures.looming_jump(
        replay, list(seeds), endpoints["dt_ms"], endpoints["stim_ms"]
    )


def scan(version: int, confirm_seeds: str) -> str:
    d = RESULTS / "silence-scan" / f"v{version}"
    report = (d / "report.txt").read_text()
    base = {
        k: ast.literal_eval(v)
        for k, v in re.findall(r"base arm, (screen|confirm) seeds: (\[.*\])", report)
    }
    return figures.silence_scan(
        pd.read_csv(d / "screen.csv"),
        pd.read_csv(d / "confirm.csv"),
        base["screen"],
        base["confirm"],
        confirm_seeds,
        version,
    )


def followup() -> str:
    d = RESULTS / "partner-followup" / "v1"
    report = (d / "report.txt").read_text()
    base = ast.literal_eval(
        re.search(r"left base arm \(DNp01 silenced\): (\[.*\])", report)[1]
    )
    left_v = re.search(r"left verdict: (.*)", report)[1]
    drive_v = re.search(r"drive verdict: (.*)", report)[1]
    pair_p = float(re.search(r"pair null: .* p ([0-9.]+)", report)[1])
    doc = partner_followup.load()
    s = partner_followup.seeds(doc)
    return figures.partner_followup(
        pd.read_csv(d / "left.csv"),
        base,
        pd.read_csv(d / "drive.csv"),
        pd.read_csv(d / "null_draws.csv"),
        pair_p,
        doc["model"]["bar"],
        (left_v, drive_v),
        f"{s.start}–{s.stop - 1}",
    )


def embodiment() -> str:
    jump = {
        k: json.loads((RESULTS / "jump" / k / "trajectory.json").read_text())
        for k in ("intact", "dnp01")
    }
    loop = dict(np.load(RESULTS / "loop" / "loop.npz"))
    return figures.embodiment(jump["intact"], jump["dnp01"], loop)


def kc(data_dir: Path) -> str:
    neurons, edges = data.load(data_dir)
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    stim = data.resolve(neurons, "ORN_DM1")
    r = sim.run(W, stim, 100.0, 600.0, 300.0, p, 0)
    types = neurons["type"].fillna("").astype(str).to_numpy()
    is_kc = np.char.startswith(types.astype(str), "KC")
    rest = ~is_kc
    rest[stim] = False
    target = data.resolve(neurons, "DM1_lPN")
    hz = r.counts / (r.bin_ms / 1000.0)
    groups = {
        f"Kenyon cells ({int(is_kc.sum()):,})": hz[:, is_kc].mean(axis=1),
        f"all other non-stimulus neurons ({int(rest.sum()):,})": hz[:, rest].mean(
            axis=1
        ),
        "DM1_lPN (target), rate / 10": hz[:, target].mean(axis=1) / 10,
    }
    # share of excitatory synapses onto Kenyon cells that come from Kenyon cells
    sign = neurons["sign"].to_numpy()
    pre, post, w = (edges[c].to_numpy() for c in ("pre", "post", "weight"))
    onto = is_kc[post] & (sign[pre] > 0)
    share = w[onto & is_kc[pre]].sum() / w[onto].sum()
    t = np.arange(1, hz.shape[0] + 1) * r.bin_ms
    return figures.kc_persistence(
        t,
        groups,
        300.0,
        f"{100 * share:.1f}% of the excitatory synapses onto Kenyon cells come from "
        "Kenyon cells; in a point neuron each reaches the soma.\nScored corner: w_syn "
        "0.192, th_jump 0, ORN_DM1 at 100 Hz for 300 ms, seed 0. Exploratory.",
    )


def homology() -> str:
    return figures.homology_pilot(pd.read_csv(ROOT / "validation/homology/pilot.csv"))


def sens() -> str:
    cells = pd.read_csv(RESULTS / "sensitivity" / "v1" / "cells.csv")
    return sensitivity.svg(cells, sensitivity.load())


# Arms named by each version's result: the default, v1's recurrence-off arm, the
# silent cholinergic-local-neuron arm, the two ends of the v4 coupling scan (0.2% down
# to 0%), and the two ends of the v5 spikelet scan (0 and 2 ms). Not a new comparison.
KC_ARMS = (
    (1, "A"),
    (1, "B"),
    (2, "A"),
    (2, "E"),
    (3, "A"),
    (3, "E"),
    (4, "A"),
    (4, "E+gap0"),
    (4, "E+gap1"),
    (5, "A"),
    (5, "E+spike0ms"),
    (5, "E+spike2ms"),
)


def sparseness() -> str:
    frames = []
    for version, arm in KC_ARMS:
        table = pd.read_csv(RESULTS / "kc-sparseness" / f"v{version}" / "arms.csv")
        row = table.loc[table["arm"] == arm].iloc[0]
        frames.append(
            {
                "version": f"v{version}",
                "arm": arm,
                "fraction_1": float(row["fraction_1"]),
                "shared_of_1": float(row["shared_of_1"]),
            }
        )
    floor = locks.load(ROOT / "validation" / "kc_sparseness.yaml")["decides"][
        "sparse_min"
    ]
    return figures.kc_sparseness(pd.DataFrame(frames), float(floor))


def jump_range() -> str:
    seeds = json.loads((RESULTS / "jump3d" / "v1" / "seeds.json").read_text())
    bounds = locks.load(ROOT / "validation" / "jump3d.yaml")["decides"]
    return figures.jump_range(
        seeds, float(bounds["range_min_mm"]), float(bounds["range_max_mm"])
    )


def t4_spikes() -> str:
    (folder,) = (RESULTS / "t4t5").glob("v4.executions/*/output")
    configs = pd.read_csv(folder / "configurations.csv")
    spikes = pd.read_csv(folder / "spikes.csv")
    t4 = spikes[spikes["subtype"].str.startswith("T4")].groupby("config")["spikes"]
    configs["t4_spikes"] = configs["config"].map(t4.sum()).astype(int)
    return figures.t4_spikes(configs)


def _dn_arena_rows(version: str, cells: list[dict]) -> list[dict]:
    rows = []
    for cell in cells:
        row = {
            "version": version,
            "verdict": cell["verdict"],
            "intact": float(cell["intact"]),
            "script": float(cell["script"]),
            "wiring_null_minimum": float(cell["wiring_null_minimum"]),
            "wiring_null_median": float(cell["wiring_null_median"]),
            "wiring_null_maximum": float(cell["wiring_null_maximum"]),
        }
        if version == "v1":
            row["yaw_gain_deg_s_per_hz"] = float(cell["yaw_gain_deg_s_per_hz"])
            row["forward_gain_mm_s_per_hz"] = float(cell["forward_gain_mm_s_per_hz"])
        elif version == "v2":
            row["lamina_medulla_gain"] = float(cell["lamina_medulla_gain"])
        else:
            raise ValueError(version)
        rows.append(row)
    return rows


def dn_arena() -> str:
    arena = RESULTS / "dn-arena"
    (v1_path,) = arena.glob("v1.executions/*/output/verdict.json")
    (v2_path,) = arena.glob("v2.executions/*/output/verdict.json")
    v1 = json.loads(v1_path.read_text())
    v2 = json.loads(v2_path.read_text())
    rows = _dn_arena_rows("v1", v1["cells"]) + _dn_arena_rows(
        "v2", v2["configurations"]
    )
    return figures.dn_arena(pd.DataFrame(rows))


FIGURES = {
    "looming-jump.svg": looming_jump,
    "silence-scan-v2.svg": lambda: scan(2, "20–22"),
    "silence-scan-v3.svg": lambda: scan(3, "30–32"),
    "partner-followup.svg": followup,
    "embodiment.svg": embodiment,
    "kc-persistence.svg": kc,
    "kc-sparseness.svg": sparseness,
    "jump-range.svg": jump_range,
    "homology-pilot.svg": homology,
    "sensitivity-rate.svg": sens,
    "t4-spikes.svg": t4_spikes,
    "dn-arena.svg": dn_arena,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("FLYMSG_DATA", "data")),
        help="data dir (env FLYMSG_DATA)",
    )
    args = parser.parse_args()
    for name, draw in FIGURES.items():
        (IMG / name).write_text((kc(args.data) if draw is kc else draw()) + "\n")
        print(f"docs/img/{name}")


if __name__ == "__main__":
    main()
