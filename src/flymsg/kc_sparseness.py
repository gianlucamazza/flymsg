"""Kenyon cell sparseness diagnostic (issue #95). The YAML file is the lock.

Arms differ only in the weight matrix: each removes the fast effect of named synapse
classes (KC -> KC, metabotropic in the fly, Manoim et al. 2022; APL -> KC; cholinergic
antennal-lobe local neuron -> projection neuron, electrical in the fly, Yaksi & Wilson 2010).
Each arm drives two ORN types and counts the responding Kenyon cells, those shared between
the odors, and the projection neurons that spike. The default model is not changed by the
result. Version 1 (arms A-D) ran from b096b4a; version 2 runs arms A, B, E, F. Version 4
(issue #85) adds electrical synapses (`sim.Gap`) to arms E and F: excitatory local neuron to
PN coupling scanned over a grid, sister-PN coupling at its measured value.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, eye, locks, odors, plasticity, prereg, sim

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "kc_sparseness.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "d5343b238f61e3bd9cb51ed8fc21981da7a418ad5fdfe7133fe201899c33caba",  # arms A-D, odors ORN_VA1d and ORN_DL3, seeds 60-62
    2: "bcfef9af52861dfd0a903c8b01aded5f8f504b645cdf6933d91b01ae47350322",  # arms A, B, E, F (cholinergic LN -> PN), seeds 70-72
    3: "0a6b0ec6d7b8829cf9aa35de0c945841259a3502ec59e70bd569e1dfd54e0bd2",  # Hige odors from DoOR, lower bound, seeds 80-82
    4: "72059246ade98ec69b49ce32bac587e0f6f52d39b2cb747c962fb4177694af67",  # E and F with electrical eLN-PN coupling 0-1 and sister PNs at 0.013, seeds 83-85
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
SPENT_SEEDS = {1: (60, 61, 62), 2: (70, 71, 72), 3: (80, 81, 82)}
# Kazama & Wilson 2009 Fig 7d: coupling coefficient of homotypic PN pairs for
# hyperpolarizing steps (electrical only), read from the bar height
SISTER_PN_CC = 0.013
HIGE_ODORS = ["3-octanol", "4-methylcyclohexanol"]


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
    if proto.get("odor_source") == "door":
        if proto["odors"] != HIGE_ODORS:
            raise SparsenessError("the odors are not Hige et al. 2015's")
    elif proto["odors"] != [mb["cs_plus"], mb["cs_minus"]]:
        raise SparsenessError("the odors are not the KC -> MBON11 lock's")
    if set(doc["arms"]) - set(ARM_CLASSES) or next(iter(doc["arms"])) != "A":
        raise SparsenessError("the arms changed")
    if "coupling" in doc:
        c = doc["coupling"]
        if c["sister_cc"] != SISTER_PN_CC or not set(c["bases"]) <= set(doc["arms"]):
            raise SparsenessError("the coupling is not the sourced one")
        if c["eln_pn"] != sorted(set(c["eln_pn"])) or min(c["eln_pn"]) != 0.0:
            raise SparsenessError("the coupling grid must start at 0 and increase")
    for v, spent in SPENT_SEEDS.items():
        if v < doc["version"] and set(proto["seeds"]) & set(spent):
            raise SparsenessError(f"seeds must not reuse version {v}'s")
    dec = doc["decides"]
    if (dec["sparse_max"], dec["overlap_max"]) != (0.17, 0.646) or dec.get(
        "sparse_min", 0.0
    ) not in (0.0, 0.01):
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
        f"{', '.join(p['odors'])} "
        + (
            f"(DoOR, {p['rate_at_response_1_hz']:g} Hz at response 1)"
            if p.get("odor_source") == "door"
            else f"at {p['rate_hz']:g} Hz"
        )
        + f" for {p['odor_ms']:g} ms; seeds "
        f"{', '.join(map(str, p['seeds']))}; within if {d.get('sparse_min', 0)}-"
        f"{d['sparse_max']} of KCs respond "
        f"and <= {d['overlap_max']} of responders are shared"
        + (
            f"; {len(coupled_arms(doc))} coupled arms ({'/'.join(doc['coupling']['bases'])} "
            f"+ eLN-PN coupling {min(doc['coupling']['eln_pn']):g}-"
            f"{max(doc['coupling']['eln_pn']):g}, sister PNs at coefficient "
            f"{doc['coupling']['sister_cc']:g})"
            if "coupling" in doc
            else ""
        )
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


def coupled_arms(doc: dict) -> list[tuple[str, str, float]]:
    """(name, base arm, eLN-PN coupling) of every coupled arm, in lock order."""
    c = doc.get("coupling")
    if not c:
        return []
    return [(f"{b}+gap{k:g}", b, k) for b in c["bases"] for k in c["eln_pn"]]


def gap_pairs(
    neurons: pd.DataFrame, edges: pd.DataFrame, idx: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Candidate electrical pairs. eLN-PN: each cholinergic local neuron and PN joined by
    chemical synapses (either direction), with their synapse count; EM does not show gap
    junctions, so the chemical contacts stand in for the electrical ones. Sister PNs: every
    pair of PNs of the same type on the same side (Kazama & Wilson 2009 recorded
    ipsilateral homotypic pairs)."""
    ln, pn = idx["ACH_LN"], idx["PN"]
    fwd = edges[np.isin(edges["pre"], ln) & np.isin(edges["post"], pn)]
    back = edges[np.isin(edges["pre"], pn) & np.isin(edges["post"], ln)]
    both = pd.concat(
        [
            fwd.rename(columns={"pre": "ln", "post": "pn"}),
            back.rename(columns={"pre": "pn", "post": "ln"}),
        ]
    )
    eln = both.groupby(["ln", "pn"], as_index=False)["weight"].sum()
    rows = []
    t = neurons["type"].to_numpy()
    side = neurons["instance"].map(eye.side_of).to_numpy()
    groups: dict = {}
    for k in pn:
        if isinstance(t[k], str) and side[k] is not None:
            groups.setdefault((t[k], side[k]), []).append(k)
    for members in groups.values():
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                rows.append((members[a], members[b]))
    sisters = pd.DataFrame(rows, columns=["i", "j"])
    return eln, sisters


