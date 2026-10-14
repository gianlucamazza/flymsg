import copy

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest
from pyarrow import feather
from scipy import io

from flymsg import evidence, sim, song

DOC = song.assert_matches_code()


def short(train_ms=360.0):
    d = copy.deepcopy(DOC)
    d["stimulus"]["train_ms"] = train_ms
    return d


def test_lock_matches_code_and_names_its_evidence():
    assert song.summary(DOC).startswith("song v1")
    assert evidence.check_lock(DOC, evidence.load(), "song.yaml")
    bad = copy.deepcopy(DOC)
    bad["stimulus"]["pause_ms"] = 25.0
    with pytest.raises(song.SongError):
        song.assert_locked(bad)


def test_envelopes_keep_pulses_and_drop_the_period():
    p = sim.Params()
    rng = np.random.default_rng(0)
    steps = round(10000 / p.dt)
    pulse = song.envelope("pulse", steps, p.dt, DOC, rng)
    assert pulse[:160].all() and not pulse[160:360].any() and pulse[360]
    aper = song.envelope("aperiodic", steps, p.dt, DOC, rng)
    assert aper.sum() == pulse.sum()  # same pulses, same time on
    onsets = np.flatnonzero(np.diff(np.r_[0, aper.astype(int)]) == 1)
    assert len(onsets) == 278 and len(set(np.diff(onsets))) > 10  # no fixed period
    assert song.envelope("sine", steps, p.dt, DOC, rng).all()


def test_dead_time_and_equal_kicks_per_neuron():
    k = np.zeros((100, 2), int)
    k[[0, 5, 30, 31, 60], 0] = [1, 2, 1, 1, 3]
    out = song.dead_time(k, 22)
    assert np.flatnonzero(out[:, 0]).tolist() == [0, 30, 60] and out.max() == 1
    p = sim.Params()
    kicks = song.matched_kicks(7, 100.0, 3, short(), p)
    counts = [kicks[k].sum(axis=0) for k in song.KINDS]
    assert all((c == counts[0]).all() for c in counts) and counts[0].sum() > 0
    gap = round(p.t_ref / p.dt)
    for k in kicks.values():
        for j in range(k.shape[1]):
            assert np.all(np.diff(np.flatnonzero(k[:, j])) >= gap)
    # pulse kicks fall only while a pulse is on
    on = song.envelope("pulse", kicks["pulse"].shape[0], p.dt, DOC, None)
    assert not kicks["pulse"][~on].any()


def test_weighted_kicks_set_the_measured_ratio():
    k = {"pulse": np.ones((20000, 4), np.int8), "sine": np.ones((20000, 4), np.int8)}
    sub = np.array(["A", "A", "B", "D"])
    w = song.weighted_kicks(k, sub, {"pulse": 0.5, "sine": 2.0}, 0)
    pa_ = w["pulse_w"].sum(axis=0)
    assert abs(pa_[0] / pa_[2] - 0.5) < 0.02 and pa_[3] == 20000
    si = w["sine_w"].sum(axis=0)
    assert abs(si[0] / si[2] - 2.0) < 0.05 and si[0] == 20000


def test_region_counts_and_pooled_label_weights(tmp_path):
    roi = pa.array(["AVLP(L)", "AVLP(R)", "SAD", "LH(L)"]).dictionary_encode()
    t = pa.table(
        {
            "body_pre": pa.array([1, 1, 2, 3], pa.int64()),
            "body_post": pa.array([2, 3, 3, 1], pa.int64()),
            "primary_post": roi,
        }
    )
    path = tmp_path / "syn.feather"
    feather.write_feather(t, path)
    r = song.region_counts(path)
    got = {(b, n): s for b, n, s in r.itertuples(index=False)}
    assert (
        got[(1, "AVLP(L)")] == 1
        and got[(3, "SAD")] == 1
        and got[(2, "SAD")] == 1
        and got[(1, "LH(L)")] == 1
    )
    neurons = pd.DataFrame({"bodyId": [1, 2, 3]})
    W, labels = song.label_weights(r, neurons, DOC)
    assert "SAD" not in labels and "AMMC" not in labels and "mALT" not in labels
    avlp = labels.index("AVLP")
    assert W[:, avlp].toarray().ravel().tolist() == [2.0, 1.0, 1.0]  # L and R pooled


def test_index_and_seed_resolution():
    assert np.isnan(song.index(np.array([0.0]), np.array([0.0])))[0]
    idx = pd.DataFrame(
        {
            "seed": [0, 1, 0, 1, 0, 1],
            "label": ["a", "a", "b", "b", "c", "c"],
            "index": [0.2, 0.1, 0.3, -0.1, np.nan, np.nan],
        }
    )
    s = song.model_signs(idx).set_index("label")
    assert s.loc["a", "resolved"] and s.loc["a", "sign"] == 1
    assert not s.loc["b", "resolved"] and s.loc["b", "sign"] == 0
    assert not s.loc["c", "resolved"]
    ok, _ = song.no_go(s.reset_index(), DOC)
    assert not ok  # 1 of 3 below one half


def test_magnitude_is_the_papers_rule():
    t = np.arange(-10, 20.5, 0.5)
    trace = np.zeros((2, t.size))
    trace[:, t < -0.4] = 1.0  # baseline 1
    trace[0, (t >= 0) & (t <= 12)] = 3.0  # +2 sustained
    trace[1, (t >= 0) & (t <= 12)] = -1.0  # -2 sustained
    m = song.magnitude(trace, t, DOC["data_rule"])
    assert np.allclose(m, [2.0, 2.0])


