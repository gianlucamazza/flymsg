"""The NeuroMechFly body jumps when its TTMs twitch, and not otherwise (MuJoCo, CPU)."""

import numpy as np
from scipy import sparse

from flymsg import jump3d, sim

CFG = jump3d.BodyConfig(settle_ms=50.0)


def test_no_spike_no_takeoff():
    out = jump3d.jump({}, 20.0, CFG)
    assert out["takeoff_ms"] is None and out["range_mm"] == 0.0


def test_ttm_twitches_lift_the_body_off_the_ground():
    out = jump3d.jump({"lm": [0.0, 5.0], "rm": [0.0, 5.0]}, 30.0, CFG)
    assert out["takeoff_ms"] is not None and 0 < out["takeoff_ms"] < 30
    assert out["velocity_m_s"][2] > 0 and out["thorax_rise_mm"] > 0


def _net():
    # 0 stimulus -> 1 (left TTMn) and 2 (right TTMn), strong enough to fire them
    W = sparse.csc_matrix(
        (np.full(2, 200.0, dtype=np.float32), ([1, 2], [0, 0])), shape=(3, 3)
    )
    kicks = sim.poisson_kicks(3, 400.0, 0.1, 1000, 1)
    return W, np.array([0]), {"lm": 1, "rm": 2}, kicks


def test_closed_loop_matches_open_loop_until_the_cut_and_stops_after():
    W, stim, motor, kicks = _net()
    out = jump3d.closed_loop(W, stim, motor, kicks, 100.0, CFG)
    assert out["takeoff_ms"] is not None and out["input_cut_ms"] is not None
    ref = sim.run(W, stim, duration_ms=100.0, kicks=kicks, trace=np.array([1, 2]))
    cut = out["input_cut_ms"]
    for i, side in enumerate(("lm", "rm")):
        open_loop = np.flatnonzero(ref.traced[:, i]) * 0.1
        before = [t for t in out["spikes_ms"][side] if t < cut]
        np.testing.assert_allclose(before, open_loop[open_loop < cut])
        # nothing drives the motor neurons once the input is gone and the last kick has
        # crossed the synaptic delay
        assert not [t for t in out["spikes_ms"][side] if t > cut + 5.0]
