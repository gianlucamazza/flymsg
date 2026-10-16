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
