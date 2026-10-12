"""Exploration chooses nothing; confirmation runs only registered, unedited locks once."""

import pytest
from test_cli import run

from flymsg import data, intervention, prereg

LOCK = """schema: flymsg.intervention/v1
version: 1
content_sha256: X
stimulus: [A]
target: C
sets:
  relay: [B]
seed0: 10
seeds: 2
explored_seeds: [0, 1, 2]
rate_hz: 150.0
stim_ms: 100.0
draws: 40
alpha: 0.05
tail: lower
"""


def _lock(tmp_path, text=LOCK):
    doc = prereg.load_yaml(text)
    digest = prereg.content_hash(doc)
    path = tmp_path / "relay.yaml"
    path.write_text(text.replace("content_sha256: X", f"content_sha256: {digest}"))
    return path, {("relay", 1): digest}


def test_explore_separates_anatomy_from_simulation(data_dir):
    neurons, edges = data.load(data_dir)
    got = intervention.explore(neurons, edges, "A", "C", seeds=2, stim_ms=100.0)
    assert got["label"] == "exploratory"
    assert got["anatomy"][0]["types"] == ["A", "B", "C"]
    assert got["anatomy"][0]["evidence"] == "anatomy"
    (row,) = got["interventions"]
    assert row["evidence"] == "simulation, exploratory" and row["silenced"] == "B"
    assert (
        row["mean_change_hz"] < 0 and max(row["silenced_hz"]) == 0.0
    )  # the only relay


def test_explore_writes_a_manifest_and_replays_it(
    monkeypatch, capsys, data_dir, tmp_path
):
    d = ["--data", str(data_dir)]
    out = tmp_path / "explore"
    run(monkeypatch, capsys, *d, "explore", "A", "C", "--seeds", "2", "--out", str(out))
    (saved,) = list((out / "A-C").iterdir())
    text = run(monkeypatch, capsys, *d, "explore", "--replay", str(saved))
    assert "replay reproduces the saved contrast" in text
    with pytest.raises(SystemExit, match="exists"):
        run(
            monkeypatch,
            capsys,
            *d,
            "explore",
            "A",
            "C",
            "--seeds",
            "2",
            "--out",
            str(out),
        )


def test_confirm_refuses_unregistered_edited_or_reused_seed_locks(data_dir, tmp_path):
    neurons, edges = data.load(data_dir)
    path, hashes = _lock(tmp_path)
    with pytest.raises(intervention.InterventionError, match="not in VERSION_HASHES"):
        intervention.confirm(neurons, edges, path, tmp_path / "o")  # not registered
    path.write_text(path.read_text().replace("draws: 40", "draws: 41"))
    with pytest.raises(intervention.InterventionError, match="without a bump"):
        intervention.confirm(neurons, edges, path, tmp_path / "o", hashes=hashes)
    path, hashes = _lock(tmp_path, LOCK.replace("seed0: 10", "seed0: 1"))
    with pytest.raises(intervention.InterventionError, match="overlap"):
        intervention.confirm(neurons, edges, path, tmp_path / "o", hashes=hashes)


def test_confirm_runs_once_and_reports_an_undefined_null(data_dir, tmp_path):
    neurons, edges = data.load(data_dir)
    path, hashes = _lock(tmp_path)
    table = intervention.confirm(neurons, edges, path, tmp_path / "o", hashes=hashes)
    row = table.iloc[0]
    assert row["evidence"] == "simulation, confirmatory" and row["silenced_hz"] == 0.0
    # three neurons: no other responder can match B, so there is no p and no pass
    assert row["p"] != row["p"] and not row["passes"]
    assert (tmp_path / "o" / "relay" / "v1" / "result.csv").exists()
    with pytest.raises(intervention.InterventionError, match="never overwritten"):
        intervention.confirm(neurons, edges, path, tmp_path / "o", hashes=hashes)


@pytest.fixture
def relay_dir(tmp_path):
    """A -> B -> C, and A -> D1..D3 that reach nothing: B is the relay, Ds are matched
    responders the null can draw."""
    import pandas as pd

    raw = tmp_path / "raw"
    raw.mkdir()
    ann = pd.DataFrame({c: [None] * 6 for c in data.ANN_COLS})
    ann["bodyId"] = [10, 20, 30, 40, 50, 60]
    ann["type"] = ["A", "B", "C", "D", "D", "D"]
    ann["status"] = ["Traced"] * 6
    ann["superclass"] = ["sensory", "x", "y", "x", "x", "x"]
    ann.to_feather(raw / data.RAW["annotations"])
    pd.DataFrame(
        {"body": [10, 20, 30, 40, 50, 60], "consensus_nt": ["acetylcholine"] * 6}
    ).to_feather(raw / data.RAW["nt"])
    pd.DataFrame(
        {
            "body_pre": [10, 20, 10, 10, 10],
            "body_post": [20, 30, 40, 50, 60],
            "weight": [200, 200, 200, 200, 200],
        }
    ).to_feather(raw / data.RAW["weights"])
    data.build(tmp_path)
    return tmp_path


def test_confirm_passes_a_true_relay_and_not_a_bystander(relay_dir, tmp_path):
    neurons, edges = data.load(relay_dir)
    path, hashes = _lock(tmp_path)
    relay = intervention.confirm(neurons, edges, path, tmp_path / "o", hashes=hashes)
    # silencing B removes C; no draw of a D does, so every draw stays above: p = 1/41
    assert relay.iloc[0]["p"] == pytest.approx(1 / 41) and relay.iloc[0]["passes"]
    other = tmp_path / "other"
    other.mkdir()
    path, _ = _lock(other, LOCK.replace("relay: [B]", "relay: [D]"))
    hashes = {("relay", 1): prereg.content_hash(intervention.load(path))}
    bystander = intervention.confirm(neurons, edges, path, other / "o", hashes=hashes)
    assert bystander.iloc[0]["silenced_hz"] > 0 and not bystander.iloc[0]["passes"]


def test_a_set_is_never_in_the_null_of_another(relay_dir, tmp_path):
    neurons, edges = data.load(relay_dir)
    path, hashes = _lock(
        tmp_path, LOCK.replace("  relay: [B]", "  relay: [B]\n  bystander: [D]")
    )
    table = intervention.confirm(neurons, edges, path, tmp_path / "o", hashes=hashes)
    # with every D in a set, no matched responder is left: reported without a p
    assert table["p"].isna().all() and not table["passes"].any()


def test_a_governed_target_says_so():
    assert "silence_scan" in intervention.GOVERNED["TTMn_R"]


@pytest.fixture
def two_target_dir(tmp_path):
    """A drives C1 through the relay B and C2 weakly through D. Silencing B must be read on
    C1, the target neuron the baseline picks, not on C2, which D keeps firing."""
    from conftest import build_dataset

    return build_dataset(
        tmp_path,
        ["A", "B", "C", "C", "D"],
        ["sensory", "x", "y", "y", "x"],
        [(0, 1, 400), (1, 2, 400), (0, 4, 400), (4, 3, 160)],  # C2 at ~40 Hz, C1 ~85
    )


def test_every_arm_reads_the_target_neuron_the_baseline_chose(two_target_dir):
    neurons, edges = data.load(two_target_dir)
    got = intervention.explore(neurons, edges, "A", "C", seeds=2, stim_ms=100.0)
    assert got["target_neuron"] == 30  # C1
    rows = {r["silenced"]: r for r in got["interventions"]}
    # B silenced: C1 goes silent; C2 still fires through D but is not the measured neuron
    assert max(rows["B"]["silenced_hz"]) == 0.0
