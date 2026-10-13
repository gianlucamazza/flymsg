"""Embodiment commands: the decoded jump, the closed loop, their frozen locks, and the
MANC muscle of each motor neuron."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import (
    behavior,
    data,
    jump,
    jump3d_lock,
    loop,
    managed,
    manc_muscles,
    manifest,
    sim,
)
from flymsg.cli.common import stamp


def cmd_jump(a, neurons, edges):
    """M1: simulate, decode the motor neuron's spikes with an engineered gain, move a body."""
    from flymsg.embodiment import Provenance

    started = datetime.now(UTC)
    stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.sim]))
    motor = data.resolve(neurons, a.motor)
    if motor.size != 1:
        sys.exit(f"flymsg: {a.motor} is {motor.size} neurons; the decoder reads one")
    silence = (
        np.concatenate([data.resolve(neurons, q) for q in a.silence])
        if a.silence
        else None
    )
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    r = sim.run(
        W, stim, a.rate, a.duration, a.stim_ms, p, a.seed, silence=silence, trace=motor
    )
    steps = np.flatnonzero(r.traced[:, 0])
    info = manifest.dataset_info(a.dataset, a.data, neurons, edges)
    digest = info["files"]["edges.parquet"]["sha256"]
    git = manifest.git_info()
    out = jump.run_jump(
        steps,
        body_id=int(neurons["bodyId"].iat[motor[0]]),
        gain_n=a.gain_n,
        mass_kg=a.mass_kg,
        duration_us=round(a.duration * 1000),
        provenance=Provenance(
            f"malecns {info.get('release', '')}".strip(),
            digest,
            git.get("commit") or "unknown",
            a.seed,
        ),
    )
    print(out["note"])
    print(
        f"{a.motor}: {out['spikes']} spikes; takeoff "
        f"{'none' if out['takeoff_ms'] is None else f'{out["takeoff_ms"]:.1f} ms'}; "
        f"max height {1000 * out['max_height_m']:.2f} mm"
    )
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "trajectory.json").write_text(json.dumps(out))
    stamp(
        a.out,
        "jump",
        a,
        neurons,
        edges,
        {
            "sim": list(a.sim),
            "silence": list(a.silence or []),
            "motor": a.motor,
            "gain_n": a.gain_n,
            "mass_kg": a.mass_kg,
            "rate": a.rate,
            "duration": a.duration,
            "stim_ms": a.stim_ms,
            "decoder": jump.ENGINEERED,
        },
        {"seed": a.seed},
        started,
        extra={"label": "exploratory", "note": jump.NOTE},
    )
    print(f"-> {a.out / 'trajectory.json'}")


def cmd_loop(a, neurons, edges):
    """M2: closed loop with its three controls, same seed, engineered transducer and decoder."""
    started = datetime.now(UTC)
    stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.sim]))
    motor = data.resolve(neurons, a.motor)
    if motor.size != 1:
        sys.exit(f"flymsg: {a.motor} is {motor.size} neurons; the decoder reads one")
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    kw = {
        "looming": loop.Looming(a.radius_m, a.distance_m, a.speed_m_s),
        "transducer": loop.Transducer(a.transducer_gain, a.max_rate_hz),
        "decoder_gain_n": a.gain_n,
        "mass_kg": a.mass_kg,
        "duration_ms": a.duration,
        "seed": a.seed,
        "p": p,
    }
    runs = {
        m: loop.run_loop(W, stim, int(motor[0]), mode=m, **kw)
        for m in ("closed", "disconnected", "shuffled")
    }
    runs["replay"] = loop.run_loop(
        W,
        stim,
        int(motor[0]),
        mode="replay",
        replay_counts=runs["closed"]["input_counts"],
        **kw,
    )
    summary = {}
    for mode, r in runs.items():
        lifted = np.flatnonzero(r["height_m"] > 0)
        summary[mode] = {
            "motor_spikes": int(r["motor_spikes"].sum()),
            "input_kicks": int(r["input_counts"].sum()),
            "takeoff_ms": float(r["t_ms"][lifted[0]]) if lifted.size else None,
            "max_height_m": float(r["height_m"].max()),
        }
        print(f"{mode:>12}: {summary[mode]}")
    same = np.array_equal(
        runs["replay"]["motor_spikes"], runs["closed"]["motor_spikes"]
    )
    differ = int(
        (runs["closed"]["input_counts"] != runs["disconnected"]["input_counts"])
        .any(axis=1)
        .sum()
    )
    print(f"replay reproduces the closed loop's motor spikes: {same}")
    print(f"neural steps whose input differs between closed and disconnected: {differ}")
    print(jump.NOTE)
    a.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        a.out / "loop.npz",
        **{
            f"{m}_{k}": v
            for m, r in runs.items()
            for k, v in r.items()
            if isinstance(v, np.ndarray) and k != "input_counts"
        },
    )
    (a.out / "loop.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "replay_matches": same,
                "input_steps_differing": differ,
            },
            indent=1,
        )
    )
    stamp(
        a.out,
        "loop",
        a,
        neurons,
        edges,
        {
            "sim": list(a.sim),
            "motor": a.motor,
            "radius_m": a.radius_m,
            "distance_m": a.distance_m,
            "speed_m_s": a.speed_m_s,
            "transducer_gain": a.transducer_gain,
            "max_rate_hz": a.max_rate_hz,
            "gain_n": a.gain_n,
            "mass_kg": a.mass_kg,
            "duration": a.duration,
            "decoder": jump.ENGINEERED,
        },
        {"seed": a.seed},
        started,
        extra={"label": "exploratory", "note": jump.NOTE},
    )
    print(f"-> {a.out}")


