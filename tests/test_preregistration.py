"""The locked preregistration file matches the live code and rejects drift."""

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
