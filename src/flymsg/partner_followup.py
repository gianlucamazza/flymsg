"""Residual partner follow-up (issue #76). The YAML file is the lock.

Two model-side tests of the scan v3 naming. `left`: the mirrored arm (LC4_L -> TTMn_L with
both DNp01 silenced), testing only DNp02 and DNp06 against the scan's matched null. `drive`:
without LC4 and with DNp01 silenced, DNp02_R, DNp06_R and the pair are driven directly, and
the pair is compared with matched pairs driven the same way. Every null draw is kept.
"""

from __future__ import annotations

import math
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import (
    behavior,
    data,
    dimorphism,
    draws,
    locks,
    parallel,
    prereg,
    silence_scan,
    sim,
)
from flymsg.paths import repository_root

ROOT = repository_root()
PATH = ROOT / "validation" / "partner_followup.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "513ebd2c8237f1805c42f45b55fe0168e985ecd7e39940a7a17639e9249a4d99",  # left mirror on DNp02, DNp06; direct drive of the pair; seeds 40-42
}

# seeds any earlier run of this question has used: the scan screen and confirm seeds, and
# the exploratory mirror check (0-2)
SPENT_SEEDS = frozenset({*range(3), *range(10, 13), *range(20, 23), *range(30, 33)})
_LEFT = (
    "no_residual",
    "undetermined",
    "contributes",
    "names_partner",
    "replicates",
    "partial",
    "not_replicated",
)
_DRIVE = (
    "reaches",
    "fails",
    "single_sufficient",
    "conjunction",
    "pair_sufficient",
    "not_specific",
    "insufficient",
)


class FollowupError(ValueError):
    """The follow-up protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    locks.check(doc, VERSION_HASHES, FollowupError, "follow-up protocol")
    return doc


def seeds(doc: dict) -> range:
    s = doc["seeds"]
    return range(s["seed0"], s["seed0"] + s["seeds"])


def assert_matches_code(doc: dict | None = None) -> dict:
    """The follow-up repeats the scan's arm and null at the live default model."""
    doc = assert_locked() if doc is None else doc
    scan = silence_scan.assert_matches_code()
    if doc["parent"] != {
        "lock": "silence_scan",
        "version": scan["version"],
        "verdict": "names_partner: DNp02, DNp06",
    }:
        raise FollowupError("the parent is not the scan v3 naming")
    bp = behavior.load()["protocol"]
    model = doc["model"]
    if abs(model["w_syn"] - sim.Params.w_syn) > 1e-12 or (
        model["th_jump"] != sim.Params.th_jump or model["dt_ms"] != sim.Params.dt
    ):
        raise FollowupError("model parameters are not the simulator default")
    if model["bar"] != bp["min_spikes"]:
        raise FollowupError("the bar is not the behavior jump bit")
    if doc["seeds"]["seeds"] != bp["seeds"]:
        raise FollowupError("the follow-up uses the behavior seed count")
    if set(seeds(doc)) & SPENT_SEEDS:
        raise FollowupError("seeds must be fresh")
    left, sp = doc["left"], scan["protocol"]
    for key in ("base_silence", "base_silence_n", "rate_hz", "stim_ms", "duration_ms"):
        if left[key] != sp[key]:
            raise FollowupError(f"left.{key} is not the scan's")
    if (left["stimulus"], left["motor"]) != ("LC4_L", "TTMn_L"):
        raise FollowupError("the left test mirrors LC4_R -> TTMn_R")
    if left["units"] != ["DNp02", "DNp06"]:
        raise FollowupError("the left test checks only the units the scan named")
    sc = scan["confirm"]
    for key in ("null", "match", "base_silence_in_every_draw", "tail", "alpha"):
        if left[key] != sc[key]:
            raise FollowupError(f"left.{key} is not the scan's")
    if left["draws"] != sc["min_draws"]:
        raise FollowupError("left.draws is not the scan's")
    drive = doc["drive"]
    if drive["driven"] != ["DNp02_R", "DNp06_R"] or drive["motor"] != "TTMn_R":
        raise FollowupError("the drive test is the right-side pair onto TTMn_R")
    if drive["arms"] != ["DNp02_R", "DNp06_R", "pair"] or drive["tail"] != "upper":
        raise FollowupError("the drive arms changed")
    if drive["silence"] != sp["base_silence"] or not drive["silence_in_every_draw"]:
        raise FollowupError("every drive arm and draw keeps DNp01 silenced")
    if drive["draws"] * drive["alpha"] < 1:
        raise FollowupError("the draw count cannot reach the threshold")
    if (
        tuple(doc["decides"]["left"]) != _LEFT
        or tuple(doc["decides"]["drive"]) != _DRIVE
    ):
        raise FollowupError("the deciding outcomes changed")
    for name, row in doc["reported"].items():
        if row["decides"] is not False:
            raise FollowupError(f"reported row {name} must not decide")
    if (
        doc["prediction"]["status"] != "unverified"
        or doc["prediction"]["tests_animal"] is not False
    ):
        raise FollowupError("the prediction is unverified model-side")
    return doc


