import argparse
import json
import os
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import (
    behavior,
    benchmarks,
    compare,
    data,
    dimorphism,
    draws,
    graph,
    intervention,
    jump,
    loop,
    manifest,
    nulls,
    prereg,
    quality,
    sensitivity,
    silence_scan,
    sim,
    tracing,
    validate,
    viz,
    wiring,
    workbench,
)

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


def _stamp(out, command, a, neurons, edges, config, seeds, started, extra=None):
    """Write a run manifest next to this command's outputs."""
    dataset_dir = a.data / "fafb" if a.dataset == "fafb" else a.data
    manifest.write(
        out,
        command=command,
        config=config,
        seeds=seeds,
        dataset=manifest.dataset_info(a.dataset, a.data, neurons, edges),
        started_at=started,
        extra={"data_dir": os.fspath(dataset_dir), **(extra or {})},
    )


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
        _stamp(
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
    _stamp(
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


def cmd_sensitivity(a, neurons, edges):
    """Run the locked sensitivity grid and write every cell, the spreads and a figure."""
    started = datetime.now(UTC)
    doc = sensitivity.assert_matches_code()
    print(sensitivity.summary(doc))
    cells = sensitivity.run(neurons, edges, a.workers, a.checkpoint)
    out = Path("runs/sensitivity") / f"v{doc['version']}"
    out.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out / "cells.csv", index=False)
    held = sensitivity.holds(cells, doc)
    held.to_csv(out / "holds.csv", index=False)
    spread = sensitivity.spreads(cells)
    spread.to_csv(out / "spreads.csv", index=False)
    (out / "rate.svg").write_text(sensitivity.svg(cells, doc))
    grid = held.pivot_table(
        index=["case", "target"], columns=["th_jump", "w_syn_factor"], values="holds"
    )
    text = "\n".join(
        [
            sensitivity.summary(doc),
            "holds (v4 floor) per cell:",
            grid.replace({True: "yes", False: "no"}).to_string(),
            "spreads (seed range at the default cell vs range of medians over cells):",
            spread.to_string(index=False),
        ]
    )
    (out / "report.txt").write_text(text + "\n")
    print(text)
    _stamp(
        out,
        "sensitivity --run",
        a,
        neurons,
        edges,
        {
            "sensitivity_version": doc["version"],
            "sensitivity_sha256": doc["content_sha256"],
            "grid": doc["grid"],
        },
        {"seed0": doc["grid"]["seed0"], "seeds": doc["grid"]["seeds"]},
        started,
    )
    print(f"report -> {out / 'report.txt'}")


def cmd_experiment(a, neurons, edges):
    """Validate an exploratory config and, unless --check, run it into an immutable dir."""
    cfg = workbench.validate_config(workbench.load_config(a.config), neurons)
    digest = workbench.config_hash(cfg)
    print(
        f"config ok: {workbench.CONFIG_SCHEMA}, sha256 {digest[:16]}, label exploratory"
    )
    if a.check:
        return
    out = workbench.run(cfg, neurons, edges, a.root, a.data)
    print(pd.read_csv(out / "metrics.csv").to_string(index=False))
    print(f"-> {out}")


def _explore_config(a) -> dict:
    return {
        "source": a.source,
        "target": a.target,
        "paths": a.paths,
        "seeds": a.seeds,
        "seed0": a.seed0,
        "base_silence": list(a.silence or []),
    }


def cmd_explore(a, neurons, edges):
    """Exploratory: paths (anatomy), then silencing each intermediate type (simulation)."""
    started = datetime.now(UTC)
    if a.replay:
        saved = json.loads((a.replay / "manifest.json").read_text())["config"]
        cfg = {
            k: saved[k]
            for k in ("source", "target", "paths", "seeds", "seed0", "base_silence")
        }
    else:
        if not (a.source and a.target):
            sys.exit("flymsg: explore needs SOURCE and TARGET, or --replay DIR")
        cfg = _explore_config(a)
    result = intervention.explore(
        neurons, edges, cfg["source"], cfg["target"], paths=cfg["paths"],
        seeds=cfg["seeds"], seed0=cfg["seed0"], base_silence=cfg["base_silence"],
    )  # fmt: skip
    for row in result["anatomy"]:
        print(
            f"anatomy, path {row['path']}: {' -> '.join(row['types'])}  synapses {row['synapses']}"
        )
    for row in result["interventions"]:
        lo, hi = row["ci95_change_hz"]
        print(
            f"simulation (exploratory), silence {row['silenced']} ({row['neurons']}): "
            f"{row['mean_change_hz']:+.1f} Hz [{lo:+.1f}, {hi:+.1f}]"
        )
    print(result["note"])
    if result["governed_by"]:
        print(f"governed by {result['governed_by']}")
    if a.replay:
        saved = json.loads((a.replay / "explore.json").read_text())
        same = (
            saved["interventions"] == result["interventions"]
            and saved["anatomy"] == result["anatomy"]
        )
        print(
            "replay reproduces the saved contrast"
            if same
            else "replay DIFFERS from the saved contrast"
        )
        if not same:
            sys.exit(1)
        return
    out = (
        a.out
        / f"{a.source}-{a.target}".replace("/", "_")
        / workbench.config_hash(cfg)[:12]
    )
    if out.exists():
        sys.exit(f"flymsg: {out} exists; use --replay {out} to check it")
    out.mkdir(parents=True)
    (out / "explore.json").write_text(json.dumps(result, indent=1))
    _stamp(out, "explore", a, neurons, edges, cfg, {"seed0": cfg["seed0"], "seeds": cfg["seeds"]},
           started, extra={"label": "exploratory"})  # fmt: skip
    print(f"-> {out}")


def cmd_confirm(a, neurons, edges):
    """Run a registered intervention lock on fresh seeds against a matched null."""
    started = datetime.now(UTC)
    table = intervention.confirm(neurons, edges, a.lock, a.out, checkpoint=a.checkpoint)
    print(table.to_string(index=False))
    doc = intervention.load(a.lock)
    out = a.out / a.lock.stem / f"v{doc['version']}"
    _stamp(out, "confirm", a, neurons, edges, {"lock": str(a.lock), "lock_sha256": doc["content_sha256"]},
           {"seed0": doc["seed0"], "seeds": doc["seeds"]}, started, extra={"label": "preregistered"})  # fmt: skip


def cmd_jump(a, neurons, edges):
    """M1: simulate, decode the motor neuron's spikes with an engineered gain, move a body."""
    from flymsg.embodiment import Provenance

    started = datetime.now(UTC)
    stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.sim]))
    motor = data.resolve(neurons, a.motor)
    if motor.size != 1:
        sys.exit(f"flymsg: {a.motor} is {motor.size} neurons; the decoder reads one")
    silence = (
        np.concatenate([data.resolve(neurons, q) for q in a.silence])
        if a.silence
        else None
    )
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    r = sim.run(
        W, stim, a.rate, a.duration, a.stim_ms, p, a.seed, silence=silence, trace=motor
    )
    steps = np.flatnonzero(r.traced[:, 0])
    info = manifest.dataset_info(a.dataset, a.data, neurons, edges)
    digest = info["files"]["edges.parquet"]["sha256"]
    git = manifest.git_info()
    out = jump.run_jump(
        steps, body_id=int(neurons["bodyId"].iat[motor[0]]), gain_n=a.gain_n,
        mass_kg=a.mass_kg, duration_us=round(a.duration * 1000),
        provenance=Provenance(f"malecns {info.get('release', '')}".strip(), digest,
                              git.get("commit") or "unknown", a.seed),
    )  # fmt: skip
    print(out["note"])
    print(
        f"{a.motor}: {out['spikes']} spikes; takeoff "
        f"{'none' if out['takeoff_ms'] is None else f'{out["takeoff_ms"]:.1f} ms'}; "
        f"max height {1000 * out['max_height_m']:.2f} mm"
    )
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "trajectory.json").write_text(json.dumps(out))
    _stamp(
        a.out, "jump", a, neurons, edges,
        {"sim": list(a.sim), "silence": list(a.silence or []), "motor": a.motor,
         "gain_n": a.gain_n, "mass_kg": a.mass_kg, "rate": a.rate,
         "duration": a.duration, "stim_ms": a.stim_ms, "decoder": jump.ENGINEERED},
        {"seed": a.seed}, started, extra={"label": "exploratory", "note": jump.NOTE},
    )  # fmt: skip
    print(f"-> {a.out / 'trajectory.json'}")


