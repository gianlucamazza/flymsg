import numpy as np
import pytest
from scipy import sparse

from flymsg import sim
from flymsg.runtime import CpuRuntime
from flymsg.sensory import LoomingStimulus, encode_looming
from flymsg.sensory_runtime import schedule_sensory_drive

RATE = {"gain_hz_per_rad_s": 100.0, "max_rate_hz": 200.0}  # engineered test values


def _runtime(steps=100):
    return CpuRuntime(
        sparse.csc_matrix((2, 2)),
        np.array([0]),
        steps=steps,
        kicks=np.zeros((0, 1), dtype=np.int64),
        per_bin=10,
    )


def test_sensory_bridge_replays_deterministically():
    samples = encode_looming(LoomingStimulus(0.01, 0.5, 0.1, 10_000), **RATE)

    def run():
        runtime = _runtime()
        schedule_sensory_drive(runtime, samples, sample_period_us=1000, seed=4)
        runtime.advance_to(100)
        return runtime.snapshot()["input_counts"], runtime.result().counts

    a, counts_a = run()
    b, counts_b = run()
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(counts_a, counts_b)


def test_tick_and_width_come_from_the_runtime():
    runtime = _runtime()
    assert runtime.tick_us == round(sim.Params.dt * 1000) and runtime.n_inputs == 1


def test_bridge_rejects_wrong_grid_without_advancing():
    samples = encode_looming(LoomingStimulus(0.01, 0.5, 0.1, 10_000), **RATE)
    runtime = _runtime()
    with pytest.raises(ValueError):
        schedule_sensory_drive(runtime, samples, sample_period_us=250, seed=4)
    with pytest.raises(ValueError):
        schedule_sensory_drive(runtime, samples[1:], sample_period_us=1000, seed=4)
    assert runtime.step == 0
    assert not runtime.snapshot()["input_counts"].any()


def test_drive_follows_the_rate():
    # 1000 Hz for 100 ms at 0.1 ms steps: about 100 kicks, well above a 0 Hz drive
    from flymsg.sensory import SensoryDrive

    hot = tuple(SensoryDrive(t, 0.0, 0.0, 1000.0) for t in range(0, 100_000, 1000))
    cold = tuple(SensoryDrive(t, 0.0, 0.0, 0.0) for t in range(0, 100_000, 1000))
    a, b = _runtime(1000), _runtime(1000)
    schedule_sensory_drive(a, hot, sample_period_us=1000, seed=1)
    schedule_sensory_drive(b, cold, sample_period_us=1000, seed=1)
    assert 70 < a.snapshot()["input_counts"].sum() < 130
    assert b.snapshot()["input_counts"].sum() == 0
