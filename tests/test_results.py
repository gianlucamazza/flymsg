"""results/ holds the archived run outputs the figures are drawn from."""

import importlib.util
import json
import runpy
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


def test_archived_attempts_do_not_expose_absolute_local_paths(tmp_path, monkeypatch):
    archive = _load("archive_results")
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    original = {
        "extra": {
            "data_dir": str(tmp_path / "data"),
            "out": "/another/host/output.csv",
            "attempts": [{"checkpoint": "/another/host/checkpoint.jsonl"}],
        }
    }
    clean = archive.clean_manifest(original)
    assert clean["extra"]["data_dir"] == "data"
    assert clean["extra"]["out"] == "output.csv"
    assert clean["extra"]["attempts"][0]["checkpoint"] == "checkpoint.jsonl"


def test_package_archive_uses_the_given_root(tmp_path, monkeypatch):
    from flymsg import archive_results as archive

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    root = tmp_path / "repo"
    runs, results = root / "runs", root / "results"
    src = runs / "x" / "v1"
    src.mkdir(parents=True)
    manifest = {
        "schema": "s",
        "cwd": "/home/a",
        "extra": {
            "data_dir": str(root / "data"),
            "out": "/another/host/output.csv",
            "replay": str(root / "replay" / "run"),
            "note": "keep",
            "attempts": [
                {"checkpoint": "/another/host/checkpoint.jsonl"},
                {"checkpoint": "relative/checkpoint.jsonl"},
            ],
        },
    }
    (src / "manifest.json").write_text(json.dumps(manifest))
    (src / "t.csv").write_text("a\n1\n")
    (src / "t.ckpt.jsonl").write_text("{}")
    archive.main(["x/v1"], root=root, runs=runs, results=results)
    doc = json.loads((results / "x/v1/manifest.json").read_text())
    assert doc["extra"]["data_dir"] == "data"
    assert doc["extra"]["out"] == "output.csv"
    assert doc["extra"]["replay"] == "replay/run"
    assert doc["extra"]["note"] == "keep"
    assert doc["extra"]["attempts"][0]["checkpoint"] == "checkpoint.jsonl"
    assert doc["extra"]["attempts"][1]["checkpoint"] == "relative/checkpoint.jsonl"
    assert "cwd" not in doc
    assert (results / "x/v1/t.csv").read_text() == "a\n1\n"
    assert not (results / "x/v1/t.ckpt.jsonl").exists()
    assert not (results / ".staging").exists()
    archive.main(["x/v1"], root=root, runs=runs, results=results)
    (src / "t.csv").write_text("a\n2\n")
    with pytest.raises(SystemExit, match="new version"):
        archive.main(["x/v1"], root=root, runs=runs, results=results)
    big = runs / "big"
    big.mkdir()
    (big / "manifest.json").write_text("{}")
    (big / "blob.bin").write_bytes(b"x" * (archive.MAX_BYTES + 1))
    with pytest.raises(SystemExit, match="byte guard"):
        archive.archive("big", root=root, runs=runs, results=results)
    with pytest.raises(SystemExit, match="no manifest.json"):
        archive.archive("missing", root=root, runs=runs, results=results)


def test_archive_script_reexports_the_package_constants():
    from flymsg import archive_results as package

    script = _load("archive_results")
    assert script.DIRS is package.DIRS
    assert script.MAX_BYTES is package.MAX_BYTES


def test_entry_points_resolve_the_repository_from_another_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scripts = ROOT / "scripts"
    loaded = {}
    for name in ("archive_results", "replication_index"):
        loaded[name] = runpy.run_path(
            str(scripts / f"{name}.py"), run_name=f"flymsg_{name}"
        )
        assert loaded[name]["ROOT"] == ROOT
        assert loaded[name]["RESULTS"] == ROOT / "results"
    assert loaded["archive_results"]["RUNS"] == ROOT / "runs"
    assert loaded["archive_results"]["DIRS"] is loaded["replication_index"]["DIRS"]
    assert loaded["replication_index"]["INDEX"] == (
        ROOT / "docs" / "evidence" / "replication-index.json"
    )
    audit_ns = runpy.run_path(
        str(scripts / "replication_audit.py"), run_name="flymsg_replication_audit"
    )
    assert audit_ns["ROOT"] == ROOT
    assert audit_ns["INDEX"] == ROOT / "docs/evidence/replication-index.json"
    completed = subprocess.run(
        ["uv", "run", "python", str(scripts / "replication_audit.py"), "--help"],
        cwd=ROOT / "docs",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Audit the archived replication inventory" in completed.stdout
    for name in ("archive_results", "replication_index", "replication_audit"):
        text = (ROOT / "src" / "flymsg" / f"{name}.py").read_text()
        assert "__file__" not in text
        assert "parents[" not in text
        assert "importlib" not in text
