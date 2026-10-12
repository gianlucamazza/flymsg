"""Residual TTMn_R partner scan (issue #20). The YAML file is the lock.

`summary` prints it. The candidate rule, the screen, the draw count, the p and the verdict
are fixed here before any scan run, so the run cannot choose them after the numbers.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import behavior, prereg, sim

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "silence_scan.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "0982767d4ce972c7c9ef08b2c3491885e8bf242d7aeb54c22927eb6437a2bb1b",
}

_DECIDES = ("contributes", "names_partner", "none", "no_residual")
_EXCLUDE = ("stimulus", "motor", "base_silence")


class ScanError(ValueError):
    """The scan protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return prereg.load_yaml(path.read_text(encoding="utf-8"))


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    """Refuse a protocol whose locked fields changed without a new version."""
    doc = load() if doc is None else doc
    version = doc.get("version")
    if version not in VERSION_HASHES:
        raise ScanError(f"scan version {version} is not in VERSION_HASHES")
    digest = content_hash(doc)
    if digest != VERSION_HASHES[version]:
        raise ScanError("scan protocol changed without a bump")
    if doc.get("content_sha256") != digest:
        raise ScanError("content_sha256 does not match the protocol")
    return doc


def assert_matches_code(doc: dict | None = None) -> dict:
    """The scan is the behavior v1 silence arm at the live default model."""
    doc = assert_locked() if doc is None else doc
    parent = behavior.assert_matches_code()
    if doc["parent"] != {
        "lock": "behavior",
        "version": parent["version"],
        "arm": "silence",
    }:
        raise ScanError("the scan is not the behavior v1 silence arm")
    if doc["blind"]["ranking_used"] is not False:
        raise ScanError("the candidate set may not come from a ranking")
    protocol, task, bp = doc["protocol"], parent["task"], parent["protocol"]
    expected = {
        "stimulus": task["stimulus"],
        "stimulus_n": task["stimulus_n"],
        "motor": task["motor"],
        "motor_n": task["motor_n"],
        "base_silence": task["command"],
        "base_silence_n": task["command_n"],
        "rate_hz": bp["rate_hz"],
        "stim_ms": bp["stim_ms"],
        "duration_ms": bp["stim_ms"],
        "dt_ms": float(sim.Params.dt),
        "drive_cut": False,
    }
    for key, want in expected.items():
        if protocol[key] != want:
            raise ScanError(f"protocol.{key} is {protocol[key]}, expected {want}")
    if abs(protocol["w_syn"] - sim.Params.w_syn) > 1e-12 or (
        protocol["th_jump"] != sim.Params.th_jump
    ):
        raise ScanError("protocol parameters are not the simulator default")
    cand = doc["candidates"]
    if cand["min_weight"] != prereg.load()["criterion"]["control_min_weight"]:
        raise ScanError("min_weight is not the v4 control weight")
    if tuple(cand["exclude"]) != _EXCLUDE or cand["cap"] != "none":
        raise ScanError("the candidate rule changed")
    if doc["base_arm"]["stop_if_max_spikes_at_most"] != bp["min_spikes"] - 1:
        raise ScanError("the base arm stop is not the behavior silence bar")
    screen, confirm = doc["screen"], doc["confirm"]
    if screen["decides"] is not False or screen["null"] != "none":
        raise ScanError("the screen only chooses what is confirmed")
    if screen["seeds"] != bp["seeds"] or confirm["seeds"] != bp["seeds"]:
        raise ScanError("both stages use the behavior seed count")
    screen_seeds = set(range(screen["seed0"], screen["seed0"] + screen["seeds"]))
    confirm_seeds = set(range(confirm["seed0"], confirm["seed0"] + confirm["seeds"]))
    if screen_seeds & confirm_seeds:
        raise ScanError("confirm seeds must be fresh")
    if confirm["base_silence_in_every_draw"] is not True or confirm["tail"] != "lower":
        raise ScanError("the null keeps DNp01 silenced and tests a drop")
    if confirm["draws_per_test"] * confirm["alpha"] < 1:
        raise ScanError("the draw count cannot reach the corrected threshold")
    if tuple(doc["decides"]) != _DECIDES:
        raise ScanError("the deciding outcomes changed")
    for name, row in doc["reported"].items():
        if row["decides"] is not False:
            raise ScanError(f"reported row {name} must not decide")
    if (
        doc["prediction"]["status"] != "unverified"
        or doc["prediction"]["tests_animal"] is not False
    ):
        raise ScanError("the prediction is unverified model-side")
    return doc


