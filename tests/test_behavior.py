"""The one-bit looming-jump protocol matches the live model.

`--run` is the closed loop. These tests never load the connectome.
"""

import numpy as np
import pytest
from test_core import chain

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
    assert "calibration feasibility FAIL: silence" in out


def test_behavior_run_needs_the_dataset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["flymsg", "--data", str(tmp_path), "behavior", "--run"]
    )
    try:
        cli.main()
    except SystemExit as err:
        assert "fetch" in str(err)
    else:
        raise AssertionError("expected a missing-data exit")


def _record(
    seed,
    jump_step,
    closed_stim_steps,
    open_spikes,
    closed_spikes,
    silence_spikes,
    silence_stim_steps=3000,
    persistent=10,
):
    jumped = jump_step is not None
    return {
        "seed": seed,
        "jump_step": jump_step,
        "closed_stim_steps": closed_stim_steps,
        "open_spikes": np.asarray(open_spikes, dtype=np.int64),
        "closed_spikes": np.asarray(closed_spikes, dtype=np.int64),
        "silence_spikes": np.asarray(silence_spikes, dtype=np.int64),
        "silence_stim_steps": silence_stim_steps,
        "persistent": persistent,
        "first_ttmn_ms": 13.2 if jumped else np.nan,
        "first_dnp_r_ms": 4.4 if jumped else np.nan,
        "first_dnp_l_ms": 5.0 if jumped else np.nan,
    }


def _three(seeds):
    doc = behavior.load()
    report = behavior.assess(doc, seeds)
    return behavior.verdict(report), report


def test_two_on_time_seeds_and_a_clean_silence_pass():
    early = np.array([10, 40, 100, 200])
    at_window = np.array([10, 40, 3000])
    verdict, report = _three(
        [
            _record(0, 100, 101, early, early, [10, 40], persistent=5000),
            _record(1, 3000, 3000, at_window, at_window, [10]),
            _record(2, None, 3000, [10, 40], [99], []),
        ]
    )
    assert verdict == "calibration feasibility PASS"
    stability = report[(report["check"] == "stability") & (report["seed"] == "all")]
    assert bool(stability["decides"].iloc[0]) is False
    assert stability["value"].iloc[0] > 100


def test_one_on_time_seed_fails_the_jump():
    spikes = np.array([10, 40, 100])
    late = np.array([10, 40, 3001])
    verdict, _ = _three(
        [
            _record(0, 100, 101, spikes, spikes, []),
            _record(1, 3001, 3000, late, late, []),
            _record(2, None, 3000, [10], [10], []),
        ]
    )
    assert verdict == "calibration feasibility FAIL: jump"


def test_three_silence_spikes_fail_without_a_cut():
    spikes = np.array([10, 40, 100])
    verdict, _ = _three(
        [_record(s, 100, 101, spikes, spikes, [10, 40, 80]) for s in range(3)]
    )
    assert verdict == "calibration feasibility FAIL: silence"


def test_a_cut_silence_drive_fails():
    spikes = np.array([10, 40, 100])
    verdict, _ = _three(
        [
            _record(s, 100, 101, spikes, spikes, [10, 40], silence_stim_steps=41)
            for s in range(3)
        ]
    )
    assert verdict == "calibration feasibility FAIL: silence"


def test_a_decoder_mismatch_fails():
    opened = np.array([10, 40, 100, 200])
    closed = np.array([10, 50, 100, 200])
    verdict, _ = _three([_record(s, 100, 101, opened, closed, []) for s in range(3)])
    assert verdict == "calibration feasibility FAIL: decoder_match"


def test_the_wrong_stimulus_length_fails_feedback():
    spikes = np.array([10, 40, 100, 200])
    verdict, _ = _three([_record(s, 100, 100, spikes, spikes, []) for s in range(3)])
    assert verdict == "calibration feasibility FAIL: feedback"


def test_explicit_kicks_match_the_seeded_draw_and_the_trace():
    edges, sign, n = chain([400])
    W = sim.weight_matrix(edges, sign, n, sim.Params.w_syn)
    stim = np.array([0])
    plain = sim.run(W, stim, 100.0, 100.0, stim_ms=50.0, seed=2)
    traced = sim.run(
        W, stim, 100.0, 100.0, stim_ms=50.0, seed=2, trace=np.array([1, 0])
    )
    kicks = sim.poisson_kicks(2, 100.0, sim.Params.dt, int(50.0 / sim.Params.dt), 1)
    explicit = sim.run(
        W, stim, 100.0, 100.0, seed=2, kicks=kicks, trace=np.array([1, 0])
    )
    assert plain.traced is None
    assert np.array_equal(plain.counts, traced.counts)
    assert np.array_equal(traced.counts, explicit.counts)
    assert np.allclose(plain.first_spike_ms, traced.first_spike_ms, equal_nan=True)
    per_bin = round(traced.bin_ms / sim.Params.dt)
    summed = traced.traced.reshape(-1, per_bin, 2).sum(axis=1)
    assert np.array_equal(summed[:, 0], traced.counts[:, 1])
    assert np.array_equal(summed[:, 1], traced.counts[:, 0])


def test_a_shorter_kick_prefix_keeps_spikes_through_the_third():
    edges, sign, n = chain([400])
    W = sim.weight_matrix(edges, sign, n, sim.Params.w_syn)
    dt = sim.Params.dt
    full = int(100.0 / dt)
    kicks = sim.poisson_kicks(0, 100.0, dt, full, 1)
    stim = np.array([0])
    opened = sim.run(W, stim, 100.0, 200.0, seed=0, kicks=kicks, trace=np.array([1]))
    spikes = np.flatnonzero(opened.traced[:, 0])
    assert spikes.size >= 3
    step = int(spikes[2])
    assert step < full
    closed = sim.run(
        W, stim, 100.0, 200.0, seed=0, kicks=kicks[: step + 1], trace=np.array([1])
    )
    closed_spikes = np.flatnonzero(closed.traced[:, 0])
    assert np.array_equal(spikes[spikes <= step], closed_spikes[closed_spikes <= step])
    assert closed.stim_ms == pytest.approx((step + 1) * dt)
    assert closed.stim_ms < opened.stim_ms
