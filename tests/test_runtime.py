import json
from dataclasses import replace

import numpy as np
import pytest
from scipy import sparse

from flymsg import sim
from flymsg.runtime import CpuRuntime


def fixture(p=None, seed=4, silence=None):
    p = p or sim.Params(th_jump=2)
    W = sparse.csc_matrix(
        np.array([[0, 0, -1], [50, 0, 0], [0, 40, 0]], dtype=np.float32)
    )
    kicks = sim.poisson_kicks(seed, 500, p.dt, 700, 1)
    kwargs = {
        "steps": 1000,
        "kicks": kicks,
        "p": p,
        "per_bin": 100,
        "silence": silence,
        "trace": np.arange(3),
    }
    return W, kicks, kwargs


@pytest.mark.parametrize(
    "p", [sim.Params(), sim.Params(th_jump=2), sim.Params(delay=0.3, t_ref=0.4)]
)
@pytest.mark.parametrize("silence", [None, np.array([1])])
def test_chunked_and_checkpoint_resume_match_existing_kernel(tmp_path, p, silence):
    W, kicks, kwargs = fixture(p, silence=silence)
    expected = sim.run(
        W,
        np.array([0]),
        duration_ms=100,
        kicks=kicks,
        p=p,
        silence=silence,
        trace=np.arange(3),
    )
    runtime = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    for end in [1, 19, 23, 217]:
        runtime.advance_to(end)
    runtime.checkpoint(tmp_path / "state.npz")
    resumed = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    resumed.restore(tmp_path / "state.npz")
    for end in [218, 700, 799, 1000]:
        runtime.advance_to(end)
        resumed.advance_to(end)
    for actual in [runtime.result(), resumed.result()]:
        np.testing.assert_array_equal(actual.counts, expected.counts)
        np.testing.assert_array_equal(actual.first_spike_ms, expected.first_spike_ms)
        np.testing.assert_array_equal(actual.traced, expected.traced)
    for name, value in runtime.snapshot().items():
        restored = resumed.snapshot()[name]
        assert restored.dtype == value.dtype and restored.shape == value.shape
        assert restored.tobytes() == value.tobytes()


def test_snapshot_is_detached_and_zero_step_is_noop():
    W, _, kwargs = fixture()
    runtime = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    before = runtime.snapshot()
    runtime.advance_to(0)
    runtime.snapshot()["v"][:] = 0
    np.testing.assert_array_equal(before["v"], runtime.snapshot()["v"])
    with pytest.raises(ValueError):
        runtime.result()
    for target in [-1, 1001, True, 0.5]:
        with pytest.raises(ValueError):
            runtime.advance_to(target)


def test_incompatible_or_corrupt_checkpoint_is_transactional(tmp_path):
    W, _, kwargs = fixture()
    runtime = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    runtime.advance_to(217)
    path = tmp_path / "state.npz"
    runtime.checkpoint(path)
    other = CpuRuntime(
        W,
        np.array([0]),
        input_encoding="counts",
        **{**kwargs, "p": replace(kwargs["p"], w_syn=0.5)},
    )
    with pytest.raises(ValueError, match="incompatible"):
        other.restore(path)
    assert other.step == 0
    with np.load(path, allow_pickle=False) as archive:
        saved = {name: archive[name] for name in archive.files}
    saved["ring_len"] = np.full_like(saved["ring_len"], 99)
    np.savez(path, **saved)
    with pytest.raises(ValueError, match="queue"):
        runtime.restore(path)
    assert runtime.step == 217
    saved["metadata"] = np.array(json.dumps({"schema": "future"}))
    np.savez(path, **saved)
    with pytest.raises(ValueError, match="incompatible"):
        runtime.restore(path)


@pytest.mark.parametrize(
    "edit",
    [
        {"steps": True},
        {"per_bin": 0},
        {"steps": 999},
        {"kicks": np.array([[-1]])},
        {"kicks": np.array([[1.5]])},
        {"p": sim.Params(tau_m=5, tau_syn=5)},
        {"trace": np.array([3])},
        {"silence": np.array([-1])},
    ],
)
def test_invalid_inputs(edit):
    W, _, kwargs = fixture()
    with pytest.raises(ValueError):
        CpuRuntime(W, np.array([0]), input_encoding="counts", **{**kwargs, **edit})


