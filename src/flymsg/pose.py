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
time t, advance the neural model over the tick, then step physics to t + body_us under the
command held since the last control tick. Motor events aggregate at control ticks once
their latency has passed, as in M0 v1 (`embodiment.run_fixture`). `state_at` returns the latest state not after the
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


def _hamilton(a, b) -> tuple[float, float, float, float]:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _canonical(q) -> tuple[float, float, float, float]:
    """q and -q are one rotation: store the one whose first nonzero component is
    positive, with no negative zeros."""
    for c in q:
        if c != 0:
            sign = 1.0 if c > 0 else -1.0
            return tuple(sign * v + 0.0 for v in q)
    return tuple(v + 0.0 for v in q)


@dataclass(frozen=True)
class Quat:
    """Unit quaternion (w, x, y, z) in canonical sign. Direct construction checks and
    never rescales, so a stored quaternion parses back bit for bit; `Quat.of`
    normalises a computed one first."""

    w: float
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        q = (self.w, self.x, self.y, self.z)
        if not all(type(c) is float and math.isfinite(c) for c in q):
            raise ContractError("quaternion components must be finite floats")
        n = math.sqrt(sum(c * c for c in q))
        if abs(n - 1.0) > NORM_TOL:
            raise ContractError(f"quaternion norm {n!r} is not 1")
        if _canonical(q) != q:
            raise ContractError("quaternion is not in canonical sign")

    @classmethod
    def of(cls, values) -> Quat:
        values = _finite(values, "quaternion")
        if len(values) != 4:
            raise ContractError("a quaternion has four components (w, x, y, z)")
        n = math.sqrt(sum(c * c for c in values))
        if abs(n - 1.0) > NORM_TOL:
            raise ContractError(f"quaternion norm {n!r} is not 1")
        return cls(*_canonical(tuple(c / n for c in values)))

    def components(self) -> tuple[float, float, float, float]:
        return (self.w, self.x, self.y, self.z)

    def __mul__(self, o: Quat) -> Quat:
        return Quat.of(_hamilton(self.components(), o.components()))

    def inverse(self) -> Quat:
        return Quat.of((self.w, -self.x, -self.y, -self.z))

    def matrix(self) -> tuple[tuple[float, float, float], ...]:
        """Rotation matrix whose columns are the rotated x, y, z axes."""
        cols = [self.rotate(e) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        return tuple(tuple(c[i] for c in cols) for i in range(3))

    def rotate(self, v) -> tuple[float, float, float]:
        q = self.components()
        conj = (self.w, -self.x, -self.y, -self.z)
        r = _hamilton(_hamilton(q, (0.0, *_finite(v, "vector"))), conj)
        return (r[1], r[2], r[3])

    @classmethod
    def from_matrix(cls, m) -> Quat:
        """Rotation matrix (rows) to quaternion; refuses a reflection or a non-rotation."""
        r = [_finite(row, "matrix") for row in m]
        if len(r) != 3 or any(len(row) != 3 for row in r):
            raise ContractError("a rotation matrix is 3 x 3")
        for i in range(3):
            for j in range(3):
                dot = sum(r[k][i] * r[k][j] for k in range(3))
                if abs(dot - (i == j)) > 1e-6:
                    raise ContractError("matrix is not orthonormal")
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
        position = _finite(self.position_m, "position")
        if len(position) != 3:
            raise ContractError("position must have three components")
        object.__setattr__(self, "position_m", position)  # stored as a float tuple
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
            v = _finite(getattr(self, name), name)
            if len(v) != 3:
                raise ContractError(f"{name} must have three components")
            object.__setattr__(self, name, v)


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
    """A compiled MuJoCo actuator, by name and id, with the unit of its control and the
    model it was compiled from. Whether a neuron may drive it is the motor map's call
    (its rows carry the source and status); neurons stay MaleCNS bodyIds, as in v1."""

    name: str
    mujoco_id: int
    unit: str
    source: str

    def __post_init__(self) -> None:
        integer(self.mujoco_id, "mujoco_id")
        if not self.name or self.unit not in ("N", "N*m", "rad", "m/s", "rad/s"):
            raise ContractError(
                "an actuator needs a name and a unit in N, N*m, rad, m/s or rad/s"
            )
        if not self.source:
            raise ContractError("an actuator needs the model it was compiled from")


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
    q = d["orientation"]
    if set(q) != set("wxyz"):
        raise ContractError("orientation needs exactly w, x, y, z")
    # direct construction: a stored quaternion is checked, never rescaled
    return Pose(
        d["parent"], d["child"], tuple(d["position_m"]), Quat(*(q[k] for k in "wxyz"))
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
    except (AttributeError, KeyError, TypeError, ValueError) as err:
        raise ContractError(f"malformed v2 trace: {err!r}") from err
    trace.validate()
    return trace


def flygym_eye_mounts() -> tuple[EyeMount, EyeMount]:
    """Body <- eye mounts read from FlyGym 2.1.0's NeuroMechFly vision cameras.

    Compiled with ``fusestatic`` off. FlyGym's default (on) fuses the rigid head and eye
    bodies into their parent: in a simulation, with the fly on a free joint, both cameras
    land on the thorax origin, 0.23 mm behind, 0.38 mm medial to and 0.02 mm below the
    eyes (0.44 mm; the orientation survives). The head is rigid in this skeleton, so the
    mounts are fixed in the body frame."""
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

    def find(kind, name: str) -> int:
        i = mujoco.mj_name2id(model, kind, name)
        if i < 0:
            raise ContractError(f"FlyGym model has no {name}")
        return i

    root = find(mujoco.mjtObj.mjOBJ_BODY, "c_thorax")
    body = Pose(
        "world",
        "body",
        tuple(mm(v) for v in data.xpos[root]),
        Quat.of(tuple(data.xquat[root])),
    )
    mounts = []
    for side, cam in (("L", "l_eye_cam_camera"), ("R", "r_eye_cam_camera")):
        cid = find(mujoco.mjtObj.mjOBJ_CAMERA, cam)
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
