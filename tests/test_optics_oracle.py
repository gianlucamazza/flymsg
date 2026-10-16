"""Independent 3D ray oracle: integrate a spherical Gaussian with Sobol rays.

Does not call the cap quadrature, angular transforms or Rice CDF to compute the
reference. Rays hit by closest approach (cross product), not the implementation's
quadratic intersection. The acceptance profile is an engineering assumption.
"""

import math

import numpy as np
import pytest
from scipy import stats

from flymsg import optics


@pytest.fixture(scope="module")
def rays():
    uv = stats.qmc.Sobol(2, scramble=True, seed=179).random_base2(18)
    sigma = math.radians(8.23) / (2 * math.sqrt(2 * math.log(2)))
    alpha = sigma * np.sqrt(-2 * np.log(uv[:, 0]))
    phi = 2 * math.pi * uv[:, 1]
    directions = np.column_stack(
        (np.cos(alpha), np.sin(alpha) * np.cos(phi), np.sin(alpha) * np.sin(phi))
    )
    weights = np.sinc(
        alpha / math.pi
    )  # sin(alpha)/alpha: planar -> solid-angle measure
    return directions, weights


@pytest.mark.parametrize(
    "angle,radius",
    [
        (0, 0.5),
        (0, 5),
        (5, 5),
        (10, 5),
        (20, 20),
        (45, 45),
        (85, 89),
        (95, 89),
        (175, 89),
    ],
)
def test_coverage_against_independent_solid_angle_rays(rays, angle, radius):
    directions, weights = rays
    a = math.radians(angle)
    centre = np.array([math.cos(a), math.sin(a), 0.0])
    cross = np.cross(directions, centre)
    hits = ((cross * cross).sum(axis=1) < math.sin(math.radians(radius)) ** 2) & (
        (directions * centre).sum(axis=1) > 0
    )
    oracle = weights[hits].sum() / weights.sum()
    spherical = optics.coverage_exact(angle, radius, 8.23)
    planar = stats.rice.cdf(radius / (8.23 / optics.FWHM), angle / (8.23 / optics.FWHM))
    assert abs(spherical - oracle) < 0.0005
    assert abs(planar - oracle) < 0.0085
