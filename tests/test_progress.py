"""Resumable steps and measured progress for long locked runs."""

import io

import pandas as pd
import pytest

from flymsg import progress


def test_steps_resume_what_finished_and_refuse_another_lock(tmp_path):
    calls = []

    def compute():
        calls.append(1)
        return {
            "t": pd.DataFrame(
                {"a": [1, 2, 3], "b": [0.1 + 0.2, 1 / 7, 0.15000000000000002]}
            )
        }

    first = progress.Steps(tmp_path, {"source": "abc", "lock": "frozen"})
    got, fresh = first.get("s1", compute)
    assert fresh and calls == [1]
    again = progress.Steps(tmp_path, {"source": "abc", "lock": "frozen"})
    back, fresh = again.get("s1", compute)
    assert not fresh and calls == [1] and again.resumed == ["s1"]
    # floats round-trip bit for bit
    pd.testing.assert_frame_equal(back["t"], got["t"], check_exact=True)
    with pytest.raises(ValueError, match="another execution"):
        progress.Steps(tmp_path, {"source": "other", "lock": "frozen"})


def test_an_unfinished_step_is_computed_again(tmp_path):
    steps = progress.Steps(tmp_path, {"source": "abc", "lock": "frozen"})
    (tmp_path / ".s1.interrupted.tmp").mkdir()
    (tmp_path / ".s1.interrupted.tmp" / "t.parquet").write_bytes(b"unfinished")
    got, fresh = steps.get("s1", lambda: {"t": pd.DataFrame({"a": [1]})})
    assert fresh and got["t"]["a"].tolist() == [1]


def test_progress_reports_count_and_eta():
    out = io.StringIO()
    p = progress.Progress(4, "x", stream=out)
    p.step(note="first")
    p.step(2)
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("[x] 1/4 in ") and "(first)" in lines[0]
    assert lines[1].startswith("[x] 3/4 in ") and "eta" in lines[1]


def test_resume_does_not_count_cached_units_as_measured_work(monkeypatch):
    ticks = iter([0.0, 0.001, 60.0])
    monkeypatch.setattr(progress.time, "monotonic", lambda: next(ticks))
    out = io.StringIO()
    report = progress.Progress(100, "fixture", stream=out)
    report.step(50, resumed=True)
    report.step()
    lines = out.getvalue().splitlines()
    assert "eta unknown" in lines[0]
    assert "eta 49.0 min" in lines[1] and "resumed 50" in lines[1]


def test_step_corruption_and_unexpected_files_are_refused(tmp_path):
    identity = {"source": "abc", "lock": "frozen"}
    progress.Steps(tmp_path, identity).get(
        "s1", lambda: {"t": pd.DataFrame({"a": [1]})}
    )
    (tmp_path / "s1" / "t.parquet").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="integrity"):
        progress.Steps(tmp_path, identity).get(
            "s1", lambda: pytest.fail("recomputed corrupt completed step")
        )


def test_protocol_hash_only_and_legacy_steps_are_refused(tmp_path):
    with pytest.raises(TypeError, match="full execution"):
        progress.Steps(tmp_path, "abc")
    (tmp_path / "lock.json").write_text('{"content_sha256": "abc"}')
    with pytest.raises(ValueError, match="legacy"):
        progress.Steps(tmp_path, {"source": "abc"})


def test_typed_table_roundtrips_strings_missing_values_and_index(tmp_path):
    table = pd.DataFrame(
        {
            "label": pd.Series(["NA", "", None], dtype="string"),
            "count": pd.Series([1, None, 3], dtype="Int64"),
            "value": [1 / 7, float("nan"), 0.15000000000000002],
        }
    )
    table.index = pd.Index([7, 9, 11], name="row")
    steps = progress.Steps(tmp_path, {"source": "abc"})
    steps.get("s1", lambda: {"typed": table})
    loaded, fresh = steps.get("s1", lambda: pytest.fail("recomputed"))
    assert not fresh
    pd.testing.assert_frame_equal(loaded["typed"], table, check_exact=True)


@pytest.mark.parametrize("damage", ["missing-table", "missing-record", "extra"])
def test_missing_or_extra_step_artifacts_are_refused(tmp_path, damage):
    steps = progress.Steps(tmp_path, {"source": "abc"})
    steps.get("s1", lambda: {"t": pd.DataFrame({"value": [1 / 7]})})
    if damage == "extra":
        (tmp_path / "s1" / "unexpected").write_text("extra")
    else:
        (
            tmp_path
            / "s1"
            / ("t.parquet" if damage == "missing-table" else "step.json")
        ).unlink()
    with pytest.raises(ValueError):
        steps.get("s1", lambda: pytest.fail("corrupt completed step recomputed"))


@pytest.mark.parametrize("field", ["params", "backend", "numerical_mode"])
def test_changed_execution_policy_cannot_reuse_steps(tmp_path, field):
    identity = {
        "params": {"w_syn": 1},
        "backend": "cpu",
        "numerical_mode": "ordered-f32",
    }
    progress.Steps(tmp_path, identity).get(
        "s1", lambda: {"t": pd.DataFrame({"value": [1 / 7]})}
    )
    with pytest.raises(ValueError, match="another execution"):
        progress.Steps(tmp_path, {**identity, field: "changed"})
