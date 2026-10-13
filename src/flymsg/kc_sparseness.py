"""Kenyon cell sparseness diagnostic (issue #95). The YAML file is the lock.

Four arms differ only in the weight matrix: the default; Kenyon cell to Kenyon cell
synapses without fast effect (they are metabotropic, Manoim et al. 2022, and the model gives
metabotropic transmission sign 0); APL -> KC removed; both. Each arm drives two ORN types
and counts the responding Kenyon cells and those shared between the odors. The default model
is not changed by the result.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, locks, plasticity, prereg, sim

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "kc_sparseness.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "d5343b238f61e3bd9cb51ed8fc21981da7a418ad5fdfe7133fe201899c33caba",  # arms A-D, odors ORN_VA1d and ORN_DL3, seeds 60-62
}
ARMS = ("A", "B", "C", "D")


class SparsenessError(ValueError):
    """The sparseness protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    locks.check(doc, VERSION_HASHES, SparsenessError, "sparseness protocol")
    return doc


def assert_matches_code(doc: dict | None = None) -> dict:
    """The odors are the plasticity lock's, and the bounds are the measured ones."""
    doc = assert_locked() if doc is None else doc
    mb = plasticity.load()["protocol"]
    proto = doc["protocol"]
    if proto["odors"] != [mb["cs_plus"], mb["cs_minus"]]:
        raise SparsenessError("the odors are not the KC -> MBON11 lock's")
    if tuple(doc["arms"]) != ARMS:
        raise SparsenessError("the arms changed")
    dec = doc["decides"]
    if (dec["sparse_max"], dec["overlap_max"]) != (0.17, 0.646):
        raise SparsenessError("the bounds are not the measured ones")
    if set(proto["seeds"]) & set(mb["seeds"]):
        raise SparsenessError("seeds must be fresh")
    for name, row in doc["reported"].items():
        if row["decides"] is not False:
            raise SparsenessError(f"reported row {name} must not decide")
    if doc["defaults_changed"] is not False:
        raise SparsenessError("the diagnostic never changes the defaults")
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    p, d = doc["protocol"], doc["decides"]
    return (
        f"kc-sparseness v{doc['version']} (issue #{doc['issue']}): arms A default, "
        f"B KC->KC without fast effect, C no APL->KC, D both; odors "
        f"{', '.join(p['odors'])} at {p['rate_hz']:g} Hz for {p['odor_ms']:g} ms; seeds "
        f"{', '.join(map(str, p['seeds']))}; within if <= {d['sparse_max']} of KCs respond "
        f"and <= {d['overlap_max']} of responders are shared"
    )


def arms(W, kcs: np.ndarray, apl: np.ndarray) -> dict:
    """The four weight matrices of the lock."""
    b = plasticity.depress(W, kcs, kcs, 0.0)
    return {
        "A": W,
        "B": b,
        "C": plasticity.depress(W, apl, kcs, 0.0),
        "D": plasticity.depress(b, apl, kcs, 0.0),
    }


def responders(counts_per_seed: list[np.ndarray], min_seeds: int) -> np.ndarray:
    """Cells with at least one spike in at least `min_seeds` of the seeds."""
    return np.sum([c > 0 for c in counts_per_seed], axis=0) >= min_seeds


def within(fractions, overlaps, sparse_max: float, overlap_max: float) -> bool:
    return bool(max(fractions) <= sparse_max and max(overlaps) <= overlap_max)


def decide(table: pd.DataFrame, sparse_max: float, overlap_max: float) -> str:
    ok = {
        arm: within(
            [row["fraction_1"], row["fraction_2"]],
            [row["shared_of_1"], row["shared_of_2"]],
            sparse_max,
            overlap_max,
        )
        for arm, row in table.set_index("arm").iterrows()
    }
    if ok["A"]:
        return "already_within"
    return "recurrence" if ok["B"] else "not_recurrence"


def protocol(W, idx: dict, doc: dict) -> dict:
    proto = doc["protocol"]
    p = sim.Params()
    kcs, apl = idx["KC"], idx[proto["apl"]]
    bins = round(proto["odor_ms"] / 10.0)
    rows = []
    for arm, Wx in arms(W, kcs, apl).items():
        resp = []
        for odor in proto["odors"]:
            per_seed = []
            for seed in proto["seeds"]:
                r = sim.run(
                    Wx,
                    idx[odor],
                    proto["rate_hz"],
                    proto["duration_ms"],
                    proto["odor_ms"],
                    p,
                    seed,
                )
                per_seed.append(r.counts[:bins, kcs].sum(axis=0))
            resp.append(responders(per_seed, 2))
        n1, n2, both = (
            int(resp[0].sum()),
            int(resp[1].sum()),
            int((resp[0] & resp[1]).sum()),
        )
        rows.append(
            {
                "arm": arm,
                "responders_1": n1,
                "responders_2": n2,
                "shared": both,
                "fraction_1": n1 / kcs.size,
                "fraction_2": n2 / kcs.size,
                "shared_of_1": both / n1 if n1 else 0.0,
                "shared_of_2": both / n2 if n2 else 0.0,
            }
        )
    table = pd.DataFrame(rows)
    d = doc["decides"]
    return {"table": table, "verdict": decide(table, d["sparse_max"], d["overlap_max"])}


def run(neurons: pd.DataFrame, edges: pd.DataFrame) -> dict:
    doc = assert_matches_code()
    proto = doc["protocol"]
    expect = dict(zip(proto["odors"], proto["odor_n"], strict=True))
    expect[proto["apl"]] = proto["apl_n"]
    idx = {}
    for name, n in expect.items():
        got = data.resolve(neurons, name)
        if got.size != n:
            raise SparsenessError(f"{name} has {got.size} neurons, the lock says {n}")
        idx[name] = got
    idx["KC"] = np.flatnonzero(
        neurons["type"].fillna("").str.contains(proto["kc"]).to_numpy()
    )
    return protocol(sim.network(neurons, edges, sim.Params()), idx, doc)
