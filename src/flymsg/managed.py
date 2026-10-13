"""CLI integration of the common experiment lifecycle; no scientific policy lives here."""

import json
from contextlib import ExitStack
from importlib import metadata
from pathlib import Path

from flymsg import (
    behavior,
    benchmarks,
    data,
    eye,
    jump3d_lock,
    kc_sparseness,
    odors,
    partner_followup,
    plasticity,
    prereg,
    runstore,
    sensitivity,
    silence_scan,
    t4t5,
)

PROTOCOLS = {
    "validate": prereg,
    "nulls": prereg,
    "select-model": prereg,
    "behavior": behavior,
    "benchmarks": benchmarks,
    "sensitivity": sensitivity,
    "silence-scan": silence_scan,
    "partner-followup": partner_followup,
    "mb-plasticity": plasticity,
    "kc-sparseness": kc_sparseness,
    "t4t5": t4t5,
    "jump3d": jump3d_lock,
    "calibrate": prereg,
    "wiring-null": prereg,
    "dimorphism": prereg,
    "sim": None,
    "trace": None,
    "compare": None,
    "homology": None,
    "jump": None,
    "loop": None,
}


FILE_OUTPUT = {"sim", "calibrate"}


def enabled(a):
    if a.cmd not in PROTOCOLS:
        return False
    if a.cmd == "wiring-null" and a.stats:
        return False
    return a.cmd not in {"select-model", *FILE_OUTPUT} or a.out is not None


def prepare(a):
    """Resolve all assets and freeze identity before data.load reads the compact tables."""
    if not enabled(a):
        return None
    module = PROTOCOLS[a.cmd]
    doc = module.load() if module is not None else {}
    base = a.data / "fafb" if a.dataset == "fafb" else a.data
    paths = {name: base / name for name in ("neurons.parquet", "edges.parquet")}
    for path in paths.values():
        if not path.is_file():
            raise ValueError(f"missing input {path}; run flymsg fetch/build")
    if a.cmd in {"select-model", "compare", "homology"}:
        paths.update(
            {
                f"fafb/{name}": a.data / "fafb" / name
                for name in ("neurons.parquet", "edges.parquet")
            }
        )
    if a.cmd == "kc-sparseness" and doc["protocol"].get("odor_source") == "door":
        odors.fetch(a.data)
        paths.update(
            {f"door/{name}": odors.raw_dir(a.data) / name for name in odors.DOOR_FILES}
        )
    if a.cmd == "t4t5":
        eye.fetch(a.data)
        paths.update(
            {f"eyemap/{name}": eye.raw_dir(a.data) / name for name in eye.EYEMAP_FILES}
        )
        paths["raw/annotations"] = a.data / "raw" / data.RAW["annotations"]
    if a.cmd == "jump3d":
        distribution = metadata.distribution("flygym")
        paths.update(
            {
                str(p): Path(distribution.locate_file(p))
                for p in distribution.files
                if str(p).startswith("flygym/assets/")
            }
        )
    for path in paths.values():
        if not path.is_file():
            raise ValueError(f"missing input {path}; run flymsg fetch/build")
    config = {
        k: v
        for k, v in vars(a).items()
        if k not in {"data", "out", "checkpoint", "cmd"} and not k.startswith("_")
    }
    # Namespace flags are JSON scalars/lists; paths outside the execution assets are not inputs.
    config = json.loads(json.dumps(config, default=str))
    identity = runstore.execution(a.cmd, config, doc, paths)
    return identity, paths, doc


def base_path(a, doc):
    if getattr(a, "out", None) is not None:
        return a.out.with_suffix("") if a.cmd in FILE_OUTPUT else a.out
    if a.cmd == "benchmarks" and a.corners:
        return Path("runs/benchmarks/corners")
    if a.cmd in {
        "validate",
        "behavior",
        "benchmarks",
        "nulls",
        "wiring-null",
        "dimorphism",
    }:
        return Path("runs") / a.cmd
    return Path("runs") / a.cmd / f"v{doc['version']}"


def output(a, historical):
    """Resolve every sister writer through the same policy; callers do not choose latest."""
    run = getattr(a, "_run", None)
    return run.output if run is not None else historical


def execute(a, neurons, edges, command, prepared):
    if prepared is None:
        return command(a, neurons, edges)
    identity, paths, doc = prepared
    # Detect changes while data.load was reading, before creating outputs or computing.
    runstore.verify_execution(identity, paths)
    original_out = getattr(a, "out", None)
    original_checkpoint = getattr(a, "checkpoint", None)
    with runstore.Run(base_path(a, doc), identity) as run:
        if run.completed:
            print(f"verified completed execution {run.id}: {run.output}")
            if run.exit_code:
                raise SystemExit(run.exit_code)
            return
        a._run = run
        if hasattr(a, "out"):
            a.out = (
                run.output / original_out.name if a.cmd in FILE_OUTPUT else run.output
            )
        if hasattr(a, "checkpoint"):
            a.checkpoint = original_checkpoint or run.root / "draws.ckpt.jsonl"
        a._dataset_snapshot = {
            "name": a.dataset,
            "release": "v1.0" if a.dataset == "malecns" else a.dataset,
            "n_neurons": len(neurons),
            "n_edges": len(edges),
            "files": {
                k: v
                for k, v in identity["inputs"].items()
                if k in {"neurons.parquet", "edges.parquet"}
            },
        }
        try:
            with ExitStack() as ownership:
                if hasattr(a, "checkpoint"):
                    ownership.enter_context(
                        runstore.checkpoint_owner(a.checkpoint, identity)
                    )
                    run.attempts[-1]["checkpoint"] = str(a.checkpoint.resolve())
                try:
                    result = command(a, neurons, edges)
                except SystemExit as exc:
                    # A scored validation failure is a completed scientific result.
                    if (
                        a.cmd == "validate"
                        and exc.code == 1
                        and (run.output / "manifest.json").is_file()
                    ):
                        runstore.verify_execution(identity, paths)
                        run.finalize(exit_code=1)
                    raise
                runstore.verify_execution(identity, paths)
                run.finalize()
                print(f"completed execution {run.id}: {run.output}")
                return result
        finally:
            a.out = original_out
            if hasattr(a, "checkpoint"):
                a.checkpoint = original_checkpoint
            del a._run, a._dataset_snapshot
