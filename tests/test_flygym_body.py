"""The FlyGym body adapter and a synthetic closed loop through optics, on NeuroMechFly."""

import dataclasses

import numpy as np
import pandas as pd
import pytest
from test_core import chain

from flymsg import closedloop, optics, pose, sim
from flymsg.embodiment import Clock, ContractError
from flymsg.flygym_body import BODY_EVIDENCE, FlyGymBody
from flymsg.jump3d import DEFAULT
from flymsg.pose import IDENTITY, Pose, Provenance, Registration
from flymsg.runtime import CpuRuntime

PROVENANCE = Provenance("synthetic", "a" * 64, "fixture", 11)
CLOCK = Clock(neural_us=100, body_us=100, control_us=1000)
DURATION_US = 20_000
# test-only registration: no measured eyemap -> body rotation exists (#179)
REG = Registration(Pose("body", "eyemap", (0.0, 0.0, 0.0), IDENTITY), "test identity")
COLUMNS = optics.Columns.from_frame(
    pd.DataFrame(
        {
            "side": ["L", "L", "R", "R"],
            "p": [0, 1, 0, 1],
            "q": [0, 0, 0, 0],
            "azimuth_deg": [-10.0, -40.0, 10.0, 40.0],
            "elevation_deg": [0.0, 10.0, 0.0, 10.0],
        }
    ),
    "b" * 64,
)
# a dark sphere approaching from the front at 0.2 m/s
LOOM = (optics.Sphere("loom", (0.01, 0.0, 0.0008), 0.002, (-0.2, 0.0, 0.0)),)
TTM = (
    "nmf/lm_coxa-lm_trochanterfemur-pitch-motor",
    "nmf/rm_coxa-rm_trochanterfemur-pitch-motor",
)
TORQUE_N_M = 1.5e-7  # synthetic: of the order of jump3d's TTM torque


@pytest.fixture(scope="module")
def settled():
    body = FlyGymBody()
    return body, body.reset()


def test_the_settled_body_stands_on_the_ground(settled):
    body, state = settled
    assert state.time_us == 0
    assert (state.pose.parent, state.pose.child) == ("world", "body")
    assert 0 < state.pose.position_m[2] < 2e-3  # thorax about a millimetre up
    state, contacts = body.step((), 1000)
    assert state.time_us == 1000
    assert any("tarsus" in name and force > 0 for name, force in contacts)
    # total ground reaction of the order of the body weight (about 1 mg)
    weight = sum(f for _, f in contacts)
    assert 1e-6 < weight < 1e-4


def test_bad_steps_refuse(settled):
    body, _ = settled
    with pytest.raises(ContractError, match="whole physics steps"):
        body.step((), 150)
    stranger = pose.ActuatorRef("lift", 0, "N", "toy")
    with pytest.raises(ContractError, match="not an actuator of this body"):
        body.step(((stranger, 1.0),), 100)
    with pytest.raises(ContractError, match="reset the body"):
        FlyGymBody().step((), 100)


def lift(body, commands):
    body.reset()
    for _ in range(5):
        state, _ = body.step(commands, 1000)
    return state


def test_torque_moves_the_body_and_steps_repeat_exactly(settled):
    body, _ = settled
    torque = tuple((body.actuators[n], TORQUE_N_M) for n in TTM)
    rest, pushed, again = lift(body, ()), lift(body, torque), lift(body, torque)
    assert pushed.pose.position_m[2] > rest.pose.position_m[2]
    assert pushed == again


def runtime():
    edges, sign, n = chain([400])
    p = sim.Params()
    return CpuRuntime(
        sim.weight_matrix(edges, sign, n, p.w_syn),
        np.array([0]),
        steps=DURATION_US // CLOCK.neural_us,
        kicks=np.zeros((0, 1), dtype=np.int64),
        p=p,
        per_bin=CLOCK.control_us // CLOCK.neural_us,
        trace=np.array([1]),
    )


def loop(body, arm="intact", replay=None, gain=TORQUE_N_M, **kw):
    stimulus, config = closedloop.optical(
        COLUMNS, REG, pose.flygym_eye_mounts(), LOOM, 8.23
    )
    ttm = tuple(body.actuators[n] for n in TTM)
    return closedloop.run(
        runtime(),
        body,
        input_ids=(1,),
        traced_ids=(2,),
        stimulus=stimulus,
        transducer=lambda s: np.array([400.0 + 4000.0 * max(s)]),
        decoder=lambda spikes: tuple((a, gain * len(spikes)) for a in ttm),
        compiled=body.compiled,
        clock=CLOCK,
        duration_us=DURATION_US,
        arm=arm,
        mode="synthetic",
        evidence={
            **dict.fromkeys(closedloop.COMPONENTS, "synthetic"),
            "body": BODY_EVIDENCE,
        },
        provenance=PROVENANCE,
        optics_config_sha256=config,
        run_identity_sha256="c" * 64,
        input_gap_steps=0,
        replay=replay,
        **kw,
    )


def test_a_closed_loop_through_optics_and_the_body(settled):
    body, _ = settled
    closed = loop(body)
    assert sum(len(t.spikes) for t in closed.ticks) > 0
    assert any(t.commands and t.commands[0][2] > 0 for t in closed.ticks)
    # the stimulus is the optics of the state the tick read
    stimulus, _ = closedloop.optical(COLUMNS, REG, pose.flygym_eye_mounts(), LOOM, 8.23)
    for t in closed.ticks[::50]:
        assert t.stimulus == stimulus(t.time_us, t.state)
    # pose -> retina: the same seed without torque sees another retina once the body moved
    still = loop(body, gain=0.0)
    assert closed.ticks[0].stimulus == still.ticks[0].stimulus
    assert closed.ticks[-1].stimulus != still.ticks[-1].stimulus
    assert closedloop.from_json(closed.to_json()) == closed
    closedloop.replay_parity(closed, loop(body, "replay", replay=closed))
    held = loop(body, "disconnected")
    assert all(t.state.pose == held.ticks[0].state.pose for t in held.ticks)


def test_a_biological_run_on_this_body_refuses():
    with pytest.raises(ContractError, match="measured components"):
        closedloop.require(
            {**dict.fromkeys(closedloop.COMPONENTS, "measured"), "body": BODY_EVIDENCE},
            "biological",
        )


class Fresh(FlyGymBody):
    def reset(self):
        raise AssertionError("a resumed body is restored, not reset")


class Killed(FlyGymBody):
    def step(self, commands, dt_us):
        if self._t_us >= 12_000:
            raise RuntimeError("killed")
        return super().step(commands, dt_us)


def test_a_resumed_flygym_run_equals_the_uninterrupted_one(settled, tmp_path):
    body, _ = settled
    whole = loop(body)
    with pytest.raises(ContractError, match="killed"):
        loop(Killed(), checkpoint_dir=tmp_path, checkpoint_every_us=5000)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "body-10000.npz",
        "loop.json",
        "neural-10000.npz",
        "ticks-10000.json",
        "ticks-5000.json",
    ]
    assert loop(Fresh(), checkpoint_dir=tmp_path, checkpoint_every_us=5000) == whole
    # the same body under another posture gain refuses its checkpoint
    with pytest.raises(ContractError, match="another body construction"):
        Fresh(dataclasses.replace(DEFAULT, posture_kp=40.0)).restore(
            next(tmp_path.glob("body-*.npz"))
        )
