import json

import numpy as np
import pandas as pd
import pytest

from flymsg import dimorphism, draws, sim


def test_a_short_matched_pool_is_reported_without_running_the_null(monkeypatch):
    from flymsg import parallel, validate

    class Case:
        name = "c"
        targets = ("T",)

        def stim_idx(self, neurons):
            return np.array([0])

        def target_idx(self, neurons):
            return np.array([1])

    monkeypatch.setattr(validate, "case_by_name", lambda name: Case())
    silenced = np.array([0, 1])
    key = np.array(["cb_intrinsic/1", "cb_intrinsic/1"])
    pool = np.array([False, False])
    monkeypatch.setattr(
        dimorphism, "_set_draw", lambda *a, **k: (silenced, key, pool, "label")
    )

    def rates(silence=None, per_seed=False):
        value = 8.0 if silence is not None else 10.0
        if per_seed:
            return np.array([value]), np.full((1, 3), value)
        return np.array([value])

    def null_must_not_run(*a, **k):
        raise AssertionError("null ran")

    monkeypatch.setattr(dimorphism, "_case_rates", lambda *a, **k: rates)
    monkeypatch.setattr(draws, "null_rates", null_must_not_run)
    parallel._init(
        (
            (np.zeros(2), None, None, 3, 1000, dimorphism.T4_SETS),
            None,
            {"kind": "loop"},
        )
    )
    rows = dimorphism._job(("pIP10 song pathway", "AVLP717m"))
    assert len(rows) == 1
    assert rows[0]["drop"] == pytest.approx(0.2)
    assert np.isnan(rows[0]["p_drop"])
    assert draws.matched_pool_shortfall(key, pool, silenced) == [
        ("cb_intrinsic/1", 0, 2)
    ]


def test_rise_interval_is_the_shipped_bootstrap_and_overlap_is_closed():
    from flymsg import validate

    base = [10.0, 10.0, 10.0]
    doubled = [20.0, 20.0, 20.0]
    quadrupled = [40.0, 40.0, 40.0]
    low = dimorphism.rise_interval(base, doubled)
    high = dimorphism.rise_interval(base, quadrupled)
    assert low == validate.bootstrap_ci(dimorphism.seed_rises(base, doubled))
    assert high == validate.bootstrap_ci([3.0, 3.0, 3.0])
    assert dimorphism.intervals_overlap(low, low)
    assert not dimorphism.intervals_overlap(low, high)


def test_t4_confirms_avlp717m_in_both_courtship_cases_and_leaves_t3_alone():
    jobs = dimorphism.confirmatory_jobs(dimorphism.T4_SETS)
    assert jobs == [
        ("pIP10 song pathway", "AVLP717m"),
        ("P1 courtship drive", "AVLP717m"),
    ]
    assert dimorphism.confirmatory_jobs(dimorphism.T3_SETS) == [
        ("pIP10 song pathway", "IN03B024"),
        ("pIP10 song pathway", "vMS12"),
        ("P1 courtship drive", "IN03B024"),
        ("P1 courtship drive", "vMS12"),
    ]


def test_responders_need_most_seeds_and_exclude_the_stimulus():
    def result(fired):
        counts = np.array([fired], dtype=np.uint16)
        return sim.Result(counts, np.full(len(fired), np.nan), 10.0, 10.0)

    results = [result([1, 1, 0, 1]), result([1, 0, 0, 1]), result([1, 1, 1, 0])]
    assert dimorphism.responders(results, np.array([0])).tolist() == [1, 3]


def test_enrichment_detects_an_overrepresented_category_within_superclass():
    # 100 central neurons, 10 of them fru+; responders are 10 of the fru+ ones
    n = 100
    neurons = pd.DataFrame(
        {
            "superclass": ["central"] * n,
            "fruDsx": ["fru_high"] * 10 + [None] * (n - 10),
            "dimorphism": [None] * n,
        }
    )
    table = dimorphism.enrichment(
        neurons, np.arange(10), np.array([99]), np.random.default_rng(0), n_null=200
    ).set_index("category")
    fru = table.loc["fru/dsx+"]
    assert fru["share"] == 1.0 and fru["ratio"] > 5 and fru["p"] < 0.01
    assert table.loc["dimorphic", "share"] == 0.0


