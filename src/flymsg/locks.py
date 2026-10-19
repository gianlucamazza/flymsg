"""Locked YAML files: a version, a content hash, and the table of hashes in the code.

`behavior`, `benchmarks`, `motor_map` and `silence_scan` keep their own `load`,
`assert_locked` and `VERSION_HASHES`; the common check lives here. `lock_codec` owns the YAML
parser and the canonical hash.
"""

from pathlib import Path

from flymsg import lock_codec
from flymsg.paths import require_repository_path

content_hash = lock_codec.content_hash


def load(path: Path) -> dict:
    return lock_codec.load_yaml(
        require_repository_path(path).read_text(encoding="utf-8")
    )


def check(doc: dict, hashes: dict, error: type[Exception], label: str) -> dict:
    """Refuse a document whose locked fields changed without a new version."""
    version = doc.get("version")
    if version not in hashes:
        raise error(f"{label} version {version} is not in VERSION_HASHES")
    digest = lock_codec.content_hash(doc)
    if digest != hashes[version]:
        raise error(f"{label} changed without a bump")
    if doc.get("content_sha256") != digest:
        raise error(f"content_sha256 does not match the {label}")
    return doc
