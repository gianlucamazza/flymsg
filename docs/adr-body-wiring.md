# ADR: wiring a 3D body through B6 v2

Status: proposed, 2026-10-14. Needs the user's acceptance before an actual body is wired
([#178](https://github.com/gianlucamazza/flymsg/issues/178)).
Scope: the G5 closed loop ([#180](https://github.com/gianlucamazza/flymsg/issues/180)) of the
[sensorimotor plan](sensorimotor-environment-plan.md); supplements the accepted
[architecture](architecture.md), [runtime](runtime.md) and
[run integrity](adr-run-integrity.md) decisions without editing them.

## Context

M0 v1 (`flymsg.embodiment/v1`) couples a scalar point mass to motor events and is frozen. B6
v2 (`flymsg.pose`, G1) types world, body and eye frames, body states and compiled actuators
but wires no body. G2 (`flymsg.optics`) turns a pose and dark spheres into per-column
geometry on the measured MaleCNS columns; the micro-CT → NeuroMechFly head registration is
unmeasured. M2 (`flymsg.loop`) closes a loop with an engineered looming transducer and an
engineered force decoder on a one-axis body. `validation/motor_map.yaml` maps none of the 59
NeuroMechFly actuators, so `motor_map.command` and `pose.command` refuse every command
([embodiment](embodiment.md)).

A 3D body can be attached in several ways, and each fixes what a later result can mean: which
clock decides, whether a pose can reach an earlier neural input, and what a run does when a
component has no evidence. This decision fixes that before any body is wired.

## Decision

1. **One scheduler.** The existing `embodiment.Clock` (integer microseconds, neural tick =
   `sim.Params.dt`, body tick, control tick, latency on the neural grid) drives the run. The
   body integrates only the steps the scheduler asks for; no physics engine, renderer or
   headset clock decides when the neural model advances.
2. **A body adapter, not a body inside the loop.** A body is a v2 adapter with `reset() →
pose.BodyState` and `step(commands, dt_us) → (pose.BodyState, contacts)`, where commands
   are `(pose.ActuatorRef, value)` pairs in the actuator's unit and contacts are named normal
   forces in newtons. A FlyGym/NeuroMechFly adapter sits behind it; any adapter exception
   aborts the run as a `ContractError`, as in M0.
3. **Causal order per control tick T** (period [T, T + control)):
   1. _command_: aggregate the spikes of earlier periods whose time + latency ≤ T into
      actuator commands through `motor_map`; at T = 0 the command is empty;
   2. _sample_: read the body state at T with `pose.state_at` (never a later one);
   3. _stimulus_: project the world at T onto the columns with `optics.sample`;
   4. _input_: a transducer turns the stimulus into seeded input counts for the neural steps
      of [T, T + control); the counts are recorded;
   5. _neural_: `CpuRuntime` advances to T + control;
   6. _physics_: the body steps in body ticks over [T, T + control) under the command of
      step 1, held.

   Steps 5 and 6 do not read each other within a period; a spike can move the body at the
   earliest one control period later. No pose, contact or spike later than T enters the input
   of [T, T + control).

4. **Evidence fails closed.** Every component (optics registration, transducer, motor map,
   body) carries a status: `measured`, `engineered`, `unmapped` or `synthetic`. A
   _biological_ run refuses unless every component is `measured`; today none of the transducer,
   the registration or the motor map is, so a biological run refuses. A _synthetic_ run is
   allowed, carries its statuses in its record and supports no claim about the fly.
5. **Arms.** Intact (closed loop), disconnected (input computed from a body held at its initial
   pose), shuffled (the disconnected input in a seeded random order), replay (the exact
   recorded input counts, no feedback) and silenced (named neurons silenced). Each arm records
   its random input counts. A replay must reproduce the original spikes exactly; anything else
   is a failure, not a tolerance.
6. **One record.** A versioned `flymsg.closedloop/v1` record holds, per control tick, the body
   state, per-column stimulus, input counts, spikes (MaleCNS bodyIds), actuator commands and
   contacts; and once, the arm, mode, component evidence, clock, seed, optics configuration
   hash and run identity (`runstore`). It serialises to canonical JSON, parses back identically
   and never parses as a v1 or v2 embodiment trace or the reverse.

## Invariants

- No change to M0 v1, `sim.Params`, `CpuRuntime` numerics, archived protocols and results or
  B4 manifests. M0 v1 and B6 v2 records keep parsing exactly as before.
- No artificial gain, learned controller, force boost or enlarged body motion to manufacture
  a closed-loop effect. Equal closed and disconnected results are reported as observed.
- No guessed transfer function or actuator row: an unmeasured one stays `unmapped` or
  `engineered`, and the biological run refuses.
- Rendering on or off changes no number: the loop takes no renderer input.

## Consequences

- G5 code can be written and tested now on synthetic components (a toy circuit on
  `CpuRuntime`, a toy body): the schedule, the refusal, the record and replay parity.
- A FlyGym adapter is added only after this ADR is accepted, behind the adapter protocol, and
  runs biologically only when G3 (measured transduction, #84/#97/#140) and G4 (measured motor
  map, #19/#35) exist. Until then its runs are synthetic.
- Sampling the stimulus once per control tick bounds the visual update rate by the control
  period; a finer optical sampling is a new clock, not a hidden resampling.
- M2 (`flymsg.loop`) stays as recorded; it is not migrated to this record.

## Alternatives

| Alternative                                         | Problem                                                                          | Verdict  |
| --------------------------------------------------- | -------------------------------------------------------------------------------- | -------- |
| Let FlyGym's simulation loop call the neural model  | The physics timestep decides neural timing; a second scheduler                   | Rejected |
| Couple through a MuJoCo control callback            | Hidden ordering inside the physics step; poses can leak into the same step input | Rejected |
| Reuse M0 v1 `BodyState`/`MotorCommand` for 3D       | Scalar position and force silently stand for a 6-DoF articulated body            | Rejected |
| Fill unmapped actuators or transducers with a guess | A run that looks biological without evidence                                     | Rejected |
| FlyBody instead of NeuroMechFly                     | Undecided (#35); the adapter protocol admits either                              | Deferred |
| Adapter behind B6 v2 and the existing clock         | Biological runs wait for G3 and G4                                               | Adopted  |

## Acceptance

- The schedule lists command, sample, stimulus, input, neural and physics steps in the order
  above; a test refuses a misordered or off-grid event and any pose later than its tick.
- A biological run with any non-`measured` component refuses before the first neural step.
- Bad frames, units, timestamps, missing maps and body adapter exceptions refuse.
- The record round-trips bit for bit; a replay reproduces the original spikes; disconnected
  and shuffled arms keep the recorded input counts.
- M0 v1, B6 v2 and `CpuRuntime` tests unchanged; full CI green.
