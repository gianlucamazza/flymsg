"""Smoke tests: every subcommand runs on a tiny synthetic dataset, and bad arguments give a
message instead of a traceback."""

import numpy as np
import pandas as pd
import pytest

from flymsg import cli, data


@pytest.fixture
def data_dir(tmp_path):
    """Three traced neurons, A -> B -> C, built through the real `data.build`."""
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
    return tmp_path


def run(monkeypatch, capsys, *args) -> str:
    monkeypatch.setattr("sys.argv", ["flymsg", *args])
    cli.main()
    return capsys.readouterr().out


def test_info_path_and_sim_run_on_a_tiny_dataset(monkeypatch, capsys, data_dir):
    d = ["--data", str(data_dir)]
    assert "A" in run(monkeypatch, capsys, *d, "info", "A")
    assert "B" in run(monkeypatch, capsys, *d, "path", "A", "C")
    out = run(
        monkeypatch, capsys, *d, "sim", "A_R", "--duration", "100", "--seeds", "1"
    )
    assert "Hz" in out or "B" in out


def test_audit_on_one_sided_types_says_so_instead_of_dividing_by_zero(
    monkeypatch, capsys, data_dir
):
    # every type has a right side only, so there is no left/right spread to score against
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, capsys, "--data", str(data_dir), "audit")
    assert "no pair to compare" in str(e.value)


def test_unknown_neuron_query_is_a_message_not_a_traceback(
    monkeypatch, capsys, data_dir
):
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, capsys, "--data", str(data_dir), "info", "NOPE")
    assert "NOPE" in str(e.value)


def test_missing_data_dir_is_a_message(monkeypatch, capsys, tmp_path):
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, capsys, "--data", str(tmp_path / "none"), "info", "A")
    assert "flymsg fetch" in str(e.value)


def test_bad_duration_is_a_message(monkeypatch, capsys, data_dir):
    with pytest.raises(SystemExit) as e:
        run(
            monkeypatch,
            capsys,
            "--data",
            str(data_dir),
            "sim",
            "A_R",
            "--duration",
            "105",
        )
    assert "bin_ms" in str(e.value)


def test_progress_without_checkpoint_is_an_argparse_error(
    monkeypatch, capsys, data_dir
):
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, capsys, "--data", str(data_dir), "dimorphism", "--progress")
    assert e.value.code == 2


def test_fafb_only_commands_are_refused_on_the_male_dataset(
    monkeypatch, capsys, data_dir
):
    with pytest.raises(SystemExit) as e:
        run(
            monkeypatch,
            capsys,
            "--data",
            str(data_dir),
            "--dataset",
            "fafb",
            "validate",
        )
    assert "malecns" in str(e.value)


def test_graph_helpers(data_dir):
    from flymsg import graph

    neurons, edges = data.load(data_dir)
    frac = graph.input_fraction(edges, len(neurons))
    assert np.allclose(frac, [1.0, 1.0])  # each target has one input
    up = graph.partners(neurons, edges, np.array([1]), upstream=True)
    assert up.index.tolist() == ["A"] and up["synapses"].tolist() == [200]
