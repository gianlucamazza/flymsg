from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flymsg import data, sim, validate

DATA = Path(__file__).parent.parent / "data"


def test_control_matches_superclasses_and_skips_target_inputs():
    neurons = pd.DataFrame({"superclass": ["a", "a", "a", "a", "b", "b", "t"]})
    # 1 (class a) feeds the target 6 strongly, so it must never be picked
    edges = pd.DataFrame({"pre": [1, 2], "post": [6, 6], "weight": [10, 2]})
    rng = np.random.default_rng(0)
    for _ in range(20):
        ctrl = validate.control_idx(
            neurons, edges, np.array([0, 4]), np.array([6]), rng
        )
        assert sorted(neurons["superclass"].iloc[ctrl]) == ["a", "b"]
        assert not np.isin(ctrl, [0, 1, 4, 6]).any()


@pytest.mark.slow
@pytest.mark.skipif(
    not (DATA / "edges.parquet").exists(), reason="needs `flymsg build`"
)
def test_battery_with_default_params_fails_only_the_known_checks():
    # Criterion v4 passes everything with the defaults (29/29 at seeds 0-2, and at 10 seeds
    # in the model selection and the replication, docs/validation.md). If anything starts
    # failing, the docs need updating.
    known: set[tuple[str, str, str]] = set()
    neurons, edges = data.load(DATA)
    report = validate.run(neurons, edges, sim.Params(), seeds=3)
    failed = report[~report["passed"]]
    assert set(zip(failed["case"], failed["kind"], failed["subject"])) == known, (
        failed.to_string()
    )


def test_respond_reports_best_neuron_reliability_and_latency():
    # 0 drives 1 strongly and 2 weakly; 1 and 2 share type "T"
    neurons = pd.DataFrame({"type": ["S", "T", "T"]})
    edges = pd.DataFrame({"pre": [0, 0], "post": [1, 2], "weight": [200, 1]})
    W = sim.weight_matrix(edges, np.ones(3, dtype=np.int8), 3, 0.275)
    out, persistent = validate.respond(
        W, neurons, np.array([0]), ["T"], sim.Params(), seeds=3
    )
    t = out["T"]
    assert t["reliable"] == 3 and t["rate"] > 0
    assert 0 < t["latency"] < validate.STIM_MS
    assert persistent == 0


def test_order_counts_only_seeds_where_both_fire():
    inf = np.inf
    ok, note = validate.in_order(np.array([5.0, 6, inf]), np.array([9.0, 4, 7]), 2 / 3)
    assert not ok and note == "1/2 seeds in order"
    ok, _ = validate.in_order(np.array([5.0, 6, 1]), np.array([9.0, 8, inf]), 2 / 3)
    assert ok
    assert not validate.in_order(np.full(3, inf), np.full(3, inf), 2 / 3)[0]


def test_dose_allows_one_spike_of_noise_but_needs_a_rise():
    tol = validate.DOSE_TOL_HZ
    assert validate.dose_ok([0, 10, 10 - 0.9 * tol, 20])
    assert not validate.dose_ok([0, 10, 10 - 1.1 * tol, 20])
    assert not validate.dose_ok([5, 5, 5, 5])


def test_sugar_grns_are_right_lb3b_and_lb3c():
    neurons = pd.DataFrame(
        {"instance": ["LB3a_R", "LB3b_R", "LB3c_R", "LB3c_L", "LB3d_R", None]}
    )
    assert validate.sugar_grns(neurons).tolist() == [1, 2]


def test_control_matches_class_for_sensory_stimuli():
    neurons = pd.DataFrame(
        {
            "superclass": ["cb_sensory"] * 6 + ["central"],
            "class": [
                "gustatory",
                "gustatory",
                "gustatory",
                "mechano",
                "mechano",
                "mechano",
                "c",
            ],
        }
    )
    edges = pd.DataFrame({"pre": [], "post": [], "weight": []}, dtype=int)
    rng = np.random.default_rng(0)
    for _ in range(20):
        ctrl = validate.control_idx(neurons, edges, np.array([0]), np.array([6]), rng)
        assert neurons["class"].iloc[ctrl].tolist() == ["gustatory"]
        assert ctrl[0] in (1, 2)


