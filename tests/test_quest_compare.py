"""Independent admission checks over raw, complete A/B/B/A evidence."""

import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "quest_compare", Path(__file__).resolve().parents[1] / "scripts/quest_compare.py"
)
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


def arm(value):
    return {
        "eligible": True,
        "camera_profile": {"camera_world": [1]},
        "render_settings": {"samples": 4},
        "source_sha256": {"main": "same"},
        "identity": {
            "representation": "skeleton",
            "selected": 1128,
            "represented": 1128,
            "width": 100,
            "height": 100,
            "pixel_ratio": 1,
            "samples": 4,
        },
        "raw_intervals_ms": [value] * 100,
        "intervals_ms": {"p95": value},
        "after": {"resources": {"gpu_resources": {"owned_gpu_bytes": 4096}}},
    }


def matrix(size=4, ratio=0.85, memory=4096):
    return [
        {
            "page_mib": size,
            "view": view,
            "repeat": repeat,
            "valid": True,
            "summary": {"ratio": ratio, "paged_memory_bytes": memory},
        }
        for view in compare.VIEWS
        for repeat in range(3)
    ]


def test_summary_recomputes_raw_cadence_and_preserves_memory():
    records = [arm(value) for value in (100, 80, 90, 100)]
    summary = compare.block_summary(records)
    assert summary["ratio"] == 0.85
    assert summary["paged_memory_bytes"] == 4096
    records[1]["raw_intervals_ms"][-10:] = [1000] * 10
    with pytest.raises(ValueError, match="differs"):
        compare.block_summary(records)


@pytest.mark.parametrize(
    "damage", ["nan", "missing", "quality", "source", "ineligible"]
)
def test_invalid_arms_cannot_be_admitted(damage):
    records = [arm(value) for value in (100, 80, 80, 100)]
    if damage == "nan":
        records[1]["raw_intervals_ms"][0] = float("nan")
    elif damage == "missing":
        records.pop()
    elif damage == "quality":
        records[1]["render_settings"]["samples"] = 0
    elif damage == "source":
        records[1]["source_sha256"]["main"] = "changed"
    else:
        records[1]["eligible"] = False
    with pytest.raises(ValueError):
        compare.block_summary(records)


def test_admission_requires_exact_matrix_and_repeatable_motion_gain():
    good = matrix()
    assert compare.admission(good, (4,))["winner_mib"] == 4
    duplicate = copy.deepcopy(good)
    duplicate[-1] = copy.deepcopy(duplicate[0])
    assert compare.admission(duplicate, (4,))["winner_mib"] is None
    assert (
        compare.admission([{"page_mib": 4, "valid": False, "phase": "oracle"}], (4,))[
            "winner_mib"
        ]
        is None
    )
    for row in good:
        if row["repeat"] == 2:
            row["summary"]["ratio"] = 1.01
    assert compare.admission(good, (4,))["winner_mib"] is None


def test_memory_tie_break_and_regression_gate():
    rows = matrix(4, 0.85, 1000) + matrix(16, 0.845, 2000)
    assert compare.admission(rows, (4, 16))["winner_mib"] == 4
    for row in rows:
        if row["page_mib"] == 4 and row["view"] == "close-static":
            row["summary"]["ratio"] = 1.11
    assert compare.admission(rows, (4, 16))["winner_mib"] == 16


def test_partial_matrix_can_prove_a_veto_but_never_admit():
    rows = [row for row in matrix(ratio=1.5) if row["view"] == "dense-all"]
    decision = compare.admission(rows, (4,))
    assert decision["winner_mib"] is None
    candidate = decision["candidates"][0]
    assert candidate["regression_views"] == ["dense-all"]
    assert "regression-over-ten-percent" in candidate["reasons"]
    assert set(candidate["unmeasured_views"]) == set(compare.VIEWS) - {"dense-all"}
    # No early positive admission and no veto from an incomplete set of repeats.
    for row in rows:
        row["summary"]["ratio"] = 0.5
    assert compare.admission(rows, (4,))["winner_mib"] is None
    rows[0]["summary"]["ratio"] = 1.5
    assert not compare.admission(rows[:1], (4,))["candidates"][0]["regression_views"]


