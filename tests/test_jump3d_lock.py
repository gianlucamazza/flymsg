"""The TTM-driven jump is locked before any run; no connectome is loaded."""

import pytest

from flymsg import cli, jump3d_lock


def test_locked_to_the_measured_values():
    doc = jump3d_lock.assert_matches_code()
    assert doc["version"] == 1
    assert jump3d_lock.content_hash(doc) == jump3d_lock.VERSION_HASHES[1]
    assert doc["neural"]["motor"] == {"lm": "TTMn_L", "rm": "TTMn_R"}


def test_bounds_other_than_the_measured_ones_are_refused():
    doc = jump3d_lock.load()
    doc["decides"]["range_max_mm"] = 60.0
    with pytest.raises(jump3d_lock.Jump3DError, match="measured"):
        jump3d_lock.assert_matches_code(doc)


@pytest.mark.parametrize(
    ("ranges", "takeoffs", "expected"),
    [
        ([30.0, 31.0, 29.0], [10, 11, 9], "consistent"),
        ([5.0, 6.0, 4.0], [10, 11, 9], "short"),
        ([50.0, 60.0, 55.0], [10, 11, 9], "long"),
        ([30.0, 0.0, 31.0], [10, None, 9], "no_takeoff"),
        ([30.0, 0.0, 31.0], [10.0, float("nan"), 9.0], "no_takeoff"),
    ],
)
def test_decide(ranges, takeoffs, expected):
    assert jump3d_lock.decide(ranges, takeoffs, 28.6, 37.75) == expected


def test_prints_the_protocol_without_data(monkeypatch, capsys, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    monkeypatch.setattr("sys.argv", ["flymsg", "--data", str(tmp_path), "jump3d"])
    cli.main()
    assert "TTM twitch -> NeuroMechFly" in capsys.readouterr().out
