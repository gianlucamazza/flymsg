"""The T4/T5 test is locked before any run; no data are loaded."""

import numpy as np
import pandas as pd
import pytest

from flymsg import cli, t4t5


def test_locked_to_the_sourced_values():
    doc = t4t5.assert_matches_code()
    assert doc["version"] == 1
    assert t4t5.content_hash(doc) == t4t5.VERSION_HASHES[1]
    assert doc["protocol"]["acceptance_deg"] == 8.23
    assert doc["protocol"]["preferred"] == {
        "a": "front_to_back",
        "b": "back_to_front",
        "c": "upward",
        "d": "downward",
    }


def test_an_unsourced_acceptance_is_refused():
    doc = t4t5.load()
    doc["protocol"]["acceptance_deg"] = 5.0
    with pytest.raises(t4t5.T4T5Error, match="sourced"):
        t4t5.assert_matches_code(doc)


def test_prints_the_protocol_without_data(monkeypatch, capsys, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    monkeypatch.setattr("sys.argv", ["flymsg", "--data", str(tmp_path), "t4t5"])
    cli.main()
    assert "ON/OFF edges, 4 directions" in capsys.readouterr().out


def test_vector_sum_and_angle_error():
    front = t4t5.preferred_angle({"front_to_back": 10, "back_to_front": 2})
    assert t4t5.angle_error(front, 0.0) == pytest.approx(0.0, abs=1e-9)
    assert t4t5.preferred_angle({"upward": 5, "downward": 1}) == pytest.approx(90.0)
    assert t4t5.angle_error(350.0, 10.0) == 20.0


def test_off_edges_darken_and_on_edges_light_what_they_crossed():
    cov = np.array([0.0, 0.5, 1.0])
    assert t4t5.light(cov, "off").tolist() == [1.0, 0.5, 0.0]
    assert t4t5.light(cov, "on").tolist() == [0.0, 0.5, 1.0]


def _table(t4_pd, t5_pd):
    rows = []
    for sub in ["T4a", "T4b", "T4c", "T4d", "T5a", "T5b", "T5c", "T5d"]:
        pref = "on" if sub.startswith("T4") else "off"
        good = t4_pd if sub.startswith("T4") else t5_pd
        target = {
            "a": "front_to_back",
            "b": "back_to_front",
            "c": "upward",
            "d": "downward",
        }[sub[-1]]
        for direction in t4t5.ANGLE:
            for pol in ("on", "off"):
                spikes = 1
                if pol == pref:
                    spikes = 10 if (direction == target and good) else 3
                rows.append(
                    {
                        "subtype": sub,
                        "direction": direction,
                        "polarity": pol,
                        "seed": 0,
                        "spikes": spikes,
                    }
                )
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("t4", "t5", "expected"), [(True, True, "both"), (False, False, "polarity only")]
)
def test_decide(t4, t5, expected):
    doc = t4t5.load()
    out = t4t5.decide(_table(t4, t5), doc["protocol"]["preferred"])
    assert out["verdict"] == expected
    assert out["metrics"]["polarity_ok"].all()