def cmd_loop(a, neurons, edges):
    """M2: closed loop with its three controls, same seed, engineered transducer and decoder."""
    started = datetime.now(UTC)
    stim = np.unique(np.concatenate([data.resolve(neurons, q) for q in a.sim]))
    motor = data.resolve(neurons, a.motor)
    if motor.size != 1:
        sys.exit(f"flymsg: {a.motor} is {motor.size} neurons; the decoder reads one")
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    kw = {
        "looming": loop.Looming(a.radius_m, a.distance_m, a.speed_m_s),
        "transducer": loop.Transducer(a.transducer_gain, a.max_rate_hz),
        "decoder_gain_n": a.gain_n,
        "mass_kg": a.mass_kg,
        "duration_ms": a.duration,
        "seed": a.seed,
        "p": p,
    }
    runs = {
        m: loop.run_loop(W, stim, int(motor[0]), mode=m, **kw)
        for m in ("closed", "disconnected", "shuffled")
    }
    runs["replay"] = loop.run_loop(
        W,
        stim,
        int(motor[0]),
        mode="replay",
        replay_counts=runs["closed"]["input_counts"],
        **kw,
    )
    summary = {}
    for mode, r in runs.items():
        lifted = np.flatnonzero(r["height_m"] > 0)
        summary[mode] = {
            "motor_spikes": int(r["motor_spikes"].sum()),
            "input_kicks": int(r["input_counts"].sum()),
            "takeoff_ms": float(r["t_ms"][lifted[0]]) if lifted.size else None,
            "max_height_m": float(r["height_m"].max()),
        }
        print(f"{mode:>12}: {summary[mode]}")
    same = np.array_equal(
        runs["replay"]["motor_spikes"], runs["closed"]["motor_spikes"]
    )
    differ = int(
        (runs["closed"]["input_counts"] != runs["disconnected"]["input_counts"])
        .any(axis=1)
        .sum()
    )
    print(f"replay reproduces the closed loop's motor spikes: {same}")
    print(f"neural steps whose input differs between closed and disconnected: {differ}")
    print(jump.NOTE)
    a.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out / "loop.npz", **{
        f"{m}_{k}": v for m, r in runs.items() for k, v in r.items()
        if isinstance(v, np.ndarray) and k != "input_counts"
    })  # fmt: skip
    (a.out / "loop.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "replay_matches": same,
                "input_steps_differing": differ,
            },
            indent=1,
        )
    )
    _stamp(
        a.out, "loop", a, neurons, edges,
        {"sim": list(a.sim), "motor": a.motor, "radius_m": a.radius_m, "distance_m": a.distance_m,
         "speed_m_s": a.speed_m_s, "transducer_gain": a.transducer_gain, "max_rate_hz": a.max_rate_hz,
         "gain_n": a.gain_n, "mass_kg": a.mass_kg, "duration": a.duration, "decoder": jump.ENGINEERED},
        {"seed": a.seed}, started, extra={"label": "exploratory", "note": jump.NOTE},
    )  # fmt: skip
    print(f"-> {a.out}")


