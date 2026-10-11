"""The held-out manifest matches criterion v4 and rejects a silent edit."""

from flymsg import benchmarks, cli, sim, validate


def test_manifest_is_locked_to_the_live_battery():
    doc = benchmarks.assert_matches_code()
    assert doc["version"] == 1
    assert benchmarks.content_hash(doc) == benchmarks.VERSION_HASHES[1]
    case = doc["confirmatory"]
    assert case["stimulus"] == "ORN_DM1"
    assert case["target"] == "DM1_lPN"
    assert case["decides"] is True
    assert doc["reported"]["decides"] is False
    assert doc["endpoints"]["checks"] == ["positive", "specific", "stability"]
    assert "biological_hz" in doc["endpoints"]["not_scored"]
    assert doc["sensitivity"]["scored"]["w_syn"] == sim.Params.w_syn
    assert [c.name for c in validate.CASES] == doc["partition"]["calibration"][:-1]


def test_a_held_out_edit_without_a_version_bump_fails():
    doc = benchmarks.load()
    doc["confirmatory"]["target"] = "MN9"
    doc["content_sha256"] = benchmarks.content_hash(doc)
    try:
        benchmarks.assert_locked(doc)
        raise AssertionError("expected a lock failure")
    except benchmarks.BenchmarkError as err:
        assert "without a bump" in str(err)


def test_benchmarks_prints_the_manifest_and_does_not_need_data(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["flymsg", "--data", str(tmp_path), "benchmarks"])
    cli.main()
    out = capsys.readouterr().out
    assert "ORN_DM1 -> DM1_lPN" in out
    assert "held-out simulation has not been run" in out