def test_online_inputs_survive_checkpoint_and_match_explicit_oracle(tmp_path):
    W, _, kwargs = fixture()
    kwargs["kicks"] = np.zeros((0, 1), dtype=np.int64)
    runtime = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    runtime.advance_to(217)
    block = np.full((50, 1), 2, dtype=np.int64)
    runtime.schedule_inputs(block)
    path = tmp_path / "online.npz"
    runtime.checkpoint(path)
    resumed = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    resumed.restore(path)
    runtime.advance_to(1000)
    resumed.advance_to(1000)
    explicit = np.zeros((267, 1), dtype=np.int64)
    explicit[217:] = block
    expected = sim.run(
        W,
        np.array([0]),
        duration_ms=100,
        kicks=explicit,
        p=kwargs["p"],
        trace=np.arange(3),
    )
    for actual in (runtime.result(), resumed.result()):
        np.testing.assert_array_equal(actual.traced, expected.traced)
        assert actual.stim_ms == expected.stim_ms
    assert runtime.result().counts.sum() > 0


def test_checkpoint_numeric_corruption_is_rejected(tmp_path):
    W, _, kwargs = fixture()
    runtime = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    path = tmp_path / "corrupt.npz"
    runtime.checkpoint(path)
    with np.load(path, allow_pickle=False) as archive:
        saved = {name: archive[name] for name in archive.files}
    saved["v"][0] += 0.1
    np.savez(path, **saved)
    with pytest.raises(ValueError, match="integrity"):
        runtime.restore(path)
    assert runtime.step == 0


def test_feedback_can_change_toy_body_and_neural_outputs():
    from flymsg.embodiment import MockBody, MotorCommand

    W, _, kwargs = fixture()
    kwargs["kicks"] = np.zeros((0, 1), dtype=np.int64)

    def experiment(feedback):
        runtime = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
        body = MockBody(position_m=0.001)
        for start in range(0, 1000, 100):
            if feedback and body.position_m > 0:
                runtime.schedule_inputs(np.ones((100, 1), dtype=np.int64))
            runtime.advance_to(start + 100)
            motor_spikes = runtime.snapshot()["traced"][start : start + 100, 1].sum()
            body.step(MotorCommand(start * 100, float(motor_spikes), ()), 10000)
        return runtime.result(), body.position_m

    closed, closed_x = experiment(True)
    opened, opened_x = experiment(False)
    assert closed.counts.sum() > opened.counts.sum() == 0
    assert closed_x > opened_x == 0.001


@pytest.mark.parametrize("damage", ["bytes", "missing", "field", "semantics"])
def test_checkpoint_storage_and_numerical_mode_fail_closed(tmp_path, damage):
    W, _, kwargs = fixture()
    runtime = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    runtime.advance_to(217)
    before = runtime.snapshot()
    path = tmp_path / "state.npz"
    runtime.checkpoint(path)
    if damage == "bytes":
        path.write_bytes(b"corrupted checkpoint")
    elif damage == "missing":
        path.unlink()
    else:
        with np.load(path, allow_pickle=False) as archive:
            saved = {name: archive[name] for name in archive.files}
        if damage == "field":
            del saved["v"]
        else:
            meta = json.loads(str(saved["metadata"]))
            meta["semantics"] = "different-backend-or-numerical-mode"
            saved["metadata"] = np.array(json.dumps(meta))
        np.savez(path, **saved)
    with pytest.raises((ValueError, FileNotFoundError)):
        runtime.restore(path)
    assert runtime.step == 217
    for name, value in before.items():
        assert runtime.snapshot()[name].tobytes() == value.tobytes()


def test_changed_runtime_numerical_mode_refuses_old_checkpoint(tmp_path, monkeypatch):
    from flymsg import runtime as module

    W, _, kwargs = fixture()
    old = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    old.advance_to(217)
    path = tmp_path / "state.npz"
    old.checkpoint(path)
    monkeypatch.setattr(module, "SEMANTICS", "flymsg.lif/other-numerical-mode")
    changed = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    before = changed.snapshot()
    with pytest.raises(ValueError, match="incompatible"):
        changed.restore(path)
    assert changed.step == 0
    for name, value in before.items():
        assert changed.snapshot()[name].tobytes() == value.tobytes()


COUNTS_STATE = {
    "counts",
    "first",
    "g",
    "input_counts",
    "ref_until",
    "ring",
    "ring_len",
    "th",
    "traced",
    "v",
}
STEPS = 200
STOPS = (1, 17, 80, STEPS)


def _same_snapshot(left, right):
    assert set(left) == set(right)
    for name, value in left.items():
        other = right[name]
        assert other.dtype == value.dtype and other.shape == value.shape
        assert other.tobytes() == value.tobytes()


def _same_result(actual, expected):
    np.testing.assert_array_equal(actual.counts, expected.counts)
    np.testing.assert_array_equal(actual.first_spike_ms, expected.first_spike_ms)
    np.testing.assert_array_equal(actual.traced, expected.traced)
    if expected.graded_v is None:
        assert actual.graded_v is None
    else:
        np.testing.assert_array_equal(actual.graded_v, expected.graded_v)
    assert actual.stim_ms == expected.stim_ms


