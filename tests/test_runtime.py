import hashlib
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


_N = 12
_STEPS = 200
_PER_BIN = 10
_STOPS = (1, 2, 5, 7, 19, 20, 64, 65, 100, 137, 138, 199, _STEPS)
_MID = 100
_STIM = np.array([0, 5])
_GRADED_IDX = np.array([5, 6])
_SILENCE_IDX = np.array([9])
_GAP_I, _GAP_J = 10, 11
_CHECKPOINT_META = {
    "schema",
    "semantics",
    "identity",
    "step",
    "state_sha256",
    "input_end",
    "input_encoding",
}


def _mixed_membrane(branch):
    """Two membrane classes. Neuron 0 is the scalar reference the kernel uses."""
    if branch == "few":
        return sim.Membrane(
            idx=np.array([3, 4]),
            tau_m=np.array([12.0, 30.0]),
            tau_syn=np.array([2.5, 7.0]),
            v_rest=np.array([-55.0, -48.0]),
            v_th=np.array([-46.0, -40.0]),
        )
    if branch == "most":
        idx = np.array([i for i in range(_N) if i not in (0, _GAP_I, _GAP_J)])
        k = idx.size
        return sim.Membrane(
            idx=idx,
            tau_m=np.full(k, 15.0),
            tau_syn=np.full(k, 3.0),
            v_rest=np.full(k, -60.0),
            v_th=np.full(k, -48.0),
        )
    return sim.Membrane(
        idx=np.array([0, 1]),
        tau_m=np.full(2, 11.0),
        tau_syn=np.full(2, 4.0),
        v_rest=np.full(2, -57.0),
        v_th=np.full(2, -47.0),
    )


def _mixed_case(encoding, branch, solver):
    p = sim.Params()
    pre = np.array([0, 1, 0, 3, 5, 8, 2, 4, 0, 10], dtype=np.int64)
    post = np.array([1, 2, 3, 4, 6, 9, 7, 10, 11, 11], dtype=np.int64)
    count = np.array([120, 80, 100, 60, 40, 70, 30, 50, 90, 40], dtype=np.float64)
    W = sparse.csc_matrix(
        ((count * p.w_syn).astype(np.float32), (post, pre)), shape=(_N, _N)
    )
    if encoding == "counts":
        kicks = sim.poisson_kicks(4, 500.0, p.dt, _STEPS, _STIM.size)
    else:
        kicks = np.linspace(0.0, 1.5, _STEPS * _STIM.size, dtype=np.float32)
        kicks = kicks.reshape(_STEPS, _STIM.size)
    graded = sim.Graded(
        idx=_GRADED_IDX,
        v_lo=np.array([-60.0, -58.0]),
        span=np.array([20.0, 16.0]),
        rate_hz=np.array([80.0, 40.0]),
    )
    gap = sim.Gap(
        i=np.array([_GAP_I]),
        j=np.array([_GAP_J]),
        coupling=np.array([0.2]),
        solver=solver,
    )
    return {
        "W": W,
        "stim": _STIM,
        "p": p,
        "kicks": kicks,
        "encoding": encoding,
        "silence": _SILENCE_IDX,
        "trace": np.array([0, 1, 3, 11]),
        "graded": graded,
        "gap": gap,
        "membrane": _mixed_membrane(branch),
        "branch": branch,
        "solver": solver,
    }


def _mixed_runtime(case):
    return CpuRuntime(
        case["W"],
        case["stim"],
        steps=_STEPS,
        kicks=case["kicks"],
        input_encoding=case["encoding"],
        p=case["p"],
        per_bin=_PER_BIN,
        silence=case["silence"],
        trace=case["trace"],
        graded=case["graded"],
        gap=case["gap"],
        membrane=case["membrane"],
    )


def _mixed_run(case):
    p = case["p"]
    return sim.run(
        case["W"],
        case["stim"],
        duration_ms=_STEPS * p.dt,
        kicks=case["kicks"],
        p=p,
        bin_ms=_PER_BIN * p.dt,
        silence=case["silence"],
        trace=case["trace"],
        graded=case["graded"],
        gap=case["gap"],
        membrane=case["membrane"],
    )