def cmd_wiring_null(a, neurons, edges):
    """N1. Parameters and seeds are the pre-registered ones; there is no flag to change them."""
    started = datetime.now(UTC)
    shuffled, stats = wiring.shuffle_targets(edges)
    print(
        f"shuffle seed {wiring.SHUFFLE_SEED}: {stats['n_edges']:,} edges,"
        f" {stats['n_self_loops']:,} self-loops,"
        f" {stats['n_duplicate_pairs']:,} duplicate pairs"
        f" ({stats['n_extra_edges']:,} extra edges)"
    )
    if a.stats:
        return
    params = sim.Params()
    prereg.assert_run_matches(
        prereg.run_config(params.w_syn, params.th_jump, wiring.N1_SEEDS)
    )
    print(
        f"criterion v4, w_syn={params.w_syn} th_jump={params.th_jump},"
        f" seeds 0..{wiring.N1_SEEDS - 1}, real graph then shuffle"
    )
    real = validate.run(neurons, edges, params, wiring.N1_SEEDS)
    shuf = validate.run(neurons, shuffled, params, wiring.N1_SEEDS)
    out = Path("runs")
    out.mkdir(exist_ok=True)
    real.to_csv(out / "n1-real.csv", index=False)
    shuf.to_csv(out / "n1-shuffle.csv", index=False)
    for name, report in ("real", real), ("shuffle", shuf):
        passed = int(report["passed"].sum())
        print(
            f"{name}: {passed}/{len(report)} checks passed (descriptive except specific)"
        )
    still = shuf.loc[shuf["passed"], ["case", "kind", "subject"]]
    print("shuffle still passes:")
    print(still.to_string(index=False) if len(still) else "(none)")
    print(wiring.verdict(wiring.confirmatory(real, shuf)))
    _stamp(
        out,
        "wiring-null",
        a,
        neurons,
        edges,
        {
            "family": "degree_preserving",
            "w_syn": params.w_syn,
            "th_jump": params.th_jump,
            "preregistration": prereg.load()["version"],
        },
        {"shuffle_seed": wiring.SHUFFLE_SEED, "seeds": wiring.N1_SEEDS},
        started,
        extra={"stats": stats},
    )


def cmd_validate(a, neurons, edges):
    started = datetime.now(UTC)
    params = sim.Params(w_syn=a.w_syn, th_jump=a.th_jump)
    prereg.assert_run_matches(
        prereg.run_config(params.w_syn, params.th_jump, a.seeds),
        exploratory=a.exploratory,
    )
    print(
        f"w_syn={params.w_syn} th_jump={params.th_jump}, {a.seeds} seed(s) per run ..."
    )
    report = validate.run(neurons, edges, params, a.seeds)
    print(report.round(1).to_string(index=False))
    failed = int((~report["passed"]).sum())
    print(f"\n{len(report) - failed}/{len(report)} checks passed")
    out = a.out or Path("runs/validate")
    out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "report.csv", index=False)
    _stamp(
        out,
        "validate",
        a,
        neurons,
        edges,
        {
            "w_syn": params.w_syn,
            "th_jump": params.th_jump,
            "exploratory": a.exploratory,
            "preregistration": prereg.load()["version"],
        },
        {"seeds": a.seeds, "seed0": 0, "control_seed": 0},
        started,
    )
    if failed:
        sys.exit(1)


def _cmd_benchmark_corners(a, neurons, edges, started):
    """The two frozen sensitivity corners. The scored report is left where it is."""
    doc = benchmarks.assert_matches_code()
    corners = benchmarks.sensitivity_corners(doc)
    listed = ", ".join(f"w_syn={p.w_syn} th_jump={p.th_jump}" for p in corners)
    print(f"benchmarks v{doc['version']}: sensitivity corners only, {listed}")
    report = benchmarks.score_sensitivity(neurons, edges)
    print(report.round(1).to_string(index=False))
    text = benchmarks.corner_verdicts(report)
    print(text)
    out = Path("runs/benchmarks/corners")
    out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "report.csv", index=False)
    _stamp(
        out,
        "benchmarks --corners",
        a,
        neurons,
        edges,
        {
            "corners": [{"w_syn": p.w_syn, "th_jump": p.th_jump} for p in corners],
            "benchmarks_version": doc["version"],
            "benchmarks_sha256": doc["content_sha256"],
            "checks": doc["endpoints"]["checks"],
        },
        {
            "seeds": doc["endpoints"]["seeds"],
            "seed0": doc["endpoints"]["seed0"],
            "control_seed": doc["endpoints"]["control_seed"],
        },
        started,
        extra={"verdicts": text},
    )
    print(f"report -> {out / 'report.csv'}")


def cmd_behavior(a, neurons, edges):
    """The frozen one-bit loop. No flag chooses another weight, seed, or body."""
    started = datetime.now(UTC)
    doc = behavior.assert_matches_code()
    protocol = doc["protocol"]
    last = protocol["seed0"] + protocol["seeds"] - 1
    print(
        f"behavior v{doc['version']}: closed loop,"
        f" w_syn={protocol['w_syn']} th_jump={protocol['th_jump']},"
        f" seeds {protocol['seed0']}-{last}"
    )
    report, replay = behavior.run_loop(neurons, edges)
    print(report.to_string(index=False))
    text = behavior.verdict(report)
    print(text)
    print("reported rows do not decide and are not a retune")
    out = Path("runs/behavior")
    out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "report.csv", index=False)
    np.savez_compressed(out / "replay.npz", **replay)
    _stamp(
        out,
        "behavior --run",
        a,
        neurons,
        edges,
        {
            "w_syn": protocol["w_syn"],
            "th_jump": protocol["th_jump"],
            "behavior_version": doc["version"],
            "behavior_sha256": doc["content_sha256"],
            "checks": list(doc["decides"]),
            "rate_hz": protocol["rate_hz"],
            "stim_ms": protocol["stim_ms"],
            "duration_ms": protocol["duration_ms"],
        },
        {"seeds": protocol["seeds"], "seed0": protocol["seed0"]},
        started,
        extra={"verdict": text, "replay": os.fspath(out / "replay.npz")},
    )
    print(f"report -> {out / 'report.csv'}")


