import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import compare, data, dimorphism, graph, sim, validate, viz

NG = "https://neuroglancer-demo.appspot.com/#!"


def ng_link(body_ids) -> str:
    state = {
        "layers": [
            {
                "type": "image",
                "source": "precomputed://gs://flyem-male-cns/em/em-clahe-jpeg",
                "name": "em",
            },
            {
                "type": "segmentation",
                "source": "precomputed://gs://flyem-male-cns/v1.0/segmentation",
                "segments": [str(b) for b in body_ids],
                "name": "neurons",
            },
        ],
        "layout": "3d",
    }
    return NG + urllib.parse.quote(json.dumps(state, separators=(",", ":")))


def label(neurons: pd.DataFrame, i: int) -> str:
    r = neurons.iloc[i]
    name = next((x for x in (r["instance"], r["type"]) if pd.notna(x)), "untyped")
    return f"{name} ({r['bodyId']}, {r['nt']}, {r['superclass']})"


def cmd_info(a, neurons, edges):
    idx = data.resolve(neurons, a.query)
    print(neurons.iloc[idx].drop(columns="sign").to_string(index=False))
    for up in (True, False):
        print(f"\n{'upstream' if up else 'downstream'} types:")
        print(graph.partners(neurons, edges, idx, upstream=up, top=a.top).to_string())
    print(f"\nneuroglancer: {ng_link(neurons['bodyId'].to_numpy()[idx])}")


def cmd_path(a, neurons, edges):
    src, dst = data.resolve(neurons, a.src), data.resolve(neurons, a.dst)
    # a route is identified by its cell types; untyped neurons count one by one
    groups = neurons["type"].fillna(neurons["bodyId"].astype(str)).to_numpy()
    paths = graph.alternative_paths(
        edges, len(neurons), src, dst, groups, a.alt, a.min_weight
    )
    if not paths:
        print("no path")
        return
    for r, path in enumerate(paths):
        if len(paths) > 1:
            print(f"route {r + 1}" + (" (avoiding the types above)" if r else ""))
        weights = [0, *graph.edge_weights(edges, path)]
        for k, (i, w) in enumerate(zip(path, weights)):
            hop = f"  --{w} syn-->  " if k else "  "
            print(f"{hop}{label(neurons, i)}")
        print(f"neuroglancer: {ng_link(neurons['bodyId'].to_numpy()[path])}\n")


def summarize(
    neurons: pd.DataFrame, results: list[sim.Result], stim: np.ndarray, superclass=None
) -> pd.DataFrame:
    """Per-type response across seeds.

    n: neurons of the type; p_active: share of seeds where any of them fired during the
    stimulus; hz/hz_sd: mean and across-seed SD of the type's mean rate during the stimulus
    (silent neurons included); latency_ms: median first spike of the type's earliest neuron;
    post_hz: mean rate after stimulus end (only with --stim-ms).
    """
    keep = np.ones(len(neurons), dtype=bool)
    keep[stim] = False
    if superclass:
        keep &= neurons["superclass"].isin(superclass).to_numpy()
    types = neurons["type"].fillna("untyped").to_numpy()[keep]
    r0 = results[0]
    post = r0.stim_ms + r0.bin_ms <= r0.duration_ms
    per_seed = []
    for r in results:
        df = pd.DataFrame(
            {
                "type": types,
                "hz": r.rate(0, r.stim_ms)[keep],
                "fired": r.counts[: round(r.stim_ms / r.bin_ms)].sum(axis=0)[keep] > 0,
                "latency": r.first_spike_ms[keep],
            }
        )
        if post:
            df["post_hz"] = r.rate(r.stim_ms)[keep]
        per_seed.append(
            df.groupby("type").agg(
                n=("hz", "size"),
                hz=("hz", "mean"),
                fired=("fired", "any"),
                latency=("latency", "min"),
                **({"post_hz": ("post_hz", "mean")} if post else {}),
            )
        )
    stack = pd.concat(per_seed, keys=range(len(per_seed)), names=["seed", "type"])
    g = stack.groupby(level="type")
    out = pd.DataFrame(
        {
            "n": g["n"].first(),
            "p_active": g["fired"].mean(),
            "hz": g["hz"].mean(),
            "hz_sd": g["hz"].std(ddof=0),
            "latency_ms": g["latency"].median(),
        }
    )
    if post:
        out["post_hz"] = g["post_hz"].mean()
    out["superclass"] = (
        pd.Series(neurons["superclass"].to_numpy()[keep], index=types)
        .groupby(level=0)
        .first()
    )
    return out[out["p_active"] > 0].sort_values("hz", ascending=False).round(2)