def fake_dataset(path, pulse, sine, fly, neuropil, sex):
    t = np.tile(np.arange(-10, 20.5, 0.5), 3)
    stim = np.zeros(t.size, np.uint8)
    for k in range(3):
        stim[61 * k + 20 : 61 * k + 41] = k + 1
    n = len(fly)
    sig = np.zeros((n, t.size))
    on = (t >= 0) & (t <= 10)
    for k, amp in ((0, pulse), (1, sine)):
        block = np.zeros(t.size, bool)
        block[61 * k : 61 * (k + 1)] = True
        sig[:, block & on] = np.asarray(amp)[:, None]
    names = np.array(
        ["AMMC", "AVLP", "LH"] + [f"X{i}" for i in range(38)], dtype=object
    )
    io.savemat(
        path,
        {
            "dataset": {
                "median_z_scored_signal_per_roi": sig,
                "timestamps": t,
                "stimuli_index_vector": stim,
                "stimuli_name_string": np.array(
                    ["Pulse", "Sine", "White Noise"], dtype=object
                ),
                "neuropil_index_per_roi": np.asarray(neuropil, np.uint8),
                "neuropil_full_names": names,
                "fly_index_per_roi": np.asarray(fly),
                "sex_index_per_roi": np.asarray(sex, np.uint8),
                "sex_full_name_string": np.array(["Female", "Male"], dtype=object),
            }
        },
    )


def test_data_targets_by_fly_with_sex_and_fly_floor(tmp_path):
    path = tmp_path / "d.mat"
    # AVLP (index 2): 4 male flies, 3 prefer pulse -> share 3/4 >= 2/3 -> +1
    # LH (index 3): 3 male flies only -> no sign; female ROIs and index 0 ignored
    fly = [1, 2, 3, 4, 1, 2, 3, 5, 6]
    neuropil = [2, 2, 2, 2, 3, 3, 3, 2, 0]
    sex = [2, 2, 2, 2, 2, 2, 2, 1, 2]
    pulse = [3, 3, 3, 1, 3, 1, 3, 1, 3]
    sine = [1, 1, 1, 3, 1, 3, 1, 3, 1]
    fake_dataset(path, pulse, sine, fly, neuropil, sex)
    t = song.data_targets(path, DOC).set_index("label")
    assert t.loc["AVLP", "flies"] == 4 and t.loc["AVLP", "sign"] == 1
    assert t.loc["LH", "flies"] == 3 and t.loc["LH", "sign"] == 0
    assert "X0" not in t.index


def test_balanced_accuracy():
    truth = np.array([1, 1, 1, -1])
    assert song.balanced_accuracy(np.array([1, 1, 1, 1]), truth) == 0.5
    assert song.balanced_accuracy(np.array([1, 1, 1, -1]), truth) == 1.0
    assert song.balanced_accuracy(np.array([0, 0, 0, 0]), truth) == 0.0


def cells_for(labels, pulse_sign, seeds=(0, 1), shuffles=3):
    """Synthetic cells: the real network's pulse/sine sign per label is `pulse_sign`;
    shuffles and the aperiodic train predict nothing (all ties)."""
    base = np.ones(len(labels))
    pulse = base * (1 + 0.5 * np.asarray(pulse_sign))
    rows = []
    for s in seeds:
        for kind, act in (("pulse", pulse), ("sine", base), ("aperiodic", base)):
            rows.append(("real", -1, s, kind, list(act)))
        for k in range(shuffles):
            rows += [("shuffle", k, s, kind, list(base)) for kind in ("pulse", "sine")]
    cols = ["family", "shuffle", "seed", "kind", "activity"]
    return pd.DataFrame(rows, columns=cols).assign(rate_hz=100.0)


def test_judge_verdicts():
    labels = [f"N{i}" for i in range(10)]
    signs = [1, 1, 1, 1, 1, -1, -1, -1, -1, -1]
    targets = pd.DataFrame({"label": labels, "sign": signs})
    d = copy.deepcopy(DOC)
    d["score"]["permutations"] = 999
    perfect = song.judge(cells_for(labels, signs, shuffles=20), labels, targets, d)
    assert perfect["balanced_accuracy"] == 1.0 and perfect["verdict"] == "pass"
    few = song.judge(cells_for(labels[:5], signs[:5]), labels[:5], targets[:5], d)
    assert few["verdict"].startswith("uninformative")
    wrong = song.judge(
        cells_for(labels, [-s for s in signs], shuffles=20), labels, targets, d
    )
    assert wrong["verdict"] == "fail"


def test_peak_follows_their_pipeline():
    y = DOC["secondary"]
    frames = np.arange(1, 101)
    drift = 1000 - 2.0 * frames  # bleaching
    raw = np.repeat(drift[:, None], 4, axis=1).astype(float)
    raw[20:40] += 500.0  # response during frames 21-40
    peak = song._peak(raw, y)
    assert 0.4 < peak < 0.6  # about 500 / 1000 once the linear drift is removed


def test_cli_prints_the_lock(capsys, monkeypatch):
    from flymsg import cli

    monkeypatch.setattr("sys.argv", ["flymsg", "song"])
    cli.main()
    assert "held-out against Pacheco" in capsys.readouterr().out
