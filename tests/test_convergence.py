"""The timestep convergence check is locked, keeps delays exact and judges against seeds."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from test_core import chain

from flymsg import convergence, evidence, sim


def test_locked_on_the_defaults_and_the_sensitivity_cases():
    doc = convergence.assert_matches_code()
    assert doc["grid"]["dt_ms"][0] == sim.Params.dt
    assert len(convergence.jobs(doc)) == 3 * 6
    assert evidence.check_lock(doc, evidence.load(), "convergence") == []
    edited = convergence.load()
    edited["grid"]["seeds"] = 3
    edited["content_sha256"] = convergence.content_hash(edited)
    with pytest.raises(convergence.ConvergenceError, match="without a bump"):
        convergence.assert_locked(edited)


def test_refuses_timesteps_that_round_the_delay():
    doc = convergence.load()
    doc["grid"]["dt_ms"] = [0.1, 0.07, 0.025]
    with pytest.raises(convergence.ConvergenceError, match="whole steps"):
        convergence.assert_matches_code(doc)
    doc = convergence.load()
    doc["grid"]["dt_ms"] = [0.05, 0.1, 0.025]
    with pytest.raises(convergence.ConvergenceError, match="start at the default"):
        convergence.assert_matches_code(doc)


def test_evidence_none_needs_a_reason_and_an_unscored_lock_on_the_defaults():
    with pytest.raises(evidence.EvidenceError, match="evidence_none"):
        evidence.check_lock({"yaml_subset": 2, "evidence": "none"}, {}, "x")
    base = {"yaml_subset": 2, "evidence": "none", "evidence_none": "defaults only"}
    for doc in (
        {**base, "claim": {"scored": True}, "defaults_changed": False},
        {**base, "claim": {"scored": False}, "defaults_changed": True},
        base,
    ):
        with pytest.raises(evidence.EvidenceError, match="unscored lock"):
            evidence.check_lock(doc, {}, "x")


def test_a_chain_responds_alike_at_finer_steps():
    edges, sign, n = chain([200, 200])
    W = sim.weight_matrix(edges, sign, n, 0.275)
    stim = np.array([0])
    rates = []
    for dt in (0.1, 0.05, 0.025):
        p = replace(sim.Params(), dt=dt)
        r = sim.run(W, stim, 100.0, 300.0, None, p, 0)
        rates.append(r.rate(0, 300.0))
    assert all(np.isfinite(x).all() for x in rates)
    assert (rates[0][-1] > 0) == (rates[2][-1] > 0)


def _cells(rates_by_dt):
    rows = []
    for dt, rates in rates_by_dt.items():
        for seed, rate in enumerate(rates):
            rows.append(
                {
                    "case": "c",
                    "target": "T",
                    "dt_ms": dt,
                    "seed": seed,
                    "rate": rate,
                    "latency": 10.0,
                    "recruited": 5,
                    "persistent": 0,
                }
            )
    return pd.DataFrame(rows)


def test_judges_the_median_against_the_finest_seed_range():
    doc = convergence.load()
    near = _cells({0.1: [20, 22, 24], 0.05: [20, 21, 23], 0.025: [18, 21, 25]})
    judged = convergence.judge(near, doc)
    assert judged["converged"].all()
    assert convergence.verdict(judged, doc) == "converged"
    far = _cells({0.1: [40, 42, 44], 0.05: [20, 21, 23], 0.025: [18, 21, 25]})
    judged = convergence.judge(far, doc)
    assert convergence.verdict(judged, doc) == "not_converged: c/T"


def test_a_silent_reference_tolerates_one_spike_in_the_window():
    doc = convergence.load()
    stray = _cells({0.1: [0, 10 / 3, 10 / 3], 0.05: [0, 0, 0], 0.025: [0, 0, 0]})
    assert convergence.verdict(convergence.judge(stray, doc), doc) == "converged"
    two = _cells({0.1: [0, 20 / 3, 20 / 3], 0.05: [0, 0, 0], 0.025: [0, 0, 0]})
    assert convergence.verdict(convergence.judge(two, doc), doc) != "converged"


def test_jobs_start_with_the_finest_step():
    assert convergence.jobs(convergence.load())[0][0] == 0.025


def test_a_holds_flip_does_not_converge():
    doc = convergence.load()
    # 3 spikes in 300 ms is 10 Hz: the coarse step holds in no seed, the finest in all
    flip = _cells({0.1: [9, 9, 9], 0.05: [10, 10, 10], 0.025: [10, 10, 30]})
    judged = convergence.judge(flip, doc)
    row = judged[judged["dt_ms"] == 0.1].iloc[0]
    assert not row["holds"] and not row["converged"]