def cmd_silence_scan(a, neurons, edges):
    """The frozen residual TTMn_R scan. No flag chooses another unit, seed, or weight."""
    started = datetime.now(UTC)
    doc = silence_scan.assert_matches_code()
    print(silence_scan.summary(doc))
    out = silence_scan.run(neurons, edges, a.workers, a.checkpoint)
    path = Path("runs/silence-scan") / f"v{doc['version']}"  # never overwrite a version
    path.mkdir(parents=True, exist_ok=True)
    lines = [
        f"base arm, screen seeds: {out['base_screen']}",
        f"base arm, confirm seeds: {out.get('base_confirm')}",
    ]
    for stage in ("screen", "confirm"):
        if stage in out:
            table = out[stage]
            table.to_csv(path / f"{stage}.csv", index=False)
            lines += [f"{stage}:", table.to_string(index=False)]
    lines.append(out["verdict"])
    text = "\n".join(lines)
    print(text)
    (path / "report.txt").write_text(text + "\n")
    protocol = doc["protocol"]
    _stamp(
        path,
        "silence-scan --run",
        a,
        neurons,
        edges,
        {
            "w_syn": protocol["w_syn"],
            "th_jump": protocol["th_jump"],
            "scan_version": doc["version"],
            "scan_sha256": doc["content_sha256"],
            "rate_hz": protocol["rate_hz"],
            "stim_ms": protocol["stim_ms"],
            "duration_ms": protocol["duration_ms"],
            "m": out.get("m"),
        },
        {
            "screen": list(silence_scan._seeds(doc["screen"])),
            "confirm": list(silence_scan._seeds(doc["confirm"])),
        },
        started,
        extra={"verdict": out["verdict"]},
    )
    print(f"report -> {path / 'report.txt'}")


def cmd_benchmarks(a, neurons, edges):
    """The frozen held-out cases. No flag chooses a weight that is not in the manifest."""
    started = datetime.now(UTC)
    if a.corners:
        return _cmd_benchmark_corners(a, neurons, edges, started)
    doc = benchmarks.assert_matches_code()
    corner = doc["sensitivity"]["scored"]
    print(
        f"benchmarks v{doc['version']}: scored corner only,"
        f" w_syn={corner['w_syn']} th_jump={corner['th_jump']},"
        f" seeds {doc['endpoints']['seed0']}-{doc['endpoints']['seed0'] + doc['endpoints']['seeds'] - 1}"
    )
    report = benchmarks.score(neurons, edges)
    print(report.round(1).to_string(index=False))
    print(benchmarks.verdict(report))
    print("reported rows do not decide and are not a retune")
    out = Path("runs/benchmarks")
    out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "report.csv", index=False)
    _stamp(
        out,
        "benchmarks --run",
        a,
        neurons,
        edges,
        {
            "w_syn": corner["w_syn"],
            "th_jump": corner["th_jump"],
            "benchmarks_version": doc["version"],
            "benchmarks_sha256": doc["content_sha256"],
            "checks": doc["endpoints"]["checks"],
        },
        {
            "seeds": doc["endpoints"]["seeds"],
            "seed0": doc["endpoints"]["seed0"],
            "control_seed": doc["endpoints"]["control_seed"],
        },
        started,
        extra={"verdict": benchmarks.verdict(report)},
    )
    print(f"report -> {out / 'report.csv'}")


def audit_focus_types(neurons: pd.DataFrame) -> list[str]:
    """Cell types behind published results: validation stimuli and targets, the negative
    case, sex-comparison targets and the neurons of the predicted dPR1 feedback loop."""
    types = set()
    for case in validate.CASES:
        types |= set(neurons["type"].iloc[case.stim_idx(neurons)].dropna())
        types |= set(case.targets)
    for _, stim_fn, target, _ in validate.NEGATIVES:
        types |= set(neurons["type"].iloc[stim_fn(neurons)].dropna()) | {target}
    return sorted(types | {"dMS9", "vPR9_a", "IN00A038"})


def cmd_audit(a, neurons, edges):
    totals = quality.synapse_totals(neurons, edges)
    asym = quality.pair_asymmetry(neurons, totals)
    q = asym["log2_RL"].quantile([0.05, 0.5, 0.95])
    print(
        f"{len(asym):,} bilateral types; log2(R/L) of median input synapses:"
        f" 5% {q[0.05]:.2f}, median {q[0.5]:.2f}, 95% {q[0.95]:.2f};"
        f" {int(asym['flag'].sum())} flagged (|robust z| > {quality.Z_FLAG:g})"
    )
    focus = a.types or audit_focus_types(neurons)
    rows = asym.reindex([t for t in focus if t in asym.index]).copy()
    # traced-input share per side, if the raw weights table is present
    raw = a.data / "raw" / data.RAW["weights"]
    if raw.exists():
        idx = np.flatnonzero(neurons["type"].isin(rows.index).to_numpy())
        share = quality.traced_input_share(a.data, neurons, idx)
        sides = [quality.side_of(i) for i in neurons["instance"].iloc[idx]]
        sh = pd.DataFrame(
            {"type": neurons["type"].iloc[idx].to_numpy(), "side": sides, "s": share}
        ).dropna(subset=["side"])
        med = sh.groupby(["type", "side"])["s"].median().unstack()
        rows["traced_in_L"] = med["L"].reindex(rows.index)
        rows["traced_in_R"] = med["R"].reindex(rows.index)
    # the same pair in the female brain, where the type is matched
    fafb_dir = a.data / "fafb" / "edges.parquet"
    if fafb_dir.exists():
        fn, fe = data.load(a.data, "fafb")
        f_asym = quality.pair_asymmetry(fn, quality.synapse_totals(fn, fe))
        fw = (
            neurons.dropna(subset=["flywireType"])
            .groupby("type")["flywireType"]
            .first()
        )
        rows["fafb_log2_RL"] = [
            f_asym["log2_RL"].get(fw.get(t), np.nan) for t in rows.index
        ]
    pd.set_option("display.width", 200)
    print(rows.round(2).to_string())
    flagged = asym[asym["flag"]].sort_values("z", key=abs, ascending=False)
    print(f"\nmost asymmetric bilateral types (of {len(flagged)} flagged):")
    print(flagged.head(a.top).round(2).to_string())