def gap_for(
    eln: pd.DataFrame, sisters: pd.DataFrame, k: float, sister_cc: float
) -> sim.Gap:
    """eLN-PN pairs share `k` in proportion to synapses, scaled so that the median PN's total
    eLN coupling is `k`; sister PNs at c / (1 - c) of the measured coupling coefficient."""
    per_pn = eln.groupby("pn")["weight"].sum()
    scale = k / float(per_pn.median()) if k > 0 else 0.0
    keep = eln[eln["weight"] > 0] if k > 0 else eln.iloc[:0]
    return sim.Gap(
        i=np.r_[keep["ln"].to_numpy(), sisters["i"].to_numpy()].astype(np.int64),
        j=np.r_[keep["pn"].to_numpy(), sisters["j"].to_numpy()].astype(np.int64),
        coupling=np.r_[
            keep["weight"].to_numpy() * scale,
            np.full(len(sisters), sister_cc / (1.0 - sister_cc)),
        ],
    )


def responders(counts_per_seed: list[np.ndarray], min_seeds: int) -> np.ndarray:
    """Cells with at least one spike in at least `min_seeds` of the seeds."""
    return np.sum([c > 0 for c in counts_per_seed], axis=0) >= min_seeds


def within(
    fractions, overlaps, sparse_max: float, overlap_max: float, sparse_min: float = 0.0
) -> bool:
    return bool(
        sparse_min <= min(fractions)
        and max(fractions) <= sparse_max
        and max(overlaps) <= overlap_max
    )


