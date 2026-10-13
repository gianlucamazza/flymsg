"""Draw the docs figures from archived run outputs. Usage: uv run python scripts/build_figures.py

Reads results/ (tracked; filled from runs/ by scripts/archive_results.py, manifests included):
  results/behavior/           flymsg behavior --run
  results/silence-scan/v{2,3}/  flymsg silence-scan --run (locks v2, v3)
  results/partner-followup/v1/  flymsg partner-followup --run
  results/jump/{intact,dnp01}/  flymsg jump --sim LC4_R [--silence DNp01]
  results/loop/               flymsg loop --sim LC4_R ...
  results/sensitivity/v1/     flymsg sensitivity --run
  validation/homology/        flymsg homology
and reruns one exploratory simulation (the scored ORN_DM1 corner, seed 0) for the Kenyon
cell figure, which needs the MaleCNS tables. Writes docs/img/*.svg. Nothing here changes a
result.
"""

import ast
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import behavior, data, figures, partner_followup, sensitivity, sim

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


def kc() -> str:
    neurons, edges = data.load(ROOT / "data")
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


FIGURES = {
    "looming-jump.svg": looming_jump,
    "silence-scan-v2.svg": lambda: scan(2, "20–22"),
    "silence-scan-v3.svg": lambda: scan(3, "30–32"),
    "partner-followup.svg": followup,
    "embodiment.svg": embodiment,
    "kc-persistence.svg": kc,
    "homology-pilot.svg": homology,
    "sensitivity-rate.svg": sens,
}


def main() -> None:
    for name, draw in FIGURES.items():
        (IMG / name).write_text(draw() + "\n")
        print(f"docs/img/{name}")


if __name__ == "__main__":
    main()