def cmd_nulls(a, neurons, edges):
    """Pre-registered multi-draw null families. Default draw count is the CI value."""
    started = datetime.now(UTC)
    locked = prereg.load()
    draws = locked["nulls"]["draws_full"] if a.full else a.draws
    families = tuple(a.families) if a.families else nulls.FAMILIES
    params = sim.Params()
    prereg.assert_run_matches(
        prereg.run_config(params.w_syn, params.th_jump, draws=draws),
        exploratory=a.exploratory,
    )
    print(
        f"{len(families)} families x {draws} draws, "
        f"w_syn={params.w_syn} th_jump={params.th_jump} ..."
    )
    results = nulls.run_all(neurons, edges, draws, families, a.seed0)
    text = nulls.format_report(results)
    print(text)
    out = a.out or Path("runs/nulls")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.txt").write_text(text + "\n", encoding="utf-8")
    for family, got in results.items():
        got["headline"].to_csv(out / f"{family}-headline.csv", index=False)
        for metric, table in got["by_metric"].items():
            table.to_csv(out / f"{family}-{metric}.csv", index=False)
        got["real"].to_csv(out / f"{family}-real.csv", index=False)
    _stamp(
        out,
        "nulls",
        a,
        neurons,
        edges,
        {
            "families": list(families),
            "w_syn": params.w_syn,
            "th_jump": params.th_jump,
            "preregistration": locked["version"],
            "full": a.full,
        },
        {"seed0": a.seed0, "draws": draws},
        started,
    )


def cmd_select_model(a, neurons, edges):
    """Pre-registered selection between the calibrated model (A) and the published model at
    MaleCNS synapse density without compensation (B); B-/B+ are sensitivity variants."""
    started = datetime.now(UTC)
    fafb = data.load(a.data, "fafb")
    rho, n_types = compare.synapse_density_ratio((neurons, edges), fafb)
    lo, hi = a.rho_range
    w0 = sim.SHIU_W_SYN
    models = {
        "A": sim.Params(w_syn=w0, th_jump=a.th_jump_a),
        "B": sim.Params(w_syn=w0 / rho, th_jump=0.0),
        "B-": sim.Params(w_syn=w0 / lo, th_jump=0.0),
        "B+": sim.Params(w_syn=w0 / hi, th_jump=0.0),
    }
    # replication (pre-registered in docs/validation.md): A vs B- on fresh simulation seeds
    # and fresh control draws; B- replaces A unless A passes more checks
    eligible, tie_break = (["A", "B-"], "B-") if a.replication else (["A", "B"], "B")
    if a.replication:
        models = {k: models[k] for k in eligible}
    print(
        f"synapse density ratio {rho:.2f} ({n_types} matched types);"
        f" {len(models)} models x {a.seeds} seeds from seed {a.seed0},"
        f" control draws seed {a.control_seed} ..."
    )
    reports = validate.compare_models(
        neurons, edges, models, a.seeds, a.workers, a.seed0, a.control_seed
    )
    passed = {k: int(r["passed"].sum()) for k, r in reports.items()}
    for name, report in reports.items():
        print(f"\n=== {name}: {models[name]}")
        print(report.round(1).to_string(index=False))
        if a.out:
            tag = "replication-" if a.replication else ""
            report.to_csv(
                a.out / f"validate-v4-{tag}{a.seeds}seeds-{name}.csv", index=False
            )
    total = len(next(iter(reports.values())))
    print("\n" + ", ".join(f"{k} {v}/{total}" for k, v in passed.items()))
    winner = validate.select_model(passed, eligible, tie_break)
    print(f"winner (pre-registered rule): {winner}")
    if a.out:
        _stamp(
            a.out,
            "select-model",
            a,
            neurons,
            edges,
            {
                "replication": a.replication,
                "th_jump_a": a.th_jump_a,
                "rho_range": list(a.rho_range),
                "winner": winner,
            },
            {"seed0": a.seed0, "seeds": a.seeds, "control_seed": a.control_seed},
            started,
        )


def cmd_compare(a, neurons, edges):
    """Regenerate the male-vs-female numbers of docs/comparison.md."""
    started = datetime.now(UTC)
    male, female = (neurons, edges), data.load(a.data, "fafb")
    rho, n_types = compare.synapse_density_ratio(male, female)
    print(f"synapse density male/female: {rho:.2f} over {n_types} matched types")
    a.out.mkdir(parents=True, exist_ok=True)
    if a.sex:
        print(f"same model on both sexes, female w_syn x {rho:.2f} ...")
        table = compare.sex_comparison(
            male, female, compare.sex_cases(male, female), seeds=a.seeds,
            female_w_scale=rho,
        )  # fmt: skip
        _write(table, a.out / "sex-comparison.csv")
    if a.fingerprint:
        table = compare.fingerprint(male, female, a.fingerprint, compare.REFERENCE_SETS)
        print(table.round(2).to_string())
    if a.lb3_split:
        split = compare.lb3_split(male, female)
        print(
            pd.crosstab(split["shiu_set"], split["nearest"]).to_string(),
            end="\n\n",
        )
        _write(split, a.out / "lb3-fafb-split.csv")
        print(f"published model on the parts of their sugar set ({a.seeds} seeds) ...")
        print(
            compare.lb3_mn9_rates(female, split, seeds=a.seeds)
            .round(1)
            .to_string(index=False)
        )
    _stamp(
        a.out,
        "compare",
        a,
        neurons,
        edges,
        {"sex": a.sex, "fingerprint": a.fingerprint, "lb3_split": a.lb3_split},
        {"seeds": a.seeds},
        started,
    )


