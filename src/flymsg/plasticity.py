"""Dopamine-gated depression at Kenyon cell -> MBON11 synapses (issue #85). The YAML file is
the lock. Optional: nothing else in flymsg applies it, and `sim.Params` is unchanged.

The measured depression (Hige et al. 2015) lasts at least 40 min, so it acts between trials,
not inside one: a pairing run records which Kenyon cells spike before a dopamine pulse, the
rule scales their synapses onto MBON11 in the weight matrix, and the test runs use the new
matrix. The kernel is not changed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

from flymsg import benchmarks, data, locks, prereg, sim

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "mb_plasticity.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "ca75a5247ff4f5081f1034bbbf939636181829f5dcb2ad11fae6f1fb13610b50",  # Hige 2015 depression on KC -> MBON11; CS+ ORN_VA1d, CS- ORN_DL3; seeds 50-52
}
_DECIDES = ("undetermined", "consistent", "inconsistent", "bounds_from")


class PlasticityError(ValueError):
    """The plasticity protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    locks.check(doc, VERSION_HASHES, PlasticityError, "plasticity protocol")
    return doc


def bounds(source: dict) -> tuple[float, float]:
    """Smallest CS+ drop and largest CS- drop consistent with the fly: mean -/+ 2 SD,
    SD = SEM x sqrt(n)."""
    root_n = np.sqrt(source["spike_n"])
    low = -source["cs_plus_spike_change"] - 2 * source["cs_plus_spike_sem"] * root_n
    high = -source["cs_minus_spike_change"] + 2 * source["cs_minus_spike_sem"] * root_n
    return round(float(low), 3), round(float(high), 3)


def assert_matches_code(doc: dict | None = None) -> dict:
    """The rule's numbers are the source's, and the odors are not held out."""
    doc = assert_locked() if doc is None else doc
    src, rule, proto = doc["source"], doc["rule"], doc["protocol"]
    if abs(rule["factor"] - (1 + src["epsc_charge_change"])) > 1e-9:
        raise PlasticityError("the factor is not the measured charge change")
    first = src["pairing"]
    if "0.2 s" not in first or rule["pulses_ms"] != [200.0, 700.0, 1200.0, 1700.0]:
        raise PlasticityError("the pulses are not the measured pairing protocol")
    if rule["window_ms"] != 800.0:
        raise PlasticityError("the window is not the longest measured forward lag")
    if proto["odor_ms"] != 1000.0 or proto["pairing_duration_ms"] <= max(
        rule["pulses_ms"]
    ):
        raise PlasticityError("the pairing run must hold every pulse")
    held = benchmarks.load()
    held_out = {held["confirmatory"]["stimulus"], held["reported"]["stimulus"]}
    if {proto["cs_plus"], proto["cs_minus"]} & held_out:
        raise PlasticityError("an odor is in the held-out manifest")
    if tuple(doc["decides"]) != _DECIDES:
        raise PlasticityError("the deciding outcomes changed")
    if bounds(src) != (0.498, 0.646):
        raise PlasticityError("the bounds are not the measured mean -/+ 2 SD")
    for name, row in doc["reported"].items():
        if row["decides"] is not False:
            raise PlasticityError(f"reported row {name} must not decide")
    if doc["defaults_changed"] is not False:
        raise PlasticityError("the rule never changes the simulator defaults")
    return doc


def summary(doc: dict | None = None) -> str:
    """The frozen protocol. Printing it does not simulate."""
    doc = assert_matches_code() if doc is None else doc
    r, p = doc["rule"], doc["protocol"]
    low, high = bounds(doc["source"])
    return (
        f"mb-plasticity v{doc['version']} (issue #{doc['issue']}): KC -> {r['post']} x "
        f"{r['factor']:g} for Kenyon cells spiking up to {r['window_ms']:g} ms before a "
        f"{r['dan']} pulse at {', '.join(f'{t:g}' for t in r['pulses_ms'])} ms; "
        f"CS+ {p['cs_plus']}, CS- {p['cs_minus']} at {p['rate_hz']:g} Hz for "
        f"{p['odor_ms']:g} ms; seeds {', '.join(map(str, p['seeds']))}; consistent if "
        f"CS+ drops >= {low} and CS- <= {high}"
    )


def eligible(traced: np.ndarray, pulses_ms, window_ms: float, dt: float) -> np.ndarray:
    """Columns of `traced` (steps x cells spike bits) that spike in (pulse - window, pulse]
    of at least one pulse."""
    hit = np.zeros(traced.shape[1], dtype=bool)
    w = round(window_ms / dt)
    for t in pulses_ms:
        p = round(t / dt)
        hit |= traced[max(0, p - w + 1) : p + 1].any(axis=0)
    return hit


