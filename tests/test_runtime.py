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
    runtime = CpuRuntime(W, np.array([0]), **kwargs)
    for end in [1, 19, 23, 217]:
        runtime.advance_to(end)
    runtime.checkpoint(tmp_path / "state.npz")
    resumed = CpuRuntime(W, np.array([0]), **kwargs)
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
    runtime = CpuRuntime(W, np.array([0]), **kwargs)
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
    runtime = CpuRuntime(W, np.array([0]), **kwargs)
    runtime.advance_to(217)
    path = tmp_path / "state.npz"
    runtime.checkpoint(path)
    other = CpuRuntime(
        W, np.array([0]), **{**kwargs, "p": replace(kwargs["p"], w_syn=0.5)}
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
        CpuRuntime(W, np.array([0]), **{**kwargs, **edit})


def test_online_inputs_survive_checkpoint_and_match_explicit_oracle(tmp_path):
    W, _, kwargs = fixture()
    kwargs["kicks"] = np.zeros((0, 1), dtype=np.int64)
    runtime = CpuRuntime(W, np.array([0]), **kwargs)
    runtime.advance_to(217)
    block = np.full((50, 1), 2, dtype=np.int64)
    runtime.schedule_inputs(block)
    path = tmp_path / "online.npz"
    runtime.checkpoint(path)
    resumed = CpuRuntime(W, np.array([0]), **kwargs)
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
    runtime = CpuRuntime(W, np.array([0]), **kwargs)
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
        runtime = CpuRuntime(W, np.array([0]), **kwargs)
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
    runtime = CpuRuntime(W, np.array([0]), **kwargs)
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
    old = CpuRuntime(W, np.array([0]), **kwargs)
    old.advance_to(217)
    path = tmp_path / "state.npz"
    old.checkpoint(path)
    monkeypatch.setattr(module, "SEMANTICS", "flymsg.lif/other-numerical-mode")
    changed = CpuRuntime(W, np.array([0]), **kwargs)
    before = changed.snapshot()
    with pytest.raises(ValueError, match="incompatible"):
        changed.restore(path)
    assert changed.step == 0
    for name, value in before.items():
        assert changed.snapshot()[name].tobytes() == value.tobytes()