def cmd_sim(a, neurons, edges):
    n = len(neurons)
    stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.stim]))
    params = sim.Params(w_syn=a.w_syn, th_jump=a.th_jump)
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), n, params.w_syn)
    stim_ms = a.stim_ms or a.duration
    print(
        f"stimulating {stim.size} neurons at {a.rate} Hz for {stim_ms} of {a.duration} ms, {a.seeds} seed(s) ..."
    )
    results = [
        sim.run(W, stim, a.rate, a.duration, a.stim_ms, params, seed)
        for seed in range(a.seed, a.seed + a.seeds)
    ]
    fired = np.mean([(r.counts.sum(axis=0) > 0).sum() for r in results])
    line = f"{fired:,.0f} neurons fired"
    if a.duration - stim_ms >= 200:
        line += f", {np.mean([r.persistent().size for r in results]):,.0f} still firing from {stim_ms + 100:g} ms (self-sustained)"
    print(line)
    print(summarize(neurons, results, stim, a.superclass).head(a.top).to_string())
    if a.out:
        rates = np.mean([r.rate(0, r.stim_ms) for r in results], axis=0)
        neurons.assign(rate=rates)[
            ["bodyId", "type", "instance", "superclass", "rate"]
        ].to_csv(a.out, index=False)
        print(f"per-neuron stimulus-window rates (mean over seeds) -> {a.out}")


def cmd_validate(a, neurons, edges):
    params = sim.Params(w_syn=a.w_syn, th_jump=a.th_jump)
    print(
        f"w_syn={params.w_syn} th_jump={params.th_jump}, {a.seeds} seed(s) per run ..."
    )
    report = validate.run(neurons, edges, params, a.seeds)
    print(report.round(1).to_string(index=False))
    failed = int((~report["passed"]).sum())
    print(f"\n{len(report) - failed}/{len(report)} checks passed")
    if failed:
        sys.exit(1)


def cmd_select_model(a, neurons, edges):
    """Pre-registered selection between the calibrated model (A) and the published model at
    MaleCNS synapse density without compensation (B); B-/B+ are sensitivity variants."""
    fafb = data.load(a.data, "fafb")
    rho, n_types = compare.synapse_density_ratio((neurons, edges), fafb)
    lo, hi = a.rho_range
    w0 = sim.Params.w_syn
    models = {
        "A": sim.Params(w_syn=w0, th_jump=a.th_jump_a),
        "B": sim.Params(w_syn=w0 / rho, th_jump=0.0),
        "B-": sim.Params(w_syn=w0 / lo, th_jump=0.0),
        "B+": sim.Params(w_syn=w0 / hi, th_jump=0.0),
    }
    print(
        f"synapse density ratio {rho:.2f} ({n_types} matched types);"
        f" {len(models)} models x {a.seeds} seeds ..."
    )
    reports = validate.compare_models(neurons, edges, models, a.seeds, a.workers)
    passed = {k: int(r["passed"].sum()) for k, r in reports.items()}
    for name, report in reports.items():
        print(f"\n=== {name}: {models[name]}")
        print(report.round(1).to_string(index=False))
        if a.out:
            report.to_csv(a.out / f"validate-v4-{a.seeds}seeds-{name}.csv", index=False)
    total = len(next(iter(reports.values())))
    print("\n" + ", ".join(f"{k} {v}/{total}" for k, v in passed.items()))
    print(
        f"winner (pre-registered rule): {validate.select_model(passed, ['A', 'B'], 'B')}"
    )


