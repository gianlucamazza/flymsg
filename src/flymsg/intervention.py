"""Causal circuit explorer (#25): anatomy, exploratory silencing, and locked confirmation.

Three kinds of evidence stay apart, and every row says which it is:

- `anatomy`: paths and synapse counts from the connectome (`graph`), no simulation;
- `simulation, exploratory`: `explore` silences each intermediate cell type of those paths and
  measures the target, with a bootstrap interval; it chooses nothing;
- `simulation, confirmatory`: `confirm` runs a lock (`flymsg.intervention/v1`) whose sets,
  seeds, null and threshold were fixed before the run, on seeds `explore` did not use.

Neither kind is experimental biology. A lock must be registered in `VERSION_HASHES` by a
commit before it runs, an edited lock without a new version is refused, and a confirmation
never overwrites an earlier one.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, dimorphism, draws, graph, locks, sim, validate

SCHEMA = "flymsg.intervention/v1"
# (lock name, version) -> content hash; a lock runs only once registered here by a commit
VERSION_HASHES: dict[tuple[str, int], str] = {}


# targets whose question is already governed by a lock: an exploration may not choose its sets
GOVERNED = {
    "TTMn_R": "issue #20 and validation/silence_scan.yaml; this ranking must not choose a "
    "later version's sets, and no partner is identified by it",
}


class InterventionError(ValueError):
    """A lock that is not registered, was edited, or would overwrite a result."""


def _rates(
    W, stim, target_idx, p, seeds, seed0, rate_hz, stim_ms, silence=None, best=None
):
    """A target neuron's rate during the stimulus, per seed, and that neuron. Without `best`
    it is the neuron with the highest mean rate over the seeds (the baseline arm picks it);
    every other arm passes the baseline's `best`, so all arms read the same neuron."""
    on = [
        sim.run(W, stim, rate_hz, stim_ms, stim_ms, p, s, silence=silence).rate(
            0, stim_ms
        )
        for s in range(seed0, seed0 + seeds)
    ]
    if best is None:
        best = target_idx[np.argmax(np.mean([r[target_idx] for r in on], axis=0))]
    return np.array([r[best] for r in on]), int(best)


def explore(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    source: str,
    target: str,
    *,
    paths: int = 3,
    seeds: int = 3,
    seed0: int = 0,
    rate_hz: float = validate.RATE_HZ,
    stim_ms: float = validate.STIM_MS,
    base_silence: list[str] = (),
    p: sim.Params | None = None,
) -> dict:
    """Up to `paths` distinct strongest routes, then the target's change when each
    intermediate type is silenced. Exploratory: seeds `seed0`.., no null, no threshold."""
    p = p or sim.Params()
    src, dst = data.resolve(neurons, source), data.resolve(neurons, target)
    types = neurons["type"].fillna("untyped").to_numpy()
    routes = graph.alternative_paths(edges, len(neurons), src, dst, types, paths)
    anatomy = []
    for i, route in enumerate(routes):
        weights = graph.edge_weights(edges, route)
        anatomy.append(
            {
                "evidence": "anatomy",
                "path": i,
                "types": [str(types[k]) for k in route],
                "bodyIds": [int(neurons["bodyId"].iat[k]) for k in route],
                "synapses": [int(w) for w in weights],
            }
        )
    base = (
        np.concatenate([data.resolve(neurons, q) for q in base_silence])
        if base_silence
        else np.empty(0, dtype=np.int64)
    )
    W = sim.network(neurons, edges, p)
    kw = {"seeds": seeds, "seed0": seed0, "rate_hz": rate_hz, "stim_ms": stim_ms}
    ref, best = _rates(W, src, dst, p, silence=base if base.size else None, **kw)
    candidates = sorted({t for a in anatomy for t in a["types"][1:-1]})
    rows = []
    for t in candidates:
        silenced = np.setdiff1d(data.resolve(neurons, t), np.concatenate([src, dst]))
        got, _ = _rates(
            W, src, dst, p, silence=np.concatenate([base, silenced]), best=best, **kw
        )
        delta = got - ref
        lo, hi = validate.bootstrap_ci(delta) if seeds > 1 else (np.nan, np.nan)
        rows.append(
            {
                "evidence": "simulation, exploratory",
                "silenced": t,
                "neurons": int(silenced.size),
                "baseline_hz": [float(x) for x in ref],
                "silenced_hz": [float(x) for x in got],
                "mean_change_hz": float(delta.mean()),
                "ci95_change_hz": [float(lo), float(hi)],
            }
        )
    return {
        "label": "exploratory",
        "source": source,
        "target": target,
        "target_neuron": int(neurons["bodyId"].iat[best]),
        "base_silence": list(base_silence),
        "seeds": {"seed0": seed0, "seeds": seeds},
        "anatomy": anatomy,
        "interventions": rows,
        "note": "anatomy and model simulation only; not evidence from animals",
        "governed_by": GOVERNED.get(target),
    }


def load(path: Path) -> dict:
    return locks.load(Path(path))


