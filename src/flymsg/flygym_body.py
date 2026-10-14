"""FlyGym's NeuroMechFly behind the closed-loop body adapter (body-wiring ADR, #180).

`closedloop.Body` over the body of `jump3d.build`: FlyGym 2.1.0's NeuroMechFly on flat
ground, the two mesothoracic coxa-trochanter pitch hinges driven by torque, every other
active leg joint held by a position actuator at FlyGym's demo gain (jump3d's named
compensation). The adapter only converts and steps:

- units at the boundary: FlyGym's g, mm, s to SI (lengths and linear velocities through
  `pose.mm`, forces × 1e-6 N, torques × 1e-9 N·m); angles in rad on both sides;
- state: the thorax root (`c_thorax`, the free joint's body) as a `pose.BodyState`, read
  from the free joint's `qpos`/`qvel` (after `mj_step`, `xpos`/`xquat` still hold the pose
  before the last step), linear velocity in world and angular velocity in body;
- time: 0 at the end of the settling period, then exactly the stepped microseconds;
- commands: every step starts from the neutral controls of the settled body and writes the
  commanded actuators, so an actuator left out of a command returns to neutral (no torque, or
  the neutral posture); the held command is the caller's, as the ADR fixes;
- contacts: the normal force of every contact between a fly body and the ground, summed per
  fly body and named by its MuJoCo body name, as MuJoCo left them: those of the last physics
  substep, computed at its start, not an average over the body tick.

No motor neuron reaches an actuator here: `pose.command` still refuses every row, so a run
with this body is synthetic (`BODY_EVIDENCE`).
"""

from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np

from flymsg import jump3d, pose
from flymsg.closedloop import Command, Contact
from flymsg.embodiment import ContractError, integer

# The body is measured anatomy, but its posture gain and torque-driven hinges are chosen
BODY_EVIDENCE = "engineered"
TORQUE_N_M = 1e-9  # one FlyGym torque unit, g mm^2 s^-2, in N*m
FORCE_N = 1e-6  # one FlyGym force unit, g mm s^-2, in N


class FlyGymBody:
    def __init__(self, cfg: jump3d.BodyConfig = jump3d.DEFAULT):
        self.cfg = cfg
        self.fly, self.sim = jump3d.build(cfg)
        m = self.sim.mj_model
        self.timestep_us = round(cfg.timestep_s * 1e6)
        if self.timestep_us <= 0 or abs(self.timestep_us - cfg.timestep_s * 1e6) > 1e-6:
            raise ContractError("the physics timestep must be whole microseconds")
        if m.jnt_type[0] != mujoco.mjtJoint.mjJNT_FREE:
            raise ContractError("the body's root is not a free joint")
        if m.jnt_qposadr[0] != 0 or m.jnt_dofadr[0] != 0 or any(m.jnt_pos[0]):
            raise ContractError(
                "the root free joint must lead qpos and sit at its body"
            )
        # the ground plane belongs to the world body
        self._ground = {i for i in range(m.ngeom) if m.geom_bodyid[i] == 0}
        source = f"FlyGym 2.1.0 NeuroMechFly, flymsg.jump3d.build({cfg!r})"
        self._identity = f"{source}; mujoco {mujoco.__version__}; nq {m.nq}; nu {m.nu}"
        self.actuators = {}
        for i in range(m.nu):
            name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
            units = {"position": "rad", "motor": "N*m"}
            unit = units.get(name.rsplit("-", 1)[-1])
            if unit is None or m.actuator_gear[i, 0] != 1.0:
                raise ContractError(f"{name} is not a unit-gear position or motor")
            self.actuators[name] = pose.ActuatorRef(name, i, unit, source)
        self.compiled = {name: a.mujoco_id for name, a in self.actuators.items()}
        self._neutral = None
        self._t_us = 0

    def reset(self) -> pose.BodyState:
        self.sim.reset()
        for _ in range(round(self.cfg.settle_ms * 1000 / self.timestep_us)):
            self.sim.step()
        self._neutral = self.sim.mj_data.ctrl.copy()
        self._t_us = 0
        return self._state()

    def step(
        self, commands: tuple[Command, ...], dt_us: int
    ) -> tuple[pose.BodyState, tuple[Contact, ...]]:
        integer(dt_us, "dt_us", 1)
        if self._neutral is None:
            raise ContractError("reset the body before stepping it")
        if dt_us % self.timestep_us:
            raise ContractError("a body tick must be whole physics steps")
        ctrl = self._neutral.copy()
        for actuator, value in commands:
            if self.actuators.get(actuator.name) != actuator:
                raise ContractError(f"{actuator.name} is not an actuator of this body")
            ctrl[actuator.mujoco_id] = (
                value / TORQUE_N_M if actuator.unit == "N*m" else value
            )
        data = self.sim.mj_data
        data.ctrl[:] = ctrl
        for _ in range(dt_us // self.timestep_us):
            self.sim.step()
        self._t_us += dt_us
        return self._state(), self._contacts()

    def snapshot(self, path: Path) -> None:
        """The full integration state, the clock and the neutral controls, atomically."""
        m, d = self.sim.mj_model, self.sim.mj_data
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(m, spec))
        mujoco.mj_getState(m, d, state, spec)
        temporary = path.with_name(path.name + ".tmp")
        try:
            with temporary.open("wb") as stream:
                np.savez(
                    stream,
                    state=state,
                    t_us=np.int64(self._t_us),
                    neutral=self._neutral,
                    identity=np.array(self._identity),
                )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def restore(self, path: Path) -> None:
        m, d = self.sim.mj_model, self.sim.mj_data
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        with np.load(path, allow_pickle=False) as saved:
            state, t_us, neutral = saved["state"], int(saved["t_us"]), saved["neutral"]
            identity = str(saved["identity"])
        if identity != self._identity:
            raise ContractError("the body checkpoint is of another body construction")
        if state.shape != (mujoco.mj_stateSize(m, spec),) or neutral.shape != (m.nu,):
            raise ContractError("the body checkpoint is not of this model")
        mujoco.mj_resetData(m, d)
        mujoco.mj_setState(m, d, state, spec)
        self._t_us, self._neutral = t_us, neutral.copy()

    def _state(self) -> pose.BodyState:
        d = self.sim.mj_data
        return pose.BodyState(
            self._t_us,
            pose.Pose(
                "world",
                "body",
                tuple(pose.mm(float(v)) for v in d.qpos[0:3]),
                pose.Quat.of(tuple(float(v) for v in d.qpos[3:7])),
            ),
            tuple(pose.mm(float(v)) for v in d.qvel[0:3]),
            tuple(float(v) for v in d.qvel[3:6]),
        )

    def _contacts(self) -> tuple[Contact, ...]:
        m, d = self.sim.mj_model, self.sim.mj_data
        wrench = np.zeros(6)
        total: dict[str, float] = {}
        for i in range(d.ncon):
            c = d.contact[i]
            if c.exclude:
                continue
            g1, g2 = int(c.geom1), int(c.geom2)
            if (g1 in self._ground) == (g2 in self._ground):
                continue
            fly_geom = g2 if g1 in self._ground else g1
            body = mujoco.mj_id2name(
                m, mujoco.mjtObj.mjOBJ_BODY, m.geom_bodyid[fly_geom]
            )
            mujoco.mj_contactForce(m, d, i, wrench)
            total[body] = total.get(body, 0.0) + float(wrench[0]) * FORCE_N
        return tuple(sorted(total.items()))
