"""Exploratory experiments and the run index (#27).

An experiment is a versioned YAML config (`flymsg.experiment/v1`): stimulus, silencing,
parameters, seeds and the targets to measure. `run` validates it, simulates, and writes
metrics and a run manifest into `runs/experiments/<config hash>/`, which it never
overwrites. Its label is always `exploratory`: a pre-registered or held-out result comes
only from a lock (`validation/*.yaml`), never from a config.

`index` lists every run manifest under the given roots with its label: declared in the
manifest, or for manifests written before labels existed, read from the command (a command
that runs a lock is pre-registered, the held-out benchmark is held-out) and from a recorded
verdict (FAIL or none is failed).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, prereg, sim

CONFIG_SCHEMA = "flymsg.experiment/v1"
LABELS = ("exploratory", "preregistered", "held-out", "failed")
# commands that execute a lock; their outputs are never exploratory
LOCKED = {
    "silence-scan --run": "preregistered",
    "behavior --run": "preregistered",
    "nulls": "preregistered",
    "wiring-null": "preregistered",
    "validate": "preregistered",
    "select-model": "preregistered",
    "benchmarks --run": "held-out",
    "benchmarks --corners": "held-out",
}
_REQUIRED = {
    "schema": str,
    "label": str,
    "stimulus": list,
    "targets": list,
    "rate_hz": float,
    "stim_ms": float,
    "duration_ms": float,
    "seed0": int,
    "seeds": int,
}
_OPTIONAL = {"silence": list, "w_syn": float, "th_jump": float, "note": str}


class ConfigError(ValueError):
    """An experiment config that cannot run as written."""


def load_config(path: Path) -> dict:
    return prereg.load_yaml(Path(path).read_text(encoding="utf-8"))


def validate_config(cfg: dict, neurons: pd.DataFrame | None = None) -> dict:
    """Refuse an unknown schema, a missing or mistyped field, an unknown key, a label other
    than exploratory, or (with `neurons`) a name the dataset does not have."""
    if cfg.get("schema") != CONFIG_SCHEMA:
        raise ConfigError(f"schema must be {CONFIG_SCHEMA}, not {cfg.get('schema')!r}")
    for key, kind in _REQUIRED.items():
        if key not in cfg:
            raise ConfigError(f"missing field {key!r}")
        value = cfg[key]
        if kind is float and isinstance(value, int) and not isinstance(value, bool):
            value = cfg[key] = float(value)
        if not isinstance(value, kind) or isinstance(value, bool):
            raise ConfigError(f"{key!r} must be {kind.__name__}")
    for key, kind in _OPTIONAL.items():
        if key in cfg:
            if kind is float and isinstance(cfg[key], int):
                cfg[key] = float(cfg[key])
            if not isinstance(cfg[key], kind):
                raise ConfigError(f"{key!r} must be {kind.__name__}")
    unknown = set(cfg) - set(_REQUIRED) - set(_OPTIONAL)
    if unknown:
        raise ConfigError(f"unknown field(s): {', '.join(sorted(unknown))}")
    if cfg["label"] != "exploratory":
        raise ConfigError(
            "a config can only be exploratory; pre-registered and held-out results come "
            "from a lock in validation/"
        )
    if not cfg["stimulus"] or not cfg["targets"]:
        raise ConfigError("stimulus and targets must not be empty")
    if cfg["seeds"] < 1 or cfg["seed0"] < 0:
        raise ConfigError("seeds must be at least 1 and seed0 non-negative")
    if not 0 < cfg["stim_ms"] <= cfg["duration_ms"]:
        raise ConfigError("stim_ms must be within the run")
    if neurons is not None:
        for name in [*cfg["stimulus"], *cfg["targets"], *cfg.get("silence", [])]:
            data.resolve(neurons, name)  # KeyError names the missing query
    return cfg


def config_hash(cfg: dict) -> str:
    return prereg.content_hash({**cfg, "version": 0, "content_sha256": ""})


def run(
    cfg: dict,
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    root: Path,
    data_dir: Path = Path("data"),
) -> Path:
    """Simulate a validated config into `root/<hash>/`; refuse if that directory exists."""
    from flymsg import manifest  # late: manifest imports prereg, which imports sim

    cfg = validate_config(dict(cfg), neurons)
    digest = config_hash(cfg)
    out = Path(root) / digest[:16]
    if out.exists():
        raise ConfigError(
            f"{out} exists; outputs are immutable (same config, same hash)"
        )
    started = datetime.now(UTC)
    p = sim.Params(
        w_syn=cfg.get("w_syn", sim.Params.w_syn),
        th_jump=cfg.get("th_jump", sim.Params.th_jump),
    )
    W = sim.network(neurons, edges, p)
    stim = np.unique(
        np.concatenate([data.resolve(neurons, q) for q in cfg["stimulus"]])
    )
    silence = (
        np.concatenate([data.resolve(neurons, q) for q in cfg["silence"]])
        if cfg.get("silence")
        else None
    )
    rows = []
    for seed in range(cfg["seed0"], cfg["seed0"] + cfg["seeds"]):
        r = sim.run(
            W, stim, cfg["rate_hz"], cfg["duration_ms"], cfg["stim_ms"], p, seed,
            silence=silence,
        )  # fmt: skip
        on = r.rate(0, cfg["stim_ms"])
        for t in cfg["targets"]:
            idx = data.resolve(neurons, t)
            best = idx[np.argmax(on[idx])]
            rows.append(
                {
                    "seed": seed,
                    "target": t,
                    "best_bodyId": int(neurons["bodyId"].iat[best]),
                    "rate_hz": float(on[best]),
                    "first_spike_ms": float(r.first_spike_ms[best]),
                    "fired_during_stimulus": int((on > 0).sum()),
                }
            )
    out.mkdir(parents=True)
    metrics = pd.DataFrame(rows)
    metrics.to_csv(out / "metrics.csv", index=False)
    (out / "config.json").write_text(json.dumps(cfg, indent=2, sort_keys=True))
    manifest.write(
        out,
        command="experiment",
        config={**cfg, "config_sha256": digest},
        seeds={"seed0": cfg["seed0"], "seeds": cfg["seeds"]},
        dataset=manifest.dataset_info("malecns", data_dir, neurons, edges),
        started_at=started,
        extra={"label": "exploratory", "metrics": "metrics.csv"},
    )
    return out


def label_of(doc: dict) -> str:
    """A manifest's label: declared, or read from its command and verdict."""
    declared = (doc.get("extra") or {}).get("label")
    if declared in LABELS:
        return declared
    verdict = str((doc.get("extra") or {}).get("verdict", ""))
    if "FAIL" in verdict or verdict.startswith("none"):
        return "failed"
    return LOCKED.get(doc.get("command"), "exploratory")


def index(roots: list[Path]) -> pd.DataFrame:
    """Every `manifest.json` under `roots`, one row each, newest first."""
    rows = []
    for root in roots:
        for path in sorted(Path(root).rglob("manifest.json")):
            try:
                doc = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                rows.append({"path": str(path.parent), "label": "unreadable"})
                continue
            if doc.get("schema") != "flymsg.run_manifest/v1":
                continue
            git = doc.get("git") or {}
            ds = doc.get("dataset") or {}
            rows.append(
                {
                    "path": str(path.parent),
                    "command": doc.get("command"),
                    "label": label_of(doc),
                    "started_at": (doc.get("timestamps") or {}).get("started_at"),
                    "commit": (git.get("commit") or "")[:7],
                    "dirty": git.get("dirty"),
                    "dataset": f"{ds.get('name', '')} {ds.get('release', '')}".strip(),
                    "seeds": json.dumps(doc.get("seeds"), sort_keys=True),
                }
            )
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values("started_at", ascending=False, na_position="last")
