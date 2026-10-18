"""The sensitivity grid is locked, centred on the defaults, and reports every cell."""

import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest
from test_core import chain

from flymsg import sensitivity, sim


def test_grid_is_locked_and_contains_the_default_cell():
    doc = sensitivity.assert_matches_code()
    assert doc["claim"]["scored"] is False
    assert 1.0 in doc["grid"]["w_syn_factors"] and 0.0 in doc["grid"]["th_jump"]
    assert len(sensitivity.jobs(doc)) == 10 * 6
    edited = sensitivity.load()
    edited["grid"]["seeds"] = 3
    edited["content_sha256"] = sensitivity.locks.content_hash(edited)
    with pytest.raises(sensitivity.SensitivityError, match="without a bump"):
        sensitivity.assert_locked(edited)


def test_cell_params_scale_only_w_syn_and_th_jump():
    p = sensitivity.cell_params(1.2, 2.0)
    assert p.w_syn == pytest.approx(sim.Params.w_syn * 1.2) and p.th_jump == 2.0
    assert p.tau_m == sim.Params.tau_m


def _cells():
    rows = []
    for f, rates in ((0.8, [0.0, 0.0, 10.0]), (1.0, [10.0, 13.4, 20.0])):
        for seed, rate in enumerate(rates):
            rows.append(
                {
                    "case": "c",
                    "target": "T",
                    "w_syn_factor": f,
                    "th_jump": 0.0,
                    "seed": seed,
                    "rate": rate,
                    "latency": 5.0 + seed,
                    "recruited": 10 * f,
                    "persistent": seed,
                }
            )
    return pd.DataFrame(rows)


def test_holds_uses_the_v4_floor_per_cell():
    held = sensitivity.holds(_cells(), sensitivity.load()).set_index("w_syn_factor")
    # 3 spikes in 300 ms is 10 Hz: 1 of 3 seeds at 0.8, 3 of 3 at 1.0
    assert held.loc[0.8, "share"] == pytest.approx(1 / 3) and not held.loc[0.8, "holds"]
    assert held.loc[1.0, "holds"]


def test_spreads_separate_seed_noise_from_parameter_sensitivity():
    s = sensitivity.spreads(_cells()).set_index("metric")
    assert s.loc["rate", "seed_range_at_default"] == pytest.approx(10.0)
    assert (s.loc["rate", "median_min"], s.loc["rate", "median_max"]) == (0.0, 13.4)


def test_the_figure_is_valid_svg_with_one_panel_per_target():
    doc = sensitivity.load()
    cells = _cells()
    cells = pd.concat(
        [cells.assign(w_syn_factor=f) for f in doc["grid"]["w_syn_factors"]]
    )
    root = ET.fromstring(sensitivity.svg(cells, doc))
    assert root.tag.endswith("svg")
    assert sum(1 for e in root.iter() if e.tag.endswith("polyline")) == 1  # one th_jump


def test_measure_is_deterministic_on_a_chain():
    edges, sign, n = chain([400, 400])
    neurons = pd.DataFrame({"type": ["S", "A", "B"]})
    p = sim.Params()
    W = sim.weight_matrix(edges, sign, n, p.w_syn)
    kw = {
        "seed0": 0,
        "seeds": 3,
        "rate_hz": 150.0,
        "stim_ms": 300.0,
        "duration_ms": 600.0,
    }
    a = sensitivity.measure(W, neurons, np.array([0]), ["B"], p, **kw)
    b = sensitivity.measure(W, neurons, np.array([0]), ["B"], p, **kw)
    assert a == b and len(a) == 3
    assert all(r["rate"] > 0 and r["recruited"] == 2 for r in a)


def test_the_report_reads_yes_or_no_per_cell(monkeypatch, capsys, data_dir, tmp_path):
    from test_cli import run

    monkeypatch.setattr(sensitivity, "run", lambda *_a, **_k: _cells())
    monkeypatch.setattr(sensitivity, "svg", lambda *_a: "<svg/>")  # needs the full grid
    monkeypatch.chdir(tmp_path)
    run(monkeypatch, capsys, "--data", str(data_dir), "sensitivity", "--run")
    (path,) = tmp_path.glob("runs/sensitivity/v1.executions/*/output/report.txt")
    report = path.read_text()
    assert (
        "yes" in report and "no" in report and "1.0  " not in report.split("spreads")[0]
    )
