"""Held-out benchmark manifest. The YAML file is the lock. This module does not simulate."""

from __future__ import annotations

from pathlib import Path

from flymsg import prereg, sim, validate

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
        "held-out simulation has not been run"
    )
