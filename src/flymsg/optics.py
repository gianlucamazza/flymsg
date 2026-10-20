"""Geometric optics onto measured optic-lobe columns (issue #179, gate G2).

Turns dark spheres in the world and a B6 v2 body state (`flymsg.pose`) into per-column
measurements: the angle from each column's axis to each sphere, the sphere's angular
radius and its rate, the sphere's angular velocity relative to the eye, the share of each column's acceptance
profile it covers, and which sphere the column axis meets first. Geometry only: no
photoreceptor gain, no spikes, no rendering. A viewer's scene cannot reach this module.

Columns come from `flymsg.eye.columns` (Zhao et al. 2025 directions on the MaleCNS hex
grid) in the `eyemap` frame; a column without a lens keeps a NaN direction and NaN output.
Their rotation into the body needs an explicit `pose.Registration` with a source: none is
measured yet (#84), so only tests construct one. It may only pitch and shift in the sagittal
plane: the left eye's columns are the right eye's mirrored, so that plane is the mirror. Every
column of an eye looks out from the position of that eye's mount (`pose.EyeMount`); the
mount's orientation is unused, the columns carry their own directions.

Coverage uses `eye.disk_coverage`'s profile, a circular Gaussian of full width at half
maximum `acceptance_deg`, with the planar Rice CDF; `coverage_exact` integrates the same
profile over the sphere and bounds the planar error (docs/reference/eye.md). A sphere's silhouette is
a spherical cap of radius asin(r / d). Coverages are per sphere as if alone: where
silhouettes overlap, `nearest` says which one the column axis sees, the shares do not
subtract.

`Bar` is the same profile on a different object: a dark vertical bar on a cylinder whose
axis is vertical in the world. `bar_coverage` integrates the Gaussian on a polar midpoint
grid about each column axis; a ray counts when it hits the screen inside the bar's azimuth
and height, and only during the bar's visibility window. The tails past the grid's last
ring are left out of both the covered share and the total. Spheres and `sample` are
untouched.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

import numba
import numpy as np
import pandas as pd
from scipy import stats

from flymsg import pose
from flymsg.embodiment import ContractError

SCHEMA = "flymsg.optics/v1"
BAR_SCHEMA = "flymsg.optics.bar/v1"
FWHM = 2 * math.sqrt(2 * math.log(2))  # full width at half maximum per sigma


@dataclass(frozen=True)
class Sphere:
    """A dark sphere: centre in world metres at time 0, constant world velocity."""

    name: str
    center_m: tuple[float, float, float]
    radius_m: float
    velocity_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if not self.name:
            raise ContractError("a sphere needs a name")
        vals = (*self.center_m, self.radius_m, *self.velocity_m_s)
        if len(vals) != 7 or not all(math.isfinite(v) for v in vals):
            raise ContractError(
                "sphere centre, radius and velocity must be finite 3-vectors"
            )
        if self.radius_m <= 0:
            raise ContractError("sphere radius must be positive")

    def center_at(self, time_us: int) -> np.ndarray:
        return np.asarray(self.center_m) + np.asarray(self.velocity_m_s) * (
            time_us * 1e-6
        )


@dataclass(frozen=True)
class Columns:
    """Column axes in the `eyemap` frame (unit vectors, NaN where no lens). The left eye's
    rows are the right eye's lenses mirrored across the frame's y = 0 plane (`eye.columns`),
    which therefore stands for the body's sagittal plane."""

    side: tuple[str, ...]
    p: tuple[int, ...]
    q: tuple[int, ...]
    direction: np.ndarray  # (n, 3)
    source_sha256: str

    @classmethod
    def from_frame(cls, cols: pd.DataFrame, source_sha256: str) -> Columns:
        """From `eye.columns` output: azimuth grows to the fly's right, elevation up, and
        `eyemap` +y is the fly's left, so y = -cos(el) sin(az)."""
        if len(source_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in source_sha256
        ):
            raise ContractError("the column table needs its lowercase SHA-256")
        if not set(cols["side"]) <= set(pose.SIDES):
            raise ContractError("column sides must be L or R")
        if cols.duplicated(["side", "p", "q"]).any():
            raise ContractError("a column appears twice")
        az = np.radians(cols["azimuth_deg"].to_numpy(float))
        el = np.radians(cols["elevation_deg"].to_numpy(float))
        d = np.stack(
            [np.cos(el) * np.cos(az), -np.cos(el) * np.sin(az), np.sin(el)], axis=1
        )
        return cls(
            tuple(cols["side"]),
            tuple(int(v) for v in cols["p"]),
            tuple(int(v) for v in cols["q"]),
            d,
            source_sha256,
        )


