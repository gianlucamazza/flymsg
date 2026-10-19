"""Kinematic planar body behind `closedloop.Body` (DN-arena ADR).

Integrate yaw rate (`rad/s`) and forward speed (`m/s`) on the plane. Emit B6 v2
`pose.BodyState`; schema stays `flymsg.embodiment/v2`. _z_, roll and pitch are
caller-supplied constants (the lock will name them; this module invents none).
SI units. No MuJoCo. `snapshot` / `restore` match what `closedloop.run` asks of
`FlyGymBody` when `checkpoint_dir` is set.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from flymsg import pose
from flymsg.closedloop import Command, Contact
from flymsg.embodiment import ContractError, integer

BODY_EVIDENCE = "synthetic"


def _finite(value, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ContractError(f"{name} must be finite")
    return out


def _axis(angle: float, axis: str) -> pose.Quat:
    half = angle / 2.0
    c, s = math.cos(half), math.sin(half)
    if axis == "x":
        return pose.Quat.of((c, s, 0.0, 0.0))
    if axis == "y":
        return pose.Quat.of((c, 0.0, s, 0.0))
    return pose.Quat.of((c, 0.0, 0.0, s))


class Arena:
    """Planar integrator: `yaw` in rad/s, `forward` in m/s."""

    def __init__(self, *, z_m: float, roll_rad: float, pitch_rad: float, source: str):
        if not source:
            raise ContractError(
                "an arena needs the kinematic model it was compiled from"
            )
        self.z_m = _finite(z_m, "z_m")
        self.roll_rad = _finite(roll_rad, "roll_rad")
        self.pitch_rad = _finite(pitch_rad, "pitch_rad")
        self.source = source
        self._identity = (
            f"{source}; kinematic planar; z_m {self.z_m!r}; "
            f"roll_rad {self.roll_rad!r}; pitch_rad {self.pitch_rad!r}"
        )
        self.actuators = {
            "yaw": pose.ActuatorRef("yaw", 0, "rad/s", source),
            "forward": pose.ActuatorRef("forward", 1, "m/s", source),
        }
        self.compiled = {name: a.mujoco_id for name, a in self.actuators.items()}
        self._tilt = _axis(self.pitch_rad, "y") * _axis(self.roll_rad, "x")
        self._ready = False

    def reset(self) -> pose.BodyState:
        self._t_us = 0
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._v = 0.0
        self._omega = 0.0
        self._ready = True
        return self._state()

    def step(
        self, commands: tuple[Command, ...], dt_us: int
    ) -> tuple[pose.BodyState, tuple[Contact, ...]]:
        integer(dt_us, "dt_us", 1)
        if not self._ready:
            raise ContractError("reset the body before stepping it")
        omega, speed = 0.0, 0.0
        for actuator, value in commands:
            if self.actuators.get(actuator.name) != actuator:
                raise ContractError(f"{actuator.name} is not an actuator of this body")
            value = _finite(value, actuator.name)
            if actuator.name == "yaw":
                omega = value
            else:
                speed = value
        dt = dt_us / 1e6
        yaw0 = self._yaw
        yaw1 = yaw0 + omega * dt
        if omega == 0.0:
            self._x += speed * math.cos(yaw0) * dt
            self._y += speed * math.sin(yaw0) * dt
        else:
            self._x += speed / omega * (math.sin(yaw1) - math.sin(yaw0))
            self._y -= speed / omega * (math.cos(yaw1) - math.cos(yaw0))
        self._yaw, self._v, self._omega = yaw1, speed, omega
        self._t_us += dt_us
        return self._state(), ()

    def snapshot(self, path: Path) -> None:
        """Clock, planar pose, held command and construction, atomically."""
        temporary = path.with_name(path.name + ".tmp")
        try:
            with temporary.open("wb") as stream:
                np.savez(
                    stream,
                    t_us=np.int64(self._t_us),
                    x=np.float64(self._x),
                    y=np.float64(self._y),
                    yaw=np.float64(self._yaw),
                    v=np.float64(self._v),
                    omega=np.float64(self._omega),
                    identity=np.array(self._identity),
                )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def restore(self, path: Path) -> None:
        with np.load(path, allow_pickle=False) as saved:
            identity = str(saved["identity"])
            t_us = int(saved["t_us"])
            x, y, yaw = float(saved["x"]), float(saved["y"]), float(saved["yaw"])
            v, omega = float(saved["v"]), float(saved["omega"])
        if identity != self._identity:
            raise ContractError("the body checkpoint is of another body construction")
        self._t_us, self._x, self._y, self._yaw = t_us, x, y, yaw
        self._v, self._omega = v, omega
        self._ready = True

    def _state(self) -> pose.BodyState:
        orientation = _axis(self._yaw, "z") * self._tilt
        return pose.BodyState(
            self._t_us,
            pose.Pose("world", "body", (self._x, self._y, self.z_m), orientation),
            (self._v * math.cos(self._yaw), self._v * math.sin(self._yaw), 0.0),
            orientation.inverse().rotate((0.0, 0.0, self._omega)),
        )