def _expect_classes(case, prep):
    if case["branch"] == "few":
        special = [3, 4]
        assert prep.few and not prep.per_neuron
    elif case["branch"] == "most":
        special = list(range(1, 10))
        assert prep.per_neuron and not prep.few
    else:
        special = list(range(2, _N))
        assert prep.per_neuron and not prep.few
    assert prep.n_special == len(special)
    assert prep.special.tolist() == special
    marked = np.zeros(_N, dtype=np.bool_)
    marked[prep.special] = True
    assert marked.tobytes() == prep.is_special.tobytes()
    em, es, gv, _, rest, threshold, _ = sim.kernel_constants(
        case["membrane"], _N, case["p"]
    )
    scalars = np.array([em[0], es[0], gv[0], rest[0], threshold[0]], dtype=np.float32)
    assert prep.scalars.tobytes() == scalars.tobytes()
    assert prep.saved_v.shape == (prep.n_special,)
    assert prep.saved_v.dtype == np.float32
    assert prep.saved_g.shape == prep.saved_v.shape
    assert prep.saved_g.dtype == np.float32
    if case["solver"] == "taylor":
        assert prep.t_ptr[-1] > 0
        assert prep.t_col.size == prep.t_a.size == prep.t_c.size == prep.t_ptr[-1]
    else:
        assert prep.t_col.size == 0


def _result_bytes(actual, expected):
    _same_result(actual, expected)
    assert actual.counts.tobytes() == expected.counts.tobytes()
    assert actual.first_spike_ms.tobytes() == expected.first_spike_ms.tobytes()
    assert actual.traced.tobytes() == expected.traced.tobytes()
    assert actual.graded_v.tobytes() == expected.graded_v.tobytes()


def _checkpoint_payload(path):
    with np.load(path, allow_pickle=False) as document:
        meta = json.loads(str(document["metadata"]))
        arrays = {
            name: (
                document[name].shape,
                document[name].dtype.str,
                document[name].tobytes(),
            )
            for name in document.files
            if name != "metadata"
        }
    return meta, arrays


@pytest.mark.parametrize("encoding", ["counts", "kick_equivalent"])
@pytest.mark.parametrize("branch", ["few", "most", "anchor"])
@pytest.mark.parametrize("solver", ["dense", "taylor"])
def test_mixed_runtime_matches_one_run_across_chunks_and_restore(
    tmp_path, encoding, branch, solver
):
    """One advance, irregular chunks, and a restored chunk stay byte-identical."""
    case = _mixed_case(encoding, branch, solver)
    expected = _mixed_run(case)
    assert expected.counts.sum() > 0
    assert expected.counts[:, _SILENCE_IDX].sum() == 0
    assert expected.counts[:, _GRADED_IDX].sum() == 0
    assert expected.graded_v is not None
    assert np.isfinite(expected.graded_v).all()

    whole = _mixed_runtime(case)
    _expect_classes(case, whole._prepared)
    whole.advance_to(_STEPS)

    parts = _mixed_runtime(case)
    for stop in _STOPS:
        parts.advance_to(stop)

    live = _mixed_runtime(case)
    resumed = None
    mid_path = tmp_path / "mid.npz"
    for stop in _STOPS:
        live.advance_to(stop)
        if stop != _MID:
            if resumed is not None:
                resumed.advance_to(stop)
            continue
        live.checkpoint(mid_path)
        meta, arrays = _checkpoint_payload(mid_path)
        assert set(meta) == _CHECKPOINT_META
        assert meta["step"] == _MID
        assert meta["identity"] == live._identity
        assert meta["input_encoding"] == encoding
        assert set(arrays) == set(live.snapshot())
        for name, value in live.snapshot().items():
            shape, dtype, raw = arrays[name]
            assert shape == value.shape
            assert dtype == value.dtype.str
            assert raw == value.tobytes()
        resumed = _mixed_runtime(case)
        resumed.restore(mid_path)
        _same_snapshot(live.snapshot(), resumed.snapshot())
    assert resumed is not None

    for runtime in (whole, parts, live, resumed):
        _result_bytes(runtime.result(), expected)
    for runtime in (parts, live, resumed):
        _same_snapshot(whole.snapshot(), runtime.snapshot())
    assert "gap_pulse" in whole.snapshot()

    payloads = []
    for name, runtime in (("whole", whole), ("parts", parts), ("resumed", resumed)):
        path = tmp_path / f"{name}.npz"
        runtime.checkpoint(path)
        payloads.append(_checkpoint_payload(path))
    for meta, arrays in payloads:
        assert set(meta) == _CHECKPOINT_META
        assert meta == payloads[0][0]
        assert arrays == payloads[0][1]


def test_prepare_kernel_is_not_called_from_advance_to(monkeypatch):
    calls = {"n": 0}
    real = sim.prepare_kernel

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(sim, "prepare_kernel", counting)
    case = _mixed_case("counts", "few", "taylor")
    runtime = _mixed_runtime(case)
    assert calls["n"] == 1
    for stop in _STOPS:
        runtime.advance_to(stop)
    runtime.advance_to(runtime.step)
    assert runtime.step == _STEPS
    assert calls["n"] == 1
    _mixed_run(case)
    assert calls["n"] == 2
    again = _mixed_runtime(case)
    assert calls["n"] == 3
    again.advance_to(_STEPS)
    assert calls["n"] == 3