def depress(
    W: sparse.csc_matrix, pre: np.ndarray, post: np.ndarray, factor: float
) -> sparse.csc_matrix:
    """A copy of W (post x pre) with the synapses from `pre` onto `post` scaled by `factor`."""
    out = W.copy()
    col = np.repeat(np.arange(out.shape[1]), np.diff(out.indptr))
    hit = np.isin(col, pre) & np.isin(out.indices, post)
    out.data[hit] = (out.data[hit] * np.float32(factor)).astype(out.data.dtype)
    return out


def decide(
    pre: dict, post: dict, low: float, high: float, min_response: float
) -> tuple[str, float, float]:
    """`pre` and `post` map CS+ / CS- to MBON11 counts per seed. Returns the verdict and the
    two relative drops."""
    if min(np.mean(pre["cs_plus"]), np.mean(pre["cs_minus"])) < min_response:
        return "undetermined", float("nan"), float("nan")
    drop = {k: 1 - np.mean(post[k]) / np.mean(pre[k]) for k in ("cs_plus", "cs_minus")}
    ok = (
        drop["cs_plus"] >= low
        and drop["cs_minus"] <= high
        and drop["cs_plus"] > drop["cs_minus"]
    )
    return (
        "consistent" if ok else "inconsistent",
        float(drop["cs_plus"]),
        float(drop["cs_minus"]),
    )


def protocol(W, idx: dict, doc: dict) -> dict:
    """Every seed in the lock's order. `idx` maps the locked names to neuron indices."""
    rule, proto = doc["rule"], doc["protocol"]
    p = sim.Params()
    kcs, mbon = idx["KC"], idx[rule["post"]]
    odor_bins = round(proto["odor_ms"] / 10.0)

    def test(Wx, odor, seed):
        r = sim.run(
            Wx,
            idx[odor],
            proto["rate_hz"],
            proto["test_duration_ms"],
            proto["odor_ms"],
            p,
            seed,
        )
        return int(r.counts[:odor_bins, mbon].sum()), r.counts[:odor_bins, kcs].any(
            axis=0
        )

    rows = []
    for seed in proto["seeds"]:
        before, fired = {}, {}
        for key in ("cs_plus", "cs_minus"):
            before[key], fired[key] = test(W, proto[key], seed)
        pairing = sim.run(
            W,
            idx[proto["cs_plus"]],
            proto["rate_hz"],
            proto["pairing_duration_ms"],
            proto["odor_ms"],
            p,
            seed,
            trace=kcs,
        )
        tagged = kcs[
            eligible(pairing.traced, rule["pulses_ms"], rule["window_ms"], p.dt)
        ]
        Wp = depress(W, tagged, mbon, rule["factor"])
        after = {key: test(Wp, proto[key], seed)[0] for key in ("cs_plus", "cs_minus")}
        rows.append(
            {
                "seed": seed,
                "cs_plus_before": before["cs_plus"],
                "cs_minus_before": before["cs_minus"],
                "cs_plus_after": after["cs_plus"],
                "cs_minus_after": after["cs_minus"],
                "eligible_kcs": int(tagged.size),
                "kcs_cs_plus": int(fired["cs_plus"].sum()),
                "kcs_cs_minus": int(fired["cs_minus"].sum()),
                "kcs_both": int((fired["cs_plus"] & fired["cs_minus"]).sum()),
            }
        )
    table = pd.DataFrame(rows)
    verdict, plus, minus = decide(
        {k: table[f"{k}_before"].tolist() for k in ("cs_plus", "cs_minus")},
        {k: table[f"{k}_after"].tolist() for k in ("cs_plus", "cs_minus")},
        *bounds(doc["source"]),
        proto["min_response"],
    )
    return {
        "table": table,
        "verdict": verdict,
        "cs_plus_drop": plus,
        "cs_minus_drop": minus,
    }


def run(neurons: pd.DataFrame, edges: pd.DataFrame) -> dict:
    """The frozen protocol on MaleCNS at the default parameters."""
    doc = assert_matches_code()
    rule, proto = doc["rule"], doc["protocol"]
    expect = {
        rule["post"]: rule["post_n"],
        rule["dan"]: rule["dan_n"],
        proto["cs_plus"]: proto["cs_plus_n"],
        proto["cs_minus"]: proto["cs_minus_n"],
    }
    idx = {}
    for name, n in expect.items():
        got = data.resolve(neurons, name)
        if got.size != n:
            raise PlasticityError(f"{name} has {got.size} neurons, the lock says {n}")
        idx[name] = got
    idx["KC"] = np.flatnonzero(
        neurons["type"].fillna("").str.contains(rule["pre"]).to_numpy()
    )
    W = sim.network(neurons, edges, sim.Params())
    return protocol(W, idx, doc)
