import ast
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from flymsg import closedloop, eye, optics, pose
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
    parts = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                parts |= set(a.name.split("."))
        elif isinstance(n, ast.ImportFrom):
            parts |= set((n.module or "").split("."))
            parts |= {a.name for a in n.names}
    assert "pose" in parts  # the walk sees dotted and from-imports
    assert not parts & {"viz", "mujoco", "flygym", "photoreceptor_kicks", "eye"}


def pitch(deg):
    h = math.radians(deg) / 2
    return Quat.of((math.cos(h), 0.0, math.sin(h), 0.0))


def test_registration_keeps_the_sagittal_plane_and_mirrors_both_eyes():
    cols = table([("R", 70.0, 20.0), ("L", -70.0, 20.0)])
    reg = Registration(
        Pose("body", "eyemap", (1e-4, 0.0, 0.0), pitch(15)), "test pitch"
    )
    out = optics.sample(
        cols,
        reg,
        MOUNTS,
        still(),
        (optics.Sphere("s", (0.0, 0.0, 0.05), 0.002),),
        ACCEPTANCE,
    )
    r_axis = np.asarray(reg.pose.orientation.matrix()) @ cols.direction[0]
    l_axis = np.asarray(reg.pose.orientation.matrix()) @ cols.direction[1]
    assert np.allclose(l_axis, r_axis * [1, -1, 1], atol=1e-15)
    assert math.isclose(out.angle_deg[0, 0], out.angle_deg[0, 1], abs_tol=1e-9)
    for bad in (
        Registration(Pose("body", "eyemap", (0.0, 0.0, 0.0), yaw(20)), "yaw"),
        Registration(Pose("body", "eyemap", (0.0, 1e-4, 0.0), IDENTITY), "shift"),
    ):
        with pytest.raises(ContractError, match="sagittal"):
            optics.sample(
                cols,
                bad,
                MOUNTS,
                still(),
                (optics.Sphere("s", (0.0, 0.0, 0.05), 0.002),),
                ACCEPTANCE,
            )


def yaw(deg):
    h = math.radians(deg) / 2
    return Quat.of((math.cos(h), 0.0, 0.0, math.sin(h)))


def test_sphere_direction_in_the_body_frame():
    out = run((optics.Sphere("s", (0.05, -0.05, 0.05 * math.sqrt(2)), 0.002),))
    # seen from the right eye (y = -0.3 mm), roughly 45 deg right and 45 deg up
    assert math.isclose(out.azimuth_deg[0, 1], 45.0, abs_tol=0.5)
    assert math.isclose(out.elevation_deg[0, 1], 45.0, abs_tol=0.5)


def test_eye_lever_arm_and_body_translation_change_the_radius_rate():
    r, d = 0.002, 0.05
    ahead_of_left = (optics.Sphere("s", (d, 3e-4, 0.0), r),)
    # yaw left at 1 rad/s: the left eye (y = +0.3 mm) moves backward at 0.3 mm/s
    turning = run(ahead_of_left, still(omega=(0.0, 0.0, 1.0)))
    expect = -math.degrees(r * 3e-4 / (d * math.sqrt(d * d - r * r)))
    assert math.isclose(turning.radius_rate_deg_s[0, 2], expect, rel_tol=1e-9)
    moving = run(ahead_of_left, still(v=(0.1, 0.0, 0.0)))
    expect = math.degrees(r * 0.1 / (d * math.sqrt(d * d - r * r)))
    assert math.isclose(moving.radius_rate_deg_s[0, 2], expect, rel_tol=1e-9)


def test_near_contact_approaches_a_half_sphere():
    near = run((optics.Sphere("s", (0.0, 3e-4 + 0.0101, 0.0), 0.01),))
    assert 81.0 < near.radius_deg[0, 0] < 90.0 and near.coverage[0, 0] > 0.999


