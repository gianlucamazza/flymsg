"""Managed, explicitly synthetic NeuroMechFly/optics fixture; no animal prediction.

The named fixture freezes the test-only registration, four optical axes, two-cell
chain, coverage-to-rate function and torque decoder of test_flygym_body. A config
cannot relabel these components measured or supply executable Python.
"""

from __future__ import annotations

import json
import resource
import time
from dataclasses import asdict
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import closedloop, optics, pose, prereg, runstore, sim
from flymsg.embodiment import Clock, ContractError, integer
from flymsg.runtime import CpuRuntime

CONFIG_SCHEMA = "flymsg.closedloop-experiment/v1"
FIXTURE = "nmf-optics-chain/v1"
EVIDENCE = {
    "registration": "synthetic",
    "transducer": "engineered",
    "motor_map": "synthetic",
    "body": "engineered",
}
TTM = tuple(
    f"nmf/{side}_coxa-{side}_trochanterfemur-pitch-motor" for side in ("lm", "rm")
)
NOTE = "Synthetic engineering fixture: two invented neurons, test-only eye registration and torque decoder; no biological claim."


def load(path: Path) -> dict:
    cfg = prereg.load_yaml(path.read_text())
    if not isinstance(cfg, dict) or set(cfg) != {
        "schema",
        "fixture",
        "mode",
        "seed",
        "duration_us",
        "clock",
        "arms",
        "checkpoint_every_us",
    }:
        raise ContractError("closedloop config has missing or unknown fields")
    if cfg["schema"] != CONFIG_SCHEMA or cfg["fixture"] != FIXTURE:
        raise ContractError("unsupported closedloop config schema or fixture")
    closedloop.require(EVIDENCE, cfg["mode"])
    integer(cfg["seed"], "seed")
    integer(cfg["duration_us"], "duration_us", 1)
    integer(cfg["checkpoint_every_us"], "checkpoint_every_us", 1)
    if not isinstance(cfg["clock"], dict) or set(cfg["clock"]) != set(asdict(Clock())):
        raise ContractError("clock needs neural_us, body_us, control_us and latency_us")
    clock = Clock(**cfg["clock"])
    clock.validate()
    if clock.neural_us != 100 or clock.body_us % 100:
        raise ContractError("fixture uses the unchanged 100 us neural and physics tick")
    if (
        cfg["duration_us"] % clock.control_us
        or cfg["checkpoint_every_us"] % clock.control_us
    ):
        raise ContractError(
            "duration and checkpoint period must be on the control grid"
        )
    if not isinstance(cfg["arms"], list) or cfg["arms"] != list(closedloop.ARMS):
        raise ContractError(f"fixture arms must be {list(closedloop.ARMS)} in order")
    return cfg


def inputs(config: Path) -> dict[str, Path]:
    dist = metadata.distribution("flygym")
    return {
        "config": config,
        **{
            str(p): Path(dist.locate_file(p))
            for p in dist.files
            if str(p).startswith("flygym/assets/")
        },
    }


def optical_fixture():
    columns_doc = {
        "side": ["L", "L", "R", "R"],
        "p": [0, 1, 0, 1],
        "q": [0, 0, 0, 0],
        "azimuth_deg": [-10.0, -40.0, 10.0, 40.0],
        "elevation_deg": [0.0, 10.0, 0.0, 10.0],
    }
    cols = optics.Columns.from_frame(
        pd.DataFrame(columns_doc), runstore.digest(columns_doc)
    )
    reg = pose.Registration(
        pose.Pose("body", "eyemap", (0.0, 0.0, 0.0), pose.IDENTITY),
        "synthetic identity; not measured",
    )
    spheres = (optics.Sphere("loom", (0.01, 0.0, 0.0008), 0.002, (-0.2, 0.0, 0.0)),)
    return closedloop.optical(cols, reg, pose.flygym_eye_mounts(), spheres, 8.23)


