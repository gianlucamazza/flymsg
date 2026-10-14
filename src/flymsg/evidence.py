"""Evidence records for biological parameters (SF1, issue #147).

`validation/evidence.yaml` lists one record per sourced quantity: where it comes from, what
was measured in which animal, how it maps onto MaleCNS cells, its uncertainty, its status
and the code that transforms it. Every field must be present; a value nobody recorded is
written `unknown`, never left out or guessed. Records fail closed: a missing field, an
unknown status or a measured record without a value is an error.

Locks parsed with `yaml_subset: 2` (every lock written after #159) name the records of
their biological parameters in `evidence`; historical locks keep their prose `sources`.
"""

from __future__ import annotations

from pathlib import Path

from flymsg import locks, prereg

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "evidence.yaml"
UNKNOWN = "unknown"
STATUSES = ("measured", "inferred", "calibrated", "scanned", "compensatory", "unknown")
FIELDS = {
    "id": None,
    "quantity": None,
    "value": None,
    "unit": None,
    "status": None,
    "method": None,
    "uncertainty": None,
    "source": ("citation", "doi", "license", "locator"),
    "organism": ("species", "sex", "stage"),
    "cell": ("type", "maps_to", "mapping_uncertainty"),
    "transfer_limits": None,
    "transformation": ("code", "inputs_sha256"),
    "used_by": None,
}
# never `unknown`: what the record is, where it was read, and who uses it
KNOWN = ("id", "quantity", "status", "source.citation", "source.locator", "used_by")


class EvidenceError(ValueError):
    """An evidence record or a lock's evidence list is incomplete."""


def _missing(value) -> bool:
    return value is None or value in ("", [], {}, UNKNOWN)


def _unknown_paths(value, path: str) -> list[str]:
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _unknown_paths(v, f"{path}.{k}")]
    return [path] if value == UNKNOWN else []


def _get(record: dict, dotted: str):
    value = record
    for part in dotted.split("."):
        value = value[part]
    return value


def check_record(record: dict) -> dict:
    name = record.get("id", "?")
    for field, subfields in FIELDS.items():
        if field not in record:
            raise EvidenceError(f"{name}: missing {field}")
        if subfields:
            if not isinstance(record[field], dict):
                raise EvidenceError(f"{name}: {field} must list {', '.join(subfields)}")
            for sub in subfields:
                if sub not in record[field]:
                    raise EvidenceError(f"{name}: missing {field}.{sub}")
    extra = set(record) - set(FIELDS)
    if extra:
        raise EvidenceError(f"{name}: unknown fields {sorted(extra)}")
    for dotted in KNOWN:
        value = _get(record, dotted)
        if _missing(value):
            raise EvidenceError(f"{name}: {dotted} must be known")
    if record["status"] not in STATUSES:
        raise EvidenceError(f"{name}: status must be one of {', '.join(STATUSES)}")
    if record["status"] == "measured" and (
        _missing(record["value"]) or _missing(record["unit"])
    ):
        raise EvidenceError(f"{name}: a measured record needs its value and unit")
    if not isinstance(record["used_by"], list):
        raise EvidenceError(f"{name}: used_by must be a list of lock files")
    for lock in record["used_by"]:
        if not (ROOT / lock).is_file():
            raise EvidenceError(f"{name}: used_by names a missing file {lock}")
    return record


def load(path: Path = PATH) -> dict[str, dict]:
    doc = locks.load(path)
    if doc.get("yaml_subset") != 2:
        raise EvidenceError("the evidence registry is parsed with yaml_subset: 2")
    records = {}
    for record in doc["records"]:
        check_record(record)
        if record["id"] in records:
            raise EvidenceError(f"duplicate evidence id {record['id']}")
        records[record["id"]] = record
    return records


def check_lock(doc: dict, records: dict[str, dict], label: str) -> list[str]:
    """A lock written with yaml_subset: 2 names existing evidence records."""
    if doc.get("yaml_subset") != 2:
        return []
    ids = doc.get("evidence")
    if ids == "none":
        # a numerical lock that uses only the live defaults states why it needs no record
        if not str(doc.get("evidence_none") or "").strip():
            raise EvidenceError(f"{label}: evidence: none needs evidence_none")
        return []
    if not isinstance(ids, list) or not ids:
        raise EvidenceError(f"{label}: a new lock lists its evidence records")
    missing = [i for i in ids if i not in records]
    if missing:
        raise EvidenceError(f"{label}: no evidence record {', '.join(missing)}")
    return ids


def audit(root: Path = ROOT) -> str:
    """Per record its status and the fields recorded as unknown; per lock its coverage."""
    records = load(root / "validation" / "evidence.yaml")
    lines = ["record | status | unknown fields | used by"]
    for rid, record in records.items():
        unknown = [p for f in FIELDS for p in _unknown_paths(record[f], f)]
        lines.append(
            f"{rid} | {record['status']} | {', '.join(unknown) or '-'} | "
            f"{', '.join(record['used_by'])}"
        )
    lines += ["", "lock | parser | evidence records"]
    for path in sorted((root / "validation").glob("*.yaml")):
        if path.name == "evidence.yaml":
            continue
        doc = prereg.load_yaml(path.read_text(encoding="utf-8"))
        ids = check_lock(doc, records, path.name)
        subset = doc.get("yaml_subset", 1)
        lines.append(
            f"{path.name} | subset {subset} | "
            + (", ".join(ids) if ids else "prose sources (historical)")
        )
    return "\n".join(lines)