def test_config_hash_tracks_every_input():
    s = (optics.Sphere("s", (0.0, 0.05, 0.0), 0.005),)
    base = run(s)
    other_cols = optics.Columns(COLS.side, COLS.p, COLS.q, COLS.direction, "c" * 64)
    changed = [
        optics.sample(other_cols, REG, MOUNTS, still(), s, ACCEPTANCE),
        optics.sample(COLS, REG, MOUNTS, still(), s, 5.0),
        optics.sample(
            COLS, Registration(REG.pose, "other"), MOUNTS, still(), s, ACCEPTANCE
        ),
        run((optics.Sphere("t", (0.0, 0.05, 0.0), 0.005),)),
    ]
    assert len({base.config_sha256, *(c.config_sha256 for c in changed)}) == 5
    assert len({base.digest(), *(c.digest() for c in changed)}) == 5


def test_column_table_refuses_duplicates_and_bad_hashes():
    df = pd.DataFrame(
        {
            "side": ["L", "L"],
            "p": [0, 0],
            "q": [0, 0],
            "azimuth_deg": [0.0, 1.0],
            "elevation_deg": [0.0, 0.0],
        }
    )
    with pytest.raises(ContractError, match="twice"):
        optics.Columns.from_frame(df, SHA)
    with pytest.raises(ContractError):
        optics.Columns.from_frame(df.iloc[:1], "Z" * 64)


@pytest.mark.parametrize("rho", [0.5, 2.0, 5.0])
def test_exact_coverage_on_and_opposite_the_axis(rho):
    # on the axis the share has a closed form for the spherical Gaussian only numerically;
    # check against a 10x finer quadrature and the antipodal complement
    on = optics.coverage_exact(0.0, rho, ACCEPTANCE)
    assert math.isclose(
        on, optics.coverage_exact(0.0, rho, ACCEPTANCE, n=200000), abs_tol=1e-6
    )
    opposite = optics.coverage_exact(180.0, 180.0 - rho, ACCEPTANCE)
    assert math.isclose(opposite, 1.0 - on, abs_tol=1e-6)


COARSE = (16, 24, 4)
FINE = (400, 720, 6)


def bar(**kwargs):
    fields = {
        "name": "b",
        "axis_xy_m": (0.0, 0.0),
        "screen_radius_m": 0.05,
        "z_bottom_m": -0.2,
        "z_top_m": 0.2,
        "width_deg": 20.0,
        "azimuth0_deg": 0.0,
        "angular_velocity_deg_s": 0.0,
        "visible_us": (0, 1_000_000),
    }
    fields.update(kwargs)
    return optics.Bar(**fields)


def mounts_at(position):
    x, y, z = position
    left = EyeMount("L", Pose("body", "eye/L", (x, y, z), LOOK_LEFT), "synthetic")
    right = EyeMount("R", Pose("body", "eye/R", (x, -y, z), LOOK_LEFT), "synthetic")
    return (left, right)


def cover(cols, bars, mounts=None, t=0, quadrature=COARSE):
    return optics.bar_coverage(
        cols,
        REG,
        mounts or mounts_at((0.0, 0.0, 0.0)),
        still(t),
        bars,
        ACCEPTANCE,
        quadrature,
    )