def test_actual_msaa_mismatch_is_rejected_even_when_composer_targets_match():
    records = [arm(value) for value in (100, 80, 80, 100)]
    records[1]["identity"]["samples"] = 0
    with pytest.raises(ValueError, match="quality mismatch"):
        compare.block_summary(records)


def test_bounded_comparison_requires_explicit_order_and_every_frame_certificate():
    records = [arm(value) for value in (100, 80, 80, 100)]
    for row in records[1:3]:
        row["identity"]["representation"] = "skeleton-bounded"
        row["frames"] = 101
        row["bounded_frames"] = [
            {"maximum_error_px": 0.4, "submitted_indices": 20, "source_indices": 100}
            for _ in range(101)
        ]
    assert (
        compare.block_summary(records, candidate_representation="skeleton-bounded")[
            "ratio"
        ]
        == 0.8
    )
    with pytest.raises(ValueError, match="mismatch"):
        compare.block_summary(records)
    for damage in ("missing", "over-limit", "nan", "wrong-count"):
        changed = copy.deepcopy(records)
        if damage == "missing":
            changed[1]["bounded_frames"].pop()
        elif damage == "wrong-count":
            changed[1]["bounded_frames"][50]["submitted_indices"] = 200
        else:
            changed[1]["bounded_frames"][50]["maximum_error_px"] = (
                float("nan") if damage == "nan" else 0.51
            )
        with pytest.raises(ValueError, match="certificate|uncertified"):
            compare.block_summary(changed, candidate_representation="skeleton-bounded")


@pytest.mark.parametrize("ignore_frozen", [False, True])
def test_run_supplies_frozen_camera_before_later_correctness_captures(
    tmp_path, monkeypatch, ignore_frozen
):
    import json
    from types import SimpleNamespace

    camera = {
        "camera_world": [1 if i % 5 == 0 else 0 for i in range(16)],
        "projection": [1 if i % 5 == 0 else 0 for i in range(16)],
        "viewport": {"width": 1280, "height": 670, "pixel_ratio": 1, "samples": 4},
    }
    calls = []
    session = SimpleNamespace(
        out=tmp_path,
        endpoint="endpoint",
        target="target",
        serial="192.168.1.146:5555",
        source={},
        device={"hardware_serial": "fake"},
        unattended=True,
    )
    session.record = lambda name, data: compare.runstore.atomic_json(
        tmp_path / name, data
    )
    session.open = lambda *args, **kwargs: None
    session.wait_ready = lambda **kwargs: {
        "eligible": kwargs.get("readback_only", False),
        "reasons": []
        if kwargs.get("readback_only", False)
        else ["operator unavailable"],
    }
    monkeypatch.setattr(compare, "identity", lambda *args: None)

    def node(*args, **kwargs):
        assert args[0] == "observer_oracle.mjs" and "--readback-only" in args
        directory = Path(args[3])
        directory.mkdir()
        selected = copy.deepcopy(camera)
        if calls:
            assert "--camera-file" in args
            profile = Path(args[args.index("--camera-file") + 1])
            assert json.loads(profile.read_text()) == camera
            if ignore_frozen:
                selected["camera_world"][0] += 1e-13
        else:
            assert "--camera-file" not in args
        calls.append(args)
        compare.runstore.atomic_json(directory / "camera.json", selected)
        return {"status": "pass"}, 0

    monkeypatch.setattr(compare, "node_json", node)
    decision = compare.run(
        session, representation="skeleton-bounded", page_sizes=(4, 16)
    )
    assert len(calls) == 2 and decision["winner_mib"] is None
    results = json.loads((tmp_path / "comparison.json").read_text())["results"]
    errors = [row for row in results if row.get("phase") == "oracle"]
    assert bool(errors) == ignore_frozen
    if ignore_frozen:
        assert "base camera changed" in errors[0]["error"]


def test_camera_declared_viewport_must_match_actual_receipts():
    records = [arm(value) for value in (100, 80, 80, 100)]
    for row in records:
        row["camera_profile"]["viewport"] = {
            key: row["identity"][key]
            for key in ("width", "height", "pixel_ratio", "samples")
        }
    assert compare.block_summary(records)["ratio"] == 0.8
    # Even if every arm drifts together, it must not differ from its frozen declaration.
    for row in records:
        row["identity"]["width"] *= 2
    with pytest.raises(ValueError, match="Frozen camera viewport"):
        compare.block_summary(records)
