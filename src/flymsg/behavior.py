"""One-bit looming-jump protocol. The YAML file is the lock.

`summary` only prints it. This version has no closed-loop runner.
"""

from __future__ import annotations

from pathlib import Path

from flymsg import prereg, sim, validate

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "behavior.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "8f7a9dd74355ed60fb156f4eda162c04a5bc9e3eb1e428320039c1b5931dab50",
}

_DECIDES = ("jump", "feedback", "silence", "decoder_match")


class BehaviorError(ValueError):
    """The behavior protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return prereg.load_yaml(path.read_text(encoding="utf-8"))


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def integer_multiple(step_s: float, dt_ms: float) -> bool:
    """True when a body step lasts an integer number of neural steps, at least one."""
    if step_s <= 0 or dt_ms <= 0:
        return False
    ratio = (step_s * 1000.0) / dt_ms
    if ratio < 1:
        return False
    return abs(ratio - round(ratio)) <= 1e-9


def assert_locked(doc: dict | None = None) -> dict:
    """Refuse a protocol whose locked fields changed without a new version."""
    doc = load() if doc is None else doc
    version = doc.get("version")
    if version not in VERSION_HASHES:
        raise BehaviorError(f"behavior version {version} is not in VERSION_HASHES")
    digest = content_hash(doc)
    if digest != VERSION_HASHES[version]:
        raise BehaviorError("behavior protocol changed without a bump")
    if doc.get("content_sha256") != digest:
        raise BehaviorError("content_sha256 does not match the protocol")
    return doc


def assert_matches_code(doc: dict | None = None) -> dict:
    """The scored bar is the live default model, and this stage cannot run."""
    doc = assert_locked() if doc is None else doc
    protocol = doc["protocol"]
    expected = {
        "min_spikes": validate.MIN_SPIKES,
        "min_seed_share_num": 2,
        "min_seed_share_den": 3,
        "rate_hz": float(validate.RATE_HZ),
        "stim_ms": float(validate.STIM_MS),
        "duration_ms": float(validate.DURATION_MS),
        "seeds": 3,
        "seed0": 0,
        "dt_ms": float(sim.Params.dt),
    }
    for key, live in expected.items():
        if protocol[key] != live:
            raise BehaviorError(
                f"protocol.{key} is {protocol[key]}, live code has {live}"
            )
    if abs(protocol["w_syn"] - sim.Params.w_syn) > 1e-12 or (
        protocol["th_jump"] != sim.Params.th_jump
    ):
        raise BehaviorError("protocol parameters are not the simulator default")
    if doc["coupling"]["neural_dt_ms"] != protocol["dt_ms"]:
        raise BehaviorError("coupling dt is not the protocol dt")
    looming = next(case for case in validate.CASES if case.name == "looming escape")
    claim = doc["claim"]
    if claim["case"] != looming.name or claim["status"] != "calibration_feasibility":
        raise BehaviorError("the task is not the looming calibration case")
    if claim["held_out"] is not False:
        raise BehaviorError("this loop is not a held-out generalization")
    if doc["task"]["stimulus"] != looming.stim:
        raise BehaviorError("the stimulus is not the looming case stimulus")
    if "DNp01" not in looming.targets or "TTMn" not in looming.targets:
        raise BehaviorError("the looming case lost DNp01 or TTMn")
    if doc["body"]["timestep_ms"] is not None or doc["body"]["name"] != "one-bit":
        raise BehaviorError("version 1 has no body integrator")
    if doc["controller"]["learned"] is not False:
        raise BehaviorError("a learned controller is not this protocol")
    if doc["flybody"]["selected"] is not False:
        raise BehaviorError("FlyBody is not the selected body")
    if doc["wiring"]["draw"] is not False or doc["wiring"]["shuffle_seed"] != 0:
        raise BehaviorError("N1 is not redrawn")
    if tuple(doc["decides"]) != _DECIDES:
        raise BehaviorError("the deciding checks changed")
    jump = doc["decides"]["jump"]
    if (
        jump["deadline_ms"] != protocol["stim_ms"]
        or jump["min_seed_share_num"] != protocol["min_seed_share_num"]
        or jump["min_seed_share_den"] != protocol["min_seed_share_den"]
    ):
        raise BehaviorError("the jump bar is not the v4 seed share inside the stimulus")
    silence = doc["decides"]["silence"]
    if (
        silence["max_spikes"] != protocol["min_spikes"] - 1
        or silence["drive_cut"] is not False
    ):
        raise BehaviorError("silence must keep TTMn_R under the jump bit")
    if (
        silence["seeds_allowed_to_jump"] != 0
        or silence["neurons_n"] != doc["task"]["command_n"]
    ):
        raise BehaviorError("silence does not cover the giant fiber")
    for name, row in doc["reported"].items():
        if row["decides"] is not False:
            raise BehaviorError(f"reported check {name} must not decide")
    if doc["reported"]["stability"]["max_persistent"] != validate.MAX_PERSISTENT:
        raise BehaviorError("the reported stability limit drifted from v4")
    if doc["reported"]["latency"]["scored_against_biology"] is not False:
        raise BehaviorError("latency is not a biological pass/fail")
    if (
        doc["prediction"]["status"] != "unverified"
        or doc["prediction"]["tests_animal"] is not False
    ):
        raise BehaviorError("the prediction is unverified model-side")
    flags = doc["flybody"]["legal_under_coupling"]
    steps = {
        "xml_timestep": doc["flybody"]["xml_timestep_s"],
        "walk_physics": doc["flybody"]["walk_physics_s"],
        "walk_control": doc["flybody"]["walk_control_s"],
        "flight_physics": doc["flybody"]["flight_physics_s"],
        "flight_control": doc["flybody"]["flight_control_s"],
    }
    for name, step in steps.items():
        legal = integer_multiple(step, protocol["dt_ms"])
        if flags[name] is not legal:
            raise BehaviorError(f"coupling flag {name} does not match the timestep")
    return doc


def summary(doc: dict | None = None) -> str:
    """The frozen task. No closed loop has been run from this protocol."""
    doc = assert_matches_code() if doc is None else doc
    task = doc["task"]
    checks = ", ".join(doc["decides"])
    return (
        f"behavior v{doc['version']}: {task['id']}; "
        f"{task['stimulus']} -> {task['motor']} ({checks}); "
        f"claim {doc['claim']['status']}; "
        f"dt {doc['coupling']['neural_dt_ms']} ms; no body step; not run"
    )