def test_bar_rejects_bad_fields():
    with pytest.raises(ContractError, match="name"):
        bar(name="")
    for bad in (
        {"axis_xy_m": (0.0,)},
        {"axis_xy_m": (0.0, float("nan"))},
        {"screen_radius_m": float("inf")},
        {"z_top_m": float("nan")},
        {"width_deg": float("nan")},
        {"azimuth0_deg": float("nan")},
        {"angular_velocity_deg_s": float("inf")},
        {"screen_radius_m": True},
    ):
        with pytest.raises(ContractError, match="finite"):
            bar(**bad)
    with pytest.raises(ContractError, match="radius"):
        bar(screen_radius_m=0.0)
    with pytest.raises(ContractError, match="bottom"):
        bar(z_bottom_m=0.1, z_top_m=0.1)
    for width in (0.0, 360.0, -10.0):
        with pytest.raises(ContractError, match="width"):
            bar(width_deg=width)
    for span in ((5, 5), (5, 4), (1.0, 2), (True, 2), [0, 10], (0, 1, 2)):
        with pytest.raises(ContractError, match="visible"):
            bar(visible_us=span)
    cols = table([("L", 0.0, 0.0)])
    origin = mounts_at((0.0, 0.0, 0.0))
    with pytest.raises(ContractError, match="unique"):
        cover(cols, (bar(), bar()))
    with pytest.raises(ContractError, match="unique"):
        cover(cols, ())
    with pytest.raises(ContractError, match="Bar"):
        cover(cols, (optics.Sphere("s", (0.0, 0.0, 0.0), 0.01),))
    with pytest.raises(ContractError, match="acceptance"):
        optics.bar_coverage(cols, REG, origin, still(), (bar(),), 0.0, COARSE)
    with pytest.raises(ContractError, match="outside"):
        cover(cols, (bar(),), mounts_at((0.0, 0.06, 0.0)))
    with pytest.raises(ContractError, match="outside"):
        cover(cols, (bar(),), mounts_at((0.05, 0.0, 0.0)))  # on the screen, not inside
    for bad in (
        (0, 24, 4),
        (16, 0, 4),
        (16, 24, 0),
        (16, 24, -1.0),
        (True, 24, 4),
        (16.0, 24, 4),
        (16, 24),
        (16, 24, 4, 1),
        (16, 24, float("nan")),
        (16, 24, float("inf")),
        (8, 8, 100),  # cap past one hemisphere at this acceptance
    ):
        with pytest.raises(ContractError):
            cover(cols, (bar(),), quadrature=bad)
    with pytest.raises(ContractError, match="Registration"):
        optics.bar_coverage(cols, None, origin, still(), (bar(),), ACCEPTANCE, COARSE)
    with pytest.raises(ContractError, match="mount"):
        optics.bar_coverage(cols, REG, (LEFT,), still(), (bar(),), ACCEPTANCE, COARSE)
    with pytest.raises(ContractError, match="sagittal"):
        optics.bar_coverage(
            cols,
            Registration(Pose("body", "eyemap", (0.0, 0.0, 0.0), yaw(20)), "yaw"),
            origin,
            still(),
            (bar(),),
            ACCEPTANCE,
            COARSE,
        )
    same = optics.bar_config_sha256(cols, REG, origin, (bar(),), ACCEPTANCE, COARSE)
    assert same == optics.bar_config_sha256(
        cols, REG, origin, (bar(),), ACCEPTANCE, (16, 24, 4.0)
    )
    assert same != optics.bar_config_sha256(
        cols, REG, origin, (bar(name="other"),), ACCEPTANCE, COARSE
    )
    assert len(same) == 64


def test_bar_coverage_is_zero_outside_its_window():
    cols = table([("L", 0.0, 0.0), ("L", float("nan"), float("nan"))])
    b = bar(visible_us=(1_000, 5_000), width_deg=40.0)
    for t in (999, 5_000):
        out = cover(cols, (b,), t=t)
        assert out.coverage[0, 0] == 0.0
        assert math.isnan(out.coverage[0, 1])
    for t in (1_000, 4_999):
        out = cover(cols, (b,), t=t)
        assert out.coverage[0, 0] > 0.5
        assert math.isnan(out.coverage[0, 1])