@dataclass(frozen=True)
class Sample:
    """Per-column measurements at `time_us`; arrays are (spheres, columns) unless noted."""

    time_us: int
    config_sha256: str  # columns source, registration, mounts, spheres, acceptance
    has_direction: np.ndarray  # (columns,)
    angle_deg: np.ndarray  # column axis to sphere centre
    azimuth_deg: np.ndarray  # sphere centre from the column's eye, body frame, + right
    elevation_deg: np.ndarray  # same, + dorsal
    radius_deg: np.ndarray  # sphere angular radius from the column's eye
    radius_rate_deg_s: np.ndarray
    angular_velocity_deg_s: (
        np.ndarray
    )  # (spheres, columns, 3) relative to the eye, world axes
    coverage: np.ndarray
    nearest: np.ndarray  # (columns,) sphere index the axis meets first, -1 none

    def digest(self) -> str:
        h = hashlib.sha256(f"{SCHEMA}:{self.time_us}:{self.config_sha256}".encode())
        for name in (
            "has_direction",
            "angle_deg",
            "azimuth_deg",
            "elevation_deg",
            "radius_deg",
            "radius_rate_deg_s",
            "angular_velocity_deg_s",
            "coverage",
            "nearest",
        ):
            a = np.ascontiguousarray(getattr(self, name))
            h.update(f"{name}{a.shape}{a.dtype}".encode())
            h.update(a.tobytes())
        return h.hexdigest()


def _matrix(q: pose.Quat) -> np.ndarray:
    return np.asarray(q.matrix())


SAGITTAL_TOL = 1e-12