def _write(table, path) -> None:
    table.to_csv(path, index=False)
    print(table.round(3).to_string(index=False), f"\n-> {path}", sep="\n")


def cmd_dimorphism(a, neurons, edges):
    params = sim.Params(w_syn=a.w_syn, th_jump=a.th_jump)
    if a.by_type:
        case, category = a.by_type
        print(
            f"silencing the {category} responders of {case!r} one cell type at a time ..."
        )
        table = dimorphism.type_silencing(
            neurons, edges, params, case, category, a.seeds, a.workers, a.checkpoint
        )
        drops = [c for c in table.columns if c.endswith("_drop")]
        table = table.reindex(
            table[drops].abs().max(axis=1).sort_values(ascending=False).index
        )
    elif a.loop:
        print(f"{a.loop}: silencing each set vs matched active neurons ...")
        table = dimorphism.loop_silencing(
            neurons, edges, params, a.seeds, a.null, a.workers,
            sets=dimorphism.LOOP_PRESETS[a.loop], checkpoint=a.checkpoint,
        )  # fmt: skip
    elif a.silencing:
        print("silencing each category vs random silencings of the same size ...")
        table = dimorphism.silencing(
            neurons, edges, params, a.seeds, a.null, a.workers, checkpoint=a.checkpoint
        )
    else:
        print(
            "responders of each validation case vs superclass-matched random sets ..."
        )
        table = dimorphism.run(neurons, edges, params, a.seeds)
    print(table.round(3).to_string(index=False))


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
        _stamp(
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
        idx = viz.select_from_result(result, stim, a.min_rate)
        groups = np.where(np.isin(idx, stim), "stimulus", "response").tolist()
    scene = viz.export(a.out, neurons, idx, groups, result, edges)
    print(
        f"{len(scene['neurons'])} neurons exported to {a.out}/ (geometry streams from GCS)\n"
        f"view: python -m http.server -d {a.out} 8000  ->  http://localhost:8000"
    )
    _stamp(
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
        },
        {"seed": a.seed},
        started,
        extra={"n_exported": len(scene["neurons"])},
    )


COMMANDS = {
    "info": cmd_info,
    "path": cmd_path,
    "sim": cmd_sim,
    "validate": cmd_validate,
    "calibrate": cmd_calibrate,
    "compare": cmd_compare,
    "dimorphism": cmd_dimorphism,
    "select-model": cmd_select_model,
    "audit": cmd_audit,
    "viz": cmd_viz,
    "wiring-null": cmd_wiring_null,
    "nulls": cmd_nulls,
    "benchmarks": cmd_benchmarks,
    "behavior": cmd_behavior,
    "silence-scan": cmd_silence_scan,
    "trace": cmd_trace,
    "sensitivity": cmd_sensitivity,
    "experiment": cmd_experiment,
    "explore": cmd_explore,
    "confirm": cmd_confirm,
    "jump": cmd_jump,
    "loop": cmd_loop,
}
# these need the whole connectome loaded; fetch and build make it, and --progress
# only reads checkpoint files
MALECNS_ONLY = (
    "validate",
    "calibrate",
    "compare",
    "dimorphism",
    "viz",
    "wiring-null",
    "nulls",
    "benchmarks",
    "behavior",
    "silence-scan",
    "trace",
    "sensitivity",
    "experiment",
    "explore",
    "confirm",
    "jump",
    "loop",
)


