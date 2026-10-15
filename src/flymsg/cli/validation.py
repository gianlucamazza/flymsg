"""Validation against the preregistered criteria, nulls, model selection, benchmarks."""

import sys
from datetime import UTC, datetime
from pathlib import Path

from flymsg import (
    apl_claws,
    baselines,
    benchmarks,
    compare,
    console,
    convergence,
    data,
    gf_looming,
    managed,
    nulls,
    prereg,
    sensitivity,
    sim,
    song,
    validate,
    wiring,
)
from flymsg.cli.common import stamp


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
    out = managed.output(a, a.out or Path("runs/validate"))
    out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "report.csv", index=False)
    stamp(
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
    out = managed.output(a, Path("runs"))
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
    stamp(
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
    out = managed.output(a, a.out or Path("runs/nulls"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.txt").write_text(text + "\n", encoding="utf-8")
    for family, got in results.items():
        got["headline"].to_csv(out / f"{family}-headline.csv", index=False)
        for metric, table in got["by_metric"].items():
            table.to_csv(out / f"{family}-{metric}.csv", index=False)
        got["real"].to_csv(out / f"{family}-real.csv", index=False)
    stamp(
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
            "exploratory": bool(a.exploratory),
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
        stamp(
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
    out = managed.output(a, Path("runs/benchmarks/corners"))
    out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "report.csv", index=False)
    stamp(
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
    out = managed.output(a, Path("runs/benchmarks"))
    out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "report.csv", index=False)
    stamp(
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


def cmd_sensitivity(a, neurons, edges):
    """Run the locked sensitivity grid and write every cell, the spreads and a figure."""
    started = datetime.now(UTC)
    doc = sensitivity.assert_matches_code()
    print(sensitivity.summary(doc))
    cells = sensitivity.run(neurons, edges, a.workers, a.checkpoint)
    out = managed.output(a, Path("runs/sensitivity") / f"v{doc['version']}")
    out.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out / "cells.csv", index=False)
    held = sensitivity.holds(cells, doc)
    held.to_csv(out / "holds.csv", index=False)
    spread = sensitivity.spreads(cells)
    spread.to_csv(out / "spreads.csv", index=False)
    (out / "rate.svg").write_text(sensitivity.svg(cells, doc))
    grid = held.assign(holds=held["holds"].map({True: "yes", False: "no"})).pivot_table(
        index=["case", "target"],
        columns=["th_jump", "w_syn_factor"],
        values="holds",
        aggfunc="first",
    )
    text = "\n".join(
        [
            sensitivity.summary(doc),
            "holds (v4 floor) per cell:",
            grid.to_string(),
            "spreads (seed range at the default cell vs range of medians over cells):",
            spread.to_string(index=False),
        ]
    )
    (out / "report.txt").write_text(text + "\n")
    print(text)
    stamp(
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


def cmd_baselines(a, neurons, edges):
    """Run the locked battery baselines and write every cell and the judgement."""
    started = datetime.now(UTC)
    doc = baselines.assert_matches_code()
    print(baselines.summary(doc))
    cells = baselines.run(neurons, edges, a.workers, a.checkpoint, a.backend)
    out = managed.output(a, Path("runs/baselines") / f"v{doc['version']}")
    out.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out / "cells.csv", index=False)
    judged = baselines.judge(cells, doc)
    judged.to_csv(out / "judged.csv", index=False)
    verdict = baselines.verdict(judged)
    text = "\n".join(
        [baselines.summary(doc), judged.to_string(index=False), f"verdict: {verdict}"]
    )
    (out / "report.txt").write_text(text + "\n")
    print(text)
    stamp(
        out,
        "baselines --run",
        a,
        neurons,
        edges,
        {
            "baselines_version": doc["version"],
            "baselines_sha256": doc["content_sha256"],
            "backend": a.backend,
            "battery": doc["battery"],
            "baseline": doc["baseline"],
        },
        {"seed0": doc["battery"]["seed0"], "seeds": doc["battery"]["seeds"]},
        started,
        {"verdict": verdict, **console.lineage(a.backend)},
    )
    print(f"report -> {out / 'report.txt'}")


def cmd_convergence(a, neurons, edges):
    """Run the locked timestep convergence check and write every cell and the judgement."""
    started = datetime.now(UTC)
    doc = convergence.assert_matches_code()
    print(convergence.summary(doc))
    cells = convergence.run(neurons, edges, a.workers, a.checkpoint)
    out = managed.output(a, Path("runs/convergence") / f"v{doc['version']}")
    out.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out / "cells.csv", index=False)
    judged = convergence.judge(cells, doc)
    judged.to_csv(out / "judged.csv", index=False)
    verdict = convergence.verdict(judged, doc)
    text = "\n".join(
        [
            convergence.summary(doc),
            judged.to_string(index=False),
            f"verdict: {verdict}",
        ]
    )
    (out / "report.txt").write_text(text + "\n")
    print(text)
    stamp(
        out,
        "convergence --run",
        a,
        neurons,
        edges,
        {
            "convergence_version": doc["version"],
            "convergence_sha256": doc["content_sha256"],
            "grid": doc["grid"],
        },
        {"seed0": doc["grid"]["seed0"], "seeds": doc["grid"]["seeds"]},
        started,
        {"verdict": verdict},
    )
    print(f"report -> {out / 'report.txt'}")


def cmd_song(a, neurons, edges):
    """Run the locked pulse/sine benchmark: the model and its no-go first, then the data."""
    started = datetime.now(UTC)
    doc = song.assert_matches_code()
    print(song.summary(doc))
    regions = song.region_table(a.data, doc)
    ratios = song.yamakoshi_ratios(
        a.data / "raw" / "yamakoshi2025" / song.YAMAKOSHI, doc
    )
    cells, labels = song.run(neurons, edges, regions, ratios, a.workers, a.checkpoint)
    out = managed.output(a, Path("runs/song") / f"v{doc['version']}")
    out.mkdir(parents=True, exist_ok=True)
    cells.to_json(out / "cells.jsonl", orient="records", lines=True)
    result = song.evaluate(cells, labels, a.data, doc)
    signs = result.pop("model")
    signs.to_csv(out / "model.csv", index=False)
    lines = [song.summary(doc), f"JO A/B ratios (Yamakoshi): {ratios}"]
    if "targets" in result:
        targets = result.pop("targets")
        targets.to_csv(out / "data.csv", index=False)
        both = signs.merge(
            targets, on="label", how="outer", suffixes=("_model", "_data")
        )
        lines.append(both.to_string(index=False))
    result["ratios"] = ratios
    lines += [f"{k}: {v}" for k, v in result.items() if k != "verdict"]
    lines.append(f"verdict: {result['verdict']}")
    text = "\n".join(str(x) for x in lines)
    (out / "report.txt").write_text(text + "\n")
    print(text)
    stamp(
        out,
        "song --run",
        a,
        neurons,
        edges,
        {
            "song_version": doc["version"],
            "song_sha256": doc["content_sha256"],
            "grid": doc["grid"],
        },
        {"seed0": doc["grid"]["seed0"], "seeds": doc["grid"]["seeds"]},
        started,
        {"verdict": result["verdict"]},
    )
    print(f"report -> {out / 'report.txt'}")


def cmd_gf_looming(a, neurons, edges):
    """Run the locked looming -> giant fiber timing benchmark: the model and its no-go
    first, then the data."""
    started = datetime.now(UTC)
    doc = gf_looming.assert_matches_code()
    print(gf_looming.summary(doc))
    gf_looming.inputs_present(a.data, doc)  # present before hours of model; not opened
    rows = gf_looming.run(neurons, edges, a.workers, a.checkpoint)
    out = managed.output(a, Path("runs/gf_looming") / f"v{doc['version']}")
    out.mkdir(parents=True, exist_ok=True)
    rows.to_csv(out / "runs.csv", index=False)
    result = gf_looming.evaluate(rows, a.data, doc)
    fits = result.pop("model")
    fits.to_csv(out / "model.csv", index=False)
    lines = [gf_looming.summary(doc), fits.to_string(index=False)]
    if "flies_table" in result:
        flies = result.pop("flies_table")
        flies.to_csv(out / "data.csv", index=False)
        lines.append(flies.to_string(index=False))
    lines += [f"{k}: {v}" for k, v in result.items() if k != "verdict"]
    lines.append(f"verdict: {result['verdict']}")
    text = "\n".join(str(x) for x in lines)
    (out / "report.txt").write_text(text + "\n")
    print(text)
    m = doc["model"]
    stamp(
        out,
        "gf-looming --run",
        a,
        neurons,
        edges,
        {
            "gf_looming_version": doc["version"],
            "gf_looming_sha256": doc["content_sha256"],
            "drive": doc["drive"],
            "model": m,
        },
        {"seed0": m["seed0"], "seeds": m["seeds"]},
        started,
        {"verdict": result["verdict"]},
    )
    print(f"report -> {out / 'report.txt'}")


def cmd_apl_claws(a, neurons, edges):
    """Run the locked APL claw contrast benchmark and write every cell and the judgement."""
    started = datetime.now(UTC)
    doc = apl_claws.assert_matches_code()
    print(apl_claws.summary(doc))
    cells = apl_claws.run(neurons, edges, a.data, a.workers, a.checkpoint)
    out = managed.output(a, Path("runs/apl_claws") / f"v{doc['version']}")
    out.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out / "cells.csv", index=False)
    judged = apl_claws.judge(cells, doc)
    judged.to_csv(out / "judged.csv", index=False)
    verdict = apl_claws.verdict(judged)
    text = "\n".join(
        [
            apl_claws.summary(doc),
            judged.to_string(index=False),
            apl_claws.describe(judged),
            f"verdict: {verdict}",
        ]
    )
    (out / "report.txt").write_text(text + "\n")
    print(text)
    stamp(
        out,
        "apl-claws --run",
        a,
        neurons,
        edges,
        {
            "apl_claws_version": doc["version"],
            "apl_claws_sha256": doc["content_sha256"],
            "protocol": doc["protocol"],
            "arms": doc["arms"],
        },
        {"all": list(doc["protocol"]["seeds"])},
        started,
        {"verdict": verdict},
    )
    print(f"report -> {out / 'report.txt'}")
