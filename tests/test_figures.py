"""Doc figures are valid SVG drawn from the numbers they are given."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flymsg import figures

ROOT = Path(__file__).resolve().parents[1]


def _parse(svg: str) -> ET.Element:
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    return root


def _texts(root: ET.Element) -> list[str]:
    return [e.text or "" for e in root.iter() if e.tag.endswith("text")]


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (0, 8, [0, 2, 4, 6, 8]),
        (0, 1.1, [0, 0.5, 1]),
        (0.8, 1.2, [0.8, 0.9, 1, 1.1, 1.2]),
    ],
)
def test_ticks_are_round_and_inside_the_range(lo, hi, expected):
    assert figures.ticks(lo, hi) == pytest.approx(expected)


def test_panel_maps_limits_to_its_box():
    p = figures.Panel(10, 20, 100, 50, (0, 10), (0, 5))
    assert (p.X(0), p.X(10), p.Y(0), p.Y(5)) == (10, 110, 70, 20)


def test_silence_scan_marks_passes_and_reports_p():
    screen = pd.DataFrame(
        {
            "unit": ["A", "B"],
            "counts": ["[0, 0, 0]", "[5, 6, 7]"],
            "mean": [0.0, 6.0],
            "passes": [True, False],
        }
    )
    confirm = pd.DataFrame(
        {
            "unit": ["A"],
            "counts": ["[0, 0, 0]"],
            "null_mean": [5.0],
            "p": [0.001],
            "names_partner": [True],
        }
    )
    root = _parse(
        figures.silence_scan(screen, confirm, [6, 6, 6], [6, 6, 6], "30–32", 3)
    )
    texts = _texts(root)
    assert "p 0.001" in texts and "null mean 5.00" in texts
    assert "Confirmation, fresh seeds 30–32" in texts
    assert any(
        t.startswith("Residual TTMn_R partner scan v3")
        and t.endswith("verdict names_partner A")
        for t in texts
    )
    reds = [e for e in root.iter() if e.get("fill") == figures.RED]
    assert len(reds) >= 6  # the passing unit's bar and seeds, and the confirm seeds


def test_embodiment_draws_every_mode():
    t = np.arange(1.0, 11.0)
    loop = {}
    for m in ("closed", "disconnected", "shuffled", "replay"):
        loop |= {
            f"{m}_t_ms": t,
            f"{m}_height_m": np.zeros(10),
            f"{m}_rate_hz": np.ones(10),
            f"{m}_motor_spikes": np.ones(10),
        }
    body = {"time_ms": list(t), "height_m": [0.0] * 10, "takeoff_ms": 3.0}
    root = _parse(figures.embodiment(body, body, loop))
    lines = [e for e in root.iter() if e.tag.endswith("polyline")]
    assert len(lines) == 2 + 3 * 4
    assert {"closed", "disconnected", "shuffled", "replay"} <= set(_texts(root))


def test_kc_persistence_one_line_per_group_and_the_note():
    t = np.arange(10.0, 610.0, 10.0)
    groups = {"a": np.ones(t.size), "b": np.zeros(t.size)}
    root = _parse(figures.kc_persistence(t, groups, 300.0, "first\nsecond"))
    assert sum(1 for e in root.iter() if e.tag.endswith("polyline")) == 2
    assert {"first", "second"} <= set(_texts(root))


def test_homology_pilot_labels_share_as_percent():
    pilot = pd.DataFrame(
        {
            "dataset": ["male", "female"],
            "DNp01": ["DNp01(GF)_R", "DNp01_L"],
            "LC4_synapses": [100, 50],
            "density_scaled": [50.0, 50.0],
            "share_of_input": [0.16, 0.08],
            "density_ratio": [2.0, 2.0],
            "ratio_types": [10, 10],
        }
    )
    texts = _texts(_parse(figures.homology_pilot(pilot)))
    assert {"16.0%", "8.0%", "male R", "female L"} <= set(texts)


def test_looming_jump_draws_closed_open_and_silence_ticks():
    replay = {
        "seed0_ttmn_closed": np.array([100, 200, 300]),
        "seed0_ttmn_open": np.array([100, 200, 300, 400, 500]),
        "seed0_ttmn_silence": np.array([600]),
    }
    root = _parse(figures.looming_jump(replay, [0], 0.1, 300.0))
    ticks = [
        e for e in root.iter() if e.tag.endswith("line") and e.get("y1") != e.get("y2")
    ]
    colours = [e.get("stroke") for e in ticks]
    # vertical ticks only (legend swatches are horizontal): closed 3, open after the third
    # spike 2, silence 1
    assert colours.count("#111827") == 3
    assert colours.count("#4b5563") == 2
    assert colours.count(figures.BLUE) == 1
    assert {"seed 0 open", "seed 0 silence"} <= set(_texts(root))


def test_partner_followup_draws_left_drive_and_null():
    left = pd.DataFrame(
        {
            "unit": ["DNp02", "DNp06"],
            "counts": ["[0, 0, 0]", "[1, 0, 0]"],
            "null_mean": [2.5, 2.4],
            "p": [0.001, 0.01],
        }
    )
    drive = pd.DataFrame(
        {
            "arm": ["DNp02_R", "DNp06_R", "pair"],
            "counts": ["[0, 0, 0]", "[1, 0, 1]", "[5, 4, 6]"],
        }
    )
    null = pd.DataFrame(
        {
            "part": ["drive"] * 4 + ["left"],
            "unit": ["pair"] * 4 + ["DNp02"],
            "draw": [0, 1, 2, 3, 0],
            "mean_count": [0.0, 0.3, 1.0, 0.0, 2.0],
        }
    )
    root = _parse(
        figures.partner_followup(
            left, [3, 2, 4], drive, null, 0.2, 3, ("replicates", "conjunction"), "40–42"
        )
    )
    texts = _texts(root)
    assert "verdict: replicates" in texts and "verdict: conjunction" in texts
    assert "Null: 4 matched DN pairs driven" in texts
    assert "pair 5.0, p 0.200" in texts
    assert sum(1 for e in root.iter() if e.get("stroke") == figures.RED) >= 1


def test_kc_sparseness_labels_an_archived_arm():
    table = pd.read_csv(ROOT / "results/kc-sparseness/v1/arms.csv")
    row = table.loc[table["arm"] == "A"].iloc[0]
    drawn = pd.DataFrame(
        [
            {
                "version": "v1",
                "arm": "A",
                "fraction_1": float(row["fraction_1"]),
                "shared_of_1": float(row["shared_of_1"]),
            }
        ]
    )
    texts = _texts(_parse(figures.kc_sparseness(drawn, 0.01)))
    assert "v1 A" in texts
    assert f"{100 * float(row['fraction_1']):.1f}%" in texts


def test_jump_range_labels_an_archived_seed_and_says_whose_clock():
    seeds = json.loads((ROOT / "results/jump3d/v1/seeds.json").read_text())
    one = next(s for s in seeds if s["seed"] == 110)
    texts = _texts(_parse(figures.jump_range([one], 28.6, 37.75)))
    assert "110" in texts
    assert f"{one['range_mm']:.2f}" in texts
    assert any("not a measured takeoff latency." in t for t in texts)
