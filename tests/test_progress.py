"""Resumable steps and measured progress for long locked runs."""

import io

import pandas as pd
import pytest

from flymsg import progress


def test_steps_resume_what_finished_and_refuse_another_lock(tmp_path):
    calls = []

    def compute():
        calls.append(1)
        return {"t": pd.DataFrame({"a": [1, 2], "b": [0.1 + 0.2, 1 / 3]})}

    first = progress.Steps(tmp_path, "abc")
    got, fresh = first.get("s1", compute)
    assert fresh and calls == [1]
    again = progress.Steps(tmp_path, "abc")
    back, fresh = again.get("s1", compute)
    assert not fresh and calls == [1] and again.resumed == ["s1"]
    pd.testing.assert_frame_equal(back["t"], got["t"])  # floats round-trip exactly
    with pytest.raises(ValueError, match="another lock"):
        progress.Steps(tmp_path, "other")


def test_an_unfinished_step_is_computed_again(tmp_path):
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1" / "t.csv").write_text("a\n9\n")  # no done marker: interrupted
    steps = progress.Steps(tmp_path, "abc")
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