_FIELDS = ("stimulus", "target", "sets", "seed0", "seeds", "explored_seeds", "rate_hz",
           "stim_ms", "draws", "alpha", "tail")  # fmt: skip


def assert_registered(doc: dict, name: str, hashes: dict | None = None) -> dict:
    """A lock runs only if registered with this content, complete, and on fresh seeds."""
    hashes = VERSION_HASHES if hashes is None else hashes
    if doc.get("schema") != SCHEMA:
        raise InterventionError(f"{name}: schema is not {SCHEMA}")
    table = {v: h for (n, v), h in hashes.items() if n == name}
    locks.check(doc, table, InterventionError, f"intervention lock {name}")
    missing = [f for f in _FIELDS if f not in doc]
    if missing:
        raise InterventionError(f"{name}: missing {', '.join(missing)}")
    seeds = set(range(doc["seed0"], doc["seed0"] + doc["seeds"]))
    if seeds & set(doc["explored_seeds"]):
        raise InterventionError(
            f"{name}: confirmation seeds overlap the explored seeds"
        )
    if doc["tail"] not in ("lower", "upper") or not doc["sets"]:
        raise InterventionError(
            f"{name}: tail must be lower or upper, with at least one set"
        )
    if doc["draws"] * doc["alpha"] / len(doc["sets"]) < 1:
        raise InterventionError(
            f"{name}: too few draws to reach the corrected threshold"
        )
    return doc


def confirm(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    lock: Path,
    out_root: Path,
    *,
    hashes: dict | None = None,
    checkpoint: Path | None = None,
) -> pd.DataFrame:
    """Run a registered lock: each set against a matched null of the base arm's responders
    (superclass and sign), never drawing from any set; p per set, Bonferroni over sets."""
    lock = Path(lock)
    doc = assert_registered(load(lock), lock.stem, hashes)
    out = Path(out_root) / lock.stem / f"v{doc['version']}"
    if out.exists():
        raise InterventionError(f"{out} exists; a confirmation is never overwritten")
    stim = np.unique(
        np.concatenate([data.resolve(neurons, q) for q in doc["stimulus"]])
    )
    target = data.resolve(neurons, doc["target"])
    base = (
        np.concatenate([data.resolve(neurons, q) for q in doc["base_silence"]])
        if doc.get("base_silence")
        else np.empty(0, dtype=np.int64)
    )
    sets = {
        k: np.concatenate([data.resolve(neurons, t) for t in v])
        for k, v in doc["sets"].items()
    }
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    kw = {k: doc[k] for k in ("seeds", "seed0", "rate_hz", "stim_ms")}
    ref, best = _rates(W, stim, target, p, silence=base if base.size else None, **kw)
    runs = [
        sim.run(W, stim, doc["rate_hz"], doc["stim_ms"], doc["stim_ms"], p, s,
                silence=base if base.size else None)
        for s in range(doc["seed0"], doc["seed0"] + doc["seeds"])
    ]  # fmt: skip
    pool = np.zeros(len(neurons), dtype=bool)
    pool[dimorphism.responders(runs, stim)] = True
    pool[np.concatenate([stim, target, base, *sets.values()])] = False
    key = (
        neurons["superclass"].fillna("none").astype(str)
        + "/"
        + neurons["sign"].astype(str)
    ).to_numpy()
    alpha = doc["alpha"] / len(sets)
    rows = []
    for name, idx in sets.items():
        got, _ = _rates(
            W, stim, target, p, silence=np.concatenate([base, idx]), best=best, **kw
        )
        observed = float(got.mean())
        row = {
            "evidence": "simulation, confirmatory",
            "set": name,
            "neurons": int(idx.size),
            "baseline_hz": float(ref.mean()),
            "silenced_hz": observed,
            "p": np.nan,
            "alpha": alpha,
        }
        if not draws.matched_pool_shortfall(key, pool, idx):
            rng = np.random.default_rng(
                zlib.crc32(f"{lock.stem}/v{doc['version']}/{name}".encode())
            )
            null = draws.null_rates(
                f"{lock.stem}/{name}",
                doc["draws"],
                lambda rng=rng, idx=idx: draws.matched_draw(rng, key, pool, idx),
                lambda pick: [
                    float(
                        _rates(
                            W,
                            stim,
                            target,
                            p,
                            silence=np.concatenate([base, pick]),
                            best=best,
                            **kw,
                        )[0].mean()
                    )
                ],
                draws.partial_path(checkpoint, (name,)) if checkpoint else None,
                {"lock": lock.stem, "version": doc["version"], "set": name},
            )[:, 0]
            tail = null <= observed if doc["tail"] == "lower" else null >= observed
            row["p"] = (1 + int(tail.sum())) / (1 + null.size)
            row["null_mean_hz"] = float(null.mean())
        row["passes"] = bool(row["p"] <= alpha) if not np.isnan(row["p"]) else False
        rows.append(row)
    table = pd.DataFrame(rows)
    out.mkdir(parents=True)
    table.to_csv(out / "result.csv", index=False)
    (out / "lock.json").write_text(json.dumps(doc, indent=2, sort_keys=True))
    return table
