"""Geometric optics onto measured optic-lobe columns (issue #179, gate G2).

Turns dark spheres in the world and a B6 v2 body state (`flymsg.pose`) into per-column
measurements: the angle from each column's axis to each sphere, the sphere's angular
radius and its rate, the sphere's angular velocity relative to the eye, the share of each column's acceptance
profile it covers, and which sphere the column axis meets first. Geometry only: no
photoreceptor gain, no spikes, no rendering. A viewer's scene cannot reach this module.

Columns come from `flymsg.eye.columns` (Zhao et al. 2025 directions on the MaleCNS hex
grid) in the `eyemap` frame; a column without a lens keeps a NaN direction and NaN output.
Their rotation into the body needs an explicit `pose.Registration` with a source: none is
measured yet (#84), so only tests construct one. Every column of an eye looks out from that
eye's mount (`pose.EyeMount`).

Coverage uses `eye.disk_coverage`'s profile, a circular Gaussian of full width at half
maximum `acceptance_deg`, with the planar Rice CDF; `coverage_exact` integrates the same
profile over the sphere and bounds the planar error (docs/eye.md). A sphere's silhouette is
a spherical cap of radius asin(r / d). Coverages are per sphere as if alone: where
silhouettes overlap, `nearest` says which one the column axis sees, the shares do not
subtract.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from flymsg import pose
from flymsg.embodiment import ContractError

SCHEMA = "flymsg.optics/v1"
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
    """Column axes in the `eyemap` frame (unit vectors, NaN where no lens)."""

    side: tuple[str, ...]
    p: tuple[int, ...]
    q: tuple[int, ...]
    direction: np.ndarray  # (n, 3)
    source_sha256: str

    @classmethod
    def from_frame(cls, cols: pd.DataFrame, source_sha256: str) -> Columns:
        """From `eye.columns` output: azimuth grows to the fly's right, elevation up, and
        `eyemap` +y is the fly's left, so y = -cos(el) sin(az)."""
        if len(source_sha256) != 64:
            raise ContractError("the column table needs its SHA-256")
        if not set(cols["side"]) <= set(pose.SIDES):
            raise ContractError("column sides must be L or R")
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
    has_direction: np.ndarray  # (columns,)
    angle_deg: np.ndarray  # column axis to sphere centre
    radius_deg: np.ndarray  # sphere angular radius from the column's eye
    radius_rate_deg_s: np.ndarray
    angular_velocity_deg_s: (
        np.ndarray
    )  # (spheres, columns, 3) relative to the eye, world axes
    coverage: np.ndarray
    nearest: np.ndarray  # (columns,) sphere index the axis meets first, -1 none

    def digest(self) -> str:
        h = hashlib.sha256(f"{SCHEMA}:{self.time_us}".encode())
        for name in (
            "has_direction",
            "angle_deg",
            "radius_deg",
            "radius_rate_deg_s",
            "angular_velocity_deg_s",
            "coverage",
            "nearest",
        ):
            h.update(np.ascontiguousarray(getattr(self, name)).tobytes())
        return h.hexdigest()


def _matrix(q: pose.Quat) -> np.ndarray:
    return np.asarray(q.matrix())


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
    sigma = acceptance_deg / FWHM
    r_wb = _matrix(state.pose.orientation)
    body_pos = np.asarray(state.pose.position_m)
    axes = columns.direction @ (r_wb @ _matrix(registration.pose.orientation)).T
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
    return Sample(state.time_us, has, angle, radius, rate, ang_v, cover, nearest)


def coverage_exact(
    angle_deg: float, radius_deg: float, acceptance_deg: float, n: int = 20000
) -> float:
    """Share of a circular Gaussian acceptance profile (on the sphere, FWHM
    `acceptance_deg`, normalised over the sphere) inside a spherical cap of angular radius
    `radius_deg` whose centre is `angle_deg` from the profile's axis; midpoint quadrature
    in the profile's polar angle out to 12 sigma (the rest weighs < 1e-30), the cap's
    azimuthal extent exact."""
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
    if math.sin(a) == 0:
        inside = (
            (alpha <= rho).astype(float)
            if a == 0
            else (alpha >= math.pi - rho).astype(float)
        )
    return float((weight * inside).sum() / weight.sum())
