"""Produce/compare short engineering states against the original v5 source.

Run this controller with PYTHONPATH pointing at the source being checked. --expected-source
is mandatory when producing a state, so accidentally importing another checkout fails.
This is numerical compatibility evidence, not a scored biological run or timing benchmark.
"""

import argparse
import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

LOCK = "2612483facfd85c1b24f606ae7a6d9ea734a1697f9d6b517bd3469c98613e21b"
MODE = "flymsg.gap/boundary-reset-v1"


def produce(a, parser):
    from flymsg import data, kc_sparseness, manifest, sim
    from flymsg.runtime import CpuRuntime

    source = manifest.git_info()
    if source != {"commit": a.expected_source, "dirty": False}:
        parser.error(f"expected clean source {a.expected_source}, imported {source}")
    if a.out.exists():
        parser.error("state output exists; choose a new path")
    doc = kc_sparseness.load()
    if doc["content_sha256"] != LOCK:
        parser.error("this controller requires the original v5 lock")
    before = manifest.dataset_info("malecns", a.data)
    neurons, edges = data.load(a.data, "malecns")
    proto, cls = doc["protocol"], neurons["class"].fillna("")
    idx = {
        "PN": np.flatnonzero((cls == proto["pn_class"]).to_numpy()),
        "ACH_LN": np.flatnonzero(
            (
                (cls == proto["ln_class"]) & (neurons["nt"] == proto["ln_transmitter"])
            ).to_numpy()
        ),
    }
    eln, sisters = kc_sparseness.gap_pairs(neurons, edges, idx)
    gap = kc_sparseness.measured_gap(eln, sisters, len(neurons), idx["ACH_LN"], 0.5)
    if "refractory_mode" in sim.Gap.__dataclass_fields__:
        if kc_sparseness.electrical_semantics(doc) != MODE:
            parser.error("v5 no longer selects the original boundary numerical mode")
        gap = replace(gap, refractory_mode="boundary")
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    stim = data.resolve(neurons, "ORN_DM1")
    kicks = sim.poisson_kicks(1357, 100, p.dt, 300, len(stim))
    rt = CpuRuntime(W, stim, steps=500, kicks=kicks, p=p, per_bin=100, gap=gap)
    rt.advance_to(217)
    rt.advance_to(500)
    state = rt.snapshot()
    after = manifest.dataset_info("malecns", a.data)
    if before != after or source != manifest.git_info():
        parser.error("source or dataset changed during the trial")
    meta = {
        "source": source,
        "dataset": {**before, "n_neurons": len(neurons), "n_edges": len(edges)},
        "packages": manifest.package_versions(),
        "params": asdict(p),
        "mode": MODE,
        "lock_sha256": LOCK,
        "steps": 500,
        "stimulus": "ORN_DM1",
        "seed": 1357,
        "input_steps": 300,
        "rate_hz": 100,
        "spike_ms": 0.5,
        "chemical_contacts": "intact",
        "kicks_sha256": hashlib.sha256(kicks.tobytes()).hexdigest(),
        "coupled_spikes": int(state["counts"][:, rt._gap[0]].sum()),
        "scope": "short engineering compatibility trial; not a scored biological run",
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("xb") as stream:
        np.savez(stream, **state, _metadata=np.array(json.dumps(meta)))
    print(
        json.dumps(
            {
                "source": source,
                "arrays": len(state),
                "coupled_spikes": meta["coupled_spikes"],
            }
        )
    )


def compare(a, parser):
    if a.report.exists():
        parser.error("verification report exists; choose a new path")
    with (
        np.load(a.compare[0], allow_pickle=False) as baseline,
        np.load(a.compare[1], allow_pickle=False) as current,
    ):
        bm, cm = (
            json.loads(str(baseline["_metadata"])),
            json.loads(str(current["_metadata"])),
        )
        if set(baseline.files) != set(current.files):
            parser.error("state field sets differ")
        for key in (
            "dataset",
            "packages",
            "params",
            "mode",
            "lock_sha256",
            "steps",
            "stimulus",
            "seed",
            "input_steps",
            "rate_hz",
            "spike_ms",
            "chemical_contacts",
            "kicks_sha256",
        ):
            if bm[key] != cm[key]:
                parser.error(f"trial invariant differs: {key}")
        if not bm["coupled_spikes"] or bm["coupled_spikes"] != cm["coupled_spikes"]:
            parser.error("trial did not reproduce coupled spiking")
        arrays = []
        for name in sorted(k for k in baseline.files if k != "_metadata"):
            left, right = baseline[name], current[name]
            if (
                left.shape != right.shape
                or left.dtype != right.dtype
                or left.tobytes() != right.tobytes()
            ):
                parser.error(f"state bytes differ: {name}")
            arrays.append(
                {
                    "name": name,
                    "shape": list(left.shape),
                    "dtype": left.dtype.str,
                    "sha256": hashlib.sha256(left.tobytes()).hexdigest(),
                }
            )
        report = {
            "schema": "flymsg.engine-parity/v1",
            "baseline": bm,
            "current": cm,
            "arrays": arrays,
            "byte_identical": True,
            "verified_at": datetime.now(UTC).isoformat(),
        }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    with a.report.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(f"exact byte parity: {len(arrays)} arrays; {a.report}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--expected-source")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path)
    parser.add_argument("--report", type=Path)
    a = parser.parse_args()
    if a.compare:
        if a.report is None or any(
            v is not None for v in (a.data, a.expected_source, a.out)
        ):
            parser.error("comparison takes --compare A B --report FILE only")
        compare(a, parser)
    else:
        if (
            any(v is None for v in (a.data, a.expected_source, a.out))
            or a.report is not None
        ):
            parser.error(
                "production takes --data DIR --expected-source COMMIT --out FILE"
            )
        produce(a, parser)


if __name__ == "__main__":
    main()
