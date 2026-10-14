"""B6 v2: 6-DoF body and eye pose contract (issue #178, gate G1).

Types only: no body is wired, no motor command passes (`motor_map.command` still
refuses every row). M0 v1 (`flymsg.embodiment`) is frozen and unchanged; a v1 record
never parses as v2 and a v2 record never parses as v1.

Frames, all right-handed, SI units (metres, m/s, rad/s), integer microseconds:

- ``world``: FlyGym's world, +z up (gravity along -z), origin on the ground plane.
- ``body``: the thorax root body (NeuroMechFly ``c_thorax``): +x anterior, +y the fly's
  left, +z dorsal. A body pose maps body coordinates to world coordinates.
- ``eye/L``, ``eye/R``: FlyGym's eye cameras (MuJoCo convention): the optical axis is
  -z, image up is +y, image right is +x. A mount maps eye coordinates to body ones.
- ``eyemap``: the Zhao et al. 2025 micro-CT head frame used by `flymsg.eye` (+x front,
  +y left, +z up). Its rotation into ``body`` is not sourced (#84, #179): only an
  explicit `Registration` with a source may connect them; there is no default.

Quaternions are (w, x, y, z), MuJoCo's order, unit norm, and stored canonical (w >= 0).
FlyGym lengths are millimetres; `mm` converts at the boundary and nothing else does.

Clock ordering per body tick [t, t + body_us): sample the sensors from the state at
time t, advance the neural model over the tick, issue the motor command at t + body_us,
then step physics to t + body_us. `state_at` returns the latest state not after the
asked time, so no future pose can enter an earlier neural input.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

from flymsg import embodiment, motor_map
from flymsg.embodiment import CLOCK, Clock, ContractError, integer

SCHEMA = "flymsg.embodiment/v2"
FRAMES = ("world", "body", "eye/L", "eye/R", "eyemap")
SIDES = ("L", "R")
NORM_TOL = 1e-9  # a quaternion further than this from unit norm is refused
MM = 1e-3  # metres per FlyGym millimetre


def mm(value_mm: float) -> float:
    """FlyGym millimetres to contract metres."""
    return value_mm * MM


def _finite(values, name: str) -> tuple[float, ...]:
    out = tuple(float(v) for v in values)
    if not all(math.isfinite(v) for v in out):
        raise ContractError(f"{name} must be finite")
    return out


@dataclass(frozen=True)
class Quat:
    """Unit quaternion (w, x, y, z); construct with `Quat.of` to normalise and check."""

    w: float
    x: float
    y: float
    z: float

    @classmethod
    def of(cls, values) -> Quat:
        values = _finite(values, "quaternion")
        if len(values) != 4:
            raise ContractError("a quaternion has four components (w, x, y, z)")
        w, x, y, z = values
        n = math.sqrt(w * w + x * x + y * y + z * z)
        if abs(n - 1.0) > NORM_TOL:
            raise ContractError(f"quaternion norm {n!r} is not 1")
        if w < 0:  # q and -q are the same rotation; store one
            w, x, y, z = -w, -x, -y, -z
        return cls(w / n, x / n, y / n, z / n)

    def __mul__(self, o: Quat) -> Quat:
        return Quat.of(
            (
                self.w * o.w - self.x * o.x - self.y * o.y - self.z * o.z,
                self.w * o.x + self.x * o.w + self.y * o.z - self.z * o.y,
                self.w * o.y - self.x * o.z + self.y * o.w + self.z * o.x,
                self.w * o.z + self.x * o.y - self.y * o.x + self.z * o.w,
            )
        )

    def inverse(self) -> Quat:
        return Quat.of((self.w, -self.x, -self.y, -self.z))

    def matrix(self) -> tuple[tuple[float, float, float], ...]:
        """Rotation matrix whose columns are the rotated x, y, z axes."""
        cols = [self.rotate(e) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        return tuple(tuple(c[i] for c in cols) for i in range(3))

    def rotate(self, v) -> tuple[float, float, float]:
        p = Quat(0.0, *_finite(v, "vector"))
        r = self._raw(self._raw(self, p), Quat(self.w, -self.x, -self.y, -self.z))
        return (r.x, r.y, r.z)

    @staticmethod
    def _raw(a: Quat, b: Quat) -> Quat:  # product without the unit-norm check
        return Quat(
            a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
            a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
            a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
            a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
        )

    @classmethod
    def from_matrix(cls, m) -> Quat:
        """Rotation matrix (rows) to quaternion; refuses a reflection or a non-rotation."""
        r = [_finite(row, "matrix") for row in m]
        det = (
            r[0][0] * (r[1][1] * r[2][2] - r[1][2] * r[2][1])
            - r[0][1] * (r[1][0] * r[2][2] - r[1][2] * r[2][0])
            + r[0][2] * (r[1][0] * r[2][1] - r[1][1] * r[2][0])
        )
        if abs(det - 1.0) > 1e-6:
            raise ContractError("matrix is not a proper rotation")
        t = r[0][0] + r[1][1] + r[2][2]
        if t > 0:
            s = 2.0 * math.sqrt(t + 1.0)
            q = (
                0.25 * s,
                (r[2][1] - r[1][2]) / s,
                (r[0][2] - r[2][0]) / s,
                (r[1][0] - r[0][1]) / s,
            )
        elif r[0][0] > r[1][1] and r[0][0] > r[2][2]:
            s = 2.0 * math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2])
            q = (
                (r[2][1] - r[1][2]) / s,
                0.25 * s,
                (r[0][1] + r[1][0]) / s,
                (r[0][2] + r[2][0]) / s,
            )
        elif r[1][1] > r[2][2]:
            s = 2.0 * math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2])
            q = (
                (r[0][2] - r[2][0]) / s,
                (r[0][1] + r[1][0]) / s,
                0.25 * s,
                (r[1][2] + r[2][1]) / s,
            )
        else:
            s = 2.0 * math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1])
            q = (
                (r[1][0] - r[0][1]) / s,
                (r[0][2] + r[2][0]) / s,
                (r[1][2] + r[2][1]) / s,
                0.25 * s,
            )
        n = math.sqrt(sum(c * c for c in q))
        return cls.of(tuple(c / n for c in q))


IDENTITY = Quat(1.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Pose:
    """Maps coordinates of frame `child` to frame `parent`: p_parent = R p_child + t."""

    parent: str
    child: str
    position_m: tuple[float, float, float]
    orientation: Quat

    def __post_init__(self) -> None:
        if (
            self.parent not in FRAMES
            or self.child not in FRAMES
            or self.parent == self.child
        ):
            raise ContractError(
                f"unknown or degenerate frame pair {self.parent}<-{self.child}"
            )
        if len(self.position_m) != 3:
            raise ContractError("position must have three components")
        _finite(self.position_m, "position")
        if not isinstance(self.orientation, Quat):
            raise ContractError("orientation must be a Quat")

    def apply(self, point_m) -> tuple[float, float, float]:
        r = self.orientation.rotate(point_m)
        return tuple(a + b for a, b in zip(r, self.position_m, strict=True))

    def direction(self, v) -> tuple[float, float, float]:
        return self.orientation.rotate(v)

    def inverse(self) -> Pose:
        inv = self.orientation.inverse()
        t = inv.rotate(self.position_m)
        return Pose(self.child, self.parent, (-t[0], -t[1], -t[2]), inv)

    def __matmul__(self, inner: Pose) -> Pose:
        """Compose a<-b with b<-c into a<-c; the shared frame must match."""
        if self.child != inner.parent:
            raise ContractError(
                f"cannot compose {self.parent}<-{self.child} with {inner.parent}<-{inner.child}"
            )
        return Pose(
            self.parent,
            inner.child,
            self.apply(inner.position_m),
            self.orientation * inner.orientation,
        )


@dataclass(frozen=True)
class EyeMount:
    """Body <- eye pose of one side, with where it was read."""

    side: str
    pose: Pose
    source: str

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ContractError("side must be L or R")
        if (self.pose.parent, self.pose.child) != ("body", f"eye/{self.side}"):
            raise ContractError("an eye mount maps eye/<side> to body")
        if not self.source:
            raise ContractError("an eye mount needs a source")


def mirror(mount: EyeMount) -> EyeMount:
    """The other side's mount under the body's sagittal mirror (y -> -y).

    The optical axis (-z) and image up (+y) are mirrored by M = diag(1, -1, 1); image
    right (+x) is mirrored and negated, R' = M R diag(-1, 1, 1), so the eye frame stays
    right-handed."""
    r = mount.pose.orientation.matrix()
    m = [
        [-r[0][0], r[0][1], r[0][2]],
        [r[1][0], -r[1][1], -r[1][2]],
        [-r[2][0], r[2][1], r[2][2]],
    ]
    other = "R" if mount.side == "L" else "L"
    x, y, z = mount.pose.position_m
    return EyeMount(
        other,
        Pose("body", f"eye/{other}", (x, -y, z), Quat.from_matrix(m)),
        f"mirror of {mount.side}: {mount.source}",
    )


@dataclass(frozen=True)
class Registration:
    """Body <- eyemap rotation. No sourced value exists yet (#84, #179)."""

    pose: Pose
    source: str

    def __post_init__(self) -> None:
        if (self.pose.parent, self.pose.child) != ("body", "eyemap") or not self.source:
            raise ContractError("a registration maps eyemap to body and needs a source")


@dataclass(frozen=True)
class BodyState:
    """World <- body pose at `time_us`; linear velocity in world, angular in body (the
    MuJoCo free-joint convention)."""

    time_us: int
    pose: Pose
    linear_velocity_m_s: tuple[float, float, float]
    angular_velocity_rad_s: tuple[float, float, float]

    def __post_init__(self) -> None:
        integer(self.time_us, "time_us")
        if (self.pose.parent, self.pose.child) != ("world", "body"):
            raise ContractError("a body state maps body to world")
        for name in ("linear_velocity_m_s", "angular_velocity_rad_s"):
            v = getattr(self, name)
            if len(v) != 3:
                raise ContractError(f"{name} must have three components")
            _finite(v, name)


def eye_pose(state: BodyState, mount: EyeMount) -> Pose:
    """World <- eye pose."""
    return state.pose @ mount.pose


def world_to_eye(state: BodyState, mount: EyeMount) -> Pose:
    """Eye <- world pose: the transform a stimulus point goes through to reach an eye."""
    return eye_pose(state, mount).inverse()


def state_at(states: tuple[BodyState, ...], time_us: int, clock: Clock) -> BodyState:
    """The latest state at or before `time_us`; states are on the body grid and ordered."""
    integer(time_us, "time_us")
    clock.validate()
    if not states:
        raise ContractError("no body state")
    previous = -1
    for s in states:
        if s.time_us <= previous or s.time_us % clock.body_us:
            raise ContractError("states must be strictly ordered on the body grid")
        previous = s.time_us
    eligible = [s for s in states if s.time_us <= time_us]
    if not eligible:
        raise ContractError("no body state at or before the asked time")
    return eligible[-1]


@dataclass(frozen=True)
class ActuatorRef:
    """A compiled MuJoCo actuator, by name and id, in the motor map."""

    name: str
    mujoco_id: int
    unit: str

    def __post_init__(self) -> None:
        integer(self.mujoco_id, "mujoco_id")
        if not self.name or self.unit not in ("N", "N*m", "rad"):
            raise ContractError("an actuator needs a name and a unit in N, N*m or rad")


def command(actuator: ActuatorRef, compiled: dict[str, int]) -> None:
    """Refuse unless the compiled model has this actuator under this id and the motor
    map has a published row for it; the motor map refuses every row today."""
    if compiled.get(actuator.name) != actuator.mujoco_id:
        raise ContractError(
            f"{actuator.name} is not compiled actuator {actuator.mujoco_id}"
        )
    try:
        motor_map.command(actuator.name)
    except motor_map.MotorMapError as err:
        raise ContractError(str(err)) from err


@dataclass(frozen=True)
class Provenance(embodiment.Provenance):
    schema: str = SCHEMA

    def validate(self) -> None:
        if self.schema != SCHEMA or self.clock != CLOCK:
            raise ContractError("incompatible contract or clock")
        embodiment.Provenance.validate(
            embodiment.Provenance(
                self.dataset, self.dataset_sha256, self.commit, self.seed
            )
        )


@dataclass(frozen=True)
class Trace:
    provenance: Provenance
    clock: Clock
    mounts: tuple[EyeMount, ...]
    states: tuple[BodyState, ...]

    def validate(self) -> None:
        self.provenance.validate()
        self.clock.validate()
        if sorted(m.side for m in self.mounts) != list(SIDES):
            raise ContractError("a trace needs exactly one mount per eye")
        if self.states:
            state_at(self.states, self.states[-1].time_us, self.clock)

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def _pose(d: dict) -> Pose:
    return Pose(
        d["parent"],
        d["child"],
        tuple(d["position_m"]),
        Quat.of(tuple(d["orientation"].values())),
    )


def from_json(text: str) -> Trace:
    """Parse a v2 trace; any other schema, clock or a missing field refuses."""
    try:
        d = json.loads(text)
        p = d["provenance"]
        if p.get("schema") != SCHEMA or p.get("clock") != CLOCK:
            raise ContractError("not a flymsg.embodiment/v2 trace")
        trace = Trace(
            Provenance(**p),
            Clock(**d["clock"]),
            tuple(
                EyeMount(m["side"], _pose(m["pose"]), m["source"]) for m in d["mounts"]
            ),
            tuple(
                BodyState(
                    s["time_us"],
                    _pose(s["pose"]),
                    tuple(s["linear_velocity_m_s"]),
                    tuple(s["angular_velocity_rad_s"]),
                )
                for s in d["states"]
            ),
        )
    except ContractError:
        raise
    except (KeyError, TypeError, ValueError) as err:
        raise ContractError(f"malformed v2 trace: {err!r}") from err
    trace.validate()
    return trace


def flygym_eye_mounts() -> tuple[EyeMount, EyeMount]:
    """Body <- eye mounts read from FlyGym 2.1.0's NeuroMechFly vision cameras.

    Compiled with ``fusestatic`` off: with FlyGym's default (on) MuJoCo fuses the static
    head and eye bodies into the thorax and both cameras land on the thorax origin, 0.23 mm behind,
    0.38 mm medial to and 0.02 mm below the eyes (0.44 mm; the orientation survives). The head is rigid
    in this skeleton, so the mounts are fixed in the body frame."""
    import mujoco
    from flygym.anatomy import AxisOrder, JointPreset, Skeleton
    from flygym.compose import KinematicPosePreset, NeuroMechFly

    fly = NeuroMechFly()
    fly.add_joints(
        Skeleton(
            axis_order=AxisOrder.YAW_PITCH_ROLL,
            joint_preset=JointPreset.LEGS_ACTIVE_ONLY,
        ),
        neutral_pose=KinematicPosePreset.NEUTRAL,
    )
    fly.add_vision()
    spec = fly.mjcf_root.copy()
    spec.compiler.fusestatic = False
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"{fly.name}/c_thorax")
    if root < 0:
        root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "c_thorax")
    body = Pose(
        "world",
        "body",
        tuple(mm(v) for v in data.xpos[root]),
        Quat.of(tuple(data.xquat[root])),
    )
    mounts = []
    for side, cam in (("L", "l_eye_cam_camera"), ("R", "r_eye_cam_camera")):
        cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, f"{fly.name}/{cam}")
        if cid < 0:
            cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, cam)
        world_eye = Pose(
            "world",
            f"eye/{side}",
            tuple(mm(v) for v in data.cam_xpos[cid]),
            Quat.from_matrix(data.cam_xmat[cid].reshape(3, 3)),
        )
        mounts.append(
            EyeMount(
                side,
                body.inverse() @ world_eye,
                "FlyGym 2.1.0 NeuroMechFly vision.yaml, compiled without fusestatic",
            )
        )
    return mounts[0], mounts[1]
