"""Source/lock binding and output integrity, on an independent tiny git archive."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from flymsg import prereg


@pytest.fixture
def archive(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/replication_audit.py"
    spec = importlib.util.spec_from_file_location("replication_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lock = "version: 1\nissue: 151\n"
    (tmp_path / "lock.yaml").write_text(lock)
    output = tmp_path / "results/toy"
    output.mkdir(parents=True)
    (output / "run.txt").write_text("negative result\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Independent fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    entry = {
        "source_commit": commit,
        "dirty": False,
        "lock": "lock.yaml",
        "lock_sha256": prereg.content_hash(prereg.load_yaml(lock)),
        "lock_version": 1,
        "command": "toy --run",
        "config": {"duration_ms": 1},
        "seeds": {"seed0": 1},
        "inputs_sha256": {"toy": "a" * 64},
        "python": "3.13",
        "flymsg": "test",
        "result": "results/toy",
        "verdict": "fail",
        "outputs_sha256": {
            "run.txt": hashlib.sha256((output / "run.txt").read_bytes()).hexdigest()
        },
    }
    return module, tmp_path, entry


def test_valid_inventory_is_not_external_replication(archive):
    module, root, entry = archive
    report = module.audit(root, [entry])
    assert report["integrity_passed"]
    assert report["external_replication"] == "not_run"
    assert report["independent_signoff"] is None
    assert report["records"][0]["verdict"] == "fail"
    assert not module.audit(root, [])["integrity_passed"]


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("checksum", "output_checksum_differs:run.txt"),
        ("missing", "output_inventory_differs"),
        ("extra", "output_inventory_differs"),
        ("source", "source_commit_unavailable"),
        ("lock", "lock_hash_differs_at_source"),
    ],
)
def test_integrity_failures_cannot_pass(archive, damage, expected):
    module, root, entry = archive
    if damage == "checksum":
        (root / "results/toy/run.txt").write_text("changed\n")
    elif damage == "missing":
        (root / "results/toy/run.txt").unlink()
    elif damage == "extra":
        (root / "results/toy/unlisted.txt").write_text("extra\n")
    elif damage == "source":
        entry["source_commit"] = "0" * 40
    elif damage == "lock":
        entry["lock_sha256"] = "0" * 64
    report = module.audit(root, [entry])
    assert not report["integrity_passed"]
    assert expected in report["records"][0]["errors"]


def test_historical_dirty_source_is_an_explicit_exception(archive):
    module, root, entry = archive
    entry["dirty"] = True
    report = module.audit(root, [entry])
    assert report["integrity_passed"]
    assert report["records"][0]["exceptions"] == [
        "source_tree_not_reconstructible_from_commit"
    ]


def test_package_audit_names_exception_categories(archive, monkeypatch):
    from flymsg import replication_audit as audit

    _module, root, entry = archive
    other = root / "wd"
    other.mkdir()
    monkeypatch.chdir(other)
    bare = dict(entry)
    bare["dirty"] = True
    bare["lock"] = None
    bare["command"] = ""
    bare["config"] = None
    bare["seeds"] = None
    bare["inputs_sha256"] = None
    bare["python"] = None
    bare["flymsg"] = None
    report = audit.audit(root, [bare])
    assert report["integrity_passed"]
    assert report["records"][0]["errors"] == []
    assert report["records"][0]["exceptions"] == [
        "source_tree_not_reconstructible_from_commit",
        "no_versioned_experiment_lock",
        "missing_command",
        "missing_config",
        "missing_seeds",
        "missing_inputs_sha256",
        "missing_python",
        "missing_flymsg",
    ]
    missing = dict(entry)
    missing["source_commit"] = None
    failed = audit.audit(root, [missing])
    assert not failed["integrity_passed"]
    assert failed["records"][0]["errors"] == ["missing_source_commit"]


def test_package_audit_stdout_exit_and_exclusive_out(archive, monkeypatch, capsys):
    from flymsg import replication_audit as audit

    _module, root, entry = archive
    other = root / "wd"
    other.mkdir()
    monkeypatch.chdir(other)
    index = root / "index.json"
    index.write_text(json.dumps({"results": [entry]}))
    monkeypatch.setattr(sys, "argv", ["replication_audit.py"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        audit.main(root, index)
    assert caught.value.code == 0
    report = audit.audit(root, [entry])
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    assert capsys.readouterr().out == text
    bad = dict(entry)
    bad["outputs_sha256"] = {"run.txt": "0" * 64}
    bad_index = root / "bad-index.json"
    bad_index.write_text(json.dumps({"results": [bad]}))
    with pytest.raises(SystemExit) as caught:
        audit.main(root, bad_index)
    assert caught.value.code == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["external_replication"] == "not_run"
    assert printed["independent_signoff"] is None
    assert "output_checksum_differs:run.txt" in printed["records"][0]["errors"]
    out = root / "audit.json"
    monkeypatch.setattr(sys, "argv", ["replication_audit.py", "--out", str(out)])
    with pytest.raises(SystemExit) as caught:
        audit.main(root, index)
    assert caught.value.code == 0
    assert out.read_text() == text
    assert capsys.readouterr().out == f"1 records -> {out}\n"
    with pytest.raises(FileExistsError):
        audit.main(root, index)
