"""Exploratory configs and interventions, and the frozen intervention locks."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from flymsg import (
    intervention,
    managed,
    partner_followup,
    silence_scan,
    workbench,
)
from flymsg.cli.common import stamp


def cmd_experiment(a, neurons, edges):
    """Validate an exploratory config and, unless --check, run it into an immutable dir."""
    cfg = workbench.validate_config(workbench.load_config(a.config), neurons)
    digest = workbench.config_hash(cfg)
    print(
        f"config ok: {workbench.CONFIG_SCHEMA}, sha256 {digest[:16]}, label exploratory"
    )
    if a.check:
        return
    out = workbench.run(cfg, neurons, edges, a.root, a.data)
    print(pd.read_csv(out / "metrics.csv").to_string(index=False))
    print(f"-> {out}")


def _explore_config(a) -> dict:
    return {
        "source": a.source,
        "target": a.target,
        "paths": a.paths,
        "seeds": a.seeds,
        "seed0": a.seed0,
        "base_silence": list(a.silence or []),
    }


def cmd_explore(a, neurons, edges):
    """Exploratory: paths (anatomy), then silencing each intermediate type (simulation)."""
    started = datetime.now(UTC)
    if a.replay:
        saved = json.loads((a.replay / "manifest.json").read_text())["config"]
        cfg = {
            k: saved[k]
            for k in ("source", "target", "paths", "seeds", "seed0", "base_silence")
        }
    else:
        if not (a.source and a.target):
            sys.exit("flymsg: explore needs SOURCE and TARGET, or --replay DIR")
        cfg = _explore_config(a)
    result = intervention.explore(
        neurons,
        edges,
        cfg["source"],
        cfg["target"],
        paths=cfg["paths"],
        seeds=cfg["seeds"],
        seed0=cfg["seed0"],
        base_silence=cfg["base_silence"],
    )
    for row in result["anatomy"]:
        print(
            f"anatomy, path {row['path']}: {' -> '.join(row['types'])}  synapses {row['synapses']}"
        )
    for row in result["interventions"]:
        lo, hi = row["ci95_change_hz"]
        print(
            f"simulation (exploratory), silence {row['silenced']} ({row['neurons']}): "
            f"{row['mean_change_hz']:+.1f} Hz [{lo:+.1f}, {hi:+.1f}]"
        )
    print(result["note"])
    if result["governed_by"]:
        print(f"governed by {result['governed_by']}")
    if a.replay:
        saved = json.loads((a.replay / "explore.json").read_text())
        same = (
            saved["interventions"] == result["interventions"]
            and saved["anatomy"] == result["anatomy"]
        )
        print(
            "replay reproduces the saved contrast"
            if same
            else "replay DIFFERS from the saved contrast"
        )
        if not same:
            sys.exit(1)
        return
    out = (
        a.out
        / f"{a.source}-{a.target}".replace("/", "_")
        / workbench.config_hash(cfg)[:12]
    )
    if out.exists():
        sys.exit(f"flymsg: {out} exists; use --replay {out} to check it")
    out.mkdir(parents=True)
    (out / "explore.json").write_text(json.dumps(result, indent=1))
    stamp(
        out,
        "explore",
        a,
        neurons,
        edges,
        cfg,
        {"seed0": cfg["seed0"], "seeds": cfg["seeds"]},
        started,
        extra={"label": "exploratory"},
    )
    print(f"-> {out}")


def cmd_confirm(a, neurons, edges):
    """Run a registered intervention lock on fresh seeds against a matched null."""
    started = datetime.now(UTC)
    table = intervention.confirm(neurons, edges, a.lock, a.out, checkpoint=a.checkpoint)
    print(table.to_string(index=False))
    doc = intervention.load(a.lock)
    out = a.out / a.lock.stem / f"v{doc['version']}"
    stamp(
        out,
        "confirm",
        a,
        neurons,
        edges,
        {"lock": str(a.lock), "lock_sha256": doc["content_sha256"]},
        {"seed0": doc["seed0"], "seeds": doc["seeds"]},
        started,
        extra={"label": "preregistered"},
    )


def cmd_silence_scan(a, neurons, edges):
    """The frozen residual TTMn_R scan. No flag chooses another unit, seed, or weight."""
    started = datetime.now(UTC)
    doc = silence_scan.assert_matches_code()
    print(silence_scan.summary(doc))
    out = silence_scan.run(neurons, edges, a.workers, a.checkpoint)
    path = managed.output(
        a, Path("runs/silence-scan") / f"v{doc['version']}"
    )  # never overwrite a version
    path.mkdir(parents=True, exist_ok=True)
    lines = [
        f"base arm, screen seeds: {out['base_screen']}",
        f"base arm, confirm seeds: {out.get('base_confirm')}",
    ]
    for stage in ("screen", "confirm"):
        if stage in out:
            table = out[stage]
            table.to_csv(path / f"{stage}.csv", index=False)
            lines += [f"{stage}:", table.to_string(index=False)]
    lines.append(out["verdict"])
    text = "\n".join(lines)
    print(text)
    (path / "report.txt").write_text(text + "\n")
    protocol = doc["protocol"]
    stamp(
        path,
        "silence-scan --run",
        a,
        neurons,
        edges,
        {
            "w_syn": protocol["w_syn"],
            "th_jump": protocol["th_jump"],
            "scan_version": doc["version"],
            "scan_sha256": doc["content_sha256"],
            "rate_hz": protocol["rate_hz"],
            "stim_ms": protocol["stim_ms"],
            "duration_ms": protocol["duration_ms"],
            "m": out.get("m"),
        },
        {
            "screen": list(silence_scan._seeds(doc["screen"])),
            "confirm": list(silence_scan._seeds(doc["confirm"])),
        },
        started,
        extra={"verdict": out["verdict"]},
    )
    print(f"report -> {path / 'report.txt'}")


def cmd_partner_followup(a, neurons, edges):
    """The frozen residual partner follow-up (issue #76). No flag chooses a unit or seed."""
    started = datetime.now(UTC)
    doc = partner_followup.assert_matches_code()
    print(partner_followup.summary(doc))
    out = partner_followup.run(neurons, edges, a.workers, a.checkpoint)
    path = managed.output(
        a, Path("runs/partner-followup") / f"v{doc['version']}"
    )  # never overwrite
    path.mkdir(parents=True, exist_ok=True)
    out["left"].to_csv(path / "left.csv", index=False)
    drive = pd.DataFrame(
        [
            {"arm": arm, "counts": counts, "driven_spikes": out["driven_spikes"][arm]}
            for arm, counts in out["drive_arms"].items()
        ]
    )
    drive.to_csv(path / "drive.csv", index=False)
    out["null_draws"].to_csv(path / "null_draws.csv", index=False)
    d = out["drive"]
    lines = [
        f"left base arm (DNp01 silenced): {out['left_base']}",
        "left:",
        out["left"].to_string(index=False),
        f"left verdict: {out['left_verdict']}",
        "drive arms:",
        drive.to_string(index=False),
        f"pair null: draws {d['draws']}, mean {d['null_mean']:.3f}, p {d['p']:.6f}",
        f"drive verdict: {out['drive_verdict']}",
    ]
    text = "\n".join(lines)
    print(text)
    (path / "report.txt").write_text(text + "\n")
    stamp(
        path,
        "partner-followup --run",
        a,
        neurons,
        edges,
        {
            "w_syn": doc["model"]["w_syn"],
            "th_jump": doc["model"]["th_jump"],
            "followup_version": doc["version"],
            "followup_sha256": doc["content_sha256"],
            "left_rate_hz": doc["left"]["rate_hz"],
            "drive_rate_hz": doc["drive"]["rate_hz"],
        },
        {"all": list(partner_followup.seeds(doc))},
        started,
        extra={"left": out["left_verdict"], "drive": out["drive_verdict"]},
    )
    print(f"report -> {path / 'report.txt'}")
