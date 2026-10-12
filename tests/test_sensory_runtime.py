import numpy as np
import pytest
from scipy import sparse

from flymsg.runtime import CpuRuntime
from flymsg.sensory import LoomingStimulus, encode_looming
from flymsg.sensory_runtime import schedule_sensory_drive


def test_sensory_bridge_replays_deterministically():
    samples = encode_looming(LoomingStimulus(0.01, 0.5, 0.1, 10_000))
    def run():
        runtime = CpuRuntime(
            sparse.csc_matrix((2, 2)), np.array([0]),
            steps=100, kicks=np.zeros((0, 1), dtype=np.int64), per_bin=10,
        )
        schedule_sensory_drive(runtime, samples, neural_dt_us=100,
                              sample_period_us=1000, n_stim=1, seed=4)
        runtime.advance_to(100)
        return runtime.snapshot()["input_counts"], runtime.result().counts
    a, counts_a = run()
    b, counts_b = run()
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(counts_a, counts_b)


def test_bridge_rejects_wrong_grid_without_advancing():
    samples = encode_looming(LoomingStimulus(0.01, 0.5, 0.1, 10_000))
    runtime = CpuRuntime(
        sparse.csc_matrix((2, 2)), np.array([0]),
        steps=100, kicks=np.zeros((0, 1), dtype=np.int64), per_bin=10,
    )
    with pytest.raises(ValueError):
        schedule_sensory_drive(runtime, samples, neural_dt_us=300,
                              sample_period_us=1000, n_stim=1, seed=4)
    assert runtime.step == 0