def config_sha256(columns, registration, mounts, spheres, acceptance_deg) -> str:
    """The configuration hash every `Sample` of these inputs carries."""
    doc = {
        "schema": SCHEMA,
        "columns": columns.source_sha256,
        "registration": [registration.source, repr(registration.pose)],
        "mounts": sorted([m.side, m.source, repr(m.pose)] for m in mounts),
        "spheres": [repr(s) for s in spheres],
        "acceptance_deg": repr(float(acceptance_deg)),
    }
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def sample(
    columns: Columns,
    registration: pose.Registration,
    mounts: tuple[pose.EyeMount, pose.EyeMount],
    state: pose.BodyState,
    spheres: tuple[Sphere, ...],
    acceptance_deg: float,
) -> Sample:
    """Measure every sphere from every column at `state.time_us`."""
    if not isinstance(registration, pose.Registration):
        raise ContractError(
            "columns reach the body only through a sourced Registration"
        )
    by_side = {m.side: m for m in mounts}
    if sorted(by_side) != list(pose.SIDES) or len(mounts) != 2:
        raise ContractError("one mount per eye is required")
    if not spheres or len({s.name for s in spheres}) != len(spheres):
        raise ContractError("spheres need unique names")
    if not (math.isfinite(acceptance_deg) and acceptance_deg > 0):
        raise ContractError("acceptance must be positive")
    r_be = _matrix(registration.pose.orientation)
    mirror = np.diag([1.0, -1.0, 1.0])
    # the left rows are mirrored lenses, so the registration must keep the sagittal plane
    # (pitch only): any yaw or roll would mirror wrongly onto the left eye
    if np.abs(mirror @ r_be @ mirror - r_be).max() > SAGITTAL_TOL or (
        abs(registration.pose.position_m[1]) > SAGITTAL_TOL
    ):
        raise ContractError(
            "a registration may only pitch and shift in the sagittal plane"
        )
    sigma = acceptance_deg / FWHM
    r_wb = _matrix(state.pose.orientation)
    body_pos = np.asarray(state.pose.position_m)
    axes = columns.direction @ (r_wb @ r_be).T
    has = np.isfinite(axes).all(axis=1)
    side = np.asarray(columns.side)
    origin = np.empty((len(side), 3))
    eye_v = np.empty((len(side), 3))
    omega = r_wb @ np.asarray(state.angular_velocity_rad_s)
    for s, mount in by_side.items():
        o = np.asarray(pose.eye_pose(state, mount).position_m)
        origin[side == s] = o
        eye_v[side == s] = np.asarray(state.linear_velocity_m_s) + np.cross(
            omega, o - body_pos
        )
    n_s, n_c = len(spheres), len(side)
    angle = np.full((n_s, n_c), np.nan)
    azimuth = np.full((n_s, n_c), np.nan)
    elevation = np.full((n_s, n_c), np.nan)
    radius = np.full((n_s, n_c), np.nan)
    rate = np.full((n_s, n_c), np.nan)
    ang_v = np.full((n_s, n_c, 3), np.nan)
    cover = np.full((n_s, n_c), np.nan)
    hit = np.full((n_s, n_c), np.inf)
    for i, sph in enumerate(spheres):
        rel = sph.center_at(state.time_us) - origin  # (columns, 3)
        dist = np.linalg.norm(rel, axis=1)
        if np.any(dist <= sph.radius_m):
            raise ContractError(f"an eye is inside or touching {sph.name}")
        u = rel / dist[:, None]
        v_rel = np.asarray(sph.velocity_m_s) - eye_v
        d_dot = np.einsum("ij,ij->i", u, v_rel)
        rho = np.arcsin(sph.radius_m / dist)
        cos_a = np.clip(np.einsum("ij,ij->i", axes, u), -1.0, 1.0)
        a = np.degrees(np.arccos(cos_a))
        angle[i] = np.where(has, a, np.nan)
        ub = u @ r_wb  # body frame
        azimuth[i] = np.where(has, np.degrees(-np.arctan2(ub[:, 1], ub[:, 0])), np.nan)
        elevation[i] = np.where(
            has, np.degrees(np.arcsin(np.clip(ub[:, 2], -1.0, 1.0))), np.nan
        )
        radius[i] = np.where(has, np.degrees(rho), np.nan)
        drho = -sph.radius_m * d_dot / (dist * np.sqrt(dist**2 - sph.radius_m**2))
        rate[i] = np.where(has, np.degrees(drho), np.nan)
        # relative to the eye, which turns with the body: minus the body's rotation
        w = np.cross(u, v_rel) / dist[:, None] - omega
        ang_v[i] = np.where(has[:, None], np.degrees(w), np.nan)
        cover[i] = np.where(
            has, stats.rice.cdf(np.degrees(rho) / sigma, a / sigma), np.nan
        )
        # ray-sphere: first positive root of |o + t axis - c|^2 = r^2
        b = np.einsum("ij,ij->i", axes, rel)
        disc = b**2 - (dist**2 - sph.radius_m**2)
        t = b - np.sqrt(np.where(disc >= 0, disc, np.nan))
        hit[i] = np.where(has & (disc >= 0) & (t > 0), t, np.inf)
    first = np.argmin(hit, axis=0)
    nearest = np.where(np.isfinite(hit.min(axis=0)), first, -1)
    config = config_sha256(columns, registration, mounts, spheres, acceptance_deg)
    return Sample(
        state.time_us,
        config,
        has,
        angle,
        azimuth,
        elevation,
        radius,
        rate,
        ang_v,
        cover,
        nearest,
    )


