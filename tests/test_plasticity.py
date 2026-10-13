"""The KC -> MBON11 depression is locked before any run and changes nothing by default.
These tests never load the connectome."""

import math

import numpy as np
import pytest
from scipy import sparse

from flymsg import cli, plasticity, sim


def test_rule_is_locked_to_the_measured_numbers():
    doc = plasticity.assert_matches_code()
    assert doc["version"] == 1
    assert plasticity.content_hash(doc) == plasticity.VERSION_HASHES[1]
    assert doc["rule"]["factor"] == pytest.approx(0.10)
    assert plasticity.bounds(doc["source"]) == (0.498, 0.646)
    assert doc["defaults_changed"] is False
    assert (doc["protocol"]["cs_plus"], doc["protocol"]["cs_minus"]) == (
        "ORN_VA1d",
        "ORN_DL3",
    )


def test_an_edit_without_a_version_bump_fails():
    doc = plasticity.load()
    doc["rule"]["factor"] = 0.5
    doc["content_sha256"] = plasticity.content_hash(doc)
    with pytest.raises(plasticity.PlasticityError, match="without a bump"):
        plasticity.assert_locked(doc)


def test_a_factor_other_than_the_measured_one_is_refused():
    doc = plasticity.load()
    doc["rule"]["factor"] = 0.5
    with pytest.raises(plasticity.PlasticityError, match="measured charge"):
        plasticity.assert_matches_code(doc)


def test_a_held_out_odor_is_refused():
    doc = plasticity.load()
    doc["protocol"]["cs_minus"] = "ORN_DM1"
    with pytest.raises(plasticity.PlasticityError, match="held-out"):
        plasticity.assert_matches_code(doc)


def test_prints_the_protocol_and_does_not_load_data(monkeypatch, capsys, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("data.load")

    monkeypatch.setattr(cli.data, "load", boom)
    monkeypatch.setattr(
        "sys.argv", ["flymsg", "--data", str(tmp_path), "mb-plasticity"]
    )
    cli.main()
    assert "CS+ ORN_VA1d, CS- ORN_DL3" in capsys.readouterr().out


def test_eligible_needs_a_spike_inside_the_window_before_a_pulse():
    traced = np.zeros((30, 4), dtype=np.uint8)
    traced[5, 0] = 1  # 0.5 ms: inside (pulse 1.0 - 0.8, 1.0]
    traced[1, 1] = 1  # 0.1 ms: before the window opens
    traced[12, 2] = 1  # 1.2 ms: after the only pulse
    traced[10, 3] = 1  # exactly at the pulse
    hit = plasticity.eligible(traced, [1.0], 0.8, 0.1)
    assert hit.tolist() == [True, False, False, True]


def test_depress_scales_only_the_named_synapses():
    W = sparse.csc_matrix(
        np.array([[0, 2.0, 3.0], [4.0, 0, 5.0], [0, 0, 0]]), dtype=np.float32
    )
    out = plasticity.depress(W, np.array([2]), np.array([0]), 0.1)
    np.testing.assert_allclose(
        out.toarray(), [[0, 2.0, 0.3], [4.0, 0, 5.0], [0, 0, 0]], rtol=1e-6
    )
    assert W.toarray()[0, 2] == 3.0  # the input matrix is not changed


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ((10, 10), (2, 8), "consistent"),
        ((10, 10), (6, 8), "inconsistent"),  # CS+ drops only 40%
        ((10, 10), (2, 2), "inconsistent"),  # CS- drops 80%
        ((2, 10), (0, 10), "undetermined"),
    ],
)
def test_decide(before, after, expected):
    pre = {"cs_plus": [before[0]] * 3, "cs_minus": [before[1]] * 3}
    post = {"cs_plus": [after[0]] * 3, "cs_minus": [after[1]] * 3}
    verdict, plus, _ = plasticity.decide(pre, post, 0.498, 0.646, 3.0)
    assert verdict == expected
    assert math.isnan(plus) == (expected == "undetermined")


def _toy():
    # 0 = CS+ ORN -> 2 (KC a); 1 = CS- ORN -> 3 (KC b); both KCs -> 4 (MBON).
    n = 5
    pre, post = [0, 1, 2, 3], [2, 3, 4, 4]
    W = sparse.csc_matrix(
        (np.full(4, 40.0, dtype=np.float32), (post, pre)), shape=(n, n)
    )
    idx = {
        "ORN_VA1d": np.array([0]),
        "ORN_DL3": np.array([1]),
        "MBON11": np.array([4]),
        "KC": np.array([2, 3]),
    }
    return W, idx


def test_pairing_depresses_the_paired_odor_only():
    W, idx = _toy()
    out = plasticity.protocol(W, idx, plasticity.load())
    t = out["table"]
    assert (t["eligible_kcs"] == 1).all()
    assert (t["cs_plus_after"] < t["cs_plus_before"]).all()
    assert (t["cs_minus_after"] == t["cs_minus_before"]).all()
    assert out["verdict"] == "consistent"


def test_the_default_simulation_is_unchanged():
    W, idx = _toy()
    a = sim.run(W, idx["ORN_VA1d"], 100.0, 100.0, 100.0, sim.Params(), 0)
    plasticity.protocol(W, idx, plasticity.load())
    b = sim.run(W, idx["ORN_VA1d"], 100.0, 100.0, 100.0, sim.Params(), 0)
    assert np.array_equal(a.counts, b.counts)
