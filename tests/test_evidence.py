"""Evidence records (SF1, #147): complete records, fail-closed checks, new locks name theirs."""

import copy

import pytest

from flymsg import evidence, kc_sparseness, locks
from flymsg.evidence import EvidenceError


def _record():
    return copy.deepcopy(evidence.load()["sister_pn_coupling"])


def test_the_registry_is_complete_and_the_audit_runs():
    records = evidence.load()
    assert records
    report = evidence.audit()
    for rid in records:
        assert rid in report


@pytest.mark.parametrize("field", list(evidence.FIELDS))
def test_a_missing_field_fails(field):
    record = _record()
    del record[field]
    with pytest.raises(EvidenceError, match="missing"):
        evidence.check_record(record)


@pytest.mark.parametrize(
    ("dotted", "value", "match"),
    [
        ("source.locator", "unknown", "must be known"),
        ("status", "guessed", "status"),
        ("value", "unknown", "value and unit"),
        ("value", None, "value and unit"),
        ("unit", "", "value and unit"),
        ("used_by", ["validation/none.yaml"], "missing file"),
    ],
)
def test_incomplete_values_fail(dotted, value, match):
    record = _record()
    *path, last = dotted.split(".")
    target = record
    for part in path:
        target = target[part]
    target[last] = value
    with pytest.raises(EvidenceError, match=match):
        evidence.check_record(record)


def test_a_missing_subfield_fails():
    record = _record()
    del record["organism"]["sex"]
    with pytest.raises(EvidenceError, match="organism.sex"):
        evidence.check_record(record)


def test_new_locks_name_existing_records():
    records = evidence.load()
    assert evidence.check_lock({"version": 1}, records, "old") == []
    with pytest.raises(EvidenceError, match="lists its evidence"):
        evidence.check_lock({"yaml_subset": 2}, records, "new")
    with pytest.raises(EvidenceError, match="no evidence record"):
        evidence.check_lock({"yaml_subset": 2, "evidence": ["nope"]}, records, "new")
    assert evidence.check_lock(
        {"yaml_subset": 2, "evidence": ["sister_pn_coupling"]}, records, "new"
    ) == ["sister_pn_coupling"]


def test_records_carry_the_values_their_locks_use():
    records = evidence.load()
    coupling = records["eln_pn_coupling"]["value"]
    assert (coupling["eln_to_pn"], coupling["pn_to_eln"]) == (
        kc_sparseness.ELN_TO_PN_CC,
        kc_sparseness.PN_TO_ELN_CC,
    )
    assert records["sister_pn_coupling"]["value"] == kc_sparseness.SISTER_PN_CC
    assert records["eln_spike_amplitude"]["value"] == kc_sparseness.ELN_SPIKE_MV
    medulla = locks.load(evidence.ROOT / "validation" / "t4t5.yaml")["protocol"][
        "medulla_mv"
    ]
    assert records["medulla_t4_input_voltages"]["value"] == medulla


def test_nested_unknowns_are_audited_and_duplicate_keys_refused():
    from flymsg import prereg

    record = _record()
    record["transformation"]["inputs_sha256"] = {"a": "unknown"}
    paths = [p for f in evidence.FIELDS for p in evidence._unknown_paths(record[f], f)]
    assert "transformation.inputs_sha256.a" in paths
    with pytest.raises(prereg.PreregistrationError, match="duplicate"):
        prereg.load_yaml("yaml_subset: 2\na: 1\na: 2\n")
    assert prereg.load_yaml("a: 1\na: 2\n") == {"a": 2}  # subset 1 unchanged
