"""Execute the locked synthetic retinal causal fixture; never score physiology."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from scipy import sparse

from flymsg import eye, sim, visual_pathway
from flymsg.paths import repository_root
from flymsg.runtime import CpuRuntime

ROOT = repository_root()
LOCK = ROOT / "validation/optic-causality-v1.json"


def run(checkpoint_dir: Path) -> dict:
    doc = json.loads(LOCK.read_text())
    rows = doc["network"]["edges_post_pre_weight"]
    W = sparse.csc_matrix(
        ([r[2] for r in rows], ([r[0] for r in rows], [r[1] for r in rows])),
        shape=(3, 3),
        dtype=np.float32,
    )
    g = doc["graded"]
    graded = sim.Graded(
        np.arange(3),
        np.array(g["v_lo_mv"]),
        np.array(g["span_mv"]),
        np.array(g["rate_hz"]),
    )
    stimulus = doc["stimulus"]

    def execute(dt, coverage, *, disconnected=False, silenced=False, missing=False):
        p = sim.Params(dt=dt)
        steps = round(stimulus["duration_ms"] / dt)
        kicks = eye.photoreceptor_kicks(
            np.full((steps, 1), coverage),
            np.array([-1 if missing else 0]),
            visual_pathway.photoreceptor_gain(stimulus["photoreceptor_response_mv"], p),
        ).astype(np.float32)
        weights = W.copy()
        if disconnected:
            weights[1, 0] = 0
        silence = np.array([0]) if silenced else None
        args = dict(p=p, graded=graded, silence=silence, kicks=kicks)
        result = sim.run(
            weights,
            np.array([0]),
            duration_ms=stimulus["duration_ms"],
            bin_ms=stimulus["bin_ms"],
            **args,
        )
        return result, weights, args

    outputs = {}
    for dt in doc["dt_ms"]:
        for label, cov in zip(("light", "dark"), stimulus["coverage"], strict=True):
            outputs[dt, label] = execute(dt, cov)[0]
    dt = doc["dt_ms"][0]
    light, dark = outputs[dt, "light"], outputs[dt, "dark"]
    delta = light.graded_v[-1] - dark.graded_v[-1]
    gates = {"causality": bool(delta[0] > 0 and (delta[1:] < 0).all())}
    gates["null"] = all(
        np.array_equal(
            execute(dt, 0.0, **{arm: True})[0].graded_v[:, 1:],
            execute(dt, 1.0, **{arm: True})[0].graded_v[:, 1:],
        )
        for arm in ("disconnected", "silenced")
    )
    gates["missing"] = np.array_equal(
        execute(dt, 0.0, missing=True)[0].graded_v, dark.graded_v
    )
    _, weights, args = execute(dt, 0.0)
    runtime_args = dict(
        steps=round(stimulus["duration_ms"] / dt),
        per_bin=round(stimulus["bin_ms"] / dt),
        input_encoding="kick_equivalent",
        **args,
    )
    rt = CpuRuntime(weights, np.array([0]), **runtime_args)
    rt.advance_to(137)
    checkpoint = checkpoint_dir / "retinal.npz"
    rt.checkpoint(checkpoint)
    restored = CpuRuntime(weights, np.array([0]), **runtime_args)
    restored.restore(checkpoint)
    for runtime in (rt, restored):
        runtime.advance_to(runtime_args["steps"])

    def identical(a, b):
        return np.array_equal(a.graded_v, b.graded_v) and np.array_equal(
            a.counts, b.counts
        )

    gates["parity"] = identical(rt.result(), light)
    gates["replay"] = identical(rt.result(), restored.result()) and identical(
        execute(dt, 0.0)[0], light
    )
    errors = {}
    for label in ("light", "dark"):
        reference = outputs[doc["dt_ms"][-1], label].graded_v[-1]
        errors[label] = [
            float(np.max(np.abs(outputs[d, label].graded_v[-1] - reference)))
            for d in doc["dt_ms"][:-1]
        ]
    gates["convergence"] = all(e[1] < e[0] and e[1] < 0.1 for e in errors.values())
    gates["spikes"] = all(not out.counts.any() for out in outputs.values())
    return {
        "schema": doc["schema"],
        "evidence_status": "SYNTHETIC",
        "physiology_status": "UNKNOWN",
        "engineering_verdict": "PASS" if all(gates.values()) else "FAILED",
        "gates": {k: bool(v) for k, v in gates.items()},
        "light_minus_dark_final_bin_mv": delta.tolist(),
        "convergence_error_mv": errors,
        "lock_sha256": hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "final_bin_mv": {
            f"{d}/{label}": out.graded_v[-1].tolist()
            for (d, label), out in outputs.items()
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT
    ):
        parser.error("commit tracked changes before recording evidence")
    with tempfile.TemporaryDirectory() as directory:
        report = run(Path(directory))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(report["engineering_verdict"])
    raise SystemExit(0 if report["engineering_verdict"] == "PASS" else 1)