def test_bitter_grns_are_right_lb1a_to_d():
    neurons = pd.DataFrame(
        {"instance": ["LB1a_R", "LB1d_R", "LB1e_R", "LB1a_L", "LB3b_R", None]}
    )
    assert validate.bitter_grns(neurons).tolist() == [0, 1]


def test_bootstrap_ci_brackets_the_mean_and_is_reproducible():
    v = [10.0, 12.0, 11.0, 30.0, 9.0]
    lo, hi = validate.bootstrap_ci(v)
    assert lo < np.mean(v) < hi
    assert validate.bootstrap_ci(v) == (lo, hi)
    assert validate.bootstrap_ci([5.0, 5.0]) == (5.0, 5.0)


def test_model_selection_rule():
    rule = validate.select_model
    assert rule({"A": 28, "B": 27}, ["A", "B"], tie_break="B") == "A"
    assert rule({"A": 27, "B": 27}, ["A", "B"], tie_break="B") == "B"
    # a sensitivity variant cannot win even with more checks
    assert rule({"A": 26, "B": 25, "B+": 29}, ["A", "B"], tie_break="B") == "A"


def test_respond_stopping_at_the_stimulus_end_gives_the_same_rates():
    # S -> A -> B, with B -> A feedback so activity outlasts the stimulus
    neurons = pd.DataFrame({"type": ["S", "A", "B"]})
    edges = pd.DataFrame(
        {"pre": [0, 1, 2], "post": [1, 2, 1], "weight": [200, 200, 200]}
    )
    p = sim.Params()
    W = sim.weight_matrix(edges, np.ones(3, dtype=np.int8), 3, p.w_syn)
    stim = np.array([0])
    full, _ = validate.respond(W, neurons, stim, ["A", "B"], p, 3)
    short, _ = validate.respond(
        W, neurons, stim, ["A", "B"], p, 3, duration_ms=validate.STIM_MS
    )
    for t in ("A", "B"):
        assert full[t]["rate"] > 0
        assert np.array_equal(full[t]["seed_rates"], short[t]["seed_rates"])


def _one_case_network(monkeypatch):
    """S -> T on a tiny network, with CASES reduced to it so the battery runs in a moment."""
    neurons = pd.DataFrame(
        {
            "type": ["S", "T", "X"],
            "instance": ["S", "T", "X"],
            "superclass": ["sensory", "motor", "sensory"],
            "class": ["c", "m", "c"],
            "sign": np.ones(3, dtype=np.int8),
        }
    )
    edges = pd.DataFrame({"pre": [0], "post": [1], "weight": [200]})
    monkeypatch.setattr(validate, "CASES", [validate.Case("c", "S", ["T"], "")])
    monkeypatch.setattr(validate, "NEGATIVES", [])
    return neurons, edges


def test_calibrate_orders_by_checks_passed_then_closeness_to_the_published_model(
    monkeypatch,
):
    neurons, edges = _one_case_network(monkeypatch)
    out = validate.calibrate(
        neurons, edges, [sim.SHIU_W_SYN, 0.05], [0.0], seeds=1, workers=1
    )
    assert list(out.columns) == ["w_syn", "th_jump", "passed", "total", "failed"]
    assert len(out) == 2 and out["passed"].is_monotonic_decreasing
    # the silent model fails checks the published weight passes
    assert out.iloc[0]["w_syn"] == sim.SHIU_W_SYN


def test_calibrate_breaks_ties_towards_the_published_weight(monkeypatch):
    neurons, edges = _one_case_network(monkeypatch)
    out = validate.calibrate(neurons, edges, [0.3, 1.0], [0.0], seeds=1, workers=1)
    assert out["passed"].nunique() == 1  # both work on this easy network
    assert out.iloc[0]["w_syn"] == 0.3  # nearer to Shiu's 0.275


def test_compare_models_reports_one_battery_per_model_in_the_given_order(monkeypatch):
    neurons, edges = _one_case_network(monkeypatch)
    models = {
        "A": sim.Params(w_syn=0.3),
        "B": sim.Params(w_syn=0.005),
    }  # B too weak to fire T
    reports = validate.compare_models(neurons, edges, models, seeds=1, workers=1)
    assert list(reports) == ["A", "B"]
    assert reports["A"]["passed"].sum() > reports["B"]["passed"].sum()
