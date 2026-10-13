"""Process-level recovery and immutable outputs, independent of scientific kernels."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from flymsg import progress, runstore

IDENTITY = {"schema": runstore.SCHEMA, "source": "fixture", "inputs": {"a": "sha"}}


def _write_result(run):
    (run.output / "report.csv").write_text("value\n7\n")
    (run.output / "manifest.json").write_text(
        json.dumps({"schema": "flymsg.run_manifest/v1"})
    )


def test_completed_run_is_verified_without_mutation(tmp_path):
    with runstore.Run(tmp_path / "v1", IDENTITY) as run:
        _write_result(run)
        run.finalize()
        root = run.root
    before = runstore.inventory(root)
    with runstore.Run(tmp_path / "v1", IDENTITY) as again:
        assert again.completed
        assert (again.output / "report.csv").read_text() == "value\n7\n"
    assert runstore.inventory(root) == before
    (root / "output" / "report.csv").write_text("value\n999\n")
    with (
        pytest.raises(ValueError, match="integrity"),
        runstore.Run(tmp_path / "v1", IDENTITY),
    ):
        raise AssertionError("corrupt output was accepted")


def test_identity_separates_code_inputs_and_protocol_without_touching_legacy(tmp_path):
    legacy = tmp_path / "v1"
    legacy.mkdir()
    (legacy / "manifest.json").write_text("historical\n")
    roots = []
    for identity in (
        IDENTITY,
        {**IDENTITY, "source": "different"},
        {**IDENTITY, "inputs": {"a": "new"}},
        {**IDENTITY, "protocol": 2},
    ):
        with runstore.Run(legacy, identity) as run:
            roots.append(run.root)
            _write_result(run)
            run.finalize()
    assert len(set(roots)) == 4
    assert list(legacy.iterdir()) == [legacy / "manifest.json"]
    assert (legacy / "manifest.json").read_text() == "historical\n"


CHILD = """
import json, os, sys
from pathlib import Path
from flymsg import runstore, progress
base, mode, identity = Path(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3])
with runstore.Run(base, identity) as run:
    if mode == 'hold':
        print('locked', flush=True)
        sys.stdin.read()
    elif mode in ('step-crash', 'step-write-crash'):
        import pandas as pd
        steps = progress.Steps(run.root / 'steps', identity)
        steps.get('arm-A', lambda: {'t': pd.DataFrame({'value': [1/7]})})
        if mode == 'step-write-crash':
            original = pd.DataFrame.to_parquet
            def crash(self, *args, **kwargs):
                original(self, *args, **kwargs)
                os._exit(23)
            pd.DataFrame.to_parquet = crash
            steps.get('arm-B', lambda: {'t': pd.DataFrame({'value': [2]})})
        os._exit(23)
    else:
        (run.output / 'report.csv').write_text('value\\n7\\n')
        (run.output / 'manifest.json').write_text(json.dumps({'schema': 'flymsg.run_manifest/v1'}))
        original = runstore.atomic_json
        def fail(path, data):
            if path.name == 'complete.json':
                os._exit(23)
            original(path, data)
        runstore.atomic_json = fail
        run.finalize()
"""


def _child(base, mode):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    return subprocess.Popen(
        [sys.executable, "-c", CHILD, str(base), mode, json.dumps(IDENTITY)],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )


def test_real_writer_exclusion_and_process_death_release(tmp_path):
    child = _child(tmp_path / "v1", "hold")
    try:
        assert child.stdout.readline().strip() == "locked"
        with (
            pytest.raises(ValueError, match="another process"),
            runstore.Run(tmp_path / "v1", IDENTITY),
        ):
            raise AssertionError("second writer acquired ownership")
    finally:
        child.kill()
        child.communicate(timeout=10)
    with runstore.Run(tmp_path / "v1", IDENTITY) as recovered:
        assert recovered.attempts[0]["status"] == "interrupted"
        for attempt in recovered.attempts:
            assert attempt["host"] == runstore.platform.node()
            assert attempt["kernel"] == runstore.platform.release()
            assert attempt["system"] == runstore.platform.system()
        _write_result(recovered)
        recovered.finalize()


def test_crash_after_output_rename_recovers_without_recompute(tmp_path):
    child = _child(tmp_path / "v1", "publish-crash")
    child.communicate(timeout=20)
    assert child.returncode == 23
    with runstore.Run(tmp_path / "v1", IDENTITY) as recovered:
        assert recovered.completed
        assert recovered.attempts == []  # no new attempt was started
        assert (recovered.output / "report.csv").read_text() == "value\n7\n"
        saved = json.loads((recovered.root / "attempts.json").read_text())
        assert saved[-1]["status"] == "completed"


@pytest.mark.parametrize("mode", ["step-crash", "step-write-crash"])
def test_crash_after_completed_step_resumes_exactly(tmp_path, mode):
    child = _child(tmp_path / "v1", mode)
    child.communicate(timeout=20)
    assert child.returncode == 23
    with runstore.Run(tmp_path / "v1", IDENTITY) as recovered:
        steps = progress.Steps(recovered.root / "steps", IDENTITY)
        table, fresh = steps.get(
            "arm-A", lambda: pytest.fail("completed arm was recomputed")
        )
        assert not fresh and float(table["t"]["value"].iloc[0]) == 1 / 7
        steps.get("arm-B", lambda: {"t": pd.DataFrame({"value": [2]})})
        assert steps.resumed == ["arm-A"] and steps.computed == ["arm-B"]
        assert not list((recovered.root / "steps").glob(".*.tmp"))
        _write_result(recovered)
        recovered.finalize()


def test_changed_inputs_are_detected_before_finalization(tmp_path, monkeypatch):
    asset = tmp_path / "aux.csv"
    asset.write_text("source one")
    monkeypatch.setattr(
        runstore.manifest, "git_info", lambda: {"commit": "c", "dirty": False}
    )
    paths = {"auxiliary": asset}
    identity = runstore.execution("fixture", {}, {}, paths)
    asset.write_text("source two")
    with pytest.raises(ValueError, match="changed"):
        runstore.verify_execution(identity, paths)


def test_dirty_source_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runstore.manifest, "git_info", lambda: {"commit": "c", "dirty": True}
    )
    with pytest.raises(ValueError, match="clean committed"):
        runstore.execution("fixture", {}, {}, {})
