"""Audit the archived replication inventory without rerunning or opening held-out data.

Print an exceptions ledger, or write --out NEW_FILE (never overwrite an audit).
Exit 1 on integrity failure. Historical provenance exceptions keep SF5 blocked;
a successful local inventory check never supplies an independent review sign-off.
"""

from pathlib import Path

from flymsg import replication_audit as _package

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/evidence/replication-index.json"


def audit(root: Path, entries: list[dict]) -> dict:
    return _package.audit(root, entries)


def main():
    _package.main(ROOT, INDEX, description=__doc__)


if __name__ == "__main__":
    main()
