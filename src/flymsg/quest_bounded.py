"""Disposable, independently checked bounded-path experiment on an explicit Quest.

This records serialized fixed-camera diagnostics, never production or XR admission.
"""

import argparse
import json
import math
import statistics
from pathlib import Path

from flymsg.quest_xr import QuestSite, node_json, wifi_serial


def assess(report):
    """Recompute exploratory gains from raw samples; geometry is checked in-browser."""
    if (
        report.get("schema") != "flymsg.bounded-skeleton-experiment/v1"
        or report.get("normal_xr_qualification") is not False
        or report.get("original_reference_unchanged") is not True
        or report.get("error_contract_px") != 0.5
        or len(report.get("blocks", [])) != 3
    ):
        raise ValueError("incomplete disposable experiment")
    neurons = report["neurons"]
    if (
        len(neurons) != len(report["original_reference"]["neurons"])
        or {n["k"] for n in neurons}
        != {n["k"] for n in report["original_reference"]["neurons"]}
        or any(not 0 <= n["maximum_error_px"] <= 0.5 for n in neurons)
    ):
        raise ValueError("incomplete selected content or failed error report")
    ratios, medians = [], []
    for repeat, block in enumerate(report["blocks"]):
        if block["repeat"] != repeat or [a["mode"] for a in block["arms"]] != [
            "original",
            "bounded",
            "bounded",
            "original",
        ]:
            raise ValueError("three complete interleaved blocks required")
        values = []
        for arm in block["arms"]:
            count_key = (
                "candidate_edges" if arm["mode"] == "bounded" else "original_edges"
            )
            if arm.get("submitted_lines") != sum(n[count_key] for n in neurons):
                raise ValueError(
                    "actual submitted skeleton count differs from source proof"
                )
            samples = arm["serialized_wall_ms"]
            if len(samples) != 8 or any(
                not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
                for v in samples
            ):
                raise ValueError(
                    "eight finite positive completed-image samples required"
                )
            values.append(statistics.median(samples))
        original = statistics.median([values[0], values[3]])
        bounded = statistics.median(values[1:3])
        medians.append({"original_ms": original, "bounded_ms": bounded})
        ratios.append(bounded / original)
    return {
        "selected_neurons": len(neurons),
        "original_segments": sum(n["original_edges"] for n in neurons),
        "bounded_segments": sum(n["candidate_edges"] for n in neurons),
        "maximum_error_px": max(n["maximum_error_px"] for n in neurons),
        "preparation_ms": report["preparation_ms"],
        "paired_medians": medians,
        "ratios": ratios,
        "exploratory_gain_gate": all(r <= 0.9 for r in ratios),
        "normal_xr_qualification": False,
        "production_admitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial", required=True, type=wifi_serial)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--port", type=int, default=8894)
    p.add_argument("--unattended", action="store_true")
    args = p.parse_args()
    session = QuestSite(
        args.serial,
        args.out,
        port=args.port,
        keep_awake=True,
        wifi_only=True,
        unattended=args.unattended,
    )
    with session:
        session.open(representation="skeleton", uploads=False, culling=False)
        ready = session.wait_ready(
            timeout=600, evidence=args.out / "preflight.jsonl", readback_only=True
        )
        if not ready["eligible"]:
            raise RuntimeError("source scene unavailable: " + str(ready["reasons"]))
        results = {}
        for view in ("dense", "close"):
            _, code = node_json(
                "observer_bounded.mjs",
                session.endpoint,
                session.target,
                args.out / view,
                view,
                timeout=240,
            )
            if code:
                raise RuntimeError("bounded experiment failed: " + view)
            report = json.loads((args.out / view / "experiment.json").read_text())
            results[view] = assess(report)
            session.record("bounded-summary.json", results)
    if not session.cleanup["ok"]:
        raise RuntimeError("device cleanup failed; retain cleanup.json")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