def summary(doc: dict | None = None) -> str:
    """The frozen follow-up. Printing it does not simulate."""
    doc = assert_matches_code() if doc is None else doc
    s, left, drive = seeds(doc), doc["left"], doc["drive"]
    return (
        f"partner-followup v{doc['version']} (issue #{doc['issue']}), seeds "
        f"{s.start}-{s.stop - 1}. left: {left['stimulus']} -> {left['motor']} with "
        f"{left['base_silence']} silenced, units {', '.join(left['units'])}, "
        f"{left['null']} null. drive: {', '.join(drive['driven'])} at "
        f"{drive['rate_hz']:g} Hz -> {drive['motor']} with {drive['silence']} silenced, "
        f"arms {', '.join(drive['arms'])}, {drive['null']} null, bar {doc['model']['bar']}"
    )


def p_upper(observed: float, null) -> float:
    """Empirical one-sided p for a rise, +1 smoothing."""
    null = np.asarray(null, dtype=float)
    return (1 + int(np.count_nonzero(null >= observed))) / (1 + null.size)


def reaches(counts, bar: int) -> bool:
    return bool(np.all(np.asarray(counts) >= bar))


def fails(counts, bar: int) -> bool:
    return bool(np.all(np.asarray(counts) <= bar - 1))


def decide_left(
    rows: pd.DataFrame, base_counts, alpha: float, bar: int
) -> tuple[pd.DataFrame, str]:
    """Per unit `contributes` and `names_partner`, and the left verdict."""
    if silence_scan.no_residual(base_counts, bar - 1):
        return rows, "no_residual"
    out = silence_scan.decide(rows, len(rows), alpha, bar - 1)
    if out["p"].isna().any():
        return out, "undetermined"
    named = int(out["names_partner"].sum())
    if named == len(out):
        return out, "replicates"
    return out, "partial" if named else "not_replicated"


def decide_drive(arms: dict, p: float, alpha: float, bar: int) -> str:
    """`arms` maps arm name to TTMn_R counts per seed; `pair` is the pair arm."""
    singles = {k: v for k, v in arms.items() if k != "pair"}
    alone = [k for k, v in singles.items() if reaches(v, bar)]
    if alone:
        return "single_sufficient: " + ", ".join(alone)
    if not reaches(arms["pair"], bar):
        return "insufficient"
    if not p <= alpha:
        return "not_specific"
    if all(fails(v, bar) for v in singles.values()):
        return "conjunction"
    return "pair_sufficient"


def _arm(W, stim, motor, silence, seed_list, rate, stim_ms, duration_ms):
    counts, results = [], []
    for seed in seed_list:
        r = sim.run(
            W, stim, rate, duration_ms, stim_ms, sim.Params(), seed, silence=silence
        )
        counts.append(int(r.counts[:, motor].sum()))
        results.append(r)
    return counts, results


def _job(job: tuple[str, str]) -> list[dict]:
    ctx, checkpoint, meta = parallel.context()
    W, doc, key = ctx["W"], ctx["doc"], ctx["key"]
    part, name = job
    s = list(seeds(doc))
    label = f"partner-followup/v{doc['version']}/{part}/{name}"
    rng = np.random.default_rng(zlib.crc32(label.encode()))
    if part == "left":
        c = ctx["left"]
        cfg = doc["left"]
        tested = c["units"][name]

        def counts_with(extra):
            silence = np.concatenate([c["base"], extra])
            got, _ = _arm(
                W,
                c["stim"],
                c["motor"],
                silence,
                s,
                cfg["rate_hz"],
                cfg["stim_ms"],
                cfg["duration_ms"],
            )
            return got

        observed = counts_with(tested)
        pool, like, tail = c["pool"], tested, silence_scan.p_lower
    else:
        c = ctx["drive"]
        cfg = doc["drive"]

        def counts_with(driven):
            got, _ = _arm(
                W,
                driven,
                c["motor"],
                c["silence"],
                s,
                cfg["rate_hz"],
                cfg["stim_ms"],
                cfg["duration_ms"],
            )
            return got

        observed = counts_with(c["pair"])
        pool, like, tail = c["pool"], c["pair"], p_upper
    row = {
        "part": part,
        "unit": name,
        "counts": observed,
        "draws": 0,
        "null_mean": math.nan,
        "p": math.nan,
        "null": [],
    }
    short = draws.matched_pool_shortfall(key, pool, like)
    if short:
        group, have, need = short[0]
        print(
            f"{label}: null not defined ({group}: {have}, need {need})", file=sys.stderr
        )
        return [row]
    null = draws.null_rates(
        label,
        cfg["draws"],
        lambda: draws.matched_draw(rng, key, pool, like),
        lambda idx: [float(np.mean(counts_with(idx)))],
        draws.partial_path(checkpoint, job),
        meta,
    )[:, 0]
    row.update(
        draws=int(null.size),
        null_mean=float(null.mean()),
        p=tail(float(np.mean(observed)), null),
        null=[float(x) for x in null],
    )
    return [row]


