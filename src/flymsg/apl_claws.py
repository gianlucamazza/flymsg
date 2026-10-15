"""APL and the odor contrast at Kenyon cell claws (issue #85).

The YAML file is the lock. Two arms differ only in the weight matrix: `on` is the default
model, `off` removes every synapse from the APL neurons, as TNT blocks APL release onto all
its targets. Each arm is driven by the two DoOR odors of the KC sparseness locks; per seed
and odor the KCs' mean depolarization over the odor window stands for the claws and the
ALPNs' spikes for the PN boutons. The verdict compares each readout's own OCT/MCH contrast
(Prisco et al. 2021): directions only, never amplitudes. The defaults do not change.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import (
    data,
    draws,
    evidence,
    kc_sparseness,
    locks,
    odors,
    parallel,
    plasticity,
    sim,
)
from flymsg.runtime import CpuRuntime

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "apl_claws.yaml"

VERSION_HASHES = {
    1: "3160817193dc193a6a61de1c633f10410496f66fae6fa9bbaf3c5cc6baae519b",
}
ARMS = ["on", "off"]
# protocol fields that must be the KC sparseness lock's
SHARED = (
    "odor_source",
    "odors",
    "rate_at_response_1_hz",
    "odor_ms",
    "duration_ms",
    "kc",
    "apl",
    "apl_n",
    "pn_class",
)


class AplClawsError(ValueError):
    """The APL claw protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return locks.prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, AplClawsError, "APL claw protocol")


def assert_matches_code(doc: dict | None = None) -> dict:
    """The odor protocol and neuron sets are the KC sparseness lock's, the seeds are
    fresh, the arms are the implemented ones and the evidence records exist."""
    doc = assert_locked() if doc is None else doc
    proto = doc["protocol"]
    kc = kc_sparseness.load()["protocol"]
    if any(proto[k] != kc[k] for k in SHARED):
        raise AplClawsError("the odor protocol is not the KC sparseness lock's")
    spent = {s for seeds in kc_sparseness.SPENT_SEEDS.values() for s in seeds}
    if set(proto["seeds"]) & (spent | set(kc["seeds"])):
        raise AplClawsError("seeds must be disjoint from every KC sparseness version's")
    if len(set(proto["seeds"])) != len(proto["seeds"]):
        raise AplClawsError("seeds must be distinct")
    if list(doc["arms"]) != ARMS:
        raise AplClawsError("the arms are not on and off")
    if doc["claim"]["scored"] is not True:
        raise AplClawsError("the claw contrast is a score")
    if doc["defaults_changed"] is not False:
        raise AplClawsError("the benchmark never changes the defaults")
    if evidence.check_lock(doc, evidence.load(), "apl_claws") != doc["evidence"]:
        raise AplClawsError("the evidence records are not the lock's")
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    p = doc["protocol"]
    return (
        f"apl-claws v{doc['version']} (issue #{doc['issue']}): arms on (default) and off "
        f"(every synapse from the {p['apl_n']} {p['apl']} neurons removed); odors "
        f"{', '.join(p['odors'])} (DoOR, {p['rate_at_response_1_hz']:g} Hz at response 1) "
        f"for {p['odor_ms']:g} ms; seeds {', '.join(map(str, p['seeds']))}; OCT/MCH "
        "contrast of KC depolarization per arm against ALPN spikes; pass if raises and "
        "restores hold on the seed medians"
    )


def arms(W, apl: np.ndarray) -> dict:
    """The weight matrix (post x pre) of each arm: `off` zeroes the APL columns, every
    synapse whose presynaptic neuron is an APL; the APL's inputs stay."""
    return {
        "on": W,
        "off": plasticity.depress(W, apl, np.arange(W.shape[0]), 0.0),
    }


def neuron_sets(neurons: pd.DataFrame, proto: dict) -> dict:
    """The KCs, the APL neurons and the ALPNs, resolved as in the KC sparseness lock."""
    apl = data.resolve(neurons, proto["apl"])
    if apl.size != proto["apl_n"]:
        raise AplClawsError(
            f"APL has {apl.size} neurons, the lock says {proto['apl_n']}"
        )
    kcs = np.flatnonzero(
        neurons["type"].fillna("").str.contains(proto["kc"]).to_numpy()
    )
    cls = neurons["class"].fillna("")
    pns = np.flatnonzero((cls == proto["pn_class"]).to_numpy())
    return {"KC": kcs, "APL": apl, "PN": pns}


