"""Public 3D fixture journey: fail closed, all arms, publication, resume and reuse."""

import json
from pathlib import Path

import pytest

from flymsg import (
    cli,
    closedloop,
    flygym_body,
    manifest,
    runstore,
)
from flymsg import (
    closedloop_experiment as experiment,
)
from flymsg.embodiment import ContractError

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/closedloop-nmf.yaml"


def call(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["flymsg", *map(str, args)])
    return cli.main()


def test_check_needs_no_connectome_and_cannot_promote_fixture_to_biology(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        cli.data, "load", lambda *a: pytest.fail("check loaded connectome")
    )
    monkeypatch.setattr(
        flygym_body, "FlyGymBody", lambda: pytest.fail("check built body")
    )
    call(monkeypatch, "closedloop", EXAMPLE, "--check")
    assert "synthetic only" in capsys.readouterr().out
    bad = tmp_path / "bad.yaml"
    bad.write_text(EXAMPLE.read_text().replace("mode: synthetic", "mode: biological"))
    with pytest.raises(SystemExit, match="measured components"):
        call(monkeypatch, "closedloop", bad, "--check")
    for before, after in [
        ("duration_us: 20000", "duration_us: 20001"),
        ("seed: 11", "seed: -1"),
        ("latency_us: 0", "latency_us: 1"),
    ]:
        bad.write_text(EXAMPLE.read_text().replace(before, after))
        with pytest.raises(ContractError):
            experiment.load(bad)
    assert not list(tmp_path.glob("*.executions"))


def test_managed_fixture_publishes_all_arms_resumes_and_verifies_cache(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        manifest, "git_info", lambda: {"commit": "synthetic-fixture", "dirty": False}
    )
    # Keep the real config in identity; production also hashes every FlyGym asset.
    monkeypatch.setattr(experiment, "inputs", lambda path: {"config": path})
    cfg = experiment.load(EXAMPLE)
    original_body = flygym_body.FlyGymBody
    whole = experiment.run(cfg, EXAMPLE, tmp_path / "whole")
    report = json.loads((whole / "summary.json").read_text())
    assert report["label"] == "synthetic"
    assert report["replay_spikes_identical"]
    assert report["pose_changes_later_optics"]
    assert report["silenced_spikes"] == 0
    assert set(report["metrics"]) == set(closedloop.ARMS)
    runstore.verify_completed(whole.parent)

    class Crash(original_body):
        def step(self, commands, dt_us):
            if self._t_us >= 12_000:
                raise RuntimeError("injected interruption")
            return super().step(commands, dt_us)

    monkeypatch.setattr(flygym_body, "FlyGymBody", Crash)
    with pytest.raises(ContractError, match="injected interruption"):
        experiment.run(cfg, EXAMPLE, tmp_path / "resumed")
    monkeypatch.setattr(flygym_body, "FlyGymBody", original_body)
    resumed = experiment.run(cfg, EXAMPLE, tmp_path / "resumed")
    for arm in closedloop.ARMS:
        assert (resumed / f"{arm}.json").read_bytes() == (
            whole / f"{arm}.json"
        ).read_bytes()
    assert (
        json.loads((resumed / "summary.json").read_text())["metrics"]["intact"][
            "new_ticks"
        ]
        < 200
    )
    before = runstore.inventory(resumed.parent)
    monkeypatch.setattr(
        flygym_body, "FlyGymBody", lambda: pytest.fail("completed fixture recomputed")
    )
    assert experiment.run(cfg, EXAMPLE, tmp_path / "resumed") == resumed
    assert before == runstore.inventory(resumed.parent)
    (resumed / "intact.json").write_text("corrupt")
    with pytest.raises(ValueError, match="integrity"):
        experiment.run(cfg, EXAMPLE, tmp_path / "resumed")