def coverage_exact(
    angle_deg: float, radius_deg: float, acceptance_deg: float, n: int = 20000
) -> float:
    """Share of a circular Gaussian acceptance profile (on the sphere, FWHM
    `acceptance_deg`, normalised over the sphere) inside a spherical cap of angular radius
    `radius_deg` whose centre is `angle_deg` from the profile's axis; midpoint quadrature
    in the profile's polar angle out to 12 sigma (the rest weighs < 1e-30), the cap's
    azimuthal extent exact; on the axis (cap centred on or opposite the profile) the cell
    the cap edge crosses gets its covered fraction."""
    sigma = math.radians(acceptance_deg) / FWHM
    a, rho = math.radians(angle_deg), math.radians(radius_deg)
    top = min(math.pi, 12 * sigma)
    alpha = (np.arange(n) + 0.5) * top / n
    weight = np.exp(-(alpha**2) / (2 * sigma**2)) * np.sin(alpha)
    # azimuthal share of the circle at polar angle alpha inside the cap (spherical law of
    # cosines: cos rho = cos a cos alpha + sin a sin alpha cos phi)
    with np.errstate(divide="ignore", invalid="ignore"):
        c = (math.cos(rho) - math.cos(a) * np.cos(alpha)) / (
            math.sin(a) * np.sin(alpha)
        )
    inside = np.where(np.isfinite(c), np.arccos(np.clip(c, -1, 1)) / math.pi, 0.0)
    if math.sin(a) < 1e-12:
        h = top / n
        edge = rho if math.cos(a) > 0 else math.pi - rho
        share = np.clip((edge - (alpha - h / 2)) / h, 0.0, 1.0)
        inside = share if math.cos(a) > 0 else 1.0 - share
    return float((weight * inside).sum() / weight.sum())


@dataclass(frozen=True)
class Bar:
    """A dark vertical bar on a cylinder. The cylinder's axis is vertical, through
    `axis_xy_m` in the world. `azimuth0_deg` is the centre's world azimuth at
    `visible_us[0]`, from +x toward +y, and it advances at `angular_velocity_deg_s`
    (counterclockwise about +z). The bar exists for start <= t < end."""

    name: str
    axis_xy_m: tuple[float, float]
    screen_radius_m: float
    z_bottom_m: float
    z_top_m: float
    width_deg: float
    azimuth0_deg: float
    angular_velocity_deg_s: float
    visible_us: tuple[int, int]

    def __post_init__(self) -> None:
        if not self.name:
            raise ContractError("a bar needs a name")
        try:
            axis = tuple(self.axis_xy_m)
        except TypeError:
            axis = ()
        vals = (
            *axis,
            self.screen_radius_m,
            self.z_bottom_m,
            self.z_top_m,
            self.width_deg,
            self.azimuth0_deg,
            self.angular_velocity_deg_s,
        )
        if len(axis) != 2 or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in vals
        ):
            raise ContractError(
                "bar axis, radius, heights, width, azimuth and speed must be finite"
            )
        if self.screen_radius_m <= 0:
            raise ContractError("screen radius must be positive")
        if not self.z_bottom_m < self.z_top_m:
            raise ContractError("the bar's bottom must be below its top")
        if not 0 < self.width_deg < 360:
            raise ContractError("bar width must be between 0 and 360 degrees")
        span = self.visible_us
        if (
            not isinstance(span, tuple)
            or len(span) != 2
            or type(span[0]) is not int
            or type(span[1]) is not int
            or not span[0] < span[1]
        ):
            raise ContractError(
                "visible_us must be integer microseconds with start < end"
            )

    def centre_azimuth_deg(self, time_us: int) -> float:
        """World azimuth of the bar's centre at `time_us`, unwrapped, degrees."""
        start, _end = self.visible_us
        return self.azimuth0_deg + self.angular_velocity_deg_s * (
            (time_us - start) * 1e-6
        )


@dataclass(frozen=True)
class BarSample:
    """Per-column bar measurements at `time_us`; arrays are (bars, columns) unless noted."""

    time_us: int
    config_sha256: str
    has_direction: np.ndarray  # (columns,)
    coverage: np.ndarray  # share of the acceptance profile whose rays hit the bar
    azimuth_deg: np.ndarray  # bar centre from the column's eye, body frame, + right
    elevation_deg: np.ndarray  # same, + dorsal

    def digest(self) -> str:
        h = hashlib.sha256(f"{BAR_SCHEMA}:{self.time_us}:{self.config_sha256}".encode())
        for name in ("has_direction", "coverage", "azimuth_deg", "elevation_deg"):
            a = np.ascontiguousarray(getattr(self, name))
            h.update(f"{name}{a.shape}{a.dtype}".encode())
            h.update(a.tobytes())
        return h.hexdigest()