def followup(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    doc: dict,
    idx: dict,
    workers: int = 1,
    checkpoint: Path | None = None,
) -> dict:
    """Both tests in the order the lock fixes. `idx` maps every locked name to neuron
    indices (`run` resolves them on MaleCNS; tests pass a small graph)."""
    W = sim.network(neurons, edges, sim.Params())
    s, bar = list(seeds(doc)), doc["model"]["bar"]
    key = (
        neurons["superclass"].fillna("none").astype(str)
        + "/"
        + neurons["sign"].astype(str)
    ).to_numpy()
    out = {"version": doc["version"]}

    left = doc["left"]
    stim, motor, base = (
        idx[left["stimulus"]],
        int(idx[left["motor"]][0]),
        idx[left["base_silence"]],
    )
    units = {u: idx[u] for u in left["units"]}
    base_counts, results = _arm(
        W, stim, motor, base, s, left["rate_hz"], left["stim_ms"], left["duration_ms"]
    )
    out["left_base"] = base_counts
    pool = np.zeros(len(neurons), dtype=bool)
    pool[dimorphism.responders(results, stim)] = True
    pool[np.concatenate([stim, [motor], base, *units.values()])] = False
    jobs = []
    if not silence_scan.no_residual(base_counts, bar - 1):
        jobs += [("left", u) for u in left["units"]]

    drive = doc["drive"]
    d_motor = int(idx[drive["motor"]][0])
    d_silence = idx[drive["silence"]]
    singles = {n: idx[n] for n in drive["driven"]}
    pair = np.concatenate(list(singles.values()))
    arms, driven_spikes = {}, {}
    for arm in drive["arms"]:
        driven = pair if arm == "pair" else singles[arm]
        counts, res = _arm(
            W,
            driven,
            d_motor,
            d_silence,
            s,
            drive["rate_hz"],
            drive["stim_ms"],
            drive["duration_ms"],
        )
        arms[arm] = counts
        driven_spikes[arm] = {
            n: [int(r.counts[:, i].sum()) for r in res] for n, i in singles.items()
        }
    out["drive_arms"], out["driven_spikes"] = arms, driven_spikes
    d_pool = np.isin(key, np.unique(key[pair]))
    exclude = [d_motor, *d_silence, *idx["DNp02"], *idx["DNp06"]]
    d_pool[exclude] = False
    jobs.append(("drive", "pair"))

    ctx = {
        "W": W,
        "doc": doc,
        "key": key,
        "left": {
            "stim": stim,
            "motor": motor,
            "base": base,
            "units": units,
            "pool": pool,
        },
        "drive": {"motor": d_motor, "silence": d_silence, "pair": pair, "pool": d_pool},
    }
    meta = {"version": doc["version"], "sha256": doc["content_sha256"]}
    rows = draws.map_jobs(_job, jobs, workers, ctx, checkpoint, meta)
    table = pd.DataFrame(rows)
    out["null_draws"] = pd.DataFrame(
        [(r["part"], r["unit"], i, x) for r in rows for i, x in enumerate(r["null"])],
        columns=["part", "unit", "draw", "mean_count"],
    )
    table = table.drop(columns="null")
    lrows = table[table["part"] == "left"].drop(columns="part").reset_index(drop=True)
    out["left"], out["left_verdict"] = decide_left(
        lrows, base_counts, left["alpha"], bar
    )
    prow = table[table["part"] == "drive"].iloc[0]
    out["drive"] = prow.drop("part").to_dict()
    out["drive_verdict"] = decide_drive(arms, prow["p"], drive["alpha"], bar)
    return out


def run(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    workers: int = 1,
    checkpoint: Path | None = None,
) -> dict:
    """The frozen follow-up on MaleCNS at the default parameters."""
    doc = assert_matches_code()
    left, drive = doc["left"], doc["drive"]
    expect = {
        left["stimulus"]: left["stimulus_n"],
        left["motor"]: left["motor_n"],
        left["base_silence"]: left["base_silence_n"],
        **{u: left["unit_n"] for u in left["units"]},
        drive["motor"]: drive["motor_n"],
        **{n: 1 for n in drive["driven"]},
    }
    idx = {}
    for name, n in expect.items():
        got = data.resolve(neurons, name)
        if got.size != n:
            raise FollowupError(f"{name} has {got.size} neurons, the lock says {n}")
        idx[name] = got
    return followup(neurons, edges, doc, idx, workers, checkpoint)