def test_bar_quadrature_matches_a_fine_grid():
    # (16, 24) steps are a quarter of a sigma by 15°. A bar edge is a step, and the
    # cells it cuts move about one percent of the Gaussian: the largest gap below is
    # 0.011. The reference is (400, 720) out to 6 sigma, about 25 times finer; the
    # mass past 4 sigma is about exp(-8), 3e-4, and both sums drop their own tails.
    # 1.5e-2 absolute is that discretisation, not a physiological uncertainty.
    cols = table(
        [
            ("L", 0.0, 0.0),
            ("L", 0.0, 15.0),
            ("L", -40.0, 0.0),
            ("L", 180.0, 0.0),
            ("R", 25.0, -10.0),
            ("L", float("nan"), float("nan")),
        ]
    )
    bars = (
        bar(name="centred", width_deg=8.0),  # edges at ±4°, through the core
        bar(name="edge", azimuth0_deg=60.0, width_deg=120.0),  # one edge on +x
        bar(name="far", azimuth0_deg=80.0, width_deg=8.0),
        bar(name="wrap", azimuth0_deg=175.0, width_deg=30.0),  # crosses ±180°
        bar(name="short", width_deg=80.0, z_top_m=0.0),  # top edge at eye height
    )
    centred = mounts_at((0.0, 0.0, 0.0))
    offset = (
        EyeMount("L", Pose("body", "eye/L", (0.012, -0.007, 0.004), LOOK_LEFT), "s"),
        EyeMount("R", Pose("body", "eye/R", (0.012, -0.007, 0.004), LOOK_LEFT), "s"),
    )
    worst = 0.0
    for mounts in (centred, offset):
        coarse = cover(cols, bars, mounts)
        fine = cover(cols, bars, mounts, quadrature=FINE)
        worst = max(worst, np.nanmax(np.abs(coarse.coverage - fine.coverage)))
        assert np.isnan(coarse.coverage[:, -1]).all()
    assert worst < 1.5e-2
    # the edge through +x is a great circle on the column axis, and the grid is
    # symmetric across it, so a centred eye sees exactly half the truncated profile
    half = cover(table([("L", 0.0, 0.0)]), (bars[1],))
    assert math.isclose(half.coverage[0, 0], 0.5, abs_tol=1e-9)
    # a half turn of the cylinder maps a bar at 0 seen along +x onto a bar at 180
    # seen along -x, rays and all, including across the branch cut of azimuth
    front = cover(table([("L", 0.0, 0.0)]), (bar(name="front", width_deg=20.0),))
    back = cover(
        table([("L", 180.0, 0.0)]),
        (bar(name="back", azimuth0_deg=180.0, width_deg=20.0),),
    )
    assert np.allclose(front.coverage, back.coverage, atol=1e-12)


def test_a_wide_tall_bar_covers_the_truncated_profile():
    # The grid normalises by its own weights. Every ray of the 4-sigma cap hits this
    # bar, so the share is the truncated total, 1. A full-sphere Gaussian would sit
    # lower by about exp(-8), 3e-4, which the sum leaves out of both parts.
    cols = table(
        [("L", 0.0, 0.0), ("L", 180.0, 0.0), ("L", float("nan"), float("nan"))]
    )
    out = cover(cols, (bar(width_deg=180.0, z_bottom_m=-1.0, z_top_m=1.0),))
    assert math.isclose(out.coverage[0, 0], 1.0, abs_tol=1e-12)
    assert out.coverage[0, 1] == 0.0
    assert math.isnan(out.coverage[0, 2])
    assert math.isclose(out.azimuth_deg[0, 0], 0.0, abs_tol=1e-9)
    assert math.isclose(out.elevation_deg[0, 0], 0.0, abs_tol=1e-9)


def test_mirrored_bars_swap_the_two_eyes():
    cols = table(
        [
            ("L", -90.0, 0.0),
            ("R", 90.0, 0.0),
            ("L", 0.0, 0.0),
            ("R", 0.0, 0.0),
            ("L", -30.0, 20.0),
            ("R", 30.0, 20.0),
        ]
    )
    phi = 30.0
    left = cover(cols, (bar(azimuth0_deg=phi, width_deg=25.0),), MOUNTS)
    right = cover(cols, (bar(name="m", azimuth0_deg=-phi, width_deg=25.0),), MOUNTS)
    for i, j in ((0, 1), (2, 3), (4, 5)):
        assert math.isclose(left.coverage[0, i], right.coverage[0, j], abs_tol=1e-12)
        assert math.isclose(left.coverage[0, j], right.coverage[0, i], abs_tol=1e-12)
        assert math.isclose(
            left.azimuth_deg[0, i], -right.azimuth_deg[0, j], abs_tol=1e-9
        )
        assert math.isclose(
            left.elevation_deg[0, i], right.elevation_deg[0, j], abs_tol=1e-9
        )


