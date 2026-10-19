"""Raw diagnostic gains cannot turn incomplete experiments into XR qualification."""

import copy

import pytest

from flymsg import quest_bounded as bounded


def fixture():
    return {
        "schema": "flymsg.bounded-skeleton-experiment/v1",
        "normal_xr_qualification": False,
        "original_reference_unchanged": True,
        "error_contract_px": 0.5,
        "preparation_ms": 20000,
        "original_reference": {"neurons": [{"k": 7}]},
        "neurons": [
            {
                "k": 7,
                "maximum_error_px": 0.49,
                "original_edges": 100,
                "candidate_edges": 25,
            }
        ],
        "blocks": [
            {
                "repeat": repeat,
                "arms": [
                    {
                        "mode": mode,
                        "submitted_lines": 100 if mode == "original" else 25,
                        "serialized_wall_ms": [200 if mode == "original" else 60] * 8,
                    }
                    for mode in ("original", "bounded", "bounded", "original")
                ],
            }
            for repeat in range(3)
        ],
    }


def test_gain_is_recomputed_and_never_admits_production_or_xr():
    result = bounded.assess(fixture())
    assert result["ratios"] == [0.3] * 3
    assert result["exploratory_gain_gate"]
    assert not result["normal_xr_qualification"]
    assert not result["production_admitted"]


@pytest.mark.parametrize(
    "failure", ["missing-neuron", "nan", "wrong-draw", "missing-repeat", "bad-error"]
)
def test_incomplete_or_invalid_experiments_are_rejected(failure):
    report = copy.deepcopy(fixture())
    if failure == "missing-neuron":
        report["neurons"][0]["k"] = 8
    elif failure == "nan":
        report["blocks"][0]["arms"][1]["serialized_wall_ms"][0] = float("nan")
    elif failure == "wrong-draw":
        report["blocks"][0]["arms"][1]["submitted_lines"] = 0
    elif failure == "missing-repeat":
        report["blocks"].pop()
    else:
        report["neurons"][0]["maximum_error_px"] = 0.51
    with pytest.raises(ValueError):
        bounded.assess(report)


def test_a_single_unfavorable_repeat_fails_the_exploratory_gate():
    report = fixture()
    for arm in report["blocks"][2]["arms"][1:3]:
        arm["serialized_wall_ms"] = [210] * 8
    assert not bounded.assess(report)["exploratory_gain_gate"]