def test_counts_encoding_matches_sim_run_and_keeps_its_state():
    W, kicks, kwargs = fixture()
    p = kwargs["p"]
    expected = sim.run(
        W,
        np.array([0]),
        duration_ms=100,
        kicks=kicks,
        p=p,
        silence=kwargs["silence"],
        trace=kwargs["trace"],
    )
    whole = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    whole.advance_to(kwargs["steps"])
    parts = CpuRuntime(W, np.array([0]), input_encoding="counts", **kwargs)
    for stop in (1, 19, 217, 700, kwargs["steps"]):
        parts.advance_to(stop)
    _same_result(whole.result(), expected)
    _same_result(parts.result(), expected)
    _same_snapshot(whole.snapshot(), parts.snapshot())
    snap = whole.snapshot()
    assert set(snap) == COUNTS_STATE
    assert snap["input_counts"].dtype == np.int64
    np.testing.assert_array_equal(snap["input_counts"][: kicks.shape[0]], kicks)
    assert not snap["input_counts"][kicks.shape[0] :].any()
    assert whole.input_encoding == "counts"
    with pytest.raises(AttributeError):
        whole.input_encoding = "kick_equivalent"


def _network():
    return sparse.csc_matrix(
        np.array([[0, 0, 0], [200, 0, 0], [0, 40, 0]], dtype=np.float32)
    )


def _drive():
    light = np.linspace(0.0, 1.0, STEPS)
    return (np.float64(1.7) * light).astype(np.float32).reshape(-1, 1)


def _case(mode):
    p = sim.Params()
    graded = membrane = None
    if mode == "graded":
        graded = sim.Graded(idx=np.array([0]), v_lo=-55.0, span=15.0, rate_hz=500.0)
    else:
        membrane = sim.Membrane(
            idx=np.array([1]),
            tau_m=np.array([9.0]),
            tau_syn=np.array([3.0]),
            v_rest=np.array([-58.0]),
            v_th=np.array([-49.0]),
        )
    return p, graded, membrane


def _kick_runtime(W, p, drive, graded, membrane, *, empty=False):
    kicks = np.zeros((0, 1), np.float32) if empty else drive
    return CpuRuntime(
        W,
        np.array([0]),
        steps=STEPS,
        kicks=kicks,
        input_encoding="kick_equivalent",
        p=p,
        per_bin=1,
        trace=np.arange(3),
        graded=graded,
        membrane=membrane,
    )


def _schedule(rt, drive, stops=STOPS):
    cursor = 0
    for stop in stops:
        rt.schedule_inputs(drive[cursor:stop])
        rt.advance_to(stop)
        cursor = stop


def _oracle(W, p, drive, graded, membrane):
    return sim.run(
        W,
        np.array([0]),
        duration_ms=STEPS * p.dt,
        kicks=drive,
        p=p,
        bin_ms=p.dt,
        trace=np.arange(3),
        graded=graded,
        membrane=membrane,
    )


@pytest.mark.parametrize("mode", ["graded", "membrane"])
def test_kick_equivalent_matches_sim_run_bit_for_bit(mode):
    """One bin per step, so a graded neuron's `graded_v` is its voltage."""
    W, drive = _network(), _drive()
    p, graded, membrane = _case(mode)
    expected = _oracle(W, p, drive, graded, membrane)
    assert expected.counts.sum() > 0
    whole = _kick_runtime(W, p, drive, graded, membrane)
    whole.advance_to(STEPS)
    parts = _kick_runtime(W, p, drive, graded, membrane, empty=True)
    _schedule(parts, drive)
    for runtime in (whole, parts):
        _same_result(runtime.result(), expected)
        assert runtime.input_encoding == "kick_equivalent"
    _same_snapshot(whole.snapshot(), parts.snapshot())
    stored = whole.snapshot()["input_drive"]
    assert stored.dtype == np.float64
    assert stored.tobytes() == drive.astype(np.float64).tobytes()
    assert "input_counts" not in whole.snapshot()
    if graded is not None:
        assert np.ptp(expected.graded_v) > 0
        np.testing.assert_array_equal(
            whole.snapshot()["v"][graded.idx].astype(np.float64),
            expected.graded_v[-1],
        )
        assert {"graded_ring", "graded_vsum", "input_drive"} <= set(whole.snapshot())
    else:
        assert expected.graded_v is None
        assert "graded_vsum" not in whole.snapshot()


