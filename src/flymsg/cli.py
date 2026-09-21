import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, graph, sim

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
    path = graph.strongest_path(edges, len(neurons), src, dst, a.min_weight)
    if not path:
        print("no path")
        return
    weights = [0, *graph.edge_weights(edges, path)]
    for k, (i, w) in enumerate(zip(path, weights)):
        hop = f"  --{w} syn-->  " if k else "  "
        print(f"{hop}{label(neurons, i)}")
    print(f"\nneuroglancer: {ng_link(neurons['bodyId'].to_numpy()[path])}")


def summarize(
    neurons: pd.DataFrame, rates: np.ndarray, stim: np.ndarray, superclass=None
) -> pd.DataFrame:
    """Per-type response: all neurons of the type count, not only those that fired."""
    df = neurons.assign(rate=rates).drop(index=stim)
    if superclass:
        df = df[df["superclass"].isin(superclass)]
    out = df.groupby("type").agg(
        n=("rate", "size"),
        active=("rate", lambda r: int((r > 0).sum())),
        mean_hz=("rate", "mean"),
        max_hz=("rate", "max"),
        superclass=("superclass", "first"),
    )
    return out[out["active"] > 0].sort_values("mean_hz", ascending=False).round(1)


def cmd_sim(a, neurons, edges):
    n = len(neurons)
    stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.stim]))
    params = sim.Params(w_syn=a.w_syn, th_jump=a.th_jump)
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), n, params.w_syn)
    print(
        f"stimulating {stim.size} neurons at {a.rate} Hz for {a.stim_ms or a.duration} of {a.duration} ms ..."
    )
    rates = sim.run(W, stim, a.rate, a.duration, a.stim_ms, params, a.seed)
    print(f"{(rates > 0).sum():,} neurons fired")
    print(summarize(neurons, rates, stim, a.superclass).head(a.top).to_string())
    if a.out:
        neurons.assign(rate=rates)[
            ["bodyId", "type", "instance", "superclass", "rate"]
        ].to_csv(a.out, index=False)
        print(f"per-neuron rates -> {a.out}")


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
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download raw tables (~1.1 GB)")
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
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", type=Path)
    a = p.parse_args()

    try:
        if a.cmd == "fetch":
            return data.fetch(a.data)
        if a.cmd == "build":
            return data.build(a.data)
        neurons, edges = data.load(a.data)
        {"info": cmd_info, "path": cmd_path, "sim": cmd_sim}[a.cmd](a, neurons, edges)
    except KeyError as err:  # unknown neuron query
        sys.exit(f"flymsg: {err.args[0]}")
    except OSError as err:  # missing data files, failed downloads
        sys.exit(f"flymsg: {err}")