def cmd_dimorphism(a, neurons, edges):
    params = sim.Params(w_syn=a.w_syn, th_jump=a.th_jump)
    if a.silencing:
        print("silencing each category vs random silencings of the same size ...")
        table = dimorphism.silencing(neurons, edges, params, a.seeds, a.null, a.workers)
    else:
        print(
            "responders of each validation case vs superclass-matched random sets ..."
        )
        table = dimorphism.run(neurons, edges, params, a.seeds)
    print(table.round(3).to_string(index=False))


def cmd_calibrate(a, neurons, edges):
    n = len(a.w_syn) * len(a.th_jump)
    print(
        f"{n} parameter sets x {len(validate.CASES) * (1 + len(validate.DOSE_RATES_HZ))} runs"
        f" x {a.seeds} seeds, {a.workers} workers ..."
    )
    table = validate.calibrate(neurons, edges, a.w_syn, a.th_jump, a.seeds, a.workers)
    print(table.to_string(index=False))
    if a.out:
        table.to_csv(a.out, index=False)


def cmd_viz(a, neurons, edges):
    result = None
    if a.types:
        parts = [data.resolve(neurons, q) for q in a.types]
        idx = np.concatenate(parts)
        groups = [q for q, part in zip(a.types, parts, strict=True) for _ in part]
    elif a.path:
        src, dst = (data.resolve(neurons, q) for q in a.path)
        idx = np.array(graph.strongest_path(edges, len(neurons), src, dst))
        if not idx.size:
            sys.exit("flymsg: no path")
        groups = ["path"] * idx.size
    else:
        stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.sim]))
        W = sim.weight_matrix(
            edges, neurons["sign"].to_numpy(), len(neurons), sim.Params.w_syn
        )
        print(f"simulating {stim.size} stimulated neurons for {a.duration} ms ...")
        result = sim.run(W, stim, a.rate, a.duration, a.stim_ms, seed=a.seed)
        idx = viz.select_from_result(result, stim, a.min_rate)
        groups = np.where(np.isin(idx, stim), "stimulus", "response").tolist()
    scene = viz.export(a.out, neurons, idx, groups, result)
    print(
        f"{len(scene['neurons'])} neurons exported to {a.out}/ (geometry streams from GCS)\n"
        f"view: python -m http.server -d {a.out} 8000  ->  http://localhost:8000"
    )


