import numpy as np
import pandas as pd
import pytest

from flymsg import dimorphism, sim


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
    rows = dimorphism._map_jobs(job, [("a",), ("b",)], 1, None, ck, meta)
    assert [r["job"] for r in rows] == ["a", "b"] and len(
        ck.read_text().splitlines()
    ) == 2
    # a rerun with one more job computes only the new one, and keeps the job order
    rows = dimorphism._map_jobs(job, [("c",), ("a",), ("b",)], 1, None, ck, meta)
    assert calls == [("a",), ("b",), ("c",)]
    assert [r["job"] for r in rows] == ["c", "a", "b"] and np.isnan(rows[2]["x"])
    with pytest.raises(dimorphism.CheckpointMismatch, match="written with"):
        dimorphism._map_jobs(job, [("a",)], 1, None, ck, {"n_null": 1000})


def test_map_jobs_in_workers_matches_serial():
    rows = dimorphism._map_jobs(_square, [(i,) for i in range(5)], 3, None, None, {})
    assert [r["y"] for r in rows] == [0, 1, 4, 9, 16]


def _square(j):
    return [{"y": j[0] ** 2}]
