"""Lock serialization stays neutral and preserves registered content identities."""

import ast
import hashlib
from pathlib import Path

import pytest

from flymsg import lock_codec, locks, prereg

ROOT = Path(__file__).resolve().parents[1]
YAMLS = sorted((ROOT / "validation").rglob("*.yaml"))


@pytest.mark.parametrize("path", YAMLS, ids=lambda path: path.name)
def test_all_validation_payloads_and_hashes(path):
    text = path.read_text(encoding="utf-8")
    doc = lock_codec.load_yaml(text)
    old_doc = prereg.load_yaml(text)
    payload = lock_codec.canonical(lock_codec.content_payload(doc)).encode()
    assert payload == prereg.canonical(prereg.content_payload(old_doc)).encode()
    digest = hashlib.sha256(payload).hexdigest()
    assert lock_codec.content_hash(doc) == prereg.content_hash(old_doc) == digest
    if "content_sha256" in doc:
        assert digest == doc["content_sha256"]


@pytest.mark.parametrize(
    "name",
    [
        "load_yaml",
        "canonical",
        "content_payload",
        "content_hash",
        "SKIP_HASH_KEYS",
        "PreregistrationError",
    ],
)
def test_prereg_exports_the_same_objects(name):
    assert getattr(prereg, name) is getattr(lock_codec, name)


@pytest.mark.parametrize("quote", ['"', "'"])
def test_quote_aware_subset(quote):
    text = (
        f"note: {quote}issue #20 is reopened{quote} # comment\n"
        f"items:\n  - {quote}Open loop: no feedback{quote}\n"
    )
    assert lock_codec.load_yaml("yaml_subset: 2\n" + text) == {
        "yaml_subset": 2,
        "note": "issue #20 is reopened",
        "items": ["Open loop: no feedback"],
    }
    # Registered subset 1 deliberately preserves its historical misparse.
    assert lock_codec.load_yaml(text) == {
        "note": quote + "issue",
        "items": [{quote + "Open loop": "no feedback" + quote}],
    }


@pytest.mark.parametrize(
    "text",
    [
        "yaml_subset: 3\n",
        "yaml_subset: 2\na: 1\na: 2\n",
        'yaml_subset: 2\nitems:\n  - "a" and "b: c"\n',
    ],
)
def test_parser_preserves_error_identity(text):
    with pytest.raises(prereg.PreregistrationError):
        lock_codec.load_yaml(text)


@pytest.mark.parametrize("module", ["locks", "lock_codec", "manifest"])
def test_infrastructure_has_no_battery_imports(module):
    tree = ast.parse((ROOT / "src" / "flymsg" / f"{module}.py").read_text())
    forbidden = {"prereg", "sim", "validate", "wiring"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            targets = [node.module or ""] + [alias.name for alias in node.names]
        else:
            continue
        for target in targets:
            assert not forbidden.intersection(target.split(".")), (module, target)


def test_codec_facades_are_the_same_objects():
    assert locks.content_hash is lock_codec.content_hash
    assert prereg.content_hash is lock_codec.content_hash
    assert prereg.load_yaml is lock_codec.load_yaml
    assert prereg.PreregistrationError is lock_codec.PreregistrationError
