"""Public CLI journeys: actual synthetic simulation, cache reuse, rejection and exit status."""

import argparse
import json

import pandas as pd
import pytest

from flymsg import cli, draws, managed, manifest, runstore, workbench


def _call(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["flymsg", *map(str, args)])
    cli.main()


@pytest.fixture
def clean_source(monkeypatch, tmp_path):
    # These are synthetic fixtures; real dirty-source refusal is tested separately.
    monkeypatch.setattr(
        manifest, "git_info", lambda: {"commit": "synthetic-fixture", "dirty": False}
    )
    monkeypatch.chdir(tmp_path)


def test_explicit_checkpoint_path_is_honored_and_bound_to_execution(
    monkeypatch,
    data_dir,
    tmp_path,
    clean_source,
):
    checkpoint = tmp_path / "explicit.jsonl"

    def compute(*args, **kwargs):
        assert kwargs["checkpoint"] == checkpoint
        return pd.DataFrame(
            draws.map_jobs(
                lambda j: [{"value": 7}],
                [("one",)],
                1,
                None,
                checkpoint,
                {"fixture": True},
            )
        )

    monkeypatch.setattr(cli.dimorphism, "loop_silencing", compute)
    _call(
        monkeypatch,
        "--data",
        data_dir,
        "dimorphism",
        "--loop",
        "t2",
        "--checkpoint",
        checkpoint,
        "--null",
        "1",
        "--seeds",
        "1",
        "--workers",
        "1",
    )
    assert checkpoint.is_file()
    marker = json.loads(
        checkpoint.with_name(checkpoint.name + ".execution.json").read_text()
    )
    assert marker["source"]["commit"] == "synthetic-fixture"
    (output,) = tmp_path.glob("runs/dimorphism.executions/*/output")
    doc = json.loads((output / "manifest.json").read_text())
    assert doc["extra"]["attempts"][0]["computed_jobs"] == [["one"]]


def test_simulation_publishes_once_and_data_change_gets_another_execution(
    monkeypatch,
    data_dir,
    tmp_path,
    clean_source,
):
    base = tmp_path / "rates.csv"
    args = [
        "--data",
        data_dir,
        "sim",
        "A",
        "--duration",
        "100",
        "--seeds",
        "1",
        "--out",
        base,
    ]
    _call(monkeypatch, *args)
    (output,) = tmp_path.glob("rates.executions/*/output")
    initial = runstore.inventory(output.parent)
    table = pd.read_csv(output / "rates.csv")
    assert table["rate"].gt(0).any()
    with monkeypatch.context() as again:
        again.setattr(
            cli.sim, "run", lambda *a, **k: pytest.fail("completed run recomputed")
        )
        _call(again, *args)
    assert runstore.inventory(output.parent) == initial
    edges = pd.read_parquet(data_dir / "edges.parquet")
    edges["weight"] += 1
    edges.to_parquet(data_dir / "edges.parquet")
    _call(monkeypatch, *args)
    assert len(list(tmp_path.glob("rates.executions/*/output"))) == 2
    assert runstore.inventory(output.parent) == initial


def test_scientific_failure_is_immutable_and_retains_its_exit_status(
    monkeypatch,
    data_dir,
    tmp_path,
    clean_source,
):
    monkeypatch.setattr(
        cli.validate, "run", lambda *a, **k: pd.DataFrame({"passed": [False]})
    )
    args = ["--data", data_dir, "validate", "--out", tmp_path / "validation"]
    with pytest.raises(SystemExit) as first:
        _call(monkeypatch, *args)
    assert first.value.code == 1
    (output,) = tmp_path.glob("validation.executions/*/output")
    before = runstore.inventory(output.parent)
    monkeypatch.setattr(
        cli.validate, "run", lambda *a, **k: pytest.fail("failed result recomputed")
    )
    with pytest.raises(SystemExit) as again:
        _call(monkeypatch, *args)
    assert again.value.code == 1
    assert runstore.inventory(output.parent) == before


def test_index_never_promotes_unfinalized_or_corrupt_output(tmp_path):
    identity = {"fixture": True}
    with runstore.Run(tmp_path / "v1", identity) as run:
        (run.output / "manifest.json").write_text(
            json.dumps({"schema": manifest.SCHEMA, "command": "sim"})
        )
        assert workbench.index([tmp_path]).empty
        run.finalize()
        assert len(workbench.index([tmp_path])) == 1
        (run.output / "manifest.json").write_text("{}")
        indexed = workbench.index([tmp_path])
        assert indexed["label"].tolist() == ["invalid"]


def test_legacy_checkpoint_is_not_imported_into_a_new_run(
    monkeypatch,
    data_dir,
    tmp_path,
    clean_source,
):
    legacy = tmp_path / "draws.ckpt.jsonl"
    legacy.write_text("historical checkpoint\n")
    with pytest.raises(SystemExit, match="legacy/external"):
        _call(
            monkeypatch,
            "--data",
            data_dir,
            "sensitivity",
            "--run",
            "--checkpoint",
            legacy,
        )
    assert legacy.read_text() == "historical checkpoint\n"


def test_execute_does_not_invent_an_out_or_checkpoint(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runstore, "verify_execution", lambda *args: None)
    args = argparse.Namespace(cmd="kc-sparseness", dataset="synthetic")
    identity = {"schema": runstore.SCHEMA, "source": "fixture", "inputs": {}}

    def command(a, neurons, edges):
        assert not hasattr(a, "out") and not hasattr(a, "checkpoint")
        (a._run.output / "manifest.json").write_text(
            json.dumps({"schema": manifest.SCHEMA})
        )
        return "ok"

    assert (
        managed.execute(args, [], [], command, (identity, {}, {"version": 1})) == "ok"
    )
    assert not hasattr(args, "out") and not hasattr(args, "checkpoint")


def test_sister_writer_policy_is_explicit_and_complete():
    required = {
        "sim",
        "trace",
        "compare",
        "homology",
        "jump",
        "loop",
        "validate",
        "benchmarks",
        "behavior",
        "silence-scan",
        "partner-followup",
        "mb-plasticity",
        "kc-sparseness",
        "t4t5",
        "dn-arena",
        "jump3d",
        "weight-rule",
        "sensitivity",
        "baselines",
        "apl-claws",
        "convergence",
        "path-metrics",
        "nulls",
        "select-model",
        "calibrate",
        "wiring-null",
        "dimorphism",
    }
    assert set(managed.PROTOCOLS) == required
    for name in required:
        args = cli.build_parser().parse_args(
            [
                name,
                *(
                    {
                        "sim": ["A"],
                        "trace": ["A", "--neurons", "B"],
                        "jump": [
                            "--sim",
                            "A",
                            "--gain-n",
                            "0.001",
                            "--mass-kg",
                            "0.000001",
                        ],
                        "loop": [
                            "--sim",
                            "A",
                            "--radius-m",
                            ".01",
                            "--distance-m",
                            ".1",
                            "--speed-m-s",
                            "1",
                            "--transducer-gain",
                            "1",
                            "--max-rate-hz",
                            "100",
                            "--gain-n",
                            ".001",
                            "--mass-kg",
                            ".000001",
                        ],
                    }.get(name, [])
                ),
            ]
        )
        if name in {"sim", "select-model", "calibrate"}:
            assert not managed.enabled(args)  # no output requested
        else:
            assert managed.enabled(args)
