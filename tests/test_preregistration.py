"""The locked preregistration file matches the live code and rejects drift."""

import pytest

from flymsg import prereg, sim, validate, wiring


def test_file_matches_live_constants_and_the_version_hash():
    doc = prereg.assert_file_matches_code()
    prereg.assert_version_locked(doc)
    assert doc["version"] == 1
    assert prereg.content_hash(doc) == prereg.VERSION_HASHES[1]
    assert doc["content_sha256"] == prereg.VERSION_HASHES[1]


def test_changing_a_locked_field_without_a_version_bump_fails(tmp_path):
    doc = prereg.load()
    doc["criterion"]["min_spikes"] = 99
    digest = prereg.content_hash(doc)
    assert digest != prereg.VERSION_HASHES[1]
    doc["content_sha256"] = digest
    try:
        prereg.assert_version_locked(doc)
        raise AssertionError("expected a version-lock failure")
    except prereg.PreregistrationError as err:
        assert "without a bump" in str(err)


def test_a_new_version_must_be_added_to_the_hash_table():
    doc = prereg.load()
    doc["version"] = 99
    doc["content_sha256"] = prereg.content_hash(doc)
    try:
        prereg.assert_version_locked(doc)
        raise AssertionError("expected a missing-version failure")
    except prereg.PreregistrationError as err:
        assert "not in VERSION_HASHES" in str(err)


def test_live_code_drift_is_reported():
    doc = prereg.load()
    doc["criterion"]["min_spikes"] = validate.MIN_SPIKES + 1
    found = prereg.mismatches(doc)
    assert any(item.startswith("criterion.min_spikes") for item in found)


def test_confirmatory_run_must_use_the_locked_defaults():
    p = sim.Params()
    prereg.assert_run_matches(prereg.run_config(p.w_syn, p.th_jump, 3, draws=2))
    prereg.assert_run_matches(prereg.run_config(p.w_syn, p.th_jump, 3, draws=20))
    try:
        prereg.assert_run_matches(prereg.run_config(0.275, 0.0, 3))
        raise AssertionError("expected a run-config failure")
    except prereg.PreregistrationError as err:
        assert "w_syn" in str(err)
    prereg.assert_run_matches(prereg.run_config(0.275, 2.0, 10), exploratory=True)
    try:
        prereg.assert_run_matches(prereg.run_config(p.w_syn, p.th_jump, draws=7))
        raise AssertionError("expected a draws failure")
    except prereg.PreregistrationError as err:
        assert "draws" in str(err)


def test_n1_seeds_stay_the_locked_ones():
    doc = prereg.load()
    assert doc["n1"]["shuffle_seed"] == wiring.SHUFFLE_SEED == 0
    assert doc["n1"]["seeds"] == wiring.N1_SEEDS == 3


LEGACY = """\
note: "issue #20 is reopened"
items:
  - "Open loop: no feedback"
"""


def test_subset_1_keeps_the_registered_parse():
    doc = prereg.load_yaml(LEGACY)
    assert doc["note"] == '"issue'
    assert doc["items"] == [{'"Open loop': 'no feedback"'}]


def test_subset_2_reads_quotes():
    doc = prereg.load_yaml("yaml_subset: 2\n" + LEGACY + "tail: x # cut\n")
    assert doc["note"] == "issue #20 is reopened"
    assert doc["items"] == ["Open loop: no feedback"]
    assert doc["tail"] == "x"


def test_subset_2_edge_cases():
    doc = prereg.load_yaml("yaml_subset: 2 # quote-aware\na: rock 'n roll # c\n")
    assert doc["a"] == "rock 'n roll"
    for bad in ("yaml_subset: 3\n", 'yaml_subset: 2\nitems:\n  - "a" and "b: c"\n'):
        with pytest.raises(prereg.PreregistrationError):
            prereg.load_yaml(bad)


# content_sha256 of the registered locks that subset 1 misreads; a new version of any of
# them is a new lock and must declare yaml_subset: 2.
SUBSET_1_LOCKS = {
    "jump3d.yaml": "c93eeebd796df1913769f3625ec033745a0ff29ae188bcced938d0b9bab9e8d2",
    "kc_sparseness.yaml": "de4274eb0bd689aefe8c9bcc9318eb40fbcdb688b9da61980a559f6c040896ef",
    "mb_plasticity.yaml": "ca75a5247ff4f5081f1034bbbf939636181829f5dcb2ad11fae6f1fb13610b50",
    "motor_map.yaml": "f8cde8f4f9e05d9373335ceee8e8d4b4fc62adc819af856442d894d10014c3f9",
    "silence_scan.yaml": "8cb7434f86ec0a0c545cee50167f1130f6d4b832feb6e785ee923e9474f28a55",
    "t4t5.yaml": "f19a2d7b82a0be9a3efb175813b165746161483b71b978115999816d00bc40b2",
    "weight_rule.yaml": "87a33e5fbc589f4445386618275c46bf88c18d7f97d46e1b02e82ff4535ef79d",
}


def test_only_registered_locks_depend_on_subset_1():
    """A new lock that subset 1 misreads must declare yaml_subset: 2 (#159)."""
    misread = {}
    for path in sorted((prereg.ROOT / "validation").rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        doc = prereg.load_yaml(text)
        if "yaml_subset" in doc:
            continue
        quoted = prereg.load_yaml("yaml_subset: 2\n" + text)
        quoted.pop("yaml_subset")
        if doc != quoted:
            misread[path.name] = doc.get("content_sha256", "")
    for name, digest in misread.items():
        assert SUBSET_1_LOCKS.get(name) == digest, name
