"""One-bit looming-jump protocol. The YAML file is the lock.

`summary` prints it. `run_loop` executes the frozen closed loop and does not
edit the protocol, criterion v4, or N1.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, prereg, sim, validate

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
    """The scored bar is the live default model."""
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
    """The frozen task and the recorded verdict. Printing it does not simulate."""
    doc = assert_matches_code() if doc is None else doc
    task = doc["task"]
    checks = ", ".join(doc["decides"])
    return (
        f"behavior v{doc['version']}: {task['id']}; "
        f"{task['stimulus']} -> {task['motor']} ({checks}); "
        f"claim {doc['claim']['status']}; "
        f"dt {doc['coupling']['neural_dt_ms']} ms; no body step; "
        "calibration feasibility FAIL: silence"
    )


def _idx(neurons: pd.DataFrame, query: str, expect: int, label: str) -> np.ndarray:
    idx = data.resolve(neurons, query)
    if idx.size != expect:
        raise BehaviorError(
            f"{label} {query} has {idx.size} neurons, the protocol says {expect}"
        )
    return idx


def _spike_steps(result: sim.Result, column: int) -> np.ndarray:
    if result.traced is None:
        raise BehaviorError("the run did not record spikes")
    return np.flatnonzero(result.traced[:, column])


def _still_firing(result: sim.Result, t0_ms: float) -> int:
    """Neurons with at least one spike from t0_ms to the end of the run."""
    return int((result.rate(t0_ms) > 0).sum())


def _simulate(W, stim, rate, duration, stim_ms, seed, trace, silence=None, kicks=None):
    """One default-parameter run. An explicit kick matrix replaces `stim_ms`."""
    return sim.run(
        W,
        stim,
        rate,
        duration,
        None if kicks is not None else stim_ms,
        sim.Params(),
        seed,
        silence=silence,
        kicks=kicks,
        trace=trace,
    )


def _row(arm, check, seed, value, note, passed, decides):
    return {
        "arm": arm,
        "check": check,
        "seed": seed,
        "value": value,
        "note": note,
        "passed": passed,
        "decides": decides,
    }


def assess(doc: dict, records: list[dict]) -> pd.DataFrame:
    """Apply the frozen checks to one record per seed. No simulation."""
    protocol = doc["protocol"]
    if len(records) != protocol["seeds"]:
        raise BehaviorError(
            f"the protocol scores {protocol['seeds']} seeds, got {len(records)}"
        )
    dt = float(protocol["dt_ms"])
    deadline = float(doc["decides"]["jump"]["deadline_ms"])
    need = int(doc["decides"]["jump"]["min_seed_share_num"])
    max_spikes = int(doc["decides"]["silence"]["max_spikes"])
    full = int(protocol["stim_ms"] / dt)
    rows = []
    on_time = 0
    feedback_ok = True
    silence_ok = True
    match_ok = True
    persistent = []
    jump_times = []
    for rec in records:
        seed = int(rec["seed"])
        step = rec["jump_step"]
        escaped = step is not None
        timely = escaped and step * dt <= deadline + 1e-9
        if timely:
            on_time += 1
        t_ms = None if step is None else step * dt
        if t_ms is not None:
            jump_times.append(t_ms)
        rows.append(
            _row(
                "closed",
                "jump",
                seed,
                t_ms if t_ms is not None else np.nan,
                "on time" if timely else "no on-time jump",
                bool(timely),
                False,
            )
        )
        if not escaped:
            feedback = True
            feedback_note = "no third spike; drive stays the open-loop window"
            expected_steps = full
        elif step >= full:
            feedback = rec["closed_stim_steps"] == full
            expected_steps = full
            feedback_note = "third spike at or after the open-loop window"
        else:
            expected_steps = step + 1
            feedback = rec["closed_stim_steps"] == expected_steps
            feedback_note = (
                f"stimulus steps {rec['closed_stim_steps']}, cut after step {step}"
            )
        feedback_ok = feedback_ok and feedback
        rows.append(
            _row(
                "closed",
                "feedback",
                seed,
                expected_steps,
                feedback_note,
                bool(feedback),
                False,
            )
        )
        if not escaped:
            matched = True
            match_note = "no jump"
        else:
            before = rec["open_spikes"][rec["open_spikes"] <= step]
            closed_before = rec["closed_spikes"][rec["closed_spikes"] <= step]
            matched = np.array_equal(before, closed_before)
            match_note = f"{before.size} spike steps through t_jump"
        match_ok = match_ok and matched
        rows.append(
            _row(
                "closed",
                "decoder_match",
                seed,
                np.nan,
                match_note,
                bool(matched),
                False,
            )
        )
        n_sil = int(np.asarray(rec["silence_spikes"]).size)
        drive_cut = int(rec["silence_stim_steps"]) != full
        sil_pass = n_sil <= max_spikes and not drive_cut
        silence_ok = silence_ok and sil_pass
        rows.append(
            _row(
                "silence",
                "silence",
                seed,
                n_sil,
                "drive cut" if drive_cut else "drive stays the open-loop window",
                bool(sil_pass),
                False,
            )
        )
        persistent.append(int(rec["persistent"]))
        rows.append(
            _row(
                "closed",
                "latency",
                seed,
                t_ms if t_ms is not None else np.nan,
                (
                    f"TTMn_R first {rec['first_ttmn_ms']:.1f} ms; "
                    f"DNp01(GF)_R first {rec['first_dnp_r_ms']:.1f} ms; "
                    f"DNp01(GF)_L first {rec['first_dnp_l_ms']:.1f} ms"
                ),
                False,
                False,
            )
        )
        rows.append(
            _row(
                "feedback_disabled",
                "order",
                seed,
                rec["first_dnp_r_ms"],
                (
                    "DNp01(GF)_R before TTMn_R"
                    if rec["first_dnp_r_ms"] < rec["first_ttmn_ms"]
                    else "DNp01(GF)_R not before TTMn_R"
                ),
                False,
                False,
            )
        )
        rows.append(
            _row(
                "closed",
                "stability",
                seed,
                rec["persistent"],
                "neurons still firing from 400 ms to 600 ms",
                False,
                False,
            )
        )
    rows.extend(
        [
            _row(
                "closed",
                "jump",
                "all",
                on_time,
                f"{on_time}/{len(records)} seeds on time; needs {need}",
                on_time >= need,
                True,
            ),
            _row(
                "closed",
                "feedback",
                "all",
                np.nan,
                "every seed that jumps cuts the drive after that spike",
                feedback_ok,
                True,
            ),
            _row(
                "silence",
                "silence",
                "all",
                np.nan,
                f"TTMn_R stays at or below {max_spikes} spikes and the drive is not cut",
                silence_ok,
                True,
            ),
            _row(
                "closed",
                "decoder_match",
                "all",
                np.nan,
                "TTMn_R spike steps through t_jump match the open loop",
                match_ok,
                True,
            ),
            _row(
                "closed",
                "stability",
                "all",
                float(np.mean(persistent)),
                f"mean neurons still firing from 400 ms; v4 limit "
                f"{doc['reported']['stability']['max_persistent']} does not decide",
                False,
                False,
            ),
            _row(
                "closed",
                "latency",
                "all",
                float(np.median(jump_times)) if jump_times else np.nan,
                "median t_jump_ms of seeds that reached three spikes; not a takeoff time",
                False,
                False,
            ),
        ]
    )
    return pd.DataFrame(rows)


def verdict(report: pd.DataFrame) -> str:
    """The four deciding rows. A reported row cannot change this sentence."""
    deciding = report[report["decides"].astype(bool)]
    failed = []
    for check in _DECIDES:
        rows = deciding[deciding["check"] == check]
        if len(rows) != 1:
            raise BehaviorError(f"deciding check {check} is missing")
        if not bool(rows["passed"].iloc[0]):
            failed.append(check)
    if not failed:
        return "calibration feasibility PASS"
    return "calibration feasibility FAIL: " + ", ".join(failed)


def run_loop(neurons: pd.DataFrame, edges: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """The frozen loop at the default parameters. Returns the report and the replay arrays."""
    doc = assert_matches_code()
    protocol = doc["protocol"]
    p = sim.Params()
    if abs(p.w_syn - protocol["w_syn"]) > 1e-12 or p.th_jump != protocol["th_jump"]:
        raise BehaviorError("run_loop refuses a parameter other than the default")
    task = doc["task"]
    stim = _idx(neurons, task["stimulus"], task["stimulus_n"], "stimulus")
    motor = _idx(neurons, task["motor"], task["motor_n"], "motor")
    command = _idx(neurons, task["command"], task["command_n"], "command")
    instances = [
        _idx(neurons, name, 1, "command")[0] for name in task["command_instances"]
    ]
    if set(instances) != set(command.tolist()):
        raise BehaviorError("command instances are not the giant-fiber pair")
    if not np.all(
        neurons["superclass"].iloc[stim].to_numpy() == task["stimulus_superclass"]
    ):
        raise BehaviorError("the stimulus superclass is not the protocol value")
    if not np.all(
        neurons["superclass"].iloc[motor].to_numpy() == task["motor_superclass"]
    ):
        raise BehaviorError("the motor superclass is not the protocol value")
    rate = float(protocol["rate_hz"])
    duration = float(protocol["duration_ms"])
    stim_ms = float(protocol["stim_ms"])
    dt = float(protocol["dt_ms"])
    full = int(stim_ms / dt)
    min_spikes = int(protocol["min_spikes"])
    trace = np.array([motor[0], instances[0], instances[1]], dtype=np.int64)
    W = sim.network(neurons, edges, p)
    started = time.perf_counter()
    records = []
    replay = {}
    for seed in range(protocol["seed0"], protocol["seed0"] + protocol["seeds"]):
        kicks = sim.poisson_kicks(seed, rate, dt, full, int(stim.size))
        opened = _simulate(W, stim, rate, duration, stim_ms, seed, trace, kicks=kicks)
        open_spikes = _spike_steps(opened, 0)
        if int(open_spikes.size) != int(opened.counts[:, motor[0]].sum()):
            raise BehaviorError("the motor trace does not match the binned counts")
        step = (
            int(open_spikes[min_spikes - 1]) if open_spikes.size >= min_spikes else None
        )
        if step is None or step >= full:
            closed = opened
            closed_steps = full
            closed_spikes = open_spikes
        else:
            closed_kicks = kicks[: step + 1]
            closed = _simulate(
                W,
                stim,
                rate,
                duration,
                stim_ms,
                seed,
                trace,
                kicks=closed_kicks,
            )
            closed_steps = int(closed_kicks.shape[0])
            closed_spikes = _spike_steps(closed, 0)
            if int(closed_spikes.size) != int(closed.counts[:, motor[0]].sum()):
                raise BehaviorError(
                    "the closed motor trace does not match the binned counts"
                )
        silenced = _simulate(
            W, stim, rate, duration, stim_ms, seed, trace, silence=command, kicks=kicks
        )
        silence_spikes = _spike_steps(silenced, 0)
        if int(silence_spikes.size) != int(silenced.counts[:, motor[0]].sum()):
            raise BehaviorError("the silence trace does not match the binned counts")
        if (
            silence_spikes.size >= min_spikes
            and int(silence_spikes[min_spikes - 1]) < full
        ):
            cut = int(silence_spikes[min_spikes - 1])
            silence_kicks = kicks[: cut + 1]
            silenced = _simulate(
                W,
                stim,
                rate,
                duration,
                stim_ms,
                seed,
                trace,
                silence=command,
                kicks=silence_kicks,
            )
            silence_spikes = _spike_steps(silenced, 0)
            if int(silence_spikes.size) != int(silenced.counts[:, motor[0]].sum()):
                raise BehaviorError(
                    "the silence trace does not match the binned counts"
                )
            silence_steps = int(silence_kicks.shape[0])
        else:
            silence_steps = full
        records.append(
            {
                "seed": seed,
                "jump_step": step,
                "closed_stim_steps": closed_steps,
                "open_spikes": open_spikes,
                "closed_spikes": closed_spikes,
                "silence_spikes": silence_spikes,
                "silence_stim_steps": silence_steps,
                "persistent": _still_firing(closed, 400.0),
                "first_ttmn_ms": float(opened.first_spike_ms[motor[0]]),
                "first_dnp_r_ms": float(opened.first_spike_ms[instances[0]]),
                "first_dnp_l_ms": float(opened.first_spike_ms[instances[1]]),
            }
        )
        sensory = np.array(kicks, copy=True)
        if step is not None and step < full:
            sensory[step + 1 :] = 0
        replay[f"seed{seed}_sensory"] = sensory
        replay[f"seed{seed}_ttmn_open"] = open_spikes
        replay[f"seed{seed}_ttmn_closed"] = closed_spikes
        replay[f"seed{seed}_ttmn_silence"] = silence_spikes
    report = assess(doc, records)
    elapsed = time.perf_counter() - started
    report = pd.concat(
        [
            report,
            pd.DataFrame(
                [
                    _row(
                        "closed",
                        "runtime_s",
                        "all",
                        elapsed,
                        "wall time of the closed loop, the open loop and the silence arm",
                        False,
                        False,
                    )
                ]
            ),
        ],
        ignore_index=True,
    )
    replay["elapsed_s"] = np.array([elapsed])
    return report, replay