def runtime(cfg, silenced=False):
    clock = Clock(**cfg["clock"])
    edges = pd.DataFrame({"pre": [0], "post": [1], "weight": [400]})
    p = sim.Params()
    return CpuRuntime(
        sim.weight_matrix(edges, np.ones(2, dtype=np.int8), 2, p.w_syn),
        np.array([0]),
        steps=cfg["duration_us"] // clock.neural_us,
        kicks=np.zeros((0, 1), dtype=np.int64),
        p=p,
        per_bin=clock.control_us // clock.neural_us,
        trace=np.array([1]),
        silence=np.array([1]) if silenced else None,
    )


def run(cfg: dict, config_path: Path, out: Path) -> Path:
    from flymsg.flygym_body import FlyGymBody

    paths = inputs(config_path)
    identity = runstore.execution(
        "closedloop", cfg, {"fixture": FIXTURE, "note": NOTE}, paths
    )
    if load(config_path) != cfg:
        raise ContractError("config changed after validation")
    with runstore.Run(out, identity) as execution:
        if execution.completed:
            print(f"verified completed execution {execution.id}: {execution.output}")
            return execution.output
        body = FlyGymBody()
        stimulus, optical_hash = optical_fixture()
        actuators = tuple(body.actuators[n] for n in TTM)
        clock = Clock(**cfg["clock"])
        provenance = pose.Provenance(
            "synthetic two-cell chain",
            runstore.digest({"weight": 400}),
            identity["source"]["commit"],
            cfg["seed"],
        )
        records, metrics = {}, {}
        for arm in cfg["arms"]:
            ticks = []
            started = time.perf_counter()
            record = closedloop.run(
                runtime(cfg, arm == "silenced"),
                body,
                input_ids=(1,),
                traced_ids=(2,),
                stimulus=stimulus,
                transducer=lambda s: np.array([400.0 + 4000.0 * max(s)]),
                decoder=lambda spikes: tuple(
                    (a, 1.5e-7 * len(spikes)) for a in actuators
                ),
                compiled=body.compiled,
                clock=clock,
                duration_us=cfg["duration_us"],
                arm=arm,
                mode=cfg["mode"],
                evidence=EVIDENCE,
                provenance=provenance,
                optics_config_sha256=optical_hash,
                run_identity_sha256=execution.id,
                silenced_ids=(2,) if arm == "silenced" else (),
                replay=records.get("intact") if arm == "replay" else None,
                checkpoint_dir=execution.root / "checkpoints" / arm,
                checkpoint_every_us=cfg["checkpoint_every_us"],
                tick_wall_s=ticks,
            )
            wall = time.perf_counter() - started
            records[arm] = record
            (execution.output / f"{arm}.json").write_text(record.to_json() + "\n")
            metrics[arm] = {
                "wall_s": wall,
                "new_ticks": len(ticks),
                "total_ticks": len(record.ticks),
                "new_simulated_s_per_wall_s": len(ticks) * clock.body_us / 1e6 / wall,
                "tick_wall_ms": {
                    f"p{p}": float(np.percentile(ticks, p) * 1000) if ticks else None
                    for p in (50, 95, 99, 100)
                },
                "input_events": sum(
                    sum(sum(row) for row in t.input_counts) for t in record.ticks
                ),
                "spikes": sum(len(t.spikes) for t in record.ticks),
            }
        closedloop.replay_parity(records["intact"], records["replay"])
        intact, disconnected = records["intact"], records["disconnected"]
        summary = {
            "label": "synthetic",
            "note": NOTE,
            "evidence": EVIDENCE,
            "replay_spikes_identical": True,
            "pose_changes_later_optics": any(
                a.stimulus != b.stimulus
                for a, b in zip(intact.ticks, disconnected.ticks, strict=True)
            ),
            "silenced_spikes": metrics["silenced"]["spikes"],
            "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * 1024,
            "metrics": metrics,
        }
        runstore.atomic_json(execution.output / "summary.json", summary)
        execution.stamp(
            command="closedloop",
            config=cfg,
            seeds={"seed": cfg["seed"]},
            dataset={"name": "synthetic", "files": {}},
            extra={"label": "exploratory", "note": NOTE, "evidence": EVIDENCE},
        )
        runstore.verify_execution(identity, paths)
        execution.finalize()
        print(json.dumps(summary, indent=2))
        print(f"-> {execution.output}")
        return execution.output