def main() -> None:
    p = argparse.ArgumentParser(
        prog="flymsg",
        description="Explore and simulate the male Drosophila CNS connectome",
    )
    p.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("FLYMSG_DATA", "data")),
        help="data dir (env FLYMSG_DATA)",
    )
    p.add_argument(
        "--dataset",
        choices=["malecns", "fafb"],
        default="malecns",
        help="malecns (male CNS, default) or fafb (female brain, FlyWire v783, in DATA/fafb)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download raw tables (malecns ~1.1 GB, fafb ~135 MB)")
    sub.add_parser("build", help="compact raw tables to data/*.parquet")
    s = sub.add_parser(
        "info", help="annotations and top partners of a type/instance/bodyId"
    )
    s.add_argument("query")
    s.add_argument("--top", type=int, default=10)
    s = sub.add_parser(
        "path", help="strongest path between two types/instances/bodyIds"
    )
    s.add_argument("src")
    s.add_argument("dst")
    s.add_argument("--min-weight", type=int, default=5)
    s.add_argument(
        "--alt",
        type=int,
        default=1,
        help="routes to list, each avoiding the intermediate types of the previous ones",
    )
    s = sub.add_parser("sim", help="LIF simulation with Poisson stimulation")
    s.add_argument(
        "stim",
        nargs="+",
        help="types/instances/bodyIds to stimulate (e.g. LC4 or LC4_R)",
    )
    s.add_argument("--rate", type=float, default=150.0)
    s.add_argument("--duration", type=float, default=1000.0, help="ms")
    s.add_argument(
        "--stim-ms", type=float, help="stimulus length in ms (default: whole run)"
    )
    s.add_argument(
        "--w-syn", type=float, default=sim.Params.w_syn, help="mV per synapse"
    )
    s.add_argument(
        "--th-jump",
        type=float,
        default=sim.Params.th_jump,
        help="adaptive threshold, mV/spike (0 = Shiu)",
    )
    s.add_argument(
        "--superclass",
        nargs="*",
        help="only report these superclasses, e.g. descending_neuron vnc_motor",
    )
    s.add_argument("--top", type=int, default=25)
    s.add_argument("--seed", type=int, default=0, help="first seed")
    s.add_argument("--seeds", type=int, default=1, help="number of seeds to average")
    s.add_argument("--out", type=Path)
    s = sub.add_parser(
        "validate", help="run the validation battery (known circuits + controls)"
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--w-syn", type=float, default=sim.Params.w_syn)
    s.add_argument("--th-jump", type=float, default=sim.Params.th_jump)
    s = sub.add_parser(
        "select-model",
        help="pre-registered choice: calibrated model vs density-scaled model",
    )
    s.add_argument("--seeds", type=int, default=10)
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--th-jump-a", type=float, default=sim.Params.th_jump)
    s.add_argument(
        "--rho-range", type=float, nargs=2, default=[1.43, 2.43], metavar=("LO", "HI")
    )
    s.add_argument("--out", type=Path, help="directory for one CSV report per model")
    s = sub.add_parser(
        "dimorphism",
        help="share of fru/dsx+, male-specific and dimorphic neurons among responders",
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument(
        "--silencing",
        action="store_true",
        help="instead: response drop when each category is silenced",
    )
    s.add_argument("--null", type=int, default=20, help="random silencings per test")
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--w-syn", type=float, default=sim.Params.w_syn)
    s.add_argument("--th-jump", type=float, default=sim.Params.th_jump)
    s = sub.add_parser(
        "calibrate", help="grid-search w_syn x th_jump against the validation battery"
    )
    s.add_argument("--w-syn", type=float, nargs="+", default=[0.2, 0.275, 0.35])
    s.add_argument(
        "--th-jump", type=float, nargs="+", default=[2.0, 4.0, 6.0, 8.0, 12.0]
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--out", type=Path)
    s = sub.add_parser(
        "viz", help="export a three.js 3D view (anatomy or simulation replay)"
    )
    what = s.add_mutually_exclusive_group(required=True)
    what.add_argument(
        "--types", nargs="+", help="types/instances/bodyIds, one colour group each"
    )
    what.add_argument(
        "--path",
        nargs=2,
        metavar=("SRC", "DST"),
        help="strongest path between two populations",
    )
    what.add_argument(
        "--sim",
        nargs="+",
        metavar="STIM",
        help="simulate and replay; shows every neuron that fires during the stimulus",
    )
    s.add_argument("--rate", type=float, default=100.0)
    s.add_argument("--duration", type=float, default=600.0, help="ms")
    s.add_argument("--stim-ms", type=float, default=300.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument(
        "--min-rate",
        type=float,
        default=0.0,
        help="replay: only neurons above this rate (Hz)",
    )
    s.add_argument("--out", type=Path, default=Path("runs/viz"))
    a = p.parse_args()

    try:
        if a.cmd == "fetch":
            return data.fetch(a.data, a.dataset)
        if a.cmd == "build":
            return data.build(a.data, a.dataset)
        if a.dataset == "fafb" and a.cmd in (
            "validate",
            "calibrate",
            "dimorphism",
            "viz",
        ):
            # the battery needs the VNC, and the 3D view streams MaleCNS geometry
            sys.exit(f"flymsg: {a.cmd} needs --dataset malecns")
        neurons, edges = data.load(a.data, a.dataset)
        {
            "info": cmd_info,
            "path": cmd_path,
            "sim": cmd_sim,
            "validate": cmd_validate,
            "calibrate": cmd_calibrate,
            "dimorphism": cmd_dimorphism,
            "select-model": cmd_select_model,
            "viz": cmd_viz,
        }[a.cmd](a, neurons, edges)
    except KeyError as err:  # unknown neuron query
        sys.exit(f"flymsg: {err.args[0]}")
    except OSError as err:  # missing data files, failed downloads
        sys.exit(f"flymsg: {err}")