def _quadrature(quadrature) -> tuple[int, int, float]:
    """(n_radial, n_angular, max_sigma): positive counts and a positive finite cap."""
    if not isinstance(quadrature, tuple) or len(quadrature) != 3:
        raise ContractError("quadrature must be (n_radial, n_angular, max_sigma)")
    n_radial, n_angular, max_sigma = quadrature
    if (
        type(n_radial) is not int
        or type(n_angular) is not int
        or n_radial < 1
        or n_angular < 1
    ):
        raise ContractError("quadrature counts must be positive integers")
    if isinstance(max_sigma, bool) or not isinstance(max_sigma, (int, float)):
        raise ContractError("max_sigma must be a positive finite number")
    max_sigma = float(max_sigma)
    if not math.isfinite(max_sigma) or max_sigma <= 0:
        raise ContractError("max_sigma must be a positive finite number")
    return n_radial, n_angular, max_sigma


def _posed_columns(columns, registration, mounts, state):
    """Column axes in world and each column's eye origin. Same placement as `sample`,
    duplicated so `sample` stays bit-identical."""
    if not isinstance(registration, pose.Registration):
        raise ContractError(
            "columns reach the body only through a sourced Registration"
        )
    by_side = {m.side: m for m in mounts}
    if sorted(by_side) != list(pose.SIDES) or len(mounts) != 2:
        raise ContractError("one mount per eye is required")
    r_be = _matrix(registration.pose.orientation)
    mirror = np.diag([1.0, -1.0, 1.0])
    # the left rows are mirrored lenses, so the registration must keep the sagittal plane
    if np.abs(mirror @ r_be @ mirror - r_be).max() > SAGITTAL_TOL or (
        abs(registration.pose.position_m[1]) > SAGITTAL_TOL
    ):
        raise ContractError(
            "a registration may only pitch and shift in the sagittal plane"
        )
    r_wb = _matrix(state.pose.orientation)
    axes = columns.direction @ (r_wb @ r_be).T
    has = np.isfinite(axes).all(axis=1)
    side = np.asarray(columns.side)
    origin = np.empty((len(side), 3))
    eyes = {}
    for s, mount in by_side.items():
        o = np.asarray(pose.eye_pose(state, mount).position_m, dtype=float)
        origin[side == s] = o
        eyes[s] = o
    return axes, has, origin, r_wb, eyes


def _check_bars(bars) -> None:
    if not bars:
        raise ContractError("bars need unique names")
    for bar in bars:
        if not isinstance(bar, Bar):
            raise ContractError("bars must be Bar values")
    if len({b.name for b in bars}) != len(bars):
        raise ContractError("bars need unique names")


def _eyes_inside(bars, eyes) -> None:
    """Every eye origin strictly inside every bar's screen cylinder."""
    for bar in bars:
        ax, ay = bar.axis_xy_m
        limit = bar.screen_radius_m**2
        for pos in eyes.values():
            dx = float(pos[0]) - float(ax)
            dy = float(pos[1]) - float(ay)
            if dx * dx + dy * dy >= limit:
                raise ContractError(f"an eye is outside the screen of {bar.name}")


