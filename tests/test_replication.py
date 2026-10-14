"""The replication index matches the archive, and every archived run names a registered lock."""

import importlib.util
import json
from pathlib import Path

from flymsg import managed

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
        hashes = managed.PROTOCOLS[r["command"].split()[0]].VERSION_HASHES
        assert hashes[int(r["lock_version"])] == r["lock_sha256"], r["result"]
    assert {r["result"] for r in results if r["dirty"]} == DIRTY
