"""Kenyon cell sparseness diagnostic (issue #95). The YAML file is the lock.

Arms differ only in the weight matrix: each removes the fast effect of named synapse
classes (KC -> KC, metabotropic in the fly, Manoim et al. 2022; APL -> KC; cholinergic
antennal-lobe local neuron -> projection neuron, electrical in the fly, Yaksi & Wilson 2010).
Each arm drives two ORN types and counts the responding Kenyon cells, those shared between
the odors, and the projection neurons that spike. The default model is not changed by the
result. Version 1 (arms A-D) ran from b096b4a; version 2 runs arms A, B, E, F; version 4
(b1116af) scanned a symmetric eLN-PN coupling without spikelets. Version 5 (issue #85) gives
arms E and F the measured, asymmetric eLN-PN and sister-PN coupling (`sim.Gap`), with eLN
spikes crossing as spikelets of the measured amplitude and a scanned duration. Version 6
restricts the eLNs to the types Eckstein et al. 2024 liken to them (`protocol.eln_sets`), one
pass of arms E and F and of the coupled arms per set; the other cholinergic local neurons stay
chemical.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import (
    data,
    electrical,
    eye,
    locks,
    odors,
    plasticity,
    prereg,
    progress,
    sim,
)

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "kc_sparseness.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "d5343b238f61e3bd9cb51ed8fc21981da7a418ad5fdfe7133fe201899c33caba",  # arms A-D, odors ORN_VA1d and ORN_DL3, seeds 60-62
    2: "bcfef9af52861dfd0a903c8b01aded5f8f504b645cdf6933d91b01ae47350322",  # arms A, B, E, F (cholinergic LN -> PN), seeds 70-72
    3: "0a6b0ec6d7b8829cf9aa35de0c945841259a3502ec59e70bd569e1dfd54e0bd2",  # Hige odors from DoOR, lower bound, seeds 80-82
    4: "72059246ade98ec69b49ce32bac587e0f6f52d39b2cb747c962fb4177694af67",  # E and F with electrical eLN-PN coupling 0-1 and sister PNs at 0.013, seeds 83-85
    5: "2612483facfd85c1b24f606ae7a6d9ea734a1697f9d6b517bd3469c98613e21b",  # measured asymmetric eLN-PN coupling, eLN spikelets 0-2 ms, seeds 86-88
    6: "bf1ae62f9b563e52df8523eefccbc7f3253c0ab457621969cf3e8ee77c1f6b9b",  # eLNs restricted to lLN2T (and lLN2T + lLN1_bc), seeds 89-91
    7: "de4274eb0bd689aefe8c9bcc9318eb40fbcdb688b9da61980a559f6c040896ef",  # v6 with the boundary reset of v5, qualified against the continuous clamp, seeds 92-94
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
SPENT_SEEDS = {
    1: (60, 61, 62),
    2: (70, 71, 72),
    3: (80, 81, 82),
    4: (83, 84, 85),
    5: (86, 87, 88),
    6: (89, 90, 91),
}
# MaleCNS types Eckstein et al. 2024 (STAR Methods, Fig S5F) liken to the cholinergic eLNs by
# soma position and morphology (lLN2T_abc), and the neighbouring lLN1_bc
ELN_SETS = {
    "lLN2T": ["lLN2T_a", "lLN2T_b", "lLN2T_c"],
    "lLN2T+lLN1_bc": ["lLN2T_a", "lLN2T_b", "lLN2T_c", "lLN1_bc"],
}
# Coupling coefficients for hyperpolarizing steps, which pass the electrical component only,
# measured from the bar heights: homotypic PN pairs, Kazama & Wilson 2009 Fig 7d; eLN -> PN
# and PN -> eLN, Yaksi & Wilson 2010 Fig 4C and 4F (control pairs of the shakB2 comparison)
SISTER_PN_CC = 0.013
ELN_TO_PN_CC = 0.0021
PN_TO_ELN_CC = 0.0039
# full-sized eLN spikes, Yaksi & Wilson 2010 (text, Fig 2D)
ELN_SPIKE_MV = 40.0
HIGE_ODORS = ["3-octanol", "4-methylcyclohexanol"]


class SparsenessError(ValueError):
    """The sparseness protocol drifted from the locked version."""


def electrical_semantics(doc: dict) -> str | None:
    """Frozen versions retain the integrator fixed before their runs, not today's default."""
    if "coupling" not in doc:
        return None
    historical = {
        4: "flymsg.gap/explicit-first-order-v1",
        5: electrical.BOUNDARY_SEMANTICS,
        6: electrical.SEMANTICS,
    }
    return historical.get(doc["version"], doc.get("electrical_semantics"))


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
        sourced = (SISTER_PN_CC, ELN_TO_PN_CC, PN_TO_ELN_CC, ELN_SPIKE_MV)
        locked = (
            c["sister_cc"],
            c["eln_to_pn_cc"],
            c["pn_to_eln_cc"],
            c["eln_spike_mv"],
        )
        if locked != sourced or not set(c["bases"]) <= set(doc["arms"]):
            raise SparsenessError("the coupling is not the sourced one")
        if c["spike_ms"] != sorted(set(c["spike_ms"])) or min(c["spike_ms"]) != 0.0:
            raise SparsenessError("the spike durations must start at 0 and increase")
    sets = {k: v["types"] for k, v in proto.get("eln_sets", {}).items()}
    if sets and sets != ELN_SETS:
        raise SparsenessError("the eLN sets are not Eckstein et al.'s types")
    # a new electrical lock names its integrator; the boundary reset only with the
    # qualification against the continuous clamp it rests on (docs/adr-gap-refractory.md)
    new_electrical = "coupling" in doc and doc["version"] >= 6
    named = doc.get("electrical_semantics")
    if new_electrical and named not in {
        electrical.SEMANTICS,
        electrical.BOUNDARY_SEMANTICS,
    }:
        raise SparsenessError("a new electrical lock names the current integrator")
    if (
        new_electrical
        and named == electrical.BOUNDARY_SEMANTICS
        and not doc.get("boundary_qualification")
    ):
        raise SparsenessError("the boundary reset needs its qualification")
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
            f"+ measured coupling, eLN spikelets of "
            f"{', '.join(f'{w:g}' for w in doc['coupling']['spike_ms'])} ms)"
            if "coupling" in doc
            else ""
        )
        + (
            "; eLN sets "
            + ", ".join(f"{k} ({v['n']})" for k, v in p["eln_sets"].items())
            if "eln_sets" in p
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


def eln_sets(doc: dict) -> list[str | None]:
    """The eLN sets of the lock, or [None]: the whole cholinergic ALLN class (v1-v5)."""
    return list(doc["protocol"].get("eln_sets", {})) or [None]


def set_arm(arm: str, eln_set: str | None) -> str:
    """An arm's name for an eLN set: arms that touch eLN synapses carry the set."""
    if eln_set is None or "ach_ln_pn" not in ARM_CLASSES[arm]:
        return arm
    return f"{arm}/{eln_set}"


def plain_arms(doc: dict) -> list[tuple[str, str, str | None]]:
    """(name, arm, eLN set) of every uncoupled arm, in lock order, each name once."""
    out, seen = [], set()
    for s in eln_sets(doc):
        for arm in doc["arms"]:
            name = set_arm(arm, s)
            if name not in seen:
                seen.add(name)
                out.append((name, arm, s))
    return out


def coupled_arms(doc: dict) -> list[tuple[str, str, float]]:
    """(name, base arm name, spikelet duration in ms) of every coupled arm, in lock order."""
    c = doc.get("coupling")
    if not c:
        return []
    return [
        (f"{set_arm(b, s)}+spike{w:g}ms", set_arm(b, s), w)
        for s in eln_sets(doc)
        for b in c["bases"]
        for w in c["spike_ms"]
    ]


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


def measured_gap(
    eln: pd.DataFrame,
    sisters: pd.DataFrame,
    n: int,
    ach_ln: np.ndarray,
    spike_ms: float,
) -> sim.Gap:
    """Each eLN-PN pair coupled as measured on each side (c / (1 - c) of the coupling
    coefficient towards that cell), sister PNs symmetric at Kazama & Wilson's coefficient,
    and, for a positive `spike_ms`, eLN spikes crossing as spikelets of the measured
    amplitude (PN spikes do not cross: their amplitude at the junction is not measured)."""

    def k(c: float) -> float:
        return c / (1.0 - c)

    spike = None
    if spike_ms > 0:
        spike = np.zeros(n)
        spike[ach_ln] = ELN_SPIKE_MV
    return sim.Gap(
        i=np.r_[eln["pn"].to_numpy(), sisters["i"].to_numpy()].astype(np.int64),
        j=np.r_[eln["ln"].to_numpy(), sisters["j"].to_numpy()].astype(np.int64),
        coupling=np.r_[
            np.full(len(eln), k(ELN_TO_PN_CC)), np.full(len(sisters), k(SISTER_PN_CC))
        ],
        coupling_back=np.r_[
            np.full(len(eln), k(PN_TO_ELN_CC)), np.full(len(sisters), k(SISTER_PN_CC))
        ],
        spike_mv=spike,
        spike_ms=spike_ms if spike_ms > 0 else None,
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


def within_arms(
    table: pd.DataFrame, sparse_max: float, overlap_max: float, sparse_min: float = 0.0
) -> list[str]:
    """The arms whose two odors are within the measured bounds, in table order."""
    return [
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


def decide(
    table: pd.DataFrame, sparse_max: float, overlap_max: float, sparse_min: float = 0.0
) -> str:
    """`within: <arms>`, or `none`."""
    ok = within_arms(table, sparse_max, overlap_max, sparse_min)
    return "within: " + ", ".join(ok) if ok else "none"


def protocol(
    W,
    idx: dict,
    doc: dict,
    steps: progress.Steps | None = None,
    report: progress.Progress | None = None,
) -> dict:
    """Every arm; `steps` stores each finished arm so an interrupted run resumes, `report`
    counts simulations."""
    proto = doc["protocol"]
    p = sim.Params()
    steps = steps or progress.Steps(None, doc["content_sha256"])
    kcs, pns = idx["KC"], idx["PN"]
    bins = round(proto["odor_ms"] / 10.0)
    rows = []
    # per eLN set: its own ACH_LN and eLN-PN pairs (idx["sets"]), or the whole class
    sets = idx.get("sets") or {None: idx}
    weights, owner = {}, {}
    for name, arm, s in plain_arms(doc):
        weights[name] = arms(W, {**idx, **sets[s]}, [arm])[arm]
        owner[name] = s
    runs = [(arm, Wx, None) for arm, Wx in weights.items()]
    n = W.shape[0]
    for name, base, width in coupled_arms(doc):
        own = sets[owner[base]]
        gap = measured_gap(own["eln"], idx["sisters"], n, own["ACH_LN"], width)
        mode = (
            "boundary"
            if electrical_semantics(doc) == electrical.BOUNDARY_SEMANTICS
            else "continuous"
        )
        gap = replace(gap, refractory_mode=mode)
        runs.append((name, weights[base], gap))
    per_arm = len(proto["odors"]) * len(proto["seeds"])

    def one_arm(arm, Wx, gap) -> dict[str, pd.DataFrame]:
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
                if report is not None:
                    report.step(note=f"{arm} {odor} seed {seed}")
            resp.append(responders(per_seed, 2))
            pn_share.append(float(responders(pn_seed, 2).mean()) if pns.size else 0.0)
        n1, n2, both = (
            int(resp[0].sum()),
            int(resp[1].sum()),
            int((resp[0] & resp[1]).sum()),
        )
        row = pd.DataFrame(
            [
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
            ]
        )
        return {"arm": row}

    for arm, Wx, gap in runs:
        got, fresh = steps.get(
            # a step name has no "/": E/lLN2T is stored as arm-E.lLN2T
            f"arm-{arm.replace('/', '.')}",
            lambda a=arm, w=Wx, g=gap: one_arm(a, w, g),
        )
        if not fresh and report is not None:
            report.step(per_arm, note=f"{arm} resumed", resumed=True)
        rows.append(got["arm"])
    table = pd.concat(rows, ignore_index=True)
    d = doc["decides"]
    verdict = decide(table, d["sparse_max"], d["overlap_max"], d.get("sparse_min", 0.0))
    return {"table": table, "verdict": verdict}


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


def n_runs(doc: dict) -> int:
    """Simulations of the locked protocol: arms x odors x seeds."""
    proto = doc["protocol"]
    arms_n = len(plain_arms(doc)) + len(coupled_arms(doc))
    return arms_n * len(proto["odors"]) * len(proto["seeds"])


def run(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    data_dir: Path | None = None,
    steps: progress.Steps | None = None,
    report: progress.Progress | None = None,
) -> dict:
    doc = assert_matches_code()
    # v4 explicitly locks the first-order integrator; it cannot be silently rescored
    # with the continuous-clamp model. A new registered lock must name the new semantics.
    if "coupling" in doc and electrical_semantics(doc) not in {
        electrical.SEMANTICS,
        electrical.BOUNDARY_SEMANTICS,
    }:
        raise SparsenessError(
            "this electrical lock names an older integrator; preserve its results and "
            "register a new lock with electrical_semantics=" + electrical.SEMANTICS
        )
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
    if "eln_sets" in proto:
        idx["sets"] = {}
        for name, spec in proto["eln_sets"].items():
            members = np.flatnonzero(neurons["type"].isin(spec["types"]).to_numpy())
            if members.size != spec["n"] or not np.isin(members, idx["ACH_LN"]).all():
                raise SparsenessError(
                    f"eLN set {name} has {members.size} neurons, the lock says "
                    f"{spec['n']}, all cholinergic ALLN"
                )
            idx["sets"][name] = {"ACH_LN": members}
    if "coupling" in doc:
        for own in (idx.get("sets") or {None: idx}).values():
            own["eln"], idx["sisters"] = gap_pairs(neurons, edges, {**idx, **own})
    return protocol(sim.network(neurons, edges, sim.Params()), idx, doc, steps, report)
