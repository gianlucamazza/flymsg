"""The replication index matches the archive, and every archived run names a registered lock."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _index_module():
    spec = importlib.util.spec_from_file_location(
        "replication_index", ROOT / "scripts" / "replication_index.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_committed_index_matches_the_archive():
    module = _index_module()
    built = json.dumps(module.build(), indent=1, sort_keys=True) + "\n"
    assert module.INDEX.read_text() == built


# runs made from a modified working tree before cited runs started from clean worktrees
# (v0.8.41); their source commit alone does not reproduce them, and docs/replication.md says so
DIRTY = {
    "results/behavior",
    "results/jump/intact",
    "results/jump/dnp01",
    "results/loop",
}


def test_every_archived_lock_hash_is_a_registered_version():
    results = _index_module().build()["results"]
    for r in results:
        if r["lock"] is None:
            continue
        hashes = _index_module().PROTOCOLS[r["command"].split()[0]].VERSION_HASHES
        assert hashes[int(r["lock_version"])] == r["lock_sha256"], r["result"]
    assert {r["result"] for r in results if r["dirty"]} == DIRTY


def test_unmanaged_scored_runs_still_name_their_protocols():
    entries = _index_module().build()["results"]
    found = {
        r["result"]: r["lock"]
        for r in entries
        if r["command"].split()[0] in {"gf-looming", "song"}
    }
    assert found == {
        "results/gf_looming/v1": "validation/gf_looming.yaml",
        "results/gf_looming/v2": "validation/gf_looming.yaml",
        "results/song/v1": "validation/song.yaml",
    }


def test_script_reexports_the_package_index_constants():
    from flymsg import replication_index as package

    script = _index_module()
    assert script.DIRS is package.DIRS
    assert script.PROTOCOLS is package.PROTOCOLS
    assert script.SCHEMA is package.SCHEMA


def test_script_index_reads_monkeypatched_globals(tmp_path, monkeypatch):
    module = _index_module()
    repo = tmp_path / "repo"
    folder = repo / "results" / "toy"
    folder.mkdir(parents=True)
    lock = repo / "validation" / "toy.yaml"
    (folder / "manifest.json").write_text(
        json.dumps({"command": "toy --once", "config": {"toy_sha256": "h"}})
    )
    (folder / "t.csv").write_text("a\n")
    index = repo / "index.json"
    monkeypatch.setattr(module, "ROOT", repo)
    monkeypatch.setattr(module, "RESULTS", repo / "results")
    monkeypatch.setattr(module, "DIRS", ("toy",))
    monkeypatch.setattr(module, "SCHEMA", "schema.test")
    monkeypatch.setattr(module, "PROTOCOLS", {"toy": SimpleNamespace(PATH=lock)})
    monkeypatch.setattr(module, "INDEX", index)
    assert tmp_path in module.INDEX.parents
    built = module.build()
    assert built["schema"] == "schema.test"
    assert built["results"][0]["lock"] == "validation/toy.yaml"
    assert built["results"][0]["lock_sha256"] == "h"
    assert built["results"][0]["lock_version"] is None
    module.main([])
    assert index.read_text() == json.dumps(built, indent=1, sort_keys=True) + "\n"
    module.main(["--check"])
    index.write_text("{}\n")
    with pytest.raises(SystemExit, match="index.json is stale"):
        module.main(["--check"])


def test_package_index_uses_the_given_root(tmp_path, monkeypatch):
    from flymsg import replication_index as index

    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "repo"
    results = repo / "results"
    protocols = {
        "toy": SimpleNamespace(PATH=repo / "validation" / "toy.yaml"),
        "old": SimpleNamespace(PATH=None),
    }
    managed_rel, historical_rel = "managed/v1", "historical/v1"
    managed = results / managed_rel
    historical = results / historical_rel
    managed.mkdir(parents=True)
    historical.mkdir(parents=True)
    (managed / "manifest.json").write_text(
        json.dumps(
            {
                "command": "toy --run",
                "git": {"commit": "abc", "dirty": False},
                "preregistration": {"version": 4, "content_sha256": "m" * 64},
                "dataset": {
                    "name": "male-cns",
                    "release": "v1",
                    "files": {"ignored": {"sha256": "z" * 64}},
                },
                "extra": {
                    "execution": {
                        "inputs": {
                            "b": {"sha256": "2" * 64},
                            "a": {"sha256": "1" * 64},
                        }
                    },
                    "verdict": "pass",
                    "execution_sha256": "e" * 64,
                    "drive": "ipsilateral",
                    "left": "results/other",
                    "unused": True,
                },
                "config": {"toy_version": 9, "toy_sha256": "should-not-win"},
                "seeds": {"seed0": 1},
                "platform": {"python": "3.13.0"},
                "packages": {"flymsg": "0.8.48"},
            }
        )
    )
    (managed / "t.csv").write_text("a\n")
    (managed / "t.ckpt.jsonl").write_text("{}\n")
    (historical / "manifest.json").write_text(
        json.dumps(
            {
                "command": "old run",
                "git": {"commit": "def", "dirty": True},
                "preregistration": {"version": 1, "content_sha256": "not-used"},
                "dataset": {
                    "name": "set",
                    "release": "r0",
                    "files": {
                        "b": {"sha256": "b" * 64},
                        "a": {"sha256": "a" * 64},
                    },
                },
                "extra": {"verdict": "fail"},
                "config": {"old_version": 2, "left_sha256": "L", "right_sha256": "R"},
                "seeds": [1, 2],
                "platform": {"python": "3.12"},
                "packages": {"flymsg": "0.8.0"},
            }
        )
    )
    (historical / "out.txt").write_text("b\n")
    dirs = (managed_rel, historical_rel)
    built = index.build(results=results, protocols=protocols, root=repo, dirs=dirs)
    assert built == {
        "schema": index.SCHEMA,
        "results": [
            {
                "result": "results/managed/v1",
                "command": "toy --run",
                "source_commit": "abc",
                "dirty": False,
                "lock": "validation/toy.yaml",
                "lock_version": 4,
                "lock_sha256": "m" * 64,
                "dataset": {"name": "male-cns", "release": "v1"},
                "inputs_sha256": {"a": "1" * 64, "b": "2" * 64},
                "config": {"toy_version": 9, "toy_sha256": "should-not-win"},
                "seeds": {"seed0": 1},
                "verdict": "pass",
                "other_results": {"drive": "ipsilateral", "left": "results/other"},
                "python": "3.13.0",
                "flymsg": "0.8.48",
                "execution_sha256": "e" * 64,
                "outputs_sha256": {
                    "t.ckpt.jsonl": index.sha256(managed / "t.ckpt.jsonl"),
                    "t.csv": index.sha256(managed / "t.csv"),
                },
            },
            {
                "result": "results/historical/v1",
                "command": "old run",
                "source_commit": "def",
                "dirty": True,
                "lock": None,
                "lock_version": 2,
                "lock_sha256": None,
                "dataset": {"name": "set", "release": "r0"},
                "inputs_sha256": {"a": "a" * 64, "b": "b" * 64},
                "config": {"old_version": 2, "left_sha256": "L", "right_sha256": "R"},
                "seeds": [1, 2],
                "verdict": "fail",
                "other_results": None,
                "python": "3.12",
                "flymsg": "0.8.0",
                "execution_sha256": None,
                "outputs_sha256": {"out.txt": index.sha256(historical / "out.txt")},
            },
        ],
    }
    found = index._config({"config": {"n_version": 1, "n_sha256": "only"}}, "_sha256")
    assert found == "only"
    assert index._config({"config": {}}, "_version") is None
    text = json.dumps(built, indent=1, sort_keys=True) + "\n"
    index_path = repo / "out" / "replication-index.json"
    index_path.parent.mkdir()
    saved = {
        "results": results,
        "protocols": protocols,
        "root": repo,
        "index": index_path,
        "dirs": dirs,
    }
    index.main([], **saved)
    assert index_path.read_text() == text
    index.main(["--check"], **saved)
    index_path.write_text("{}\n")
    with pytest.raises(SystemExit, match="out/replication-index.json is stale"):
        index.main(["--check"], **saved)
