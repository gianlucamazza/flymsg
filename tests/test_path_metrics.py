"""The weak-pathway metric check is locked, uses fresh seeds, and does not score a silence."""

import numpy as np
import pandas as pd
import pytest

from flymsg import convergence, evidence, path_metrics, sim


def test_locked_on_fresh_seeds_and_the_sensitivity_cases():
    doc = path_metrics.assert_matches_code()
    assert doc["grid"]["dt_ms"][0] == sim.Params.dt
    assert doc["grid"]["seed0"] == 5000
    assert len(path_metrics.jobs(doc)) == 3 * 6
    assert evidence.check_lock(doc, evidence.load(), "path_metrics") == []
    previous = range(convergence.load()["grid"]["seeds"])
    assert doc["grid"]["seed0"] not in previous
    edited = path_metrics.load()
    edited["grid"]["seeds"] = 3
    edited["content_sha256"] = path_metrics.content_hash(edited)
    with pytest.raises(path_metrics.PathMetricsError, match="without a bump"):
        path_metrics.assert_locked(edited)


def test_refuses_seeds_that_repeat_the_convergence_run():
    doc = path_metrics.load()
    doc["grid"]["seed0"] = 0
    with pytest.raises(path_metrics.PathMetricsError, match="overlap"):
        path_metrics.assert_matches_code(doc)


def _cells(latency_by_dt, rate=20.0, recruited=5):
    rows = []
    for dt, latencies in latency_by_dt.items():
        for seed, latency in enumerate(latencies):
            rows.append(
                {
                    "case": "c",
                    "target": "T",
                    "dt_ms": dt,
                    "seed": seed,
                    "rate": rate,
                    "latency": latency,
                    "recruited": recruited,
                }
            )
    return pd.DataFrame(rows)


def test_latency_inside_the_finest_seed_range_converges():
    doc = path_metrics.load()
    near = _cells({0.1: [10, 12, 14], 0.05: [10, 11, 13], 0.025: [9, 12, 15]})
    judged = path_metrics.judge(near, doc)
    latency = judged[(judged.metric == "latency") & (judged.dt_ms == 0.1)]
    assert latency["status"].item() == "converged"
    assert "latency: converged" in path_metrics.verdict(judged, doc)


def test_a_latency_shift_beyond_the_seed_range_does_not_converge():
    doc = path_metrics.load()
    far = _cells({0.1: [40, 42, 44], 0.05: [10, 11, 13], 0.025: [9, 12, 15]})
    judged = path_metrics.judge(far, doc)
    assert path_metrics.verdict(judged, doc).startswith("latency: not_converged (c/T)")


def test_a_missing_spike_makes_latency_and_jitter_indeterminate():
    doc = path_metrics.load()
    silent = _cells(
        {
            0.1: [np.nan, np.nan, np.nan],
            0.05: [np.nan, np.nan, np.nan],
            0.025: [np.nan, np.nan, np.nan],
        },
        rate=0.0,
        recruited=0,
    )
    judged = path_metrics.judge(silent, doc)
    text = path_metrics.verdict(judged, doc)
    assert "latency: converged, indeterminate (c/T)" in text
    assert "jitter: converged, indeterminate (c/T)" in text
    rate = judged[(judged.metric == "rate") & (judged.dt_ms == 0.1)]
    assert rate["status"].item() == "converged"


def test_jobs_start_with_the_finest_step():
    assert path_metrics.jobs(path_metrics.load())[0][0] == 0.025