def build_parser() -> argparse.ArgumentParser:
    """The command line, as a parser that can be built and inspected on its own."""
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
    s = sub.add_parser(
        "behavior",
        help="print the frozen one-bit looming-jump protocol, or run it with --run",
    )
    s.add_argument(
        "--run",
        action="store_true",
        help="run the frozen closed loop at the default parameters",
    )
    s = sub.add_parser(
        "benchmarks",
        help="print the frozen held-out manifest, or score it with --run",
    )
    s.add_argument(
        "--run",
        action="store_true",
        help="score the frozen cases at the default corner (no other parameters)",
    )
    s.add_argument(
        "--corners",
        action="store_true",
        help="score the two frozen sensitivity corners (does not replace --run)",
    )
    s = sub.add_parser(
        "experiment",
        help="validate and run an exploratory config (flymsg.experiment/v1)",
    )
    s.add_argument("config", type=Path)
    s.add_argument("--check", action="store_true", help="validate only")
    s.add_argument("--root", type=Path, default=Path("runs/experiments"))
    s = sub.add_parser(
        "jump",
        help="M1: drive a one-DOF jump body from a motor neuron through an engineered decoder",
    )
    s.add_argument("--sim", nargs="+", required=True, metavar="STIM")
    s.add_argument("--silence", nargs="+")
    s.add_argument("--motor", default="TTMn_R")
    s.add_argument(
        "--gain-n", type=float, required=True, help="newtons per spike (engineered)"
    )
    s.add_argument("--mass-kg", type=float, required=True)
    s.add_argument("--rate", type=float, default=100.0)
    s.add_argument("--duration", type=float, default=600.0)
    s.add_argument("--stim-ms", type=float, default=300.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", type=Path, default=Path("runs/jump"))
    s = sub.add_parser(
        "loop",
        help="M2: looming closed loop with disconnected, shuffled and replay controls",
    )
    s.add_argument("--sim", nargs="+", required=True, metavar="STIM")
    s.add_argument("--motor", default="TTMn_R")
    s.add_argument("--radius-m", type=float, required=True)
    s.add_argument("--distance-m", type=float, required=True)
    s.add_argument("--speed-m-s", type=float, required=True)
    s.add_argument(
        "--transducer-gain", type=float, required=True, help="Hz per rad/s (engineered)"
    )
    s.add_argument("--max-rate-hz", type=float, required=True)
    s.add_argument(
        "--gain-n", type=float, required=True, help="newtons per spike (engineered)"
    )
    s.add_argument("--mass-kg", type=float, required=True)
    s.add_argument("--duration", type=float, default=300.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", type=Path, default=Path("runs/loop"))
    s = sub.add_parser(
        "explore",
        help="paths between two populations, then silence each intermediate type (exploratory)",
    )
    s.add_argument("source", nargs="?")
    s.add_argument("target", nargs="?")
    s.add_argument("--paths", type=int, default=3)
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--seed0", type=int, default=0)
    s.add_argument("--silence", nargs="+", help="silenced in every arm (e.g. DNp01)")
    s.add_argument("--replay", type=Path, help="rerun a saved exploration and compare")
    s.add_argument("--out", type=Path, default=Path("runs/explore"))
    s = sub.add_parser(
        "confirm", help="run a registered intervention lock (flymsg.intervention/v1)"
    )
    s.add_argument("lock", type=Path)
    s.add_argument("--checkpoint", type=Path)
    s.add_argument("--out", type=Path, default=Path("runs/interventions"))
    s = sub.add_parser("runs", help="index every run manifest (no dataset needed)")
    s.add_argument(
        "roots", nargs="*", type=Path, default=[Path("runs"), Path("docs/live")]
    )
    s.add_argument("--label", choices=workbench.LABELS)
    s = sub.add_parser(
        "sensitivity",
        help="print the locked w_syn x th_jump grid, or run it with --run (a report)",
    )
    s.add_argument("--run", action="store_true")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--checkpoint", type=Path)
    s = sub.add_parser(
        "trace",
        help="record v, g, threshold, spikes and input of chosen neurons (exploratory)",
    )
    s.add_argument("stim", nargs="+", help="stimulated types/instances/bodyIds")
    s.add_argument(
        "--neurons", nargs="+", required=True, help="neurons to record (types/bodyIds)"
    )
    s.add_argument("--silence", nargs="+", help="neurons that never fire")
    s.add_argument("--rate", type=float, default=100.0)
    s.add_argument("--duration", type=float, default=600.0, help="ms")
    s.add_argument("--stim-ms", type=float, default=300.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--every", type=int, default=1, help="record every N neural steps")
    s.add_argument("--w-syn", type=float, default=sim.Params.w_syn)
    s.add_argument("--th-jump", type=float, default=sim.Params.th_jump)
    s.add_argument("--out", type=Path, default=Path("runs/trace"))
    s = sub.add_parser(
        "silence-scan",
        help="print the frozen residual TTMn_R partner scan (issue #20), or run it with --run",
    )
    s.add_argument("--run", action="store_true", help="run the frozen scan")
    s.add_argument("--workers", type=int, default=1, help="worker processes")
    s.add_argument(
        "--checkpoint",
        type=Path,
        help="JSON-lines file; an interrupted run resumes from it",
    )
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
        "wiring-null",
        help="N1: one degree-preserving shuffle, then criterion v4 on both graphs",
    )
    s.add_argument(
        "--stats",
        action="store_true",
        help="print the shuffle census and stop, without simulating",
    )
    s = sub.add_parser(
        "nulls",
        help="pre-registered null families (CI draw count by default; --full for 20)",
    )
    locked = prereg.load()
    s.add_argument(
        "--draws",
        type=int,
        default=locked["nulls"]["draws_ci"],
        help="seeded draws per family (default: CI count "
        f"{locked['nulls']['draws_ci']}; full protocol is "
        f"{locked['nulls']['draws_full']})",
    )
    s.add_argument(
        "--full",
        action="store_true",
        help=f"use the pre-registered full draw count ({locked['nulls']['draws_full']})",
    )
    s.add_argument(
        "--families",
        nargs="+",
        choices=list(nulls.FAMILIES),
        help="subset of families (default: all four)",
    )
    s.add_argument("--seed0", type=int, default=0, help="first shuffle seed")
    s.add_argument("--out", type=Path, default=Path("runs/nulls"))
    s.add_argument(
        "--exploratory",
        action="store_true",
        help="allow a draw count that is not the locked CI or full value",
    )
    s = sub.add_parser(
        "validate", help="run the validation battery (known circuits + controls)"
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--w-syn", type=float, default=sim.Params.w_syn)
    s.add_argument("--th-jump", type=float, default=sim.Params.th_jump)
    s.add_argument(
        "--out", type=Path, help="directory for report.csv and manifest.json"
    )
    s.add_argument(
        "--exploratory",
        action="store_true",
        help="allow w_syn, th_jump or seeds that differ from the preregistration",
    )
    s = sub.add_parser(
        "audit",
        help="reconstruction completeness: left/right asymmetry of bilateral types",
    )
    s.add_argument(
        "--types", nargs="+", help="types to report (default: those behind results)"
    )
    s.add_argument("--top", type=int, default=20, help="most asymmetric types to list")
    s = sub.add_parser(
        "select-model",
        help="pre-registered choice: calibrated model vs density-scaled model",
    )
    s.add_argument("--seeds", type=int, default=10)
    s.add_argument("--workers", type=int, default=4)
    # Pre-registered model A uses th_jump 2. The simulator default stays 0, so this
    # flag does not borrow sim.Params.th_jump.
    s.add_argument("--th-jump-a", type=float, default=2.0)
    s.add_argument(
        "--rho-range", type=float, nargs=2, default=[1.43, 2.43], metavar=("LO", "HI")
    )
    s.add_argument("--out", type=Path, help="directory for one CSV report per model")
    s.add_argument("--seed0", type=int, default=0, help="first simulation seed")
    s.add_argument(
        "--control-seed", type=int, default=0, help="seed of the control draws"
    )
    s.add_argument(
        "--replication",
        action="store_true",
        help="A vs B- only (the pre-registered replication; use fresh seeds)",
    )
    s = sub.add_parser(
        "compare",
        help="male vs female: synapse density, same model on both, the FAFB LB3 split",
    )
    s.add_argument("--sex", action="store_true", help="same model on both sexes")
    s.add_argument(
        "--fingerprint",
        nargs="+",
        metavar="TYPE",
        help="cosine of each male type's output profile against Shiu et al.'s FAFB sets",
    )
    s.add_argument(
        "--lb3-split",
        action="store_true",
        help="assign each FAFB LB3 neuron to a male subtype, then MN9 per part",
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--out", type=Path, default=Path("runs"))
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
    s.add_argument(
        "--loop",
        nargs="?",
        const="t2",
        choices=sorted(dimorphism.LOOP_PRESETS),
        help="instead: silence a pre-registered set of cell types vs matched responders"
        " (t2: the v0.5 loop; t3: the route it pointed to; t4: AVLP717m)",
    )
    s.add_argument("--null", type=int, default=1000, help="random silencings per test")
    s.add_argument(
        "--progress",
        action="store_true",
        help="instead: how far the run of --checkpoint has got (read-only, no data needed)",
    )
    s.add_argument(
        "--checkpoint",
        type=Path,
        help="save each finished job here and resume from it",
    )
    s.add_argument(
        "--by-type",
        nargs=2,
        metavar=("CASE", "CATEGORY"),
        help='instead: silence one type at a time, e.g. "P1 courtship drive" male-specific',
    )
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
    s.add_argument(
        "--silence", nargs="+", help="replay: neurons that never fire (types/bodyIds)"
    )
    s.add_argument("--out", type=Path, default=Path("runs/viz"))
    s = sub.add_parser(
        "viz-compare",
        help="pair two replay exports for side-by-side viewing (no simulation)",
    )
    s.add_argument("a", type=Path, help="baseline export directory")
    s.add_argument("b", type=Path, help="intervention export directory")
    s.add_argument("--labels", nargs=2, required=True, metavar=("A", "B"))
    s.add_argument(
        "--status",
        nargs=2,
        required=True,
        choices=viz.COMPARE_STATUSES,
        metavar=("A", "B"),
        help=f"protocol status of each run: {', '.join(viz.COMPARE_STATUSES)}",
    )
    s.add_argument("--notes", nargs=2, default=("", ""), metavar=("A", "B"))
    s.add_argument("--out", type=Path, default=Path("runs/viz-compare"))
    return p


def main() -> None:
    p = build_parser()
    a = p.parse_args()
    manifest.mark_start()
    if getattr(a, "progress", False) and a.checkpoint is None:
        p.error("--progress needs --checkpoint FILE")

    try:
        if a.cmd == "fetch":
            return data.fetch(a.data, a.dataset)
        if a.cmd == "build":
            return data.build(a.data, a.dataset)
        if getattr(a, "progress", False):  # reads the checkpoint files only
            return print(dimorphism.progress(a.checkpoint).to_string(index=False))
        if a.cmd == "runs":  # reads manifests only
            table = workbench.index(a.roots)
            if a.label and not table.empty:
                table = table[table["label"] == a.label]
            return print(table.to_string(index=False) if not table.empty else "no runs")
        if a.cmd == "sensitivity" and not a.run:
            return print(sensitivity.summary())
        if a.cmd == "viz-compare":  # reads two exports; loads no dataset
            scene = viz.compare_bundles(
                a.a, a.b, a.out, tuple(a.labels), tuple(a.status), tuple(a.notes)
            )
            for d in scene["comparison"]["differences"]:
                print(f"  differs: {d['key']}: {d['a']} -> {d['b']}")
            return print(f"{len(scene['neurons'])} neurons -> {a.out}/")
        if a.cmd == "silence-scan" and not a.run:
            return print(silence_scan.summary())
        if a.cmd == "behavior" and not a.run:
            return print(behavior.summary())
        if a.cmd == "benchmarks" and a.run and a.corners:
            p.error("benchmarks takes --run or --corners, not both")
        if a.cmd == "benchmarks" and not a.run and not a.corners:
            return print(benchmarks.summary())
        if a.dataset == "fafb" and a.cmd in MALECNS_ONLY:
            # the battery needs the VNC, and the 3D view streams MaleCNS geometry
            sys.exit(f"flymsg: {a.cmd} needs --dataset malecns")
        neurons, edges = data.load(a.data, a.dataset)
        COMMANDS[a.cmd](a, neurons, edges)
    except KeyError as err:  # unknown neuron query
        sys.exit(f"flymsg: {err.args[0]}")
    except OSError as err:  # missing data files, failed downloads
        sys.exit(f"flymsg: {err}")
    except draws.CheckpointMismatch as err:
        sys.exit(f"flymsg: {err}")
    except prereg.PreregistrationError as err:
        sys.exit(f"flymsg: {err}")
    except benchmarks.BenchmarkError as err:
        sys.exit(f"flymsg: {err}")
    except behavior.BehaviorError as err:
        sys.exit(f"flymsg: {err}")
    except intervention.InterventionError as err:
        sys.exit(f"flymsg: {err}")
    except workbench.ConfigError as err:
        sys.exit(f"flymsg: {err}")
    except sensitivity.SensitivityError as err:
        sys.exit(f"flymsg: {err}")
    except silence_scan.ScanError as err:
        sys.exit(f"flymsg: {err}")
    except ValueError as err:  # bad argument combinations reaching the model
        sys.exit(f"flymsg: {err}")
    except KeyboardInterrupt:
        resume = (
            " (rerun with the same --checkpoint to resume)"
            if getattr(a, "checkpoint", None)
            else ""
        )
        sys.exit(f"flymsg: interrupted{resume}")
