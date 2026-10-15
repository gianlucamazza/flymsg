"""The battery baselines are locked, use the right tail per case and correct with Holm."""

import numpy as np
import pandas as pd
import pytest

from flymsg import baselines, draws, evidence


def test_locked_on_the_battery_with_disjoint_shuffle_seeds():
    doc = baselines.assert_matches_code()
    jobs = baselines.jobs(doc)
    assert jobs[0] == ("real",) and len(jobs) == 1 + doc["baseline"]["draws"]
    assert not {0, *range(20), *range(3600, 3699)} & {s for _, s in jobs[1:]}
    assert len(baselines.responses(doc)) == 8
    assert evidence.check_lock(doc, evidence.load(), "baselines") == []
    edited = baselines.load()
    edited["baseline"]["draws"] = 99
    edited["content_sha256"] = baselines.content_hash(edited)
    with pytest.raises(baselines.BaselineError, match="without a bump"):
        baselines.assert_locked(edited)
    with pytest.raises(baselines.BaselineError, match="Holm's first threshold"):
        baselines.assert_matches_code(edited)


def test_holm_is_step_down_and_monotone():
    p = np.array([0.01, 0.04, 0.03, 0.005])
    assert baselines.holm(p) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert baselines.holm(np.array([0.5, 0.9])) == pytest.approx([1.0, 1.0])


def _cells(doc, measured, null_value, draws=199):
    rows = []
    for shuffle in [baselines.REAL, *range(4000, 4000 + draws)]:
        for case, target in baselines.responses(doc):
            for seed in range(5):
                rate = measured if shuffle == baselines.REAL else null_value
                rows.append(
                    {
                        "shuffle": shuffle,
                        "case": case,
                        "target": target,
                        "seed": seed,
                        "rate": rate(case) if callable(rate) else rate,
                        "latency": 10.0,
                        "recruited": 5,
                        "persistent": 0,
                    }
                )
    return pd.DataFrame(rows)


def test_a_response_the_shuffles_never_reach_is_specific():
    doc = baselines.load()
    # positive responses far above every shuffle; bitter silent where shuffles fire
    judged = baselines.judge(
        _cells(doc, lambda c: 0.0 if c == "bitter feeding" else 50.0, 10.0), doc
    )
    assert (judged["p"] == 1 / 200).all()
    assert judged["specific"].all()
    assert (judged["tail"] == "upper").sum() == 7
    assert "not specific: none" in baselines.verdict(judged)


def test_ties_count_against_the_measured_wiring():
    doc = baselines.load()
    judged = baselines.judge(_cells(doc, 20.0, 20.0), doc)
    assert (judged["p"] == 1.0).all() and not judged["specific"].any()
    assert judged["holds_measured"].all() and (judged["holds_share_null"] == 1.0).all()
    assert baselines.verdict(judged).startswith("specific: none")


def _echo(job):
    return [{"job": list(job)}]


def test_the_jobs_pass_through_the_checkpointed_map(tmp_path):
    doc = baselines.load()
    jobs = baselines.jobs(doc)[:3]
    rows = draws.map_jobs(_echo, jobs, 1, None, tmp_path / "ck", {"v": 1})
    assert [tuple(r["job"]) for r in rows] == jobs
