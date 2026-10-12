"""A run writes a manifest next to its outputs, with the locked fields."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from flymsg import cli, data, manifest


def test_write_records_git_dataset_config_seeds_packages_platform_time(tmp_path):
    started = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
    neurons = pd.DataFrame({"bodyId": [1], "type": ["A"]})
    edges = pd.DataFrame({"pre": [0], "post": [0], "weight": [1]})
    path = manifest.write(
        tmp_path,
        command="validate",
        config={"w_syn": 0.19230769230769232, "th_jump": 0.0},
        seeds={"seeds": 3, "seed0": 0},
        dataset=manifest.dataset_info("malecns", None, neurons, edges),
        started_at=started,
    )
    assert path == tmp_path / "manifest.json"
    doc = json.loads(path.read_text())
    assert manifest.required_keys(doc) == []
    assert doc["schema"] == manifest.SCHEMA
    assert doc["command"] == "validate"
    assert doc["git"]["commit"]
    assert doc["dataset"]["name"] == "malecns"
    assert doc["dataset"]["n_neurons"] == 1
    assert doc["dataset"]["n_edges"] == 1
    assert doc["config"]["w_syn"] == 0.19230769230769232
    assert doc["seeds"]["seeds"] == 3
    assert doc["packages"]["numpy"]
    assert doc["packages"]["flymsg"]
    assert doc["platform"]["python"]
    assert doc["platform"]["system"]
    assert doc["timestamps"]["started_at"].startswith("2026-10-11T12:00:00")
    assert doc["timestamps"]["finished_at"]
    assert doc["preregistration"]["version"] == 1


def test_sim_out_writes_a_manifest_next_to_the_csv(monkeypatch, capsys, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    ann = pd.DataFrame({c: [None] * 3 for c in data.ANN_COLS})
    ann["bodyId"] = [10, 20, 30]
    ann["type"] = ["A", "B", "C"]
    ann["instance"] = ["A_R", "B_R", "C_R"]
    ann["status"] = ["Traced"] * 3
    ann["superclass"] = ["sensory"] * 3
    ann.to_feather(raw / data.RAW["annotations"])
    pd.DataFrame(
        {"body": [10, 20, 30], "consensus_nt": ["acetylcholine"] * 3}
    ).to_feather(raw / data.RAW["nt"])
    pd.DataFrame(
        {"body_pre": [10, 20], "body_post": [20, 30], "weight": [200, 200]}
    ).to_feather(raw / data.RAW["weights"])
    data.build(tmp_path)
    csv = tmp_path / "rates.csv"
    monkeypatch.setattr(
        "sys.argv",
        [
            "flymsg",
            "--data",
            str(tmp_path),
            "sim",
            "A_R",
            "--duration",
            "100",
            "--seeds",
            "1",
            "--out",
            str(csv),
        ],
    )
    cli.main()
    capsys.readouterr()
    doc = json.loads((tmp_path / "manifest.json").read_text())
    assert doc["command"] == "sim"
    assert manifest.required_keys(doc) == []
    assert Path(doc["extra"]["out"]) == csv
    assert "neurons.parquet" in doc["dataset"]["files"]
    assert len(doc["dataset"]["files"]["neurons.parquet"]["sha256"]) == 64


def test_the_manifest_records_git_as_it_was_at_the_start(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from flymsg import manifest

    states = iter(
        [{"commit": "start", "dirty": False}, {"commit": "later", "dirty": True}]
    )
    monkeypatch.setattr(manifest, "git_info", lambda root=None: next(states))
    monkeypatch.setattr(manifest, "_START_GIT", None)
    manifest.mark_start()  # the run starts on "start"
    path = manifest.write(
        tmp_path,
        command="x",
        config={},
        seeds={},
        dataset={"name": "d", "files": {}},
        started_at=datetime.now(UTC),
    )
    import json

    assert json.loads(path.read_text())["git"] == {"commit": "start", "dirty": False}