def test_silencing_a_fru_relay_abolishes_the_response(monkeypatch):
    from flymsg import validate

    # S -> R (fru+ relay) -> T; two other fru- central neurons for the null
    neurons = pd.DataFrame(
        {
            "type": ["S", "R", "T", "X", "Y"],
            "instance": ["S", "R", "T", "X", "Y"],
            "superclass": ["s", "central", "t", "central", "central"],
            "fruDsx": [None, "fru_high", None, None, None],
            "dimorphism": [None] * 5,
            "sign": np.ones(5, dtype=np.int8),
        }
    )
    edges = pd.DataFrame({"pre": [0, 1], "post": [1, 2], "weight": [200, 200]})
    monkeypatch.setattr(validate, "CASES", [validate.Case("c", "S", ["T"], "")])
    table = dimorphism.silencing(
        neurons, edges, sim.Params(), seeds=1, n_null=4, workers=1, cases=("c",)
    )
    fru = table[table["silenced"] == "fru/dsx+"].iloc[0]
    assert fru["n_silenced"] == 1 and fru["drop"] == 1.0 and fru["null_drop_max"] == 0.0
    assert fru["p_drop"] == 1 / 5 and fru["p_rise"] == 1.0


def test_type_silencing_finds_the_relay_type(monkeypatch):
    from flymsg import validate

    # S -> A (fru+, relays to T) and S -> B (fru+, dead end)
    neurons = pd.DataFrame(
        {
            "type": ["S", "A", "B", "T"],
            "instance": ["S", "A", "B", "T"],
            "bodyId": [1, 2, 3, 4],
            "superclass": ["s", "c", "c", "t"],
            "fruDsx": [None, "fru_high", "fru_high", None],
            "dimorphism": [None] * 4,
            "sign": np.ones(4, dtype=np.int8),
        }
    )
    edges = pd.DataFrame(
        {"pre": [0, 0, 1], "post": [1, 2, 3], "weight": [200, 200, 200]}
    )
    monkeypatch.setattr(validate, "CASES", [validate.Case("c", "S", ["T"], "")])
    table = dimorphism.type_silencing(
        neurons, edges, sim.Params(), "c", "fru/dsx+", seeds=1, workers=1
    ).set_index("type")
    assert table.loc["A", "T_drop"] == 1.0 and table.loc["B", "T_drop"] == 0.0


def test_loop_silencing_detects_a_feedback_inhibitor_against_matched_responders(
    monkeypatch,
):
    from flymsg import validate

    # S -> T -> E -> I -| T (feedback inhibition); S -> X, an active dead end of E's kind
    neurons = pd.DataFrame(
        {
            "type": ["S", "T", "E", "I", "X"],
            "instance": ["S", "T", "E", "I", "X"],
            "bodyId": [1, 2, 3, 4, 5],
            "superclass": ["s", "t", "c", "c", "c"],
            "sign": np.array([1, 1, 1, -1, 1], dtype=np.int8),
        }
    )
    edges = pd.DataFrame(
        {
            "pre": [0, 1, 2, 3, 0],
            "post": [1, 2, 3, 1, 4],
            "weight": [200, 200, 200, 1000, 200],
        }
    )
    monkeypatch.setattr(validate, "CASES", [validate.Case("c", "S", ["T"], "")])
    table = dimorphism.loop_silencing(
        neurons, edges, sim.Params(), seeds=1, n_null=3, workers=1,
        cases=("c",), sets={"E": ("E",)},
    ).iloc[0]  # fmt: skip
    # silencing E lifts the inhibition of T; silencing X (the only matched responder) does not
    assert table["drop"] < 0 and table["null_drop_min"] == 0.0
    assert table["p_rise"] == 1 / 4 and table["p_drop"] == 1.0


def test_map_jobs_checkpoints_resumes_and_refuses_other_parameters(tmp_path):
    ck = tmp_path / "ck.jsonl"
    calls = []

    def job(j):
        calls.append(j)
        return [{"job": j[0], "x": float("nan") if j[0] == "b" else 1.0}]

    meta = {"n_null": 5}
    rows = draws.map_jobs(job, [("a",), ("b",)], 1, None, ck, meta)
    assert [r["job"] for r in rows] == ["a", "b"] and len(
        ck.read_text().splitlines()
    ) == 2
    # a rerun with one more job computes only the new one, and keeps the job order
    rows = draws.map_jobs(job, [("c",), ("a",), ("b",)], 1, None, ck, meta)
    assert calls == [("a",), ("b",), ("c",)]
    assert [r["job"] for r in rows] == ["c", "a", "b"] and np.isnan(rows[2]["x"])
    with pytest.raises(draws.CheckpointMismatch, match="written with"):
        draws.map_jobs(job, [("a",)], 1, None, ck, {"n_null": 1000})


def test_map_jobs_in_workers_matches_serial():
    rows = draws.map_jobs(_square, [(i,) for i in range(5)], 3, None, None, {})
    assert [r["y"] for r in rows] == [0, 1, 4, 9, 16]


