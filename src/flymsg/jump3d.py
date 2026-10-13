"""A TTM-driven jump of the NeuroMechFly body in MuJoCo (issues #90, #94).

TTMn spikes from the connectome model drive the tergotrochanteral muscle of each side
(`flymsg.ttm`, measured twitch), which acts on the mesothoracic coxa-trochanter joint of
FlyGym's NeuroMechFly (Wang-Chen et al. 2024; FlyGym v2.1.0, a female body from micro-CT).
The run is open loop: the spikes are recorded first, then replayed into the body, which
does not feed back. The body steps at 0.1 ms, the neural step.

Named compensations: the posture of the other leg joints is held by FlyGym's position
actuators at its demo gain; the muscle's moment arm is fixed at the stance posture (the
torque that turns the twitch force at the distal tarsus into a joint torque); only the TTM
acts, not the femur-tibia extensor; the body is female, the connectome male.
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np
from flygym import Simulation
from flygym.anatomy import AxisOrder, JointPreset, Skeleton
from flygym.compose import (
    ActuatorType,
    FlatGroundWorld,
    KinematicPosePreset,
    NeuroMechFly,
)
from flygym.utils.math import Rotation3D

from flymsg import ttm

GRAVITY_MM_S2 = 9810.0  # FlyGym units: g, mm, s
SIDES = ("lm", "rm")  # left and right mesothoracic legs


@dataclass(frozen=True)
class BodyConfig:
    posture_kp: float = 45.0  # FlyGym demo gain (complex_terrain), a named compensation
    spawn_height_mm: float = 0.7
    settle_ms: float = 200.0
    timestep_s: float = 1e-4


DEFAULT = BodyConfig()


def build(cfg: BodyConfig = DEFAULT):
    """NeuroMechFly with its active leg joints; every joint but the two mesothoracic
    coxa-trochanter pitch hinges held at the neutral pose; those two driven by torque."""
    fly = NeuroMechFly()
    skel = Skeleton(
        axis_order=AxisOrder.YAW_PITCH_ROLL, joint_preset=JointPreset.LEGS_ACTIVE_ONLY
    )
    joints = fly.add_joints(skel, neutral_pose=KinematicPosePreset.NEUTRAL)
    ttm_dofs = [
        d
        for d in joints
        if d.parent.name in ("lm_coxa", "rm_coxa") and d.axis.value == "pitch"
    ]
    posture = [d for d in joints if d not in ttm_dofs]
    fly.add_actuators(
        posture,
        ActuatorType.POSITION,
        neutral_input=KinematicPosePreset.NEUTRAL,
        kp=cfg.posture_kp,
    )
    fly.add_actuators(ttm_dofs, ActuatorType.MOTOR, forcelimited=False)
    world = FlatGroundWorld()
    world.add_fly(
        fly, np.array([0.0, 0.0, cfg.spawn_height_mm]), Rotation3D("quat", (1, 0, 0, 0))
    )
    return fly, Simulation(world, timestep=cfg.timestep_s)


def _ids(model) -> tuple[dict, dict, int]:
    joint_names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) or ""
        for i in range(model.njnt)
    ]
    body_names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or ""
        for i in range(model.nbody)
    ]
    joint = {
        s: next(
            i
            for i, n in enumerate(joint_names)
            if n.endswith(f"{s}_coxa-{s}_trochanterfemur-pitch")
        )
        for s in SIDES
    }
    tarsus = {
        s: next(i for i, n in enumerate(body_names) if n.endswith(f"{s}_tarsus1"))
        for s in SIDES
    }
    thorax = next(i for i, n in enumerate(body_names) if n.endswith("c_thorax"))
    return joint, tarsus, thorax


def moment_arms(model, data, joint: dict, tarsus: dict) -> dict:
    """Torque per unit downward force at the distal tarsus, at the current posture:
    the joint's column of the point Jacobian dotted with (0, 0, -1)."""
    jac = np.zeros((3, model.nv))
    out = {}
    for s in SIDES:
        mujoco.mj_jacBody(model, data, jac, None, tarsus[s])
        out[s] = float(jac[:, model.jnt_dofadr[joint[s]]] @ np.array([0.0, 0.0, -1.0]))
    return out


def jump(spikes_ms: dict, duration_ms: float, cfg: BodyConfig = DEFAULT) -> dict:
    """Settle the body, then replay the TTMn spike trains (`spikes_ms` per side, ms after
    the start of the replay) as TTM torques. Returns the takeoff time and the thorax
    velocity at takeoff (all legs off the ground), and the drag-free ballistic range."""
    fly, sim = build(cfg)
    model, data = sim.mj_model, sim.mj_data
    joint, tarsus, thorax = _ids(model)
    sim.reset()
    for _ in range(round(cfg.settle_ms / 1000.0 / cfg.timestep_s)):
        sim.step()
    arms = moment_arms(model, data, joint, tarsus)
    t0 = data.time
    steps = round(duration_ms / 1000.0 / cfg.timestep_s)
    t_ms = np.arange(steps) * cfg.timestep_s * 1000.0
    force_un = {s: ttm.force(spikes_ms.get(s, []), t_ms) * 1e6 for s in SIDES}
    z0 = float(data.xpos[thorax, 2])
    takeoff, velocity = None, None
    prev = data.xpos[thorax].copy()
    for i in range(steps):
        tau = np.array([arms[s] * force_un[s][i] for s in SIDES])
        sim.set_actuator_inputs(fly.name, ActuatorType.MOTOR, tau)
        sim.step()
        pos = data.xpos[thorax].copy()
        if takeoff is None and not sim.get_ground_contact_info(fly.name)[0].any():
            takeoff = (data.time - t0) * 1000.0
            velocity = (pos - prev) / cfg.timestep_s  # mm/s
        prev = pos
    out = {"takeoff_ms": takeoff, "thorax_rise_mm": float(data.xpos[thorax, 2]) - z0}
    if velocity is None:
        return out | {"velocity_m_s": None, "range_mm": 0.0}
    horizontal = float(np.hypot(velocity[0], velocity[1]))
    vertical = float(velocity[2])
    return out | {
        "velocity_m_s": [float(v) / 1000.0 for v in velocity],
        "range_mm": max(0.0, 2.0 * horizontal * vertical / GRAVITY_MM_S2),
    }
