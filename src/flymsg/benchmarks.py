"""Held-out benchmark manifest. The YAML file is the lock.

`summary` only prints it. `score` runs the frozen confirmatory case and the
reported case at the scored corner. It does not edit the manifest or the v4 battery.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, prereg, sim, validate

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "benchmarks.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "c370092a2236c0485e063f94e654eb8ede44415a03dee5c27f765dd478ceb3dd",
}


class BenchmarkError(ValueError):
    """The benchmark manifest drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return prereg.load_yaml(path.read_text(encoding="utf-8"))


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    """Refuse a manifest whose locked fields changed without a new version."""
    doc = load() if doc is None else doc
    version = doc.get("version")
    if version not in VERSION_HASHES:
        raise BenchmarkError(f"benchmark version {version} is not in VERSION_HASHES")
    digest = content_hash(doc)
    if digest != VERSION_HASHES[version]:
        raise BenchmarkError("benchmark manifest changed without a bump")
    if doc.get("content_sha256") != digest:
        raise BenchmarkError("content_sha256 does not match the manifest")
    return doc


def assert_matches_code(doc: dict | None = None) -> dict:
    """The scored bar is criterion v4, and the calibration list is the live battery."""
    doc = assert_locked() if doc is None else doc
    ends = doc["endpoints"]
    expected = {
        "min_spikes": validate.MIN_SPIKES,
        "min_seed_share_num": 2,
        "min_seed_share_den": 3,
        "specificity": float(validate.SPECIFICITY),
        "margin_hz": float(validate.MARGIN_HZ),
        "max_persistent": validate.MAX_PERSISTENT,
        "rate_hz": float(validate.RATE_HZ),
        "stim_ms": float(validate.STIM_MS),
        "duration_ms": float(validate.DURATION_MS),
        "seeds": 3,
        "seed0": 0,
        "control_seed": 0,
    }
    for key, live in expected.items():
        if ends[key] != live:
            raise BenchmarkError(
                f"endpoints.{key} is {ends[key]}, live code has {live}"
            )
    calibration = [case.name for case in validate.CASES] + ["bitter feeding"]
    if doc["partition"]["calibration"] != calibration:
        raise BenchmarkError("calibration partition is not the live v4 battery")
    held = {doc["confirmatory"]["stimulus"], doc["reported"]["stimulus"]}
    named = {case.stim for case in validate.CASES if isinstance(case.stim, str)}
    overlap = held & named
    if overlap:
        raise BenchmarkError(
            f"held-out stimuli are already calibration cases: {overlap}"
        )
    corner = doc["sensitivity"]["scored"]
    if (
        abs(corner["w_syn"] - sim.Params.w_syn) > 1e-12
        or corner["th_jump"] != sim.Params.th_jump
    ):
        raise BenchmarkError("scored corner is not the simulator default")
    return doc


def summary(doc: dict | None = None) -> str:
    """The frozen confirmatory case. No simulation has been run from this manifest."""
    doc = assert_matches_code() if doc is None else doc
    case = doc["confirmatory"]
    corner = doc["sensitivity"]["scored"]
    checks = ", ".join(doc["endpoints"]["checks"])
    return (
        f"benchmarks v{doc['version']}: {case['stimulus']} -> {case['target']} "
        f"({checks}); scored corner w_syn {corner['w_syn']} th_jump {corner['th_jump']}; "
        f"seeds {doc['endpoints']['seed0']}-{doc['endpoints']['seed0'] + doc['endpoints']['seeds'] - 1}; "
        "scored run 2026-10-11 confirmatory FAIL"
    )


def _indices(neurons: pd.DataFrame, query: str, expect: int, label: str) -> np.ndarray:
    idx = data.resolve(neurons, query)
    if idx.size != expect:
        raise BenchmarkError(
            f"{label} {query} has {idx.size} neurons, the manifest says {expect}"
        )
    return idx


def _jobs(doc: dict) -> list[tuple]:
    """Confirmatory first, then reported. That order fixes the shared control draws."""
    conf = doc["confirmatory"]
    reported = doc["reported"]
    return [
        (
            conf["id"],
            conf["stimulus"],
            [conf["target"]],
            conf["stimulus_n"],
            [conf["target_n"]],
            True,
        ),
        (
            reported["id"],
            reported["stimulus"],
            list(reported["targets"]),
            reported["stimulus_n"],
            list(reported["target_n"]),
            False,
        ),
    ]


def score(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    p: sim.Params | None = None,
) -> pd.DataFrame:
    """Positive, specific and stability for the frozen cases. No order, dose or retune.

    The control draw uses `control_seed` once and is not reseeded between cases.
    A reported row does not decide. Counts that differ from the manifest abort
    before the network is built.
    """
    doc = assert_matches_code()
    p = sim.Params() if p is None else p
    corner = doc["sensitivity"]["scored"]
    if abs(p.w_syn - corner["w_syn"]) > 1e-12 or p.th_jump != corner["th_jump"]:
        raise BenchmarkError("held-out score uses only the scored corner")
    ends = doc["endpoints"]
    seeds, seed0 = ends["seeds"], ends["seed0"]
    jobs = []
    for name, stim_name, targets, stim_n, target_ns, decides in _jobs(doc):
        stim = _indices(neurons, stim_name, stim_n, "stimulus")
        for target, n in zip(targets, target_ns, strict=True):
            _indices(neurons, target, n, "target")
        jobs.append((name, stim, targets, decides))
    W = sim.network(neurons, edges, p)
    rng = np.random.default_rng(ends["control_seed"])
    need = int(np.ceil(validate.MIN_SEED_SHARE * seeds))
    rows = []
    for name, stim, targets, decides in jobs:
        case = validate.Case(name, "", targets, "")
        target_idx = np.concatenate([data.resolve(neurons, t) for t in targets])
        control = validate.control_idx(neurons, edges, stim, target_idx, rng)
        pos, persistent = validate.respond(
            W, neurons, stim, targets, p, seeds, seed0=seed0
        )
        ctrl, _ = validate.respond(W, neurons, control, targets, p, seeds, seed0=seed0)
        for target in targets:
            rows += [
                (*row, decides)
                for row in validate._response_rows(
                    case, target, pos[target], ctrl[target], seeds, need
                )
            ]
        rows.append((*validate._stability_row(case, persistent), decides))
    return pd.DataFrame(
        rows,
        columns=[
            "case",
            "kind",
            "subject",
            "value",
            "note",
            "latency_ms",
            "passed",
            "decides",
        ],
    )


def verdict(report: pd.DataFrame) -> str:
    """The confirmatory case. Reported rows are named and do not rescue it."""
    deciding = report.loc[report["decides"]]
    ok = bool(len(deciding) and deciding["passed"].all())
    name = deciding["case"].iloc[0] if len(deciding) else "confirmatory"
    return f"confirmatory {name}: {'PASS' if ok else 'FAIL'}"
