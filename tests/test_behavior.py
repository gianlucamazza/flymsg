"""The one-bit looming-jump protocol matches the live model and does not run."""

import pytest

from flymsg import behavior, cli, sim, validate


def test_protocol_is_locked_to_the_looming_calibration_case():
    doc = behavior.assert_matches_code()
    assert doc["version"] == 1
    assert behavior.content_hash(doc) == behavior.VERSION_HASHES[1]
    task = doc["task"]
    assert task["stimulus"] == "LC4_R"
    assert task["stimulus_n"] == 55
    assert task["motor"] == "TTMn_R"
    assert task["motor_n"] == 1
    assert task["command_instances"] == ["DNp01(GF)_R", "DNp01(GF)_L"]
    assert doc["claim"]["held_out"] is False
    assert doc["body"]["timestep_ms"] is None
    assert doc["controller"]["learned"] is False
    assert doc["flybody"]["selected"] is False
    assert doc["wiring"]["draw"] is False
    assert doc["prediction"]["status"] == "unverified"
    assert doc["protocol"]["w_syn"] == sim.Params.w_syn
    assert [case.name for case in validate.CASES] == [
        "looming escape",
        "giant fiber output",
        "P1 courtship drive",
        "pIP10 song pathway",
        "sugar feeding",
    ]


def test_an_edit_without_a_version_bump_fails():
    doc = behavior.load()
    doc["task"]["motor"] = "MN9"
    doc["content_sha256"] = behavior.content_hash(doc)
    with pytest.raises(behavior.BehaviorError, match="without a bump"):
        behavior.assert_locked(doc)


def test_flight_physics_is_finer_than_the_neural_step():
    doc = behavior.load()
    step = doc["flybody"]["flight_physics_s"]
    assert behavior.integer_multiple(step, doc["protocol"]["dt_ms"]) is False
    assert doc["flybody"]["legal_under_coupling"]["flight_physics"] is False
    assert behavior.integer_multiple(doc["flybody"]["walk_physics_s"], 0.1) is True
    assert behavior.integer_multiple(doc["flybody"]["walk_control_s"], 0.1) is True
    doc["flybody"]["legal_under_coupling"]["flight_physics"] = True
    with pytest.raises(behavior.BehaviorError, match="flight_physics"):
        behavior.assert_matches_code(doc)


def test_behavior_prints_the_protocol_and_does_not_load_data(
    monkeypatch, capsys, tmp_path
):
    def boom(*_args, **_kwargs):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["flymsg", "--data", str(tmp_path), "behavior"])
    cli.main()
    out = capsys.readouterr().out
    assert "LC4_R -> TTMn_R" in out
    assert "calibration_feasibility" in out
    assert "not run" in out


def test_behavior_has_no_run_switch(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["flymsg", "behavior", "--run"])
    with pytest.raises(SystemExit):
        cli.main()
    err = capsys.readouterr().err
    assert "unrecognized" in err
