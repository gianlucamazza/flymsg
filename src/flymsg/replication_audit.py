"""Check archived replication records against source commits and output bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from flymsg import prereg


def audit(root: Path, entries: list[dict]) -> dict:
    records = []
    for entry in entries:
        errors, exceptions = [], []
        commit, lock = entry["source_commit"], entry["lock"]
        if entry["dirty"] is not False:
            exceptions.append("source_tree_not_reconstructible_from_commit")
        if not commit:
            errors.append("missing_source_commit")
        else:
            source = subprocess.run(
                ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                cwd=root,
                capture_output=True,
                check=False,
            )
            if source.returncode:
                errors.append("source_commit_unavailable")
            elif lock:
                blob = subprocess.run(
                    ["git", "show", f"{commit}:{lock}"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if blob.returncode:
                    errors.append("lock_unavailable_at_source")
                elif (
                    prereg.content_hash(prereg.load_yaml(blob.stdout))
                    != entry["lock_sha256"]
                ):
                    errors.append("lock_hash_differs_at_source")
        if not lock:
            exceptions.append("no_versioned_experiment_lock")
        for field in (
            "command",
            "config",
            "seeds",
            "inputs_sha256",
            "python",
            "flymsg",
        ):
            if not entry.get(field):
                exceptions.append(f"missing_{field}")
        folder = root / entry["result"]
        expected = entry["outputs_sha256"]
        actual = (
            {
                p.name
                for p in folder.iterdir()
                if p.is_file() and p.name != "manifest.json"
            }
            if folder.is_dir()
            else set()
        )
        if actual != set(expected):
            errors.append("output_inventory_differs")
        for name, digest in expected.items():
            path = folder / name
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                errors.append(f"output_checksum_differs:{name}")
        records.append(
            {
                "result": entry["result"],
                "source_commit": commit,
                "lock": lock,
                "lock_version": entry["lock_version"],
                "command": entry["command"],
                "verdict": entry["verdict"],
                "other_results": entry.get("other_results"),
                "outputs_checked": len(expected),
                "errors": errors,
                "exceptions": exceptions,
            }
        )
    return {
        "schema": "flymsg.replication-audit/v1",
        "scope": "local archive/source integrity; no simulation or held-out data access",
        "integrity_passed": bool(records) and not any(r["errors"] for r in records),
        "external_replication": "not_run",
        "independent_signoff": None,
        "licences": "Per-input licence and acquisition requirements remain in docs/replication.md; this check does not establish redistribution rights.",
        "records": records,
    }


def main(root: Path, index: Path, *, description: str | None = None) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = audit(root, json.loads(index.read_text())["results"])
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        with args.out.open("x") as stream:
            stream.write(text)
        print(f"{len(report['records'])} records -> {args.out}")
    else:
        print(text, end="")
    raise SystemExit(0 if report["integrity_passed"] else 1)
