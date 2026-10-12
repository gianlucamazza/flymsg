"""Exploratory configs run into immutable, indexed directories; nothing is promoted."""

import json

import pandas as pd
import pytest
from test_cli import run

from flymsg import cli, data, workbench

CONFIG = """schema: flymsg.experiment/v1
label: exploratory
stimulus: [A]
targets: [C]
rate_hz: 150.0
stim_ms: 100.0
duration_ms: 200.0
seed0: 0
seeds: 2
note: "golden end-to-end fixture"
"""


def _write(tmp_path, text=CONFIG):
    path = tmp_path / "exp.yaml"
    path.write_text(text)
    return path


def test_golden_experiment_is_reproducible_immutable_and_indexed(
    monkeypatch,
    capsys,
    data_dir,
    tmp_path,
):
    cfg = _write(tmp_path)
    root = tmp_path / "experiments"
    d = ["--data", str(data_dir)]
    run(monkeypatch, capsys, *d, "experiment", str(cfg), "--root", str(root))
    (out,) = list(root.iterdir())
    first = pd.read_csv(out / "metrics.csv")
    assert first["rate_hz"].gt(0).all() and len(first) == 2
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["extra"]["label"] == "exploratory"
    assert manifest["config"]["config_sha256"].startswith(out.name)
    # same config -> same directory -> refused, the first result stays
    with pytest.raises(SystemExit, match="immutable"):
        run(monkeypatch, capsys, *d, "experiment", str(cfg), "--root", str(root))
    # a second root reproduces the metrics exactly
    neurons, edges = data.load(data_dir)
    again = workbench.run(workbench.load_config(cfg), neurons, edges, tmp_path / "b")
    pd.testing.assert_frame_equal(pd.read_csv(again / "metrics.csv"), first)
    table = workbench.index([root])
    assert table["label"].tolist() == ["exploratory"] and table["command"].tolist() == [
        "experiment"
    ]


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (("label: exploratory", "label: preregistered"), "only be exploratory"),
        (("schema: flymsg.experiment/v1", "schema: other/v9"), "schema"),
        (("seeds: 2", "seeds: 2\nextra: 1"), "unknown field"),
        (("stim_ms: 100.0", "stim_ms: 900.0"), "within the run"),
        (("targets: [C]", "targets: []"), "must not be empty"),
    ],
)
def test_bad_configs_are_refused(tmp_path, edit, message):
    cfg = workbench.load_config(_write(tmp_path, CONFIG.replace(*edit)))
    with pytest.raises(workbench.ConfigError, match=message):
        workbench.validate_config(cfg)


def test_unknown_names_are_refused_against_the_dataset(tmp_path, data_dir):
    neurons, _ = data.load(data_dir)
    cfg = workbench.load_config(_write(tmp_path, CONFIG.replace("[C]", "[Z]")))
    with pytest.raises(KeyError):
        workbench.validate_config(cfg, neurons)


def test_labels_of_historical_manifests():
    assert workbench.label_of({"command": "viz"}) == "exploratory"
    assert workbench.label_of({"command": "nulls"}) == "preregistered"
    assert workbench.label_of({"command": "benchmarks --run"}) == "held-out"
    failed = {"command": "benchmarks --run", "extra": {"verdict": "x FAIL: s"}}
    assert workbench.label_of(failed) == "held-out"
    assert workbench.outcome_of(failed) == "failed"
    assert workbench.outcome_of({"command": "nulls"}) == ""
    assert workbench.label_of(
        {"command": "sim", "extra": {"label": "exploratory"}}
    ) == ("exploratory")


def test_runs_lists_manifests_without_the_dataset(monkeypatch, capsys, tmp_path):
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "manifest.json").write_text(
        json.dumps({"schema": "flymsg.run_manifest/v1", "command": "nulls"})
    )

    def boom(*_a, **_k):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    out = run(monkeypatch, capsys, "runs", str(tmp_path))
    assert "preregistered" in out and "nulls" in out


def test_the_best_neuron_is_chosen_once_over_seeds(tmp_path, twin_dir):
    # seed 1 favours one C neuron, seed 2 the other: one choice over the three seeds
    neurons, edges = data.load(twin_dir)
    cfg = workbench.load_config(
        _write(tmp_path, CONFIG.replace("seeds: 2", "seeds: 3"))
    )
    out = workbench.run(cfg, neurons, edges, tmp_path / "e")
    metrics = pd.read_csv(out / "metrics.csv")
    assert metrics.groupby("target")["best_bodyId"].nunique().eq(1).all()


def test_an_exploratory_nulls_run_is_not_indexed_as_preregistered():
    doc = {"command": "nulls", "config": {"exploratory": True}}
    assert workbench.label_of(doc) == "exploratory"
