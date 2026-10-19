"""Commands that read the connectome itself: lookups, paths, audits, sex comparisons, and
the locked weight-rule comparison."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import (
    compare,
    data,
    dimorphism,
    graph,
    homology,
    managed,
    manifest,
    quality,
    sim,
    validate,
    weight_rule,
)
from flymsg.cli.common import label, ng_link, stamp


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


def cmd_homology(a, neurons, edges):
    """The versioned male/female type mapping and the LC4 -> DNp01 pilot."""
    started = datetime.now(UTC)
    female = data.load(a.data, "fafb")
    table = homology.mapping(neurons, female[0])
    pilot = homology.pilot((neurons, edges), female)
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "mapping.csv", index=False)
    pilot.to_csv(out / "pilot.csv", index=False)
    counts = table["category"].value_counts().reindex(homology.CATEGORIES, fill_value=0)
    print(counts.to_string())
    print(pilot.to_string(index=False))
    meta = {
        "schema": homology.SCHEMA,
        "evidence": homology.EVIDENCE,
        "male": manifest.dataset_info("malecns", a.data, neurons, edges),
        "female": manifest.dataset_info("fafb", a.data, *female),
        "categories": counts.to_dict(),
    }
    meta.update(
        git=manifest.git_info(),
        flymsg=manifest.package_versions().get("flymsg"),
        created_at=started.isoformat(),
        evidence_codes={"flywireType": homology.EVIDENCE},
    )
    (out / "mapping.meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True))
    stamp(
        out,
        "homology",
        a,
        neurons,
        edges,
        {"method": "published crosswalk; no inferred homology"},
        {},
        started,
        extra={"label": "exploratory"},
    )
    print(f"-> {out}")


def cmd_compare(a, neurons, edges):
    """Regenerate the male-vs-female numbers of docs/result/comparison.md."""
    started = datetime.now(UTC)
    male, female = (neurons, edges), data.load(a.data, "fafb")
    rho, n_types = compare.synapse_density_ratio(male, female)
    print(f"synapse density male/female: {rho:.2f} over {n_types} matched types")
    a.out.mkdir(parents=True, exist_ok=True)
    if a.sex:
        print(f"same model on both sexes, female w_syn x {rho:.2f} ...")
        table = compare.sex_comparison(
            male,
            female,
            compare.sex_cases(male, female),
            seeds=a.seeds,
            female_w_scale=rho,
        )
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
    stamp(
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
            neurons,
            edges,
            params,
            a.seeds,
            a.null,
            a.workers,
            sets=dimorphism.LOOP_PRESETS[a.loop],
            checkpoint=a.checkpoint,
        )
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
    out = a._run.output
    table.to_csv(out / "table.csv", index=False)
    stamp(
        out,
        "dimorphism",
        a,
        neurons,
        edges,
        {
            "loop": a.loop,
            "silencing": a.silencing,
            "by_type": a.by_type,
            "w_syn": params.w_syn,
            "th_jump": params.th_jump,
        },
        {"seeds": a.seeds, "null": a.null},
        datetime.now(UTC),
    )


def cmd_weight_rule(a, neurons, edges):
    """The frozen count-vs-density comparison on Liu et al. 2022's uEPSPs (issue #139)."""
    started = datetime.now(UTC)
    doc = weight_rule.assert_locked()
    print(weight_rule.summary(doc))
    areas = pd.read_csv(a.data / weight_rule.AREAS)
    out = weight_rule.run(doc, neurons, edges, areas)
    path = managed.output(a, Path("runs/weight-rule") / f"v{doc['version']}")
    path.mkdir(parents=True, exist_ok=True)
    out["primary_table"].to_csv(path / "pairs.csv", index=False)
    out["sensitivity_table"].to_csv(path / "sensitivity_pairs.csv", index=False)
    lines = [
        f"{name}: "
        + ", ".join(
            f"{k} {v:.4g}" if isinstance(v, float) else f"{k} {v}"
            for k, v in out[name].items()
        )
        for name in ("primary", "measured_only", "sensitivity")
    ]
    lines.append(f"density fit r2 (Pearson): {out['density_fit_r2']:.3f}")
    lines.append(f"missing areas: {out['missing_areas'] or 'none'}")
    lines.append(f"verdict: {out['verdict']}")
    text = "\n".join(lines)
    print(text)
    (path / "report.txt").write_text(text + "\n")
    stamp(
        path,
        "weight-rule --run",
        a,
        neurons,
        edges,
        {
            "weight_rule_version": doc["version"],
            "weight_rule_sha256": doc["content_sha256"],
        },
        {"bootstrap": [doc["protocol"]["seed"]]},
        started,
        extra={"verdict": out["verdict"]},
    )
    print(f"report -> {path / 'report.txt'}")
