"""Kenyon cell sparseness diagnostic (issue #95). The YAML file is the lock.

Arms differ only in the weight matrix: each removes the fast effect of named synapse
classes (KC -> KC, metabotropic in the fly, Manoim et al. 2022; APL -> KC; cholinergic
antennal-lobe local neuron -> projection neuron, electrical in the fly, Yaksi & Wilson 2010).
Each arm drives two ORN types and counts the responding Kenyon cells, those shared between
the odors, and the projection neurons that spike. The default model is not changed by the
result. Version 1 (arms A-D) ran from b096b4a; version 2 runs arms A, B, E, F.
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
    2: "bcfef9af52861dfd0a903c8b01aded5f8f504b645cdf6933d91b01ae47350322",  # arms A, B, E, F (cholinergic LN -> PN), seeds 70-72
}
# synapse classes without fast effect in each arm
ARM_CLASSES = {
    "A": (),
    "B": ("kc_kc",),
    "C": ("apl_kc",),
    "D": ("kc_kc", "apl_kc"),
    "E": ("ach_ln_pn",),
    "F": ("kc_kc", "ach_ln_pn"),
}
SPENT_SEEDS = {1: (60, 61, 62)}


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
    if set(doc["arms"]) - set(ARM_CLASSES) or next(iter(doc["arms"])) != "A":
        raise SparsenessError("the arms changed")
    for v, spent in SPENT_SEEDS.items():
        if v < doc["version"] and set(proto["seeds"]) & set(spent):
            raise SparsenessError(f"seeds must not reuse version {v}'s")
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
    arms_text = "; ".join(
        f"{a} {'+'.join(ARM_CLASSES[a]) or 'default'}" for a in doc["arms"]
    )
    return (
        f"kc-sparseness v{doc['version']} (issue #{doc['issue']}): arms {arms_text}; odors "
        f"{', '.join(p['odors'])} at {p['rate_hz']:g} Hz for {p['odor_ms']:g} ms; seeds "
        f"{', '.join(map(str, p['seeds']))}; within if <= {d['sparse_max']} of KCs respond "
        f"and <= {d['overlap_max']} of responders are shared"
    )


def arms(W, idx: dict, names) -> dict:
    """The weight matrix of each named arm. `idx` holds the neuron sets "KC", "APL",
    "ACH_LN" and "PN"."""
    pairs = {
        "kc_kc": ("KC", "KC"),
        "apl_kc": ("APL", "KC"),
        "ach_ln_pn": ("ACH_LN", "PN"),
    }
    out = {}
    for name in names:
        Wx = W
        for cls in ARM_CLASSES[name]:
            pre, post = pairs[cls]
            Wx = plasticity.depress(Wx, idx[pre], idx[post], 0.0)
        out[name] = Wx
    return out


def responders(counts_per_seed: list[np.ndarray], min_seeds: int) -> np.ndarray:
    """Cells with at least one spike in at least `min_seeds` of the seeds."""
    return np.sum([c > 0 for c in counts_per_seed], axis=0) >= min_seeds


def within(fractions, overlaps, sparse_max: float, overlap_max: float) -> bool:
    return bool(max(fractions) <= sparse_max and max(overlaps) <= overlap_max)


def decide(table: pd.DataFrame, sparse_max: float, overlap_max: float) -> str:
    """The arms whose two odors are within the measured bounds, or `none`."""
    ok = [
        row["arm"]
        for _, row in table.iterrows()
        if within(
            [row["fraction_1"], row["fraction_2"]],
            [row["shared_of_1"], row["shared_of_2"]],
            sparse_max,
            overlap_max,
        )
    ]
    return "within: " + ", ".join(ok) if ok else "none"


def protocol(W, idx: dict, doc: dict) -> dict:
    proto = doc["protocol"]
    p = sim.Params()
    kcs, pns = idx["KC"], idx["PN"]
    bins = round(proto["odor_ms"] / 10.0)
    rows = []
    for arm, Wx in arms(W, idx, list(doc["arms"])).items():
        resp, pn_share = [], []
        for odor in proto["odors"]:
            per_seed, pn_seed = [], []
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
                pn_seed.append(r.counts[:bins, pns].sum(axis=0))
            resp.append(responders(per_seed, 2))
            pn_share.append(float(responders(pn_seed, 2).mean()) if pns.size else 0.0)
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
                "pn_spiking_1": pn_share[0],
                "pn_spiking_2": pn_share[1],
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
    idx["APL"] = idx[proto["apl"]]
    cls = neurons["class"].fillna("")
    idx["PN"] = np.flatnonzero((cls == proto["pn_class"]).to_numpy())
    idx["ACH_LN"] = np.flatnonzero(
        (
            (cls == proto["ln_class"]) & (neurons["nt"] == proto["ln_transmitter"])
        ).to_numpy()
    )
    return protocol(sim.network(neurons, edges, sim.Params()), idx, doc)