def decide(
    table: pd.DataFrame, sparse_max: float, overlap_max: float, sparse_min: float = 0.0
) -> str:
    """The arms whose two odors are within the measured bounds, or `none`."""
    ok = [
        row["arm"]
        for _, row in table.iterrows()
        if within(
            [row["fraction_1"], row["fraction_2"]],
            [row["shared_of_1"], row["shared_of_2"]],
            sparse_max,
            overlap_max,
            sparse_min,
        )
    ]
    return "within: " + ", ".join(ok) if ok else "none"


def protocol(W, idx: dict, doc: dict) -> dict:
    proto = doc["protocol"]
    p = sim.Params()
    kcs, pns = idx["KC"], idx["PN"]
    bins = round(proto["odor_ms"] / 10.0)
    rows = []
    weights = arms(W, idx, list(doc["arms"]))
    runs = [(arm, Wx, None) for arm, Wx in weights.items()]
    for name, base, k in coupled_arms(doc):
        gap = gap_for(idx["eln"], idx["sisters"], k, doc["coupling"]["sister_cc"])
        runs.append((name, weights[base], gap))
    for arm, Wx, gap in runs:
        resp, pn_share = [], []
        for odor in proto["odors"]:
            per_seed, pn_seed = [], []
            cells, rates = idx["stimuli"][odor]
            for seed in proto["seeds"]:
                k = odors.kicks(rates, seed, p.dt, round(proto["odor_ms"] / p.dt))
                r = sim.run(
                    Wx, cells, duration_ms=proto["duration_ms"], p=p, kicks=k, gap=gap
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
    verdict = decide(table, d["sparse_max"], d["overlap_max"], d.get("sparse_min", 0.0))
    out = {"table": table, "verdict": verdict}
    if "coupling" in doc:
        out["prediction"] = least_coupling(table, doc)
    return out


def least_coupling(table: pd.DataFrame, doc: dict) -> dict:
    """Per base arm, the smallest eLN-PN coupling of the grid whose arm is within, or None:
    the model's prediction of the coupling the fly would need."""
    d = doc["decides"]
    ok = set(
        decide(table, d["sparse_max"], d["overlap_max"], d.get("sparse_min", 0.0))
        .removeprefix("within: ")
        .split(", ")
    )
    out = {}
    for base in doc["coupling"]["bases"]:
        hits = [k for name, b, k in coupled_arms(doc) if b == base and name in ok]
        out[base] = min(hits) if hits else None
    return out


def stimuli(neurons: pd.DataFrame, proto: dict, data_dir: Path | None) -> dict:
    """Stimulated neurons and their Poisson rates per odor: every ORN of each responding
    type at the lock's rate times its DoOR response, or one ORN type at one rate."""
    out = {}
    if proto.get("odor_source") == "door":
        odors.fetch(data_dir)
        responses, mappings, odor_table = odors.tables(data_dir)
        orn = neurons["type"].dropna()
        types = set(orn[orn.str.startswith("ORN_")])
        for name in proto["odors"]:
            v = odors.vector(responses, mappings, odor_table, name, types)
            out[name] = odors.stimulus(
                neurons, odors.per_type(v), proto["rate_at_response_1_hz"]
            )
        return out
    for name, n in zip(proto["odors"], proto["odor_n"], strict=True):
        got = data.resolve(neurons, name)
        if got.size != n:
            raise SparsenessError(f"{name} has {got.size} neurons, the lock says {n}")
        out[name] = (got, np.full(got.size, proto["rate_hz"]))
    return out


def run(
    neurons: pd.DataFrame, edges: pd.DataFrame, data_dir: Path | None = None
) -> dict:
    doc = assert_matches_code()
    proto = doc["protocol"]
    idx = {}
    apl = data.resolve(neurons, proto["apl"])
    if apl.size != proto["apl_n"]:
        raise SparsenessError(
            f"APL has {apl.size} neurons, the lock says {proto['apl_n']}"
        )
    idx[proto["apl"]] = apl
    idx["stimuli"] = stimuli(neurons, proto, data_dir)
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
    if "coupling" in doc:
        idx["eln"], idx["sisters"] = gap_pairs(neurons, edges, idx)
    return protocol(sim.network(neurons, edges, sim.Params()), idx, doc)