def _axis_frame(axes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Orthonormal (e1, e2) across each axis. e1 is horizontal when the axis is not
    near vertical: world +z, or +x when the axis is within the cone that would make
    +z parallel to it."""
    ref = np.tile(np.array([0.0, 0.0, 1.0]), (len(axes), 1))
    ref[np.abs(axes[:, 2]) >= 0.9] = (1.0, 0.0, 0.0)
    e1 = np.cross(ref, axes)
    e1 /= np.linalg.norm(e1, axis=1, keepdims=True)
    e2 = np.cross(axes, e1)
    return e1, e2


@numba.njit(cache=True, parallel=True)
def _covered_weight(
    axes,
    e1,
    e2,
    origin,
    ca,
    sa,
    cp,
    sp,
    weight,
    radius,
    ax,
    ay,
    z0,
    z1,
    cos_c,
    sin_c,
    thresh,
):
    """Sum of polar-grid weights whose rays hit one bar.

    The grid is the midpoint rule (rings `ca`/`sa`, azimuths `cp`/`sp`). Columns are
    independent, so the pass is parallel; each column's sum is a fixed loop.
    """
    n = axes.shape[0]
    n_r = ca.shape[0]
    n_a = cp.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in numba.prange(n):
        vx, vy, vz = axes[i, 0], axes[i, 1], axes[i, 2]
        e1x, e1y, e1z = e1[i, 0], e1[i, 1], e1[i, 2]
        e2x, e2y, e2z = e2[i, 0], e2[i, 1], e2[i, 2]
        ox, oy, oz = origin[i, 0], origin[i, 1], origin[i, 2]
        qx, qy = ox - ax, oy - ay
        # eye inside the cylinder, so C is negative and a non-parallel ray hits once
        c_coef = qx * qx + qy * qy - radius * radius
        tang_x = np.empty(n_a)
        tang_y = np.empty(n_a)
        tang_z = np.empty(n_a)
        for a in range(n_a):
            tang_x[a] = cp[a] * e1x + sp[a] * e2x
            tang_y[a] = cp[a] * e1y + sp[a] * e2y
            tang_z[a] = cp[a] * e1z + sp[a] * e2z
        acc = 0.0
        for r in range(n_r):
            car, sar, w = ca[r], sa[r], weight[r]
            hits = 0.0
            for a in range(n_a):
                dx = car * vx + sar * tang_x[a]
                dy = car * vy + sar * tang_y[a]
                dz = car * vz + sar * tang_z[a]
                aa = dx * dx + dy * dy
                if aa <= 0.0:
                    continue
                bb = 2.0 * (qx * dx + qy * dy)
                disc = bb * bb - 4.0 * aa * c_coef
                root = math.sqrt(max(disc, 0.0))
                # outward root cancels in the usual formula; use the product of roots
                if bb > 0.0:
                    t = (2.0 * c_coef) / (-bb - root)
                else:
                    t = (-bb + root) / (2.0 * aa)
                if t <= 0.0:
                    continue
                hz = oz + t * dz
                if hz < z0 or hz > z1:
                    continue
                # |hit azimuth - centre| <= width/2. Width is below 360°, so the
                # half-angle is below 180°, where cosine falls as the angle grows.
                if (ox + t * dx - ax) * cos_c + (oy + t * dy - ay) * sin_c >= thresh:
                    hits += 1.0
            acc += w * hits
        out[i] = acc
    return out


def _centre_point(bar: Bar, time_us: int) -> np.ndarray:
    """Mid-height point of the bar on the screen, world metres."""
    az = math.radians(bar.centre_azimuth_deg(time_us))
    ax, ay = bar.axis_xy_m
    return np.array(
        [
            float(ax) + bar.screen_radius_m * math.cos(az),
            float(ay) + bar.screen_radius_m * math.sin(az),
            0.5 * (bar.z_bottom_m + bar.z_top_m),
        ]
    )


def _body_direction(point, origin, r_wb):
    """Azimuth (+ right) and elevation (+ dorsal) of a world point from each eye."""
    rel = point - origin
    dist = np.linalg.norm(rel, axis=1)
    ub = (rel / dist[:, None]) @ r_wb
    azimuth = np.degrees(-np.arctan2(ub[:, 1], ub[:, 0]))
    elevation = np.degrees(np.arcsin(np.clip(ub[:, 2], -1.0, 1.0)))
    return azimuth, elevation


def bar_config_sha256(
    columns, registration, mounts, bars, acceptance_deg, quadrature
) -> str:
    """The configuration hash every `BarSample` of these inputs carries."""
    n_radial, n_angular, max_sigma = _quadrature(quadrature)
    doc = {
        "schema": BAR_SCHEMA,
        "columns": columns.source_sha256,
        "registration": [registration.source, repr(registration.pose)],
        "mounts": sorted([m.side, m.source, repr(m.pose)] for m in mounts),
        "bars": [repr(b) for b in bars],
        "acceptance_deg": repr(float(acceptance_deg)),
        "quadrature": [n_radial, n_angular, max_sigma],
    }
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def bar_coverage(
    columns: Columns,
    registration: pose.Registration,
    mounts: tuple[pose.EyeMount, pose.EyeMount],
    state: pose.BodyState,
    bars: tuple[Bar, ...],
    acceptance_deg: float,
    quadrature: tuple[int, int, float],
) -> BarSample:
    """Share of each column's acceptance profile whose rays hit each bar.

    The profile is the circular Gaussian of `coverage_exact` (FWHM `acceptance_deg`,
    on the sphere). `quadrature` is `(n_radial, n_angular, max_sigma)`: a midpoint rule
    in polar angle out to `max_sigma` standard deviations, and `n_angular` uniform
    azimuths at cell centres. A sample's weight is exp(-alpha^2 / (2 sigma^2)) sin
    alpha. The covered weights are divided by the sum of the weights on the whole grid,
    so the tails past `max_sigma` sigma are left out of both the share and the total.
    At 4 sigma that omitted spherical-Gaussian mass is about exp(-8), 3e-4. The cap
    must stay inside one hemisphere (max_sigma * sigma <= pi/2).

    A column without a lens is NaN. Outside a bar's `visible_us` its coverage is 0.
    Coverages are per bar as if alone.
    """
    axes, has, origin, r_wb, eyes = _posed_columns(columns, registration, mounts, state)
    _check_bars(bars)
    if not (math.isfinite(acceptance_deg) and acceptance_deg > 0):
        raise ContractError("acceptance must be positive")
    n_radial, n_angular, max_sigma = _quadrature(quadrature)
    sigma = math.radians(acceptance_deg) / FWHM
    if max_sigma * sigma > math.pi / 2:
        raise ContractError(
            "the quadrature cap must stay inside one hemisphere"
            " (max_sigma * sigma <= pi/2)"
        )
    _eyes_inside(bars, eyes)
    alpha = (np.arange(n_radial) + 0.5) * (max_sigma * sigma / n_radial)
    phi = (np.arange(n_angular) + 0.5) * (2.0 * math.pi / n_angular)
    # midpoint rule: the bin widths cancel once the same weights normalise the sum
    weight = np.exp(-(alpha**2) / (2.0 * sigma * sigma)) * np.sin(alpha)
    total = float(weight.sum()) * n_angular
    if not (math.isfinite(total) and total > 0.0):
        raise ContractError("the normalisation total must be a positive finite number")
    n_b, n_c = len(bars), len(has)
    coverage = np.full((n_b, n_c), np.nan)
    azimuth = np.full((n_b, n_c), np.nan)
    elevation = np.full((n_b, n_c), np.nan)
    idx = np.flatnonzero(has)
    if idx.size:
        finite_axes = np.ascontiguousarray(axes[idx], dtype=np.float64)
        finite_origin = np.ascontiguousarray(origin[idx], dtype=np.float64)
        e1, e2 = _axis_frame(finite_axes)
        ca = np.cos(alpha)
        sa = np.sin(alpha)
        cp = np.cos(phi)
        sp = np.sin(phi)
    for i, bar in enumerate(bars):
        point = _centre_point(bar, state.time_us)
        az, el = _body_direction(point, origin, r_wb)
        azimuth[i] = np.where(has, az, np.nan)
        elevation[i] = np.where(has, el, np.nan)
        if not bar.visible_us[0] <= state.time_us < bar.visible_us[1]:
            coverage[i, has] = 0.0
            continue
        if not idx.size:
            continue
        centre = math.radians(bar.centre_azimuth_deg(state.time_us))
        half = math.radians(float(bar.width_deg) * 0.5)
        covered = _covered_weight(
            finite_axes,
            e1,
            e2,
            finite_origin,
            ca,
            sa,
            cp,
            sp,
            weight,
            float(bar.screen_radius_m),
            float(bar.axis_xy_m[0]),
            float(bar.axis_xy_m[1]),
            float(bar.z_bottom_m),
            float(bar.z_top_m),
            math.cos(centre),
            math.sin(centre),
            float(bar.screen_radius_m) * math.cos(half),
        )
        coverage[i, idx] = covered / total
    config = bar_config_sha256(
        columns, registration, mounts, bars, acceptance_deg, quadrature
    )
    return BarSample(state.time_us, config, has, coverage, azimuth, elevation)