@pytest.mark.parametrize("mode", ["graded", "membrane"])
def test_kick_equivalent_checkpoint_restores_bit_identically(tmp_path, mode):
    W, drive = _network(), _drive()
    p, graded, membrane = _case(mode)
    expected = _oracle(W, p, drive, graded, membrane)
    live = _kick_runtime(W, p, drive, graded, membrane, empty=True)
    resumed = None
    cursor = 0
    path = tmp_path / "drive.npz"
    for stop in STOPS:
        block = drive[cursor:stop]
        live.schedule_inputs(block)
        live.advance_to(stop)
        if resumed is not None:
            resumed.schedule_inputs(block)
            resumed.advance_to(stop)
        cursor = stop
        if stop != 80:
            continue
        live.checkpoint(path)
        with np.load(path, allow_pickle=False) as document:
            meta = json.loads(str(document["metadata"]))
            assert meta["input_encoding"] == "kick_equivalent"
            assert "input_drive" in document.files
            assert "input_counts" not in document.files
        resumed = _kick_runtime(W, p, drive, graded, membrane, empty=True)
        resumed.restore(path)
        _same_snapshot(live.snapshot(), resumed.snapshot())
    assert resumed is not None
    _same_snapshot(live.snapshot(), resumed.snapshot())
    _same_result(live.result(), expected)
    _same_result(resumed.result(), expected)
    direct = _kick_runtime(W, p, drive, graded, membrane)
    direct.advance_to(STEPS)
    _same_snapshot(live.snapshot(), direct.snapshot())


def test_input_encoding_refusals(tmp_path):
    W = _network()
    p = sim.Params()
    base = {"steps": 20, "per_bin": 10, "p": p}
    zeros_i = np.zeros((4, 1), np.int64)
    zeros_f = np.zeros((4, 1), np.float32)
    with pytest.raises(TypeError):
        CpuRuntime(W, np.array([0]), kicks=zeros_i, **base)
    for bad in ("sparse", "", "counts ", 1, None):
        with pytest.raises(ValueError, match="input_encoding"):
            CpuRuntime(W, np.array([0]), kicks=zeros_i, input_encoding=bad, **base)
    with pytest.raises(ValueError, match="integer counts"):
        CpuRuntime(W, np.array([0]), kicks=zeros_f, input_encoding="counts", **base)
    for kicks in (
        zeros_i,
        np.zeros((4, 1), np.float64),
        np.array([[1.0]], dtype=float),
    ):
        with pytest.raises(ValueError, match="float32"):
            CpuRuntime(
                W,
                np.array([0]),
                kicks=kicks,
                input_encoding="kick_equivalent",
                **base,
            )
    for bad in (np.nan, np.inf, -np.inf, -0.25):
        kicks = zeros_f.copy()
        kicks[0, 0] = bad
        with pytest.raises(ValueError, match="finite"):
            CpuRuntime(
                W,
                np.array([0]),
                kicks=kicks,
                input_encoding="kick_equivalent",
                **base,
            )
    counts = CpuRuntime(
        W,
        np.array([0]),
        kicks=np.zeros((0, 1), np.int64),
        input_encoding="counts",
        **base,
    )
    drive = CpuRuntime(
        W,
        np.array([0]),
        kicks=np.zeros((0, 1), np.float32),
        input_encoding="kick_equivalent",
        **base,
    )
    with pytest.raises(ValueError, match="integer counts"):
        counts.schedule_inputs(zeros_f)
    with pytest.raises(ValueError, match="float32"):
        drive.schedule_inputs(zeros_i)
    with pytest.raises(ValueError, match="float32"):
        drive.schedule_inputs(np.zeros((1, 1), np.float64))
    for bad in (np.nan, np.inf, -np.inf, -1.0):
        block = np.zeros((1, 1), np.float32)
        block[0, 0] = bad
        with pytest.raises(ValueError, match="finite"):
            drive.schedule_inputs(block)
    path = tmp_path / "counts.npz"
    counts.checkpoint(path)
    before = drive.snapshot()
    with pytest.raises(ValueError, match="encoding mismatch"):
        drive.restore(path)
    assert drive.step == 0
    _same_snapshot(drive.snapshot(), before)
    with np.load(path, allow_pickle=False) as document:
        saved = {name: document[name] for name in document.files}
    meta = json.loads(str(saved["metadata"]))
    del meta["input_encoding"]
    saved["metadata"] = np.array(json.dumps(meta))
    np.savez(path, **saved)
    with pytest.raises(ValueError, match="no input encoding"):
        counts.restore(path)
    assert counts.step == 0
    from flymsg.native import NativeCapabilityError, export_batch, export_fixture

    with pytest.raises(NativeCapabilityError, match="kick_equivalent"):
        export_fixture(drive, tmp_path / "fixture.bin")
    with pytest.raises(NativeCapabilityError, match="kick_equivalent"):
        export_batch([drive], tmp_path / "base.bin", tmp_path / "batch.bin")