def test_bar_centre_advances_at_its_angular_velocity():
    b = bar(angular_velocity_deg_s=90.0, visible_us=(1_000, 2_000_000))
    dt = 500_000
    assert math.isclose(b.centre_azimuth_deg(1_000), b.azimuth0_deg)
    assert math.isclose(
        b.centre_azimuth_deg(1_000 + dt) - b.centre_azimuth_deg(1_000),
        90.0 * dt * 1e-6,
        rel_tol=1e-12,
    )
    cols = table([("L", 0.0, 0.0)])
    start = cover(cols, (b,), t=1_000)
    later = cover(cols, (b,), t=1_000 + dt)
    # cylinder azimuth +45° is toward world +y, the fly's left, so the body azimuth
    # (positive to the fly's right) is -45°
    assert math.isclose(start.azimuth_deg[0, 0], 0.0, abs_tol=1e-9)
    assert math.isclose(later.azimuth_deg[0, 0], -45.0, abs_tol=1e-9)
    assert math.isclose(start.elevation_deg[0, 0], 0.0, abs_tol=1e-9)
    assert start.digest() == cover(cols, (b,), t=1_000).digest()
    assert start.config_sha256 == optics.bar_config_sha256(
        cols, REG, mounts_at((0.0, 0.0, 0.0)), (b,), ACCEPTANCE, COARSE
    )


def test_sphere_sample_digest_is_unchanged():
    # The left-hand target of test_fixed_pose_is_deterministic_and_left_target_one_sided.
    spheres = (optics.Sphere("left", (0.0, 0.05, 0.0), 0.02),)
    sample = run(spheres)
    assert (
        sample.digest()
        == "7a2a3affcfb9c2281952f01c8a21a5db67579dd8888c2a174ce19b946db174c8"
    )
    stimulus, config = closedloop.optical(COLS, REG, MOUNTS, spheres, ACCEPTANCE)
    assert config == sample.config_sha256
    assert stimulus(0, still()) == tuple(
        float(v) for v in sample.coverage[:, sample.has_direction].max(axis=0)
    )


def test_optical_bars_returns_the_largest_bar():
    cols = table([("L", 0.0, 0.0), ("R", 90.0, 0.0), ("L", float("nan"), float("nan"))])
    mounts = mounts_at((0.0, 0.0, 0.0))
    narrow = bar(name="narrow", width_deg=4.0)
    wide = bar(name="wide", width_deg=80.0)
    state = still(10)
    stimulus, config = closedloop.optical_bars(
        cols, REG, mounts, (narrow, wide), ACCEPTANCE, COARSE
    )
    assert config == optics.bar_config_sha256(
        cols, REG, mounts, (narrow, wide), ACCEPTANCE, COARSE
    )
    got = stimulus(state.time_us, state)
    sample = cover(cols, (narrow, wide), mounts, t=10)
    expect = tuple(float(v) for v in sample.coverage[:, sample.has_direction].max(0))
    assert got == expect
    assert len(got) == 2
    assert got[0] == float(sample.coverage[1, 0])
    assert got[0] > float(sample.coverage[0, 0])
    with pytest.raises(ContractError, match="own time"):
        stimulus(state.time_us + 1, state)
    dark = bar(name="dark", visible_us=(100, 200), width_deg=80.0)
    off, _ = closedloop.optical_bars(cols, REG, mounts, (dark,), ACCEPTANCE, COARSE)
    assert off(0, still(0)) == (0.0, 0.0)
