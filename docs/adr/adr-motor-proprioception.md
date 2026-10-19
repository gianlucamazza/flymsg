# ADR: motor output and proprioceptive return for NeuroMechFly

Status: **proposed**, 2026-10-20. Awaiting owner acceptance. It changes no code in
this commit and authorizes no lock or run.

Scope: the two interfaces a closed loop needs between the MaleCNS connectome and the
NeuroMechFly body: motor-neuron spikes to actuator commands, and body state back to
sensory neurons. It supplements the accepted [body-wiring](adr-body-wiring.md),
[embodiment](embodiment.md), [DN-arena](adr-dn-arena.md),
[graded eye](adr-vee1-graded-eye.md) and
[measured JO input](../adr-measured-jo-input.md) decisions without editing them. It is
the motor and mechanosensory half of VEE-1 in the
[sensorimotor plan](../plan/sensorimotor-environment-plan.md): one neuron → muscle →
actuator path and one sensory transfer, both with sources.

## Context

**Motor side.**

- `motor_map.command` refuses every actuator (`src/flymsg/motor_map.py`). It refuses
  even a row marked as a published assignment, because no torque implementation
  exists. Unlocking a row therefore needs a versioned implementation, not only a YAML
  status change.
- `validation/motor_map.yaml` lists FlyBody's 59 actuators and the two TTMn, all
  `unmapped`. That inventory is FlyBody's at a pinned commit, not NeuroMechFly's.
- The NeuroMechFly construction `jump3d` uses has 42 leg controls, 7 per leg: 40
  position controls (rad) and 2 middle-leg coxa pitch motors (N·m). They are built from
  FlyGym 2.1.0's anatomy (`src/flymsg/jump3d.py`).
- `pose.ActuatorRef` admits N, N·m, rad, m/s and rad/s.

