"""Authored motor map. The YAML file is the lock.

Every walking actuator and both TTMn neurons have a row. A row can take a
command only when a published source names that motor neuron and that actuator
together. None does, so every row is unmapped and `command` refuses.
"""

from __future__ import annotations

from pathlib import Path

from flymsg import locks, prereg

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "motor_map.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "f8cde8f4f9e05d9373335ceee8e8d4b4fc62adc819af856442d894d10014c3f9",
}


class MotorMapError(ValueError):
    """The authored map drifted, or a command was requested for an unmapped row."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    """Refuse a map whose locked fields changed without a new version."""
    doc = load() if doc is None else doc
    locks.check(doc, VERSION_HASHES, MotorMapError, "motor map")
    if doc.get("authored") != "hypothesis":
        raise MotorMapError("the map is not marked as an authored hypothesis")
    if doc.get("body_sex") != "female" or doc.get("connectome_sex") != "male":
        raise MotorMapError("the sex record changed")
    if doc.get("compensation") is not False:
        raise MotorMapError("a sex compensation is not part of this map")
    names = [row["name"] for row in doc["actuators"]]
    if len(names) != 59 or len(set(names)) != 59:
        raise MotorMapError("the map does not list 59 actuators")
    neurons = [row["name"] for row in doc["neurons"]]
    if neurons != ["TTMn_L", "TTMn_R"]:
        raise MotorMapError("the map does not list TTMn_L and TTMn_R")
    known = set(doc["reasons"])
    for row in [*doc["actuators"], *doc["neurons"]]:
        if row["status"] != "unmapped":
            raise MotorMapError(f"{row['name']} is not unmapped")
        if row["reason"] not in known:
            raise MotorMapError(f"{row['name']} has an unknown reason")
    return doc


def command(name: str, doc: dict | None = None) -> None:
    """Refuse a torque. No published row names this actuator."""
    doc = assert_locked() if doc is None else doc
    rows = {row["name"]: row for row in [*doc["actuators"], *doc["neurons"]]}
    row = rows.get(name)
    if row is None:
        raise MotorMapError(f"{name} is not in the motor map")
    if row["status"] != "published_assignment":
        reason = doc["reasons"][row["reason"]]
        raise MotorMapError(f"{name} is {row['status']}: {reason}")
    raise MotorMapError(f"{name} has no torque")
