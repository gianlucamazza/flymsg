"""The viewer baseline check compares eligible warm passes with the baseline's range
(issue #24)."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "bench_check", ROOT / "scripts" / "bench_check.py"
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def rec(scene, fps, p5, first, cache="warm", eligible=True, renderer="Iris"):
    return {
        "scene": scene,
        "cache": cache,
        "eligible": eligible,
        "gl": "gl",
        "viewport": [1400, 900],
        "gpu": {"renderer": renderer},
        "bench": {"fps": {"p50": fps, "p5": p5}, "marks": {"first_surface": first}},
    }


BASE = [rec("a", 20, 10, 2.0), rec("a", 30, 12, 3.0), rec("s", 25, 25, 1.0)]


def test_the_range_is_the_baseline_extremes_and_static_scenes_have_no_fps():
    table = check.ranges(BASE)
    assert table["a"] == {"first_surface": (2.0, 3.0, 2), "fps": (20, 30, 2)}
    assert table["s"] == {"first_surface": (1.0, 1.0, 1)}


def test_slower_frames_or_later_marks_are_worse():
    verdicts = {
        (r[0], r[1]): r[-1]
        for r in check.compare([rec("a", 19, 9, 1.5), rec("s", 99, 99, 1.2)], BASE)
    }
    assert verdicts == {
        ("a", "fps"): "worse",
        ("a", "first_surface"): "better",
        ("s", "first_surface"): "worse",
    }


def test_another_gpu_has_no_baseline():
    with pytest.raises(ValueError, match="no baseline"):
        check.compare([rec("a", 20, 10, 2.0, renderer="Adreno")], BASE)


def test_only_eligible_warm_passes_are_read(tmp_path):
    path = tmp_path / "run.jsonl"
    lines = [
        rec("a", 1, 0, 9),
        rec("a", 1, 0, 9, cache="cold"),
        rec("a", 1, 0, 9, eligible=False),
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in lines))
    assert len(check.passes([path])) == 1