def _square(j):
    return [{"y": j[0] ** 2}]


def test_null_draws_resume_after_an_interruption_with_the_same_result(tmp_path):
    def run(partial, fail_at=None):
        rng = np.random.default_rng(7)
        calls = []

        def rates(idx):
            calls.append(idx)
            if fail_at is not None and len(calls) == fail_at:
                raise KeyboardInterrupt
            return [float(idx.sum()), 1.0]

        out = draws.null_rates(
            "t", 6, lambda: rng.choice(50, 3, replace=False), rates, partial, {"m": 1}
        )
        return out, len(calls)

    full, _ = run(None)
    part = tmp_path / "job.partial"
    with pytest.raises(KeyboardInterrupt):
        run(part, fail_at=4)  # three draws saved
    with part.open("a") as f:
        f.write('{"pick": 1')  # a line cut short by the kill
    resumed, simulated = run(part)
    assert simulated == 3 and np.array_equal(resumed, full)
    # a saved draw that the generator no longer reproduces is refused
    lines = part.read_text().splitlines()
    lines[1] = lines[1].replace('"pick": ', '"pick": 1')
    part.write_text("\n".join(lines) + "\n")
    with pytest.raises(draws.CheckpointMismatch, match="draw 0"):
        run(part)


def test_map_jobs_runs_the_first_jobs_first_and_keeps_the_job_order():
    calls = []

    def job(j):
        calls.append(j)
        return [{"job": j[0]}]

    jobs = [("a",), ("b",), ("c",), ("d",)]
    rows = draws.map_jobs(job, jobs, 1, None, None, {}, first=[("c",), ("a",)])
    assert calls[:2] == [("a",), ("c",)] and set(calls[2:]) == {("b",), ("d",)}
    assert [r["job"] for r in rows] == ["a", "b", "c", "d"]


def test_progress_reads_finished_and_started_jobs_without_the_data(tmp_path):
    ck = tmp_path / "loop.jsonl"
    meta = {
        "kind": "loop",
        "n_null": 5,
        "sets": {k: list(v) for k, v in dimorphism.LOOP_SETS.items()},
    }
    job = ["pIP10 song pathway", "dMS9"]
    ck.write_text(json.dumps({"meta": meta, "job": job, "rows": []}) + "\n")
    started = draws.partial_path(ck, ("P1 courtship drive", "dMS9"))
    started.write_text(json.dumps(meta) + "\n" + '{"pick": 1, "rates": [1.0]}\n' * 2)
    table = dimorphism.progress(ck).set_index(["case", "silenced"])
    assert table.loc[tuple(job), "state"] == "done"
    assert table.loc[tuple(job), "draws"] == 5
    assert table.loc[("P1 courtship drive", "dMS9"), "draws"] == 2
    assert table.loc[("P1 courtship drive", "dMS9"), "state"] == "started"
    assert table.loc[("pIP10 song pathway", "both"), "state"] == "waiting"
    assert not table.loc[("pIP10 song pathway", "both"), "confirmatory"]
    assert table["confirmatory"].tolist()[0]  # confirmatory jobs first


def test_type_silencing_resumes_from_a_checkpoint(monkeypatch, tmp_path):
    from flymsg import validate

    neurons = pd.DataFrame(
        {
            "type": ["S", "A", "B", "T"],
            "instance": ["S", "A", "B", "T"],
            "bodyId": [1, 2, 3, 4],
            "superclass": ["s", "c", "c", "t"],
            "fruDsx": [None, "fru_high", "fru_high", None],
            "dimorphism": [None] * 4,
            "sign": np.ones(4, dtype=np.int8),
        }
    )
    edges = pd.DataFrame(
        {"pre": [0, 0, 1], "post": [1, 2, 3], "weight": [200, 200, 200]}
    )
    monkeypatch.setattr(validate, "CASES", [validate.Case("c", "S", ["T"], "")])
    ck = tmp_path / "by-type.jsonl"
    args = (neurons, edges, sim.Params(), "c", "fru/dsx+")
    first = dimorphism.type_silencing(*args, seeds=1, workers=1, checkpoint=ck)
    assert len(ck.read_text().splitlines()) == len(first)
    prog = dimorphism.progress(ck)
    assert set(prog["state"]) == {"done"} and len(prog) == len(first)
    # a rerun recomputes nothing and returns the same table
    monkeypatch.setattr(
        dimorphism, "_type_job", lambda job: pytest.fail(f"recomputed {job}")
    )
    again = dimorphism.type_silencing(*args, seeds=1, workers=1, checkpoint=ck)
    assert again.equals(first)