# State and sim.run digests of each mixed case, produced by the code before the
# kernel preparation moved out of `_advance` (main cb945e1): an oracle that the new
# code cannot share a mistake with.
_GOLDEN = {
    "counts-few-dense": (
        "f058ad8869cce42456edb877187dcf3a148bac80f23b19a2645958920c0ea082",
        "a5fcb7e5b234ef629243692e584e94b288e3dabfcf8bb5a3158df6e10e6d3e2b",
    ),
    "counts-few-taylor": (
        "f058ad8869cce42456edb877187dcf3a148bac80f23b19a2645958920c0ea082",
        "a5fcb7e5b234ef629243692e584e94b288e3dabfcf8bb5a3158df6e10e6d3e2b",
    ),
    "counts-most-dense": (
        "60b7804dc584e425816db17dd783cce364c0526bc23d53d06f6e36d930c3da22",
        "f2783d46a38ec975b15a9088ad7a1364432f045d330b75cbea0426351a999380",
    ),
    "counts-most-taylor": (
        "60b7804dc584e425816db17dd783cce364c0526bc23d53d06f6e36d930c3da22",
        "f2783d46a38ec975b15a9088ad7a1364432f045d330b75cbea0426351a999380",
    ),
    "counts-anchor-dense": (
        "caaf08eab7190e681b11c1489d3145d7394c2ecfc8f2b4d7fb61330cf723a246",
        "31d773e30d3ee45b927eec7d028640f25f38820c59e25f49f91f0e8dd3e487a4",
    ),
    "counts-anchor-taylor": (
        "caaf08eab7190e681b11c1489d3145d7394c2ecfc8f2b4d7fb61330cf723a246",
        "31d773e30d3ee45b927eec7d028640f25f38820c59e25f49f91f0e8dd3e487a4",
    ),
    "kick_equivalent-few-dense": (
        "1c56aab9751a7d3eb5682a92b40fc868599072117e3a34ece3a17423d9c00e45",
        "545460028119bd448f269ed087e539f1b92656a319e520a616b773f3eed0bc6c",
    ),
    "kick_equivalent-few-taylor": (
        "1c56aab9751a7d3eb5682a92b40fc868599072117e3a34ece3a17423d9c00e45",
        "545460028119bd448f269ed087e539f1b92656a319e520a616b773f3eed0bc6c",
    ),
    "kick_equivalent-most-dense": (
        "f7f6e309d566ccdb268137c5d110a45279aeb55342fa7d6c85db14155fb8c282",
        "03a148a457774a3c1c4fcdc0522bc701b56fcb67729974d94facf3b2b0b7a463",
    ),
    "kick_equivalent-most-taylor": (
        "f7f6e309d566ccdb268137c5d110a45279aeb55342fa7d6c85db14155fb8c282",
        "03a148a457774a3c1c4fcdc0522bc701b56fcb67729974d94facf3b2b0b7a463",
    ),
    "kick_equivalent-anchor-dense": (
        "7487111c8a3e98af76cb8ecfc5289c18a44913f1b4be1a4b016f1c4edd82bf80",
        "664054b90a4c753e07e5caf111b81cb1cb70111bfa1aa8cbb24d6c3e1e263a71",
    ),
    "kick_equivalent-anchor-taylor": (
        "7487111c8a3e98af76cb8ecfc5289c18a44913f1b4be1a4b016f1c4edd82bf80",
        "664054b90a4c753e07e5caf111b81cb1cb70111bfa1aa8cbb24d6c3e1e263a71",
    ),
}


def _digest(arrays):
    h = hashlib.sha256()
    for name in sorted(arrays):
        a = np.ascontiguousarray(arrays[name])
        h.update(name.encode())
        h.update(a.dtype.str.encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


@pytest.mark.parametrize("encoding", ["counts", "kick_equivalent"])
@pytest.mark.parametrize("branch", ["few", "most", "anchor"])
@pytest.mark.parametrize("solver", ["dense", "taylor"])
def test_mixed_cases_equal_the_code_before_the_preparation_moved(
    encoding, branch, solver
):
    case = _mixed_case(encoding, branch, solver)
    rt = _mixed_runtime(case)
    rt.advance_to(_STEPS)
    result = _mixed_run(case)
    arrays = {k: v for k, v in vars(result).items() if isinstance(v, np.ndarray)}
    expected = _GOLDEN[f"{encoding}-{branch}-{solver}"]
    assert (_digest(rt.snapshot()), _digest(arrays)) == expected