**Muscles.** MaleCNS gives 406 of 708 motor neurons one named muscle through MANC's
type-level assignment (Cheong et al. 2024; [embodiment](embodiment.md#muscles-from-manc-phase-c)).
That is anatomy, not physiology. The rest has a body region only, no target, or a
merged type.

**Spikes to force.** Only the TTM has sourced numbers, and no muscle has a sourced
spike → activation → force chain:

- Twitch: 101 ± 4.4 µN at 8.2 ms in tethered females (Zumstein).
- Latency: an upper bound of 0.85 ms from giant-fiber stimulation to the muscle
  potential.
- Shape and summation: the alpha shape and linear summation of `flymsg.ttm` are
  stated choices.
- Muscle-level constraints in [leads](../leads.md): stress 37 mN/mm², shortening 5.1
  lengths/s. These are not a whole-muscle torque.

Moment arms and tendon geometry are unmeasured; `jump3d` uses a stance-fixed Jacobian
lever, an engineered substitute.

**Sensory side.**

- The MaleCNS annotations name the subclasses `chordotonal organ`, `campaniform
sensilla`, `hair plate` and the JO types.
- FlyGym reports joint angles, joint velocities and contact forces. `pose.BodyState`
  (B6) carries root pose and velocities only. `FlyGymBody` returns summed normal
  contact forces separately.
- No source in the repository gives a calibrated mechanics → spike transfer for these
  receptors: location, coupling, tuning, baseline, gain, adaptation, latency and
  saturation are all unmeasured. JO has mechanical and calcium constraints, but calcium
  gives no Hz without an independent calibration
  ([JO design](../jo-measured-input-design.md)).

## Decision

1. **A separate NeuroMechFly inventory.** A versioned lock lists NeuroMechFly 2.1.0's
   leg controls, with names, kinds (position, motor) and units read from FlyGym. It is
   never inferred from the FlyBody rows. The existing FlyBody map stays unchanged.
2. **Anatomy and dynamics are separate fields.** A motor row joins a motor-neuron type
   to a muscle (anatomy, with its MANC certainty and its disagreements kept visible)
   and the muscle to an actuator (a geometry source). Activation and force are separate
   records with their own sources. A row missing any of these stays `unmapped`, and
   the command refuses. No row can be filled by analogy to another leg or segment.
3. **Every dynamic parameter is required.** The motor path's code takes delay,
   activation shape, summation, saturation, force scale and moment arm as required
   inputs from a lock. It has no defaults. A value that is engineered rather than
   measured makes the run `engineered`, and a biological run refuses, as now.
4. **Torque is an implementation, not a status.** `motor_map.command` gains a torque
   path only through a new lock version that names the implementation, its units and
   its sources per row. The current refusal stays the behaviour of every row without
   them.
5. **Articulated observations are a new record version.** Joint angles, joint
   velocities and per-contact forces enter the loop as a versioned observation beside
   `pose.BodyState`. The B6 records already written stay valid and unchanged.
6. **Sensory transfer needs identity and mechanics.** A proprioceptive input names its
   receptor neurons (bodyIds, side, organ) and a transfer from a mechanical quantity
   to drive, with a source. Without a source it is refused, not approximated. The
   drive uses the graded eye ADR's input encodings (`counts` or `kick_equivalent`). No
   new runtime input path is added.
7. **One scheduler.** Motor commands and sensory observations follow the body-wiring
   ADR's order and clock. Replay, disconnected and shuffled arms apply to both. A
   controller-driven NeuroMechFly milestone (DN-arena option A) stays `engineered` and
   separate from this path.

## Evidence labels

| Component                        | Status today                | Becomes measured with                                                        |
| -------------------------------- | --------------------------- | ---------------------------------------------------------------------------- |
| MN type → muscle                 | sourced (anatomy, MANC)     | already sourced; certainty and disagreements kept                            |
| Muscle → NeuroMechFly actuator   | unmapped                    | tendon geometry and moment arms per joint                                    |
| Spike → activation → force       | unmapped (TTM partly)       | identified MN spikes with simultaneous force or activation, per muscle class |
| Joint and contact observation    | engineered (FlyGym physics) | body validated against independent kinematics                                |
| Receptor identity (organ, joint) | partly annotated            | receptor-to-organ and joint assignments                                      |
| Mechanics → receptor drive       | unmapped (JO: calcium only) | calibrated mechanical stimulus → spike recordings                            |

## What is not claimed

These interfaces do not make the body biological. Until a row is measured, the loop is
synthetic or engineered and says so. Nothing here closes VEE-1 or VEE-2, or
validates walking, posture or any behaviour.

## Alternatives

| Alternative                                                     | Problem                                                                   | Verdict  |
| --------------------------------------------------------------- | ------------------------------------------------------------------------- | -------- |
| Train a controller (RL or imitation) from DN commands to joints | A trained policy replaces the connectome's VNC; not a motor map           | Rejected |
| Fill muscle dynamics from a generic insect muscle model         | Values without a source for these muscles; a hidden default               | Rejected |
| Map motor neurons straight to joints by name similarity         | No anatomical or geometric source for the join                            | Rejected |
| Use FlyBody instead of NeuroMechFly                             | Not selected (embodiment ADR); its inventory is pinned separately already | Deferred |
| Reuse `pose.BodyState` for joint observations                   | Rewrites B6 v2's meaning; existing records would mean two things          | Rejected |

## Consequences, risks, rollback

**Consequences.** Code can build the inventory, the schemas and the refusal paths now.
Every dynamic link waits for data.

**Risks.**

- The data may never arrive for most muscles. Then the path stays a set of tested
  refusals. That is the honest state, and the ADR accepts it.
- The female NeuroMechFly body against the male connectome stays a named mismatch.

**Rollback.** Each step is its own PR. Reverting one leaves the existing motor map,
`closedloop` and B6 records unchanged.

## Planned follow-up (`mp-1` … `mp-5`)

| Step | Content                                                                                 | Gate                                                                       |
| ---- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| mp-1 | NeuroMechFly 2.1.0 control inventory lock, read from FlyGym, separate from FlyBody's    | Names, kinds and units equal FlyGym's; FlyBody map unchanged               |
| mp-2 | Motor row schema: MN type → muscle (MANC) → actuator, with dynamics as separate records | Every row without sources refuses; anatomy rows reproduce `flymsg muscles` |
| mp-3 | Articulated observation record beside B6 (angles, velocities, per-contact forces)       | B6 records unchanged; replay parity with observations                      |
| mp-4 | Proprioceptive input contract: receptor identity + sourced transfer, else refusal       | Receptor rows from annotations; refusal without a transfer source          |
| mp-5 | First lock of a measured row, when a source exists (owner approval)                     | Lock before run; nulls and controls as in DN arena                         |

Implementation goes to the agents named in issue #265, and reviews are cross-vendor.

## Data this ADR depends on

Ranked by how many links each source could unblock. The holders named are those in the
repository's docs. None of these sources is a complete dataset.

1. **Identified MN spikes with simultaneous activation or force, plus posture-dependent
   tendon geometry: three forward links.** Candidates in [leads](../leads.md): Azevedo,
   Cheong, Özdil (FlyMimic), Lesser.
2. **Receptor-to-organ and joint identity, plus calibrated mechanics → spike
   recordings: two return links.** JO: Patella & Wilson, Ishikawa, Matsuo. Other
   receptors: no holder identified.
3. **Original TTM twitch trials, decay and repeated-spike saturation: one force link.**
   Zumstein; contractile constraints from Eldred and Fenwick.
4. **Independent behavioural recordings, for final qualification.** Card & Dickinson,
   pending an eligibility audit.
