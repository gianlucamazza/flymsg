"""Residual TTMn_R partner scan (issue #20). The YAML file is the lock.

`summary` prints it. The candidate rule, the screen, the draw count, the p and the verdict
are fixed here before any scan run, so the run cannot choose them after the numbers.
"""

from __future__ import annotations

import math
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import behavior, data, dimorphism, locks, parallel, prereg, sim

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "silence_scan.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "0982767d4ce972c7c9ef08b2c3491885e8bf242d7aeb54c22927eb6437a2bb1b",
    2: "79762510dae3d4f0499b8b60906f59920973469a82b0472176d88e6bc5fd4627",  # null pool excludes every screen pass; confirm seeds 20-22
}

_DECIDES = ("contributes", "names_partner", "none", "no_residual")
_EXCLUDE = ("stimulus", "motor", "base_silence")


class ScanError(ValueError):
    """The scan protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    """Refuse a protocol whose locked fields changed without a new version."""
    doc = load() if doc is None else doc
    locks.check(doc, VERSION_HASHES, ScanError, "scan protocol")
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
    if doc["version"] >= 2 and (confirm_seeds & set(range(10, 13))):
        raise ScanError("confirm seeds must not reuse the v1 confirmation (10-12)")
    if (
        doc["version"] >= 2
        and doc["confirm"].get("pool_excludes_screen_passes") is not True
    ):
        raise ScanError("v2 excludes every screen pass from the null pool")
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
        f"{c['null']} null, alpha {c['alpha']}/m"
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


def _seeds(stage: dict) -> range:
    return range(stage["seed0"], stage["seed0"] + stage["seeds"])


def _arm(
    W, stim, motor, silence, seeds, protocol
) -> tuple[list[int], list[sim.Result]]:
    """TTMn_R spike count per seed during the drive, and the runs, with `silence` off."""
    counts, results = [], []
    for seed in seeds:
        r = sim.run(
            W,
            stim,
            protocol["rate_hz"],
            protocol["duration_ms"],
            protocol["stim_ms"],
            sim.Params(),
            seed,
            silence=silence,
        )
        counts.append(int(r.counts[:, motor].sum()))
        results.append(r)
    return counts, results


def _screen_job(job: tuple[str]) -> list[dict]:
    (W, stim, motor, base, units, doc), _checkpoint, _meta = parallel.context()
    unit = job[0]
    silence = np.concatenate([base, units[unit]])
    counts, _ = _arm(W, stim, motor, silence, _seeds(doc["screen"]), doc["protocol"])
    return [{"unit": unit, "counts": counts}]


def _confirm_job(job: tuple[str]) -> list[dict]:
    (W, stim, motor, base, units, doc, key, active, n), checkpoint, meta = (
        parallel.context()
    )
    unit = job[0]
    tested = units[unit]
    seeds, protocol = _seeds(doc["confirm"]), doc["protocol"]

    def mean_count(extra):
        counts, _ = _arm(W, stim, motor, np.concatenate([base, extra]), seeds, protocol)
        return counts

    counts = mean_count(tested)
    pool = active.copy()
    pool[tested] = False
    row = {
        "unit": unit,
        "counts": counts,
        "draws": 0,
        "null_mean": math.nan,
        "p": math.nan,
    }
    short = dimorphism.matched_pool_shortfall(key, pool, tested)
    if short:
        group, have, need = short[0]
        print(
            f"{unit}: null not defined ({group}: {have}, need {need})", file=sys.stderr
        )
        return [row]
    label = f"silence-scan/v{doc['version']}/{unit}"
    rng = np.random.default_rng(zlib.crc32(label.encode()))
    null = dimorphism._null_rates(
        label,
        n,
        lambda: dimorphism._matched_draw(rng, key, pool, tested),
        lambda idx: [float(np.mean(mean_count(idx)))],
        dimorphism._partial(checkpoint, job),
        meta,
    )[:, 0]
    row.update(
        draws=int(null.size),
        null_mean=float(null.mean()),
        p=p_lower(float(np.mean(counts)), null),
    )
    return [row]


def scan(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    doc: dict,
    stim: np.ndarray,
    motor: int,
    base: np.ndarray,
    workers: int = 1,
    checkpoint: Path | None = None,
) -> dict:
    """Base arms, candidates, screen and confirmation, in the order the lock fixes.

    Returns the tables of each stage and the verdict. `run` resolves the frozen names
    and checks the lock; tests call this with a small graph.
    """
    protocol = doc["protocol"]
    W = sim.network(neurons, edges, sim.Params())
    max_spikes = doc["base_arm"]["stop_if_max_spikes_at_most"]
    meta = {"version": doc["version"], "sha256": doc["content_sha256"]}
    out = {"version": doc["version"]}

    base_counts, results = _arm(W, stim, motor, base, _seeds(doc["screen"]), protocol)
    out["base_screen"] = base_counts
    if no_residual(base_counts, max_spikes):
        out["verdict"] = "no_residual: screen seeds"
        return out
    active = np.zeros(len(neurons), dtype=bool)
    active[dimorphism.responders(results, stim)] = True
    exclude = np.concatenate([stim, [motor], base])
    cand = candidates(
        neurons, edges, motor, active, exclude, doc["candidates"]["min_weight"]
    )
    units = dict(zip(cand["unit"], cand["neurons"], strict=True))
    print(f"silence-scan: {len(units)} candidate units", file=sys.stderr)
    screen_ckpt = (
        checkpoint.with_name(checkpoint.name + ".screen") if checkpoint else None
    )
    rows = dimorphism._map_jobs(
        _screen_job,
        [(u,) for u in units],
        workers,
        (W, stim, motor, base, units, doc),
        screen_ckpt,
        {**meta, "stage": "screen"},
    )
    fraction = doc["screen"]["pass_fraction_of_base"]
    screen = cand.drop(columns="neurons").merge(
        pd.DataFrame(rows, columns=["unit", "counts"]), on="unit"
    )
    screen["mean"] = screen["counts"].map(np.mean)
    screen["passes"] = screen["counts"].map(
        lambda c: screen_pass(base_counts, c, fraction)
    )
    out["screen"] = screen
    passed = screen.loc[screen["passes"], "unit"].tolist()
    m = len(passed)
    out["m"] = m
    print(f"silence-scan: {m} units pass the screen: {passed}", file=sys.stderr)

    confirm_base, results = _arm(W, stim, motor, base, _seeds(doc["confirm"]), protocol)
    out["base_confirm"] = confirm_base
    if no_residual(confirm_base, max_spikes):
        out["verdict"] = "no_residual: confirm seeds"
        return out
    if m == 0:
        out["confirm"] = pd.DataFrame(columns=["unit", "p", "counts", "contributes"])
        out["verdict"] = verdict(out["confirm"], 0)
        return out
    pool = np.zeros(len(neurons), dtype=bool)
    pool[dimorphism.responders(results, stim)] = True
    pool[exclude] = False
    if doc["confirm"].get("pool_excludes_screen_passes"):
        # v2: a draw for one pass never silences another pass (see supersedes in the lock)
        pool[np.concatenate([units[u] for u in passed])] = False
    key = (
        neurons["superclass"].fillna("none").astype(str)
        + "/"
        + neurons["sign"].astype(str)
    ).to_numpy()
    c = doc["confirm"]
    n = n_draws(m, c["min_draws"], c["draws_per_test"])
    rows = dimorphism._map_jobs(
        _confirm_job,
        [(u,) for u in passed],
        workers,
        (W, stim, motor, base, units, doc, key, pool, n),
        checkpoint,
        {**meta, "stage": "confirm", "m": m, "draws": n},
    )
    confirm = decide(pd.DataFrame(rows), m, c["alpha"], max_spikes)
    out["confirm"] = confirm
    out["verdict"] = verdict(confirm, m)
    return out


def run(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    workers: int = 1,
    checkpoint: Path | None = None,
) -> dict:
    """The frozen scan on MaleCNS at the default parameters."""
    doc = assert_matches_code()
    protocol = doc["protocol"]
    if abs(sim.Params().w_syn - protocol["w_syn"]) > 1e-12:
        raise ScanError("run refuses a parameter other than the default")

    def idx(query, expect):
        got = data.resolve(neurons, query)
        if got.size != expect:
            raise ScanError(f"{query} has {got.size} neurons, the lock says {expect}")
        return got

    stim = idx(protocol["stimulus"], protocol["stimulus_n"])
    motor = int(idx(protocol["motor"], protocol["motor_n"])[0])
    base = idx(protocol["base_silence"], protocol["base_silence_n"])
    return scan(neurons, edges, doc, stim, motor, base, workers, checkpoint)
