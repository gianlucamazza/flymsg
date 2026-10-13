"""Simulation commands: rates, traces, calibration grids and 3D exports."""

import os
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from flymsg import data, graph, sim, tracing, validate, viz
from flymsg.cli.common import stamp


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
    started = datetime.now(UTC)
    stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.stim]))
    params = sim.Params(w_syn=a.w_syn, th_jump=a.th_jump)
    W = sim.network(neurons, edges, params)
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
        stamp(
            a.out.parent,
            "sim",
            a,
            neurons,
            edges,
            {
                "stim": list(a.stim),
                "rate": a.rate,
                "duration": a.duration,
                "stim_ms": a.stim_ms,
                "w_syn": params.w_syn,
                "th_jump": params.th_jump,
            },
            {"seed0": a.seed, "seeds": a.seeds},
            started,
            extra={"out": os.fspath(a.out)},
        )


def cmd_trace(a, neurons, edges):
    """Record v, g, threshold, refractory state, spikes and input of chosen neurons."""
    started = datetime.now(UTC)
    stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.stim]))
    watch = np.concatenate([data.resolve(neurons, q) for q in a.neurons])
    silence = (
        np.concatenate([data.resolve(neurons, q) for q in a.silence])
        if a.silence
        else None
    )
    params = sim.Params(w_syn=a.w_syn, th_jump=a.th_jump)
    W = sim.network(neurons, edges, params)
    trace, result = tracing.record(
        W,
        stim,
        watch,
        rate_hz=a.rate,
        duration_ms=a.duration,
        stim_ms=a.stim_ms,
        seed=a.seed,
        p=params,
        silence=silence,
        every=a.every,
    )
    names = neurons["instance"].fillna(neurons["type"]).fillna("untyped").to_numpy()
    print(
        f"{watch.size} neurons, {trace.v.shape[0]} samples every {trace.step_ms:g} ms"
    )
    for j, i in enumerate(watch):
        print(
            f"  {names[i]} ({neurons['bodyId'].iat[i]}): {int(trace.spikes[:, j].sum())} spikes,"
            f" v {trace.v[:, j].min():.2f}..{trace.v[:, j].max():.2f} mV,"
            f" g max {trace.g[:, j].max():.2f} mV"
        )
    a.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        a.out / "trace.npz",
        body_ids=neurons["bodyId"].to_numpy()[watch],
        times_ms=trace.times_ms,
        v=trace.v,
        g=trace.g,
        th=trace.th,
        refractory=trace.refractory,
        spikes=trace.spikes,
        input_counts=trace.input_counts,
        dt_ms=np.array(trace.dt_ms),
    )
    stamp(
        a.out,
        "trace",
        a,
        neurons,
        edges,
        {
            "stim": list(a.stim),
            "neurons": list(a.neurons),
            "silence": list(a.silence or []),
            "rate": a.rate,
            "duration": a.duration,
            "stim_ms": a.stim_ms,
            "every": a.every,
            "w_syn": params.w_syn,
            "th_jump": params.th_jump,
            "units": "v, g, th in mV; times in ms; model states, not recordings",
        },
        {"seed": a.seed},
        started,
        extra={"neurons_fired": int((result.counts.sum(axis=0) > 0).sum())},
    )
    print(f"trace -> {a.out / 'trace.npz'}")


def cmd_calibrate(a, neurons, edges):
    started = datetime.now(UTC)
    n = len(a.w_syn) * len(a.th_jump)
    print(
        f"{n} parameter sets x {len(validate.CASES) * (1 + len(validate.DOSE_RATES_HZ))} runs"
        f" x {a.seeds} seeds, {a.workers} workers ..."
    )
    table = validate.calibrate(neurons, edges, a.w_syn, a.th_jump, a.seeds, a.workers)
    print(table.to_string(index=False))
    if a.out:
        table.to_csv(a.out, index=False)
        stamp(
            a.out.parent,
            "calibrate",
            a,
            neurons,
            edges,
            {"w_syn": list(a.w_syn), "th_jump": list(a.th_jump)},
            {"seeds": a.seeds},
            started,
            extra={"out": os.fspath(a.out)},
        )


def cmd_viz(a, neurons, edges):
    started = datetime.now(UTC)
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
        W = sim.network(neurons, edges, sim.Params())
        print(f"simulating {stim.size} stimulated neurons for {a.duration} ms ...")
        silence = (
            np.concatenate([data.resolve(neurons, q) for q in a.silence])
            if a.silence
            else None
        )
        result = sim.run(
            W, stim, a.rate, a.duration, a.stim_ms, seed=a.seed, silence=silence
        )
        keep = (
            np.concatenate([data.resolve(neurons, q) for q in a.keep])
            if a.keep
            else None
        )
        idx = viz.select_from_result(result, stim, a.min_rate, keep)
        fired = result.rate(0, a.stim_ms)[idx] > a.min_rate
        groups = np.where(
            np.isin(idx, stim), "stimulus", np.where(fired, "response", "kept")
        ).tolist()
    scene = viz.export(a.out, neurons, idx, groups, result, edges)
    print(
        f"{len(scene['neurons'])} neurons exported to {a.out}/ (geometry streams from GCS)\n"
        f"view: python -m http.server -d {a.out} 8000  ->  http://localhost:8000"
    )
    stamp(
        a.out,
        "viz",
        a,
        neurons,
        edges,
        {
            "types": a.types,
            "path": a.path,
            "sim": a.sim,
            "rate": a.rate,
            "duration": a.duration,
            "stim_ms": a.stim_ms,
            "silence": list(a.silence or []),
            "keep": list(a.keep or []),
        },
        {"seed": a.seed},
        started,
        extra={"n_exported": len(scene["neurons"])},
    )
