"""Atomic publication and repository identity of the opt-in source audit."""

import hashlib
import json
import runpy
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_science_inputs.py"


@pytest.fixture
def publisher(monkeypatch):
    publish = runpy.run_path(str(SCRIPT))["publish"]
    namespace = publish.__globals__
    monkeypatch.setitem(
        namespace,
        "audit",
        lambda root: ({}, pd.DataFrame({"bodyId": [1]}), pd.DataFrame({"neuron": []})),
    )
    monkeypatch.setattr(namespace["medulla"], "ranges", lambda root: pd.DataFrame())
    return publish


def test_existing_destination_refuses_before_reading(publisher, tmp_path):
    with pytest.raises(FileExistsError):
        publisher(tmp_path / "missing", tmp_path)


def test_publish_from_other_cwd_has_identity_and_verified_outputs(
    publisher, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "data"
    root.mkdir()
    (root / "neurons.parquet").write_bytes(b"source")
    out = tmp_path / "published"
    publisher(root, out)
    report = json.loads((out / "report.json").read_text())
    assert len(report["source_commit"]) == 40
    assert (
        report["inputs_sha256"]["neurons.parquet"]
        == hashlib.sha256(b"source").hexdigest()
    )
    for name, expected in report["outputs_sha256"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == expected


def test_export_failure_does_not_publish_or_leave_staging(
    publisher, tmp_path, monkeypatch
):
    def fail(*args, **kwargs):
        raise OSError("export failed")

    monkeypatch.setattr(pd.DataFrame, "to_csv", fail)
    out = tmp_path / "published"
    with pytest.raises(OSError, match="export failed"):
        publisher(tmp_path, out)
    assert not out.exists()
    assert not list(tmp_path.glob(".audit-*"))


def test_source_change_refuses_publication(publisher, tmp_path, monkeypatch):
    source = tmp_path / "neurons.parquet"
    source.write_bytes(b"before")

    def mutate(root):
        source.write_bytes(b"after")
        return {}, pd.DataFrame(), pd.DataFrame()

    monkeypatch.setitem(publisher.__globals__, "audit", mutate)
    with pytest.raises(ValueError, match="changed during audit"):
        publisher(tmp_path, tmp_path / "output")
    assert not (tmp_path / "output").exists()
