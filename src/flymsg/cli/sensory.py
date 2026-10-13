"""Eye and odor inputs, and the frozen sensory locks built on them."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from flymsg import data, eye, kc_sparseness, managed, odors, plasticity, progress, t4t5
from flymsg.cli.common import stamp


def cmd_eye(a, neurons, edges):
    """Column -> viewing direction table and the photoreceptor -> column assignment (#84).
    Fetches the GPL-3.0 eye map into data/raw/eyemap on first use; outputs stay in data/."""
    eye.fetch(a.data)
    ann = pd.read_feather(
        a.data / "raw" / data.RAW["annotations"],
        columns=["bodyId", "type", "instance", "assignedOlHex1", "assignedOlHex2"],
    )
    cols = eye.columns(ann, eye.lenses(a.data))
    receptors = eye.photoreceptors(neurons, edges, ann)
    out = a.data / "eye"
    out.mkdir(exist_ok=True)
    cols.to_parquet(out / "columns.parquet")
    receptors.to_parquet(out / "photoreceptors.parquet")
    c = eye.check(cols, receptors)
    for s in "LR":
        print(
            f"{s}: {c['with_direction'][s]} of {c['columns'][s]} columns have a direction"
        )
    print("photoreceptors per column:", c["receptors"])
    print(
        f"dorsal-rim R7d/R8d columns: median elevation {c['dorsal_rim_elevation_deg']:.1f} deg; "
        f"other R7/R8: {c['other_r7_r8_elevation_deg']:.1f} deg"
    )
    print(f"-> {out / 'columns.parquet'}, {out / 'photoreceptors.parquet'}")


def cmd_odor(a, neurons, edges):
    """A DoOR odorant as a response per MaleCNS ORN type (#96). Fetches DoOR (CC BY-SA 4.0)
    into data/raw/door on first use; nothing is redistributed."""
    odors.fetch(a.data)
    responses, mappings, odor_table = odors.tables(a.data)
    types = set(
        neurons["type"].dropna()[neurons["type"].dropna().str.startswith("ORN_")]
    )
    v = odors.vector(responses, mappings, odor_table, a.name, types)
    c = odors.coverage(responses, odor_table, a.name, v)
    print(
        f"{a.name}: {c['measured']} of {c['receptors']} DoOR receptors measured, "
        f"{c['in_volume']} map to a MaleCNS ORN type"
    )
    print(odors.per_type(v).round(3).to_string())


def cmd_t4t5(a, neurons, edges):
    """The frozen T4/T5 direction-selectivity test through the eye (issues #84, #97)."""
    started = datetime.now(UTC)
    doc = t4t5.assert_matches_code()
    print(t4t5.summary(doc))
    path = managed.output(
        a, Path("runs/t4t5") / f"v{doc['version']}"
    )  # never overwrite
    path.mkdir(parents=True, exist_ok=True)
    steps = progress.Steps(a._run.root / "steps", a._run.identity)
    out = t4t5.run(
        neurons, edges, a.data, steps, progress.Progress(t4t5.n_runs(doc), "t4t5")
    )
    for name in ("table", "metrics", "pathway", "lmc", "configurations"):
        out[name].to_csv(
            path / f"{'spikes' if name == 'table' else name}.csv", index=False
        )
    text = "\n".join(
        [
            f"window columns: {out['window_columns']}",
            out["configurations"].round(3).to_string(index=False),
            out["lmc"]
            .groupby("config")[["settled_mv", "lowest_mv", "highest_mv"]]
            .median()
            .round(2)
            .to_string(),
            out["pathway"].groupby("config").sum(numeric_only=True).to_string(),
            f"verdict: {out['verdict']}",
        ]
    )
    print(text)
    (path / "report.txt").write_text(text + "\n")
    proto = doc["protocol"]
    stamp(
        path,
        "t4t5 --run",
        a,
        neurons,
        edges,
        {
            "t4t5_version": doc["version"],
            "t4t5_sha256": doc["content_sha256"],
            "speed_deg_s": proto["speed_deg_s"],
            "acceptance_deg": proto["acceptance_deg"],
            "envelope": proto["envelope"],
        },
        {"all": [proto["seed"]]},
        started,
        extra={"verdict": out["verdict"], "resumed_steps": steps.resumed},
    )
    print(f"report -> {path / 'report.txt'}")


def cmd_kc_sparseness(a, neurons, edges):
    """The frozen Kenyon cell sparseness diagnostic (issue #95)."""
    started = datetime.now(UTC)
    doc = kc_sparseness.assert_matches_code()
    print(kc_sparseness.summary(doc))
    path = managed.output(
        a, Path("runs/kc-sparseness") / f"v{doc['version']}"
    )  # never overwrite
    path.mkdir(parents=True, exist_ok=True)
    steps = progress.Steps(a._run.root / "steps", a._run.identity)
    out = kc_sparseness.run(
        neurons,
        edges,
        a.data,
        steps,
        progress.Progress(kc_sparseness.n_runs(doc), "kc-sparseness"),
    )
    out["table"].to_csv(path / "arms.csv", index=False)
    text = out["table"].to_string(index=False) + f"\nverdict: {out['verdict']}"
    print(text)
    (path / "report.txt").write_text(text + "\n")
    proto = doc["protocol"]
    stamp(
        path,
        "kc-sparseness --run",
        a,
        neurons,
        edges,
        {
            "sparseness_version": doc["version"],
            "electrical_semantics": kc_sparseness.electrical_semantics(doc),
            "sparseness_sha256": doc["content_sha256"],
            "rate_hz": proto.get("rate_hz", proto.get("rate_at_response_1_hz")),
            "odor_source": proto.get("odor_source", "orn_type"),
            "odor_ms": proto["odor_ms"],
        },
        {"all": list(proto["seeds"])},
        started,
        extra={
            "verdict": out["verdict"],
            "resumed_steps": steps.resumed,
        },
    )
    print(f"report -> {path / 'report.txt'}")


def cmd_mb_plasticity(a, neurons, edges):
    """The frozen KC -> MBON11 depression protocol (issue #85). No flag changes the rule."""
    started = datetime.now(UTC)
    doc = plasticity.assert_matches_code()
    print(plasticity.summary(doc))
    out = plasticity.run(neurons, edges)
    path = managed.output(
        a, Path("runs/mb-plasticity") / f"v{doc['version']}"
    )  # never overwrite
    path.mkdir(parents=True, exist_ok=True)
    out["table"].to_csv(path / "counts.csv", index=False)
    text = "\n".join(
        [
            out["table"].to_string(index=False),
            f"CS+ drop: {out['cs_plus_drop']:.3f}",
            f"CS- drop: {out['cs_minus_drop']:.3f}",
            f"verdict: {out['verdict']}",
        ]
    )
    print(text)
    (path / "report.txt").write_text(text + "\n")
    proto = doc["protocol"]
    stamp(
        path,
        "mb-plasticity --run",
        a,
        neurons,
        edges,
        {
            "plasticity_version": doc["version"],
            "plasticity_sha256": doc["content_sha256"],
            "factor": doc["rule"]["factor"],
            "rate_hz": proto["rate_hz"],
            "odor_ms": proto["odor_ms"],
        },
        {"all": list(proto["seeds"])},
        started,
        extra={"verdict": out["verdict"]},
    )
    print(f"report -> {path / 'report.txt'}")
