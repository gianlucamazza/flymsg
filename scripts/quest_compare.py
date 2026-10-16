"""Wi-Fi-only, full-content A/B/B/A observer trials with explicit admission gates.

Correctness readbacks use separate pages. A/B/B/A arms always start new documents.
No source change, hidden geometry, shader substitution or second animation loop.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quest_xr import QuestSite, identity, node_json, wifi_serial

from flymsg import runstore

VIEWS = ("dense-all", "anatomical-motion", "close-motion", "close-static")
ORDER = ("original", "paged", "paged", "original")


def blocks(page_sizes=(4, 16, 64), repeats=3):
    return [
        {"page_mib": size, "view": view, "repeat": repeat}
        for size in page_sizes
        for view in VIEWS
        for repeat in range(repeats)
    ]


def block_summary(records):
    if len(records) != 4 or not all(record.get("eligible") for record in records):
        raise ValueError("four eligible A/B/B/A arms required")
    # Page identity changes per arm; image quality, selected content and frozen camera must not.
    first = records[0]

    def invariant(record):
        return {
            "camera": record["camera_profile"],
            "settings": record["render_settings"],
            "source": record["source_sha256"],
            "anatomy": {
                key: record["identity"][key]
                for key in (
                    "representation",
                    "selected",
                    "represented",
                    "width",
                    "height",
                )
            },
        }

    if any(invariant(row) != invariant(first) for row in records[1:]):
        raise ValueError("A/B/B/A source, geometry, viewport or quality mismatch")

    def p95(row):
        values = row["raw_intervals_ms"]
        if len(values) < 20 or any(
            not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in values
        ):
            raise ValueError("at least twenty finite positive raw intervals required")
        value = sorted(values)[math.ceil(len(values) * 0.95) - 1]
        if row["intervals_ms"]["p95"] != value:
            raise ValueError("reported cadence differs from raw intervals")
        return value

    original = statistics.median(p95(row) for row in (records[0], records[3]))
    paged = statistics.median(p95(row) for row in (records[1], records[2]))
    if original <= 0:
        raise ValueError("positive original cadence required")
    memory = [
        row["after"]["resources"]["gpu_resources"].get("owned_gpu_bytes")
        for row in (records[1], records[2])
    ]
    memory = [value for value in memory if isinstance(value, (int, float))]
    return {
        "original_p95_ms": original,
        "paged_p95_ms": paged,
        "ratio": paged / original,
        "paged_memory_bytes": max(memory) if memory else None,
    }


def admission(results, page_sizes=(4, 16, 64), repeats=3):
    candidates = []
    for size in page_sizes:
        rows = [row for row in results if row["page_mib"] == size]
        reasons = []
        expected = collections.Counter(
            (view, repeat) for view in VIEWS for repeat in range(repeats)
        )
        actual = collections.Counter(
            (row.get("view"), row.get("repeat")) for row in rows
        )
        if actual != expected or any(not row.get("valid") for row in rows):
            reasons.append("incomplete-or-invalid-matrix")
        ratios = {
            view: [
                row["summary"]["ratio"]
                for row in rows
                if row.get("view") == view and row.get("valid")
            ]
            for view in VIEWS
        }
        if not reasons:
            if any(statistics.median(values) > 1.10 for values in ratios.values()):
                reasons.append("regression-over-ten-percent")
            motion = [ratios[view] for view in ("anatomical-motion", "close-motion")]
            if not any(
                statistics.median(values) <= 0.90 and all(value < 1 for value in values)
                for values in motion
            ):
                reasons.append("no-repeatable-ten-percent-motion-gain")
        memory = [
            row["summary"].get("paged_memory_bytes") for row in rows if row.get("valid")
        ]
        memory = [value for value in memory if value is not None]
        candidates.append(
            {
                "page_mib": size,
                "admitted": not reasons,
                "reasons": reasons,
                "ratios": ratios,
                "memory_bytes": max(memory) if memory else None,
            }
        )
    eligible = [row for row in candidates if row["admitted"]]

    # Comparable gains tie at 1 percentage point; then use the lower measured memory.
    def score(row):
        return min(
            statistics.median(row["ratios"][v])
            for v in ("anatomical-motion", "close-motion")
        )

    if eligible:
        best = min(score(row) for row in eligible)
        tied = [row for row in eligible if score(row) <= best + 0.01]
        winner = min(
            tied,
            key=lambda row: (
                row["memory_bytes"]
                if row["memory_bytes"] is not None
                else float("inf"),
                row["page_mib"],
            ),
        )["page_mib"]
    else:
        winner = None
    return {
        "candidates": candidates,
        "winner_mib": winner,
        "qualification": "desktop candidate admission only; physical XR still required",
    }


def run(
    session,
    *,
    scene="looming",
    representation="skeleton",
    page_sizes=(4, 16, 64),
    startup_timeout=600,
):
    results = []
    session.record(
        "protocol.json",
        {
            "schema": "flymsg.quest-compare/v1",
            "source": session.source,
            "device": session.device,
            "scene": scene,
            "representation": representation,
            "page_sizes": list(page_sizes),
            "views": list(VIEWS),
            "order": list(ORDER),
            "seconds": 30,
            "repeats": 3,
            "time_ms": 20,
            "motion": {"yaw_radians": 0.15, "period_seconds": 10},
            "close_scale": 0.35,
            "admission": {
                "motion_gain": 0.10,
                "max_regression": 0.10,
                "tie_ratio": 0.01,
            },
            "qualification": "not-scored",
        },
    )
    camera_file = session.out / "frozen-camera.json"
    for size in page_sizes:
        oracle_dir = session.out / f"oracle-{size}"
        oracle_dir.mkdir()
        session.open(scene, representation=representation, page_mib=size)
        ready = session.wait_ready(
            timeout=startup_timeout, evidence=oracle_dir / "preflight.jsonl"
        )
        if not ready["eligible"]:
            row = {
                "page_mib": size,
                "valid": False,
                "phase": "oracle-readiness",
                "reasons": ready["reasons"],
                "unsupported": ready.get("unsupported", False),
            }
            results.append(row)
            session.record("progress.json", {"results": results})
            continue
        try:
            report, code = node_json(
                "observer_oracle.mjs",
                session.endpoint,
                session.target,
                oracle_dir / "readbacks",
                timeout=1800,
            )
            if code or report.get("status") != "pass":
                raise RuntimeError("original/candidate correctness failed")
            oracle_camera = json.loads(
                (oracle_dir / "readbacks/camera.json").read_text()
            )
            if camera_file.exists():
                if json.loads(camera_file.read_text()) != oracle_camera:
                    raise RuntimeError(
                        "base camera changed between page configurations"
                    )
            else:
                runstore.atomic_json(camera_file, oracle_camera)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            results.append(
                {"page_mib": size, "valid": False, "phase": "oracle", "error": str(exc)}
            )
            session.record("progress.json", {"results": results})
            continue
        invalid = 0
        preparation_failed = False
        for view in VIEWS:
            for repeat in range(3):
                while invalid < 3:
                    attempt = (
                        session.out
                        / f"page-{size}-{view}-repeat-{repeat}-attempt-{invalid}"
                    )
                    attempt.mkdir()
                    records = []
                    phase = "preparation"
                    try:
                        for arm, mode in enumerate(ORDER):
                            identity(session.serial, session.device["hardware_serial"])
                            session.open(
                                scene,
                                representation=representation,
                                page_mib=size,
                                uploads=mode == "paged",
                                culling=view != "dense-all" and mode == "paged",
                            )
                            ready = session.wait_ready(
                                timeout=startup_timeout,
                                evidence=attempt / f"arm-{arm}-preflight.jsonl",
                            )
                            if not ready["eligible"]:
                                raise RuntimeError(
                                    "arm readiness failed: "
                                    + ", ".join(ready["reasons"])
                                )
                            phase = "measurement"
                            report, code = node_json(
                                "observer_trial.mjs",
                                session.endpoint,
                                session.target,
                                attempt / f"arm-{arm}-{mode}",
                                30,
                                view,
                                camera_file,
                                timeout=240,
                            )
                            identity(session.serial, session.device["hardware_serial"])
                            if code or not report["eligible"]:
                                raise RuntimeError("application arm excluded")
                            records.append(
                                json.loads(
                                    (
                                        attempt / f"arm-{arm}-{mode}/trial.json"
                                    ).read_text()
                                )
                            )
                            phase = "preparation"
                        phase = "assessment"
                        summary = block_summary(records)
                        row = {
                            "page_mib": size,
                            "view": view,
                            "repeat": repeat,
                            "valid": True,
                            "summary": summary,
                        }
                        results.append(row)
                        runstore.atomic_json(attempt / "block.json", row)
                        break
                    except (
                        OSError,
                        ValueError,
                        RuntimeError,
                        subprocess.SubprocessError,
                    ) as exc:
                        if phase == "preparation":
                            preparation_failed = True
                        else:
                            invalid += 1
                        runstore.atomic_json(
                            attempt / "exclusion.json",
                            {
                                "valid": False,
                                "error": str(exc),
                                "attempt": invalid,
                                "partial_arms": len(records),
                                "phase": phase,
                            },
                        )
                    finally:
                        session.record(
                            "progress.json",
                            {"phase": "desktop-comparison", "results": results},
                        )
                    if preparation_failed:
                        break
                if invalid >= 3 or preparation_failed:
                    results.append(
                        {
                            "page_mib": size,
                            "view": view,
                            "repeat": repeat,
                            "valid": False,
                            "reasons": [
                                "preparation-failed"
                                if preparation_failed
                                else "three-invalid-blocks"
                            ],
                        }
                    )
                    break
            if invalid >= 3 or preparation_failed:
                break
    decision = admission(results, page_sizes)
    session.record("comparison.json", {"results": results, **decision})
    return decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, type=wifi_serial)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8892)
    parser.add_argument("--scene", choices=("looming", "anatomy"), default="looming")
    parser.add_argument(
        "--representation", choices=("skeleton", "surface"), default="skeleton"
    )
    parser.add_argument(
        "--gpu-page-mib", type=int, choices=(4, 16, 64), nargs="+", default=[4, 16, 64]
    )
    parser.add_argument("--startup-timeout", type=int, default=600)
    parser.add_argument("--keep-awake", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.startup_timeout <= 600 or len(set(args.gpu_page_mib)) != len(
        args.gpu_page_mib
    ):
        parser.error("startup timeout 1..600 and unique page sizes required")
    try:
        session = QuestSite(
            args.serial,
            args.out,
            port=args.port,
            keep_awake=args.keep_awake,
            wifi_only=True,
        )
        with session:
            decision = run(
                session,
                scene=args.scene,
                representation=args.representation,
                page_sizes=tuple(args.gpu_page_mib),
                startup_timeout=args.startup_timeout,
            )
            print(json.dumps(decision), flush=True)
        return 0 if session.cleanup["ok"] else 1
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as exc:
        if args.out.exists():
            runstore.atomic_json(
                args.out / "failure.json",
                {
                    "qualification": "not-scored",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        print(f"Comparison incomplete; evidence retained in {args.out}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
