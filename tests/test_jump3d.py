"""The NeuroMechFly body jumps when its TTMs twitch, and not otherwise (MuJoCo, CPU)."""

from flymsg import jump3d

CFG = jump3d.BodyConfig(settle_ms=50.0)


def test_no_spike_no_takeoff():
    out = jump3d.jump({}, 20.0, CFG)
    assert out["takeoff_ms"] is None and out["range_mm"] == 0.0


def test_ttm_twitches_lift_the_body_off_the_ground():
    out = jump3d.jump({"lm": [0.0, 5.0], "rm": [0.0, 5.0]}, 30.0, CFG)
    assert out["takeoff_ms"] is not None and 0 < out["takeoff_ms"] < 30
    assert out["velocity_m_s"][2] > 0 and out["thorax_rise_mm"] > 0
