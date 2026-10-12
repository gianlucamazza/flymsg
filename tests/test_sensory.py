import math
from itertools import pairwise

import pytest

from flymsg.sensory import LoomingStimulus, encode_looming


def test_looming_is_monotone_and_deterministic():
    stim = LoomingStimulus(0.01, 0.5, 0.1, 100_000, 1000)
    a = encode_looming(stim)
    assert a == encode_looming(stim)
    assert len(a) == 100
    assert a[0].time_us == 0
    assert a[-1].time_us == 99_000
    assert all(x.angular_size_rad < y.angular_size_rad for x, y in pairwise(a))
    assert all(x.rate_hz < y.rate_hz for x, y in pairwise(a))
    assert all(math.isfinite(x.rate_hz) for x in a)


def test_rate_clamp_and_zero_gain():
    stim = LoomingStimulus(0.01, 0.5, 0.1, 10_000)
    constant = encode_looming(stim, baseline_hz=5, gain_hz_per_rad_s=0)
    capped = encode_looming(stim, baseline_hz=5, max_rate_hz=6)
    assert all(x.rate_hz == 5 for x in constant)
    assert all(x.rate_hz <= 6 for x in capped)


@pytest.mark.parametrize(
    "args",
    [
        (0, 0.5, 0.1, 1000),
        (0.01, 0.01, 0.1, 1000),
        (0.01, 0.5, -1, 1000),
        (0.01, 0.5, 1, 1_000_000),
        (0.01, 0.5, 0.1, 1500),
    ],
)
def test_invalid_stimulus_rejected(args):
    with pytest.raises(ValueError):
        LoomingStimulus(*args)


def test_invalid_rate_rejected():
    stim = LoomingStimulus(0.01, 0.5, 0.1, 1000)
    with pytest.raises(ValueError):
        encode_looming(stim, baseline_hz=float("nan"))
