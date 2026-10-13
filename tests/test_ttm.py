"""TTM force from TTMn spikes follows the measured twitch."""

import numpy as np
import pytest

from flymsg import ttm


def test_a_twitch_peaks_at_the_measured_force_and_time():
    t = np.arange(0.0, 40.0, 0.01)
    f = ttm.twitch(t)
    assert f.max() == pytest.approx(101e-6, rel=1e-4)
    assert t[f.argmax()] == pytest.approx(0.85 + 8.2, abs=0.01)
    assert f[t < 0.85].max() == 0.0


def test_spikes_sum_linearly():
    t = np.arange(0.0, 60.0, 0.1)
    one = ttm.force([0.0], t)
    two = ttm.force([0.0, 20.0], t)
    np.testing.assert_allclose(two, one + ttm.twitch(t - 20.0))