def cmd_behavior(a, neurons, edges):
    """The frozen one-bit loop. No flag chooses another weight, seed, or body."""
    started = datetime.now(UTC)
    doc = behavior.assert_matches_code()
    protocol = doc["protocol"]
    last = protocol["seed0"] + protocol["seeds"] - 1
    print(
        f"behavior v{doc['version']}: closed loop,"
        f" w_syn={protocol['w_syn']} th_jump={protocol['th_jump']},"
        f" seeds {protocol['seed0']}-{last}"
    )
    report, replay = behavior.run_loop(neurons, edges)
    print(report.to_string(index=False))
    text = behavior.verdict(report)
    print(text)
    print("reported rows do not decide and are not a retune")
    out = managed.output(a, Path("runs/behavior"))
    out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "report.csv", index=False)
    np.savez_compressed(out / "replay.npz", **replay)
    stamp(
        out,
        "behavior --run",
        a,
        neurons,
        edges,
        {
            "w_syn": protocol["w_syn"],
            "th_jump": protocol["th_jump"],
            "behavior_version": doc["version"],
            "behavior_sha256": doc["content_sha256"],
            "checks": list(doc["decides"]),
            "rate_hz": protocol["rate_hz"],
            "stim_ms": protocol["stim_ms"],
            "duration_ms": protocol["duration_ms"],
        },
        {"seeds": protocol["seeds"], "seed0": protocol["seed0"]},
        started,
        extra={"verdict": text, "replay": os.fspath(out / "replay.npz")},
    )
    print(f"report -> {out / 'report.csv'}")


def cmd_jump3d(a, neurons, edges):
    """The frozen TTM-driven jump of the NeuroMechFly body (issues #90, #94)."""
    started = datetime.now(UTC)
    doc = jump3d_lock.assert_matches_code()
    print(jump3d_lock.summary(doc))
    out = jump3d_lock.run(neurons, edges)
    path = managed.output(
        a, Path("runs/jump3d") / f"v{doc['version']}"
    )  # never overwrite
    path.mkdir(parents=True, exist_ok=True)
    out["table"].to_json(path / "seeds.json", orient="records", indent=2)
    text = out["table"].to_string(index=False) + f"\nverdict: {out['verdict']}"
    print(text)
    (path / "report.txt").write_text(text + "\n")
    n = doc["neural"]
    stamp(
        path,
        "jump3d --run",
        a,
        neurons,
        edges,
        {
            "jump3d_version": doc["version"],
            "jump3d_sha256": doc["content_sha256"],
            "rate_hz": n["rate_hz"],
            "stim_ms": n["stim_ms"],
            "body": "flygym 2.1.0 NeuroMechFly",
        },
        {"all": list(n["seeds"])},
        started,
        extra={"verdict": out["verdict"]},
    )
    print(f"report -> {path / 'report.txt'}")


def cmd_muscles(a, neurons, edges):
    """MANC's muscle per MaleCNS motor neuron (Cheong et al. 2024, Supplementary file 3,
    CC BY 4.0, fetched into data/raw/manc on first use). No row reaches a body actuator."""
    supp3 = pd.read_csv(manc_muscles.fetch(a.data))
    ann = pd.read_feather(
        a.data / "raw" / data.RAW["annotations"], columns=["bodyId", "mancType"]
    )
    motor = neurons.loc[neurons["superclass"] == "vnc_motor", ["bodyId", "type"]]
    table = manc_muscles.by_type(supp3)
    joined = manc_muscles.join(motor.merge(ann, on="bodyId", how="left"), table)
    out = a.data / "motor"
    out.mkdir(exist_ok=True)
    table.to_parquet(out / "manc_types.parquet")
    joined.to_parquet(out / "muscles.parquet")
    print(manc_muscles.summary(joined).to_string())
    muscle = joined[joined["status"] == "muscle"]
    print(
        f"{muscle['certainty_max'].notna().sum()} of {len(muscle)} neurons with a muscle "
        "have a published match certainty"
    )
    region = joined[joined["status"] == "region"]
    print(region.groupby("target").size().to_string())
    for status, g in joined[~joined["status"].isin(["muscle", "region"])].groupby(
        "status"
    ):
        names = ", ".join(sorted(g["mancType"].dropna().unique()))
        print(f"{status}: {len(g)} neurons" + (f" ({names})" if names else ""))
    print(f"source: {manc_muscles.SOURCE} ({manc_muscles.LICENSE})")
    print(f"-> {out / 'manc_types.parquet'}, {out / 'muscles.parquet'}")
