import ast
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from flymsg import eye, optics, pose
from flymsg.embodiment import ContractError
from flymsg.pose import IDENTITY, BodyState, EyeMount, Pose, Quat, Registration

ACCEPTANCE = 8.23  # deg, as T4/T5 (Gonzalez-Bellido et al. 2011)
SHA = "b" * 64
# test-only registration: no measured eyemap -> body rotation exists (#84)
REG = Registration(Pose("body", "eyemap", (0.0, 0.0, 0.0), IDENTITY), "test identity")
LOOK_LEFT = Quat.from_matrix([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
LEFT = EyeMount("L", Pose("body", "eye/L", (0.0, 3e-4, 0.0), LOOK_LEFT), "synthetic")
MOUNTS = (LEFT, pose.mirror(LEFT))


def table(rows):
    """Columns given as (side, azimuth, elevation) in eye.columns' convention."""
    return optics.Columns.from_frame(
        pd.DataFrame(
            {
                "side": [r[0] for r in rows],
                "p": range(len(rows)),
                "q": [0] * len(rows),
                "azimuth_deg": [r[1] for r in rows],
                "elevation_deg": [r[2] for r in rows],
            }
        ),
        SHA,
    )


COLS = table([("L", -90.0, 0.0), ("R", 90.0, 0.0), ("L", 0.0, 0.0), ("R", 0.0, 0.0)])


def still(t=0, q=IDENTITY, omega=(0.0, 0.0, 0.0), v=(0.0, 0.0, 0.0)):
    return BodyState(t, Pose("world", "body", (0.0, 0.0, 0.0), q), v, omega)


def run(spheres, state=None, cols=COLS):
    return optics.sample(cols, REG, MOUNTS, state or still(), spheres, ACCEPTANCE)


def test_direction_convention_matches_eye_columns():
    # azimuth grows to the fly's right, eyemap +y is the left
    c = table([("R", 90.0, 0.0), ("L", -90.0, 0.0), ("R", 0.0, 90.0)])
    assert np.allclose(c.direction, [[0, -1, 0], [0, 1, 0], [0, 0, 1]], atol=1e-15)


def test_fixed_pose_is_deterministic_and_left_target_one_sided():
    s = (optics.Sphere("left", (0.0, 0.05, 0.0), 0.02),)  # 24 deg radius
    a, b = run(s), run(s)
    assert a.digest() == b.digest()
    assert a.angle_deg[0, 0] < 1e-6 and a.angle_deg[0, 1] > 179  # left column on it
    assert a.coverage[0, 0] > 0.99 and a.coverage[0, 1] < 1e-12
    assert a.nearest.tolist() == [0, -1, -1, -1]


def test_approaching_and_receding_sphere_match_the_looming_formula():
    # a sphere on the left axis at constant speed: rho = asin(r / d); drho/dt analytic
    r, v = 0.005, 0.25
    approach = optics.Sphere("loom", (0.0, 0.1, 0.0), r, (0.0, -v, 0.0))
    recede = optics.Sphere("loom", (0.0, 0.1, 0.0), r, (0.0, v, 0.0))
    for t in (0, 100_000, 300_000):
        a = run((approach,), still(t))
        d = 0.1 - v * t * 1e-6 - 3e-4
        assert math.isclose(
            a.radius_deg[0, 0], math.degrees(math.asin(r / d)), rel_tol=1e-12
        )
        rate = math.degrees(r * v / (d * math.sqrt(d * d - r * r)))
        assert math.isclose(a.radius_rate_deg_s[0, 0], rate, rel_tol=1e-9)
        b = run((recede,), still(t))
        assert b.radius_rate_deg_s[0, 0] < 0
    with pytest.raises(ContractError, match="inside"):
        run((approach,), still(400_000 - 15_000))  # 1.7 mm away, inside r + eye offset


def test_rotational_optic_flow_is_minus_the_body_rotation():
    # a fly yawing left at 1 rad/s sees a far target drift right at 1 rad/s
    far = optics.Sphere("far", (100.0, 0.0, 0.0), 1.0)
    s = run((far,), still(omega=(0.0, 0.0, 1.0)))
    w = s.angular_velocity_deg_s[0, 2]
    assert np.allclose(w, (0.0, 0.0, -math.degrees(1.0)), rtol=1e-5, atol=1e-6)


def test_bilateral_mirror_symmetry():
    a = run((optics.Sphere("s", (0.02, 0.03, 0.01), 0.004),))
    b = run((optics.Sphere("s", (0.02, -0.03, 0.01), 0.004),))
    assert np.allclose(a.coverage[0, [0, 2]], b.coverage[0, [1, 3]], atol=1e-12)
    assert np.allclose(a.angle_deg[0, [0, 2]], b.angle_deg[0, [1, 3]], atol=1e-9)


def test_body_rotation_moves_the_view():
    target = (optics.Sphere("ahead", (0.05, 0.0, 0.0), 0.02),)
    h = math.radians(90) / 2
    turned = still(q=Quat.of((math.cos(h), 0.0, 0.0, math.sin(h))))  # facing +y
    assert run(target).coverage[0, 2] > 0.99
    assert (
        run(target, turned).coverage[0, 1] > 0.99
    )  # now on the right eye's lateral column


def test_out_of_view_occlusion_and_missing_lenses():
    cols = table([("L", -90.0, 0.0), ("L", float("nan"), float("nan"))])
    behind = optics.Sphere("behind", (-0.05, 0.0, -0.05), 0.002)
    out = run((behind,), cols=cols)
    assert out.coverage[0, 0] < 1e-12 and out.nearest[0] == -1
    assert (
        not out.has_direction[1]
        and np.isnan(out.coverage[0, 1])
        and out.nearest[1] == -1
    )
    near = optics.Sphere("near", (0.0, 0.02, 0.0), 0.003)
    far = optics.Sphere("far", (0.0, 0.08, 0.0), 0.02)
    both = run((far, near), cols=cols)
    assert both.nearest[0] == 1  # the near sphere hides the far one on the axis
    assert (
        both.coverage[1, 0] > 0.95 and both.coverage[0, 0] > 0.99
    )  # shares as if alone


def test_timestamps_and_contract_inputs():
    s = (optics.Sphere("s", (0.0, 0.05, 0.0), 0.005, (0.0, -0.1, 0.0)),)
    assert run(s, still(1234)).time_us == 1234
    assert run(s, still(1000)).digest() != run(s, still(2000)).digest()
    with pytest.raises(ContractError):
        optics.sample(COLS, REG, (LEFT,), still(), s, ACCEPTANCE)
    with pytest.raises(ContractError):
        optics.sample(COLS, None, MOUNTS, still(), s, ACCEPTANCE)
    with pytest.raises(ContractError):
        optics.sample(COLS, REG, MOUNTS, still(), s * 2, ACCEPTANCE)
    with pytest.raises(ContractError):
        optics.Sphere("s", (0.0, 0.0, 0.0), 0.0)
    with pytest.raises(ContractError):
        optics.Columns.from_frame(pd.DataFrame({"side": ["X"]}), SHA)


def test_rice_coverage_within_its_error_bound_and_eye_agrees():
    sigma = ACCEPTANCE / optics.FWHM
    worst = 0.0
    for rho in (0.5, 2, 5, 10, 20, 45, 89):
        for a in np.arange(0, 180.1, 1.0):
            exact = optics.coverage_exact(a, rho, ACCEPTANCE)
            worst = max(worst, abs(exact - stats.rice.cdf(rho / sigma, a / sigma)))
    assert worst < 0.008  # docs/eye.md: planar Rice vs the spherical profile
    assert math.isclose(optics.coverage_exact(0, 90, ACCEPTANCE), 1.0, abs_tol=1e-12)
    cols = pd.DataFrame({"azimuth_deg": [10.0], "elevation_deg": [0.0]})
    assert math.isclose(
        eye.disk_coverage(cols, 0.0, 0.0, 5.0, ACCEPTANCE)[0],
        stats.rice.cdf(5.0 / sigma, 10.0 / sigma),
    )


def test_no_viewer_or_rendering_import():
    tree = ast.parse(Path(optics.__file__).read_text())
    names = {
        a.name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "")
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in n.names
    }
    imported = {n for n in names} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names
    }
    assert not imported & {"viz", "mujoco", "flygym", "photoreceptor_kicks"}