def summary(doc: dict | None = None) -> str:
    """The frozen scan. Printing it does not simulate."""
    doc = assert_matches_code() if doc is None else doc
    p, s, c = doc["protocol"], doc["screen"], doc["confirm"]
    return (
        f"silence-scan v{doc['version']} (issue #{doc['issue']}): "
        f"{p['stimulus']} -> {p['motor']} with {p['base_silence']} silenced; "
        f"units {doc['candidates']['unit']}, >= {doc['candidates']['min_weight']} synapses "
        f"onto {p['motor']}, active in the base arm; "
        f"screen seeds {s['seed0']}-{s['seed0'] + s['seeds'] - 1} "
        f"(<= {s['pass_fraction_of_base']} of base); "
        f"confirm seeds {c['seed0']}-{c['seed0'] + c['seeds'] - 1}, "
        f"{c['null']} null, alpha {c['alpha']}/m; not run"
    )


def candidates(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    motor: int,
    active: np.ndarray,
    exclude: np.ndarray,
    min_weight: int,
) -> pd.DataFrame:
    """Every unit with at least `min_weight` synapses onto `motor` and an active neuron.

    A unit is a cell type; a neuron without a type is its own unit, named by bodyId.
    `active` is a boolean mask over neurons; `exclude` lists neurons never silenced.
    Rows are sorted by unit name, so the order carries no ranking.
    """
    onto = edges[edges["post"].to_numpy() == motor]
    w = np.zeros(len(neurons), dtype=np.int64)
    np.add.at(w, onto["pre"].to_numpy(), onto["weight"].to_numpy())
    keep = np.ones(len(neurons), dtype=bool)
    keep[np.asarray(exclude, dtype=np.int64)] = False
    types = neurons["type"].astype(object).to_numpy()
    unit = np.where(
        pd.isna(types), neurons["bodyId"].astype(str).to_numpy(), types
    ).astype(str)
    pre = np.flatnonzero((w > 0) & keep)
    rows = []
    for name in sorted(set(unit[pre])):
        members = np.flatnonzero((unit == name) & keep)
        weight = int(w[members].sum())
        if weight < min_weight or not active[members].any():
            continue
        signs = neurons["sign"].to_numpy()[members]
        rows.append(
            {
                "unit": name,
                "neurons": members,
                "n": int(members.size),
                "weight": weight,
                "sign": ",".join(str(int(x)) for x in sorted(set(signs))),
            }
        )
    return pd.DataFrame(rows, columns=["unit", "neurons", "n", "weight", "sign"])


def no_residual(base_counts, max_spikes: int) -> bool:
    """The base arm already holds TTMn_R under the jump bit in every seed."""
    return bool(np.all(np.asarray(base_counts) <= max_spikes))


def screen_pass(base_counts, unit_counts, fraction: float) -> bool:
    """Mean count with the unit silenced is at or below `fraction` of the base mean."""
    return float(np.mean(unit_counts)) <= fraction * float(np.mean(base_counts))


def n_draws(m: int, min_draws: int, per_test: int) -> int:
    """Enough draws that the smallest p, 1/(1+n), is below alpha/m for alpha 1/per_test."""
    return max(min_draws, per_test * m)


def p_lower(observed: float, null) -> float:
    """Empirical one-sided p for a drop, +1 smoothing."""
    null = np.asarray(null, dtype=float)
    return (1 + int(np.count_nonzero(null <= observed))) / (1 + null.size)


def decide(rows: pd.DataFrame, m: int, alpha: float, max_spikes: int) -> pd.DataFrame:
    """Per confirmed unit: `contributes` and `names_partner`.

    `rows` has `unit`, `p` (NaN when the null is undefined) and `counts` (per confirm seed).
    """
    out = rows.copy()
    threshold = alpha / m if m else math.nan
    out["contributes"] = out["p"].notna() & (out["p"] <= threshold)
    out["names_partner"] = out["contributes"] & out["counts"].map(
        lambda c: bool(np.all(np.asarray(c) <= max_spikes))
    )
    return out


def verdict(decided: pd.DataFrame, m: int) -> str:
    """One line. `none` when nothing passes the screen or nothing contributes."""
    if m == 0 or not decided["contributes"].any():
        return "none: the residual drive is not one cell type"
    named = decided.loc[decided["names_partner"], "unit"].tolist()
    if named:
        return "names_partner: " + ", ".join(named)
    return "contributes: " + ", ".join(decided.loc[decided["contributes"], "unit"])