def respond(W, stim, rates, kcs, pns, seed: int, proto: dict, p: sim.Params) -> dict:
    """One run: the readouts of one arm, odor and seed."""
    steps = round(proto["duration_ms"] / p.dt)
    odor_steps = round(proto["odor_ms"] / p.dt)
    kicks = odors.kicks(rates, seed, p.dt, odor_steps)
    # one count bin ends where the odor does, so the window's spikes are whole bins
    per_bin = math.gcd(odor_steps, steps)
    rt = CpuRuntime(W, stim, steps=steps, kicks=kicks, p=p, per_bin=per_bin)
    # The potential is only exposed at step boundaries, so each KC's potential above rest
    # is read after every step of the window and summed in float64: exact, without storing
    # the (steps x KCs) trace. `read` gathers four arrays of the KCs only, small next to the
    # step over the whole network.
    depol = np.zeros(kcs.size)
    for k in range(odor_steps):
        rt.advance_to(k + 1)
        depol += rt.read(kcs)["v"].astype(np.float64) - p.v_rest
    rt.advance_to(steps)
    window = rt.result().counts[: odor_steps // per_bin]
    return {
        "claw_mv": float(depol.mean() / odor_steps) if kcs.size else 0.0,
        "bouton_spikes": int(window[:, pns].sum()),
        "kc_spiking": float((window[:, kcs].sum(axis=0) > 0).mean())
        if kcs.size
        else 0.0,
    }


def _job(job: tuple) -> list[dict]:
    """One simulation: `(arm, odor, seed)`."""
    (weights, stimuli, kcs, pns, doc), _checkpoint, _meta = parallel.context()
    arm, odor, seed = job
    stim, rates = stimuli[odor]
    r = respond(
        weights[arm], stim, rates, kcs, pns, int(seed), doc["protocol"], sim.Params()
    )
    return [{"arm": arm, "odor": odor, "seed": int(seed), **r}]


def jobs(doc: dict) -> list[tuple]:
    """Tuples, as draws.map_jobs keys its checkpoint: arm, odor, seed."""
    proto = doc["protocol"]
    return [
        (arm, odor, seed)
        for arm in doc["arms"]
        for odor in proto["odors"]
        for seed in proto["seeds"]
    ]


def run(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    data_dir: Path | None = None,
    workers: int = 1,
    checkpoint: Path | None = None,
) -> pd.DataFrame:
    doc = assert_matches_code()
    proto = doc["protocol"]
    idx = neuron_sets(neurons, proto)
    stimuli = kc_sparseness.stimuli(neurons, proto, data_dir)
    weights = arms(sim.network(neurons, edges, sim.Params()), idx["APL"])
    meta = {"version": doc["version"], "sha256": doc["content_sha256"]}
    ctx = (weights, stimuli, idx["KC"], idx["PN"], doc)
    rows = draws.map_jobs(_job, jobs(doc), workers, ctx, checkpoint, meta)
    return pd.DataFrame(rows)


def contrast(oct_: float, mch: float) -> float:
    """(x_OCT - x_MCH) / (x_OCT + x_MCH); NaN when both are zero."""
    total = oct_ + mch
    return (oct_ - mch) / total if total != 0 else float("nan")


def judge(cells: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Per seed the readouts and contrasts, then a `median` row: the seed medians, on
    which the relations are scored; the per-seed rows say where each relation holds."""
    oct_, mch = doc["protocol"]["odors"]
    t = cells.set_index(["arm", "odor", "seed"]).sort_index()
    rows = []
    for seed in doc["protocol"]["seeds"]:
        row: dict = {"seed": str(seed)}
        for arm in doc["arms"]:
            for tag, odor in (("oct", oct_), ("mch", mch)):
                r = t.loc[(arm, odor, seed)]
                row[f"claw_{arm}_{tag}"] = float(r["claw_mv"])
                row[f"kc_spiking_{arm}_{tag}"] = float(r["kc_spiking"])
                if arm == "on":
                    row[f"bouton_{tag}"] = float(r["bouton_spikes"])
        row["c_on"] = contrast(row["claw_on_oct"], row["claw_on_mch"])
        row["c_off"] = contrast(row["claw_off_oct"], row["claw_off_mch"])
        row["c_pn"] = contrast(row["bouton_oct"], row["bouton_mch"])
        rows.append(row)
    per_seed = pd.DataFrame(rows)
    median = {"seed": "median", **per_seed.drop(columns="seed").median().to_dict()}
    judged = pd.DataFrame([*rows, median])
    judged["raises"] = judged["c_off"] > judged["c_on"]
    judged["restores"] = (judged["c_off"] - judged["c_pn"]).abs() < (
        judged["c_on"] - judged["c_pn"]
    ).abs()
    return judged


def no_go(judged: pd.DataFrame) -> bool:
    """The premise is absent: the PN contrast on the seed medians is not positive, or the
    claw depolarization is not positive for either odor in either arm (in any seed): a
    contrast of potentials at or below rest has no meaning."""
    seeds = judged[judged["seed"] != "median"]
    med = judged[judged["seed"] == "median"].iloc[0]
    claws = seeds[[c for c in judged.columns if c.startswith("claw_")]]
    return bool(not med["c_pn"] > 0 or (claws <= 0).any().any())


def verdict(judged: pd.DataFrame) -> str:
    """pass, partial, fail or uninformative, as the lock's score.verdict."""
    if no_go(judged):
        return "uninformative"
    med = judged[judged["seed"] == "median"].iloc[0]
    if not med["raises"]:
        return "fail"
    return "pass" if med["restores"] else "partial"


def describe(judged: pd.DataFrame) -> str:
    """The medians, each relation on them and the share of seeds in which it holds."""
    seeds = judged[judged["seed"] != "median"]
    med = judged[judged["seed"] == "median"].iloc[0]
    n = len(seeds)
    return (
        f"medians: c_on {med['c_on']:.4g}, c_off {med['c_off']:.4g}, "
        f"c_pn {med['c_pn']:.4g}; raises {bool(med['raises'])} "
        f"({int(seeds['raises'].sum())}/{n} seeds), restores {bool(med['restores'])} "
        f"({int(seeds['restores'].sum())}/{n} seeds); c_on sign "
        f"{'negative' if med['c_on'] < 0 else 'not negative'} (reported, not scored); "
        f"no-go {no_go(judged)}"
    )
