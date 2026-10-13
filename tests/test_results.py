"""results/ holds the archived run outputs the figures are drawn from."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_archived_directory_is_present_with_its_manifest():
    archive = _load("archive_results")
    for rel in archive.DIRS:
        doc = json.loads((ROOT / "results" / rel / "manifest.json").read_text())
        assert doc["schema"] == "flymsg.run_manifest/v1"
        assert "cwd" not in doc
        assert not Path((doc.get("extra") or {}).get("data_dir", "data")).is_absolute()


def test_archive_drops_local_paths_and_never_overwrites(tmp_path, monkeypatch):
    archive = _load("archive_results")
    runs, results = tmp_path / "runs", tmp_path / "results"
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    monkeypatch.setattr(archive, "RUNS", runs)
    monkeypatch.setattr(archive, "RESULTS", results)
    src = runs / "x" / "v1"
    src.mkdir(parents=True)
    manifest = {
        "schema": "s",
        "cwd": "/home/a",
        "extra": {"data_dir": str(tmp_path / "data")},
    }
    (src / "manifest.json").write_text(json.dumps(manifest))
    (src / "t.csv").write_text("a\n1\n")
    (src / "t.ckpt.jsonl").write_text("{}")
    archive.main(["x/v1"])
    doc = json.loads((results / "x/v1/manifest.json").read_text())
    assert "cwd" not in doc and doc["extra"]["data_dir"] == "data"
    assert not (results / "x/v1/t.ckpt.jsonl").exists()
    archive.main(["x/v1"])  # same content: accepted
    (src / "t.csv").write_text("a\n2\n")
    with pytest.raises(SystemExit, match="new version"):
        archive.main(["x/v1"])


def test_no_archived_file_is_ignored_by_git():
    files = [
        str(p.relative_to(ROOT)) for p in (ROOT / "results").rglob("*") if p.is_file()
    ]
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(
        ["git", "check-ignore", "--no-index", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout == ""


def test_managed_archive_requires_verified_completion(tmp_path, monkeypatch):
    from flymsg import runstore

    archive = _load("archive_results")
    monkeypatch.setattr(archive, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(archive, "RESULTS", tmp_path / "results")
    with runstore.Run(tmp_path / "runs" / "v1", {"fixture": True}) as run:
        (run.output / "manifest.json").write_text(
            json.dumps({"schema": "flymsg.run_manifest/v1"})
        )
        (run.output / "t.csv").write_text("a\n1\n")
        run.finalize()
        rel = str(run.output.relative_to(tmp_path / "runs"))
        archive.archive(rel)
        (run.output / "t.csv").write_text("a\n2\n")
        with pytest.raises(SystemExit, match="integrity"):
            archive.archive(rel)
