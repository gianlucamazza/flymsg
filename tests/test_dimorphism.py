import numpy as np
import pandas as pd

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
    assert fru["p"] == 1 / 5
