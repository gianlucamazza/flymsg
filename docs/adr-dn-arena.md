# ADR: descending-neuron readout and a kinematic arena (VEE-0)

Status: **Proposed**, 2026-10-19. No code is authorized. The owner, Gianluca Mazza,
must accept this ADR before any implementation PR, as for the
[body-wiring ADR](adr-body-wiring.md) (accepted 2026-10-14). Follow-up PR 3
(`flymsg.arena`) waits on that acceptance.

Scope: a first **synthetic** steering milestone that reuses the existing closed
loop. It supplements the accepted [body-wiring](adr-body-wiring.md),
[embodiment](embodiment.md), [runtime](runtime.md) and
[module-boundaries](adr-module-boundaries.md) decisions and the proposed
[sensorimotor plan](sensorimotor-environment-plan.md) without editing them. It
does not close that plan's VEE-0 exit, G2, G3 or G4.

## Context

The closed loop already exists. `flymsg.closedloop` (`closedloop.py`) is the one
scheduler of the body-wiring ADR: integer-microsecond `embodiment.Clock`, causal
order command → sample → stimulus → input → neural → physics, evidence statuses
`measured` / `engineered` / `unmapped` / `synthetic`, five arms
(`closedloop.ARMS`: intact, disconnected, shuffled, replay, silenced), and
record `flymsg.closedloop/v1`. A body is a `closedloop.Body` adapter
(`reset() → pose.BodyState`, `step(commands, dt_us) → (pose.BodyState, contacts)`).
`flymsg.flygym_body.FlyGymBody` puts NeuroMechFly (FlyGym 2.1.0; Wang-Chen et al.
2024, _Nat Methods_, doi:10.1038/s41592-024-02497-y) behind that adapter and
offers `snapshot` / `restore` for `closedloop.run` checkpoints. Pose is B6 v2
(`flymsg.pose`, schema `flymsg.embodiment/v2`). Neural steps go through
`runtime.CpuRuntime`, bit-identical to `sim.run`.

Today the executable fixture is synthetic. `closedloop_experiment` and
`examples/closedloop-nmf.yaml` run a two-neuron toy circuit, a test-only
registration, an engineered looming transducer and a synthetic torque decoder.
That is infrastructure, not a world→sensory or muscle→actuator map.

The maps that would make a run biological are missing:

- world → sensory: G2 registration of the Zhao et al. 2025 eyemap into a body
  frame is unmeasured
  ([#179](https://github.com/gianlucamazza/flymsg/issues/179);
  [leads](leads.md), [g2-capsule-rotation](g2-capsule-rotation.md)); G3
  transduction is not a measured photoreceptor or LC4/LPLC2 transfer
  ([#140](https://github.com/gianlucamazza/flymsg/issues/140); T4/T5 v1 is
  neither and v2–v4 are robust neither, [eye](eye.md)).
- muscle → actuator: MANC names a muscle for 406 of 708 `vnc_motor` neurons
  (Cheong et al. 2024, _eLife_, doi:10.7554/eLife.96084); `validation/motor_map.yaml`
  has every actuator row `unmapped`, so `motor_map.command` and `pose.command`
  refuse every command
  ([#19](https://github.com/gianlucamazza/flymsg/issues/19),
  [#35](https://github.com/gianlucamazza/flymsg/issues/35)).

`closedloop.require` therefore refuses a biological run. Equal closed and
disconnected results are reported as observed. Issue
[#31](https://github.com/gianlucamazza/flymsg/issues/31) forbids a learned
controller masquerading as a connectome-derived mechanism.

A first steering milestone can still be written as **synthetic**, with every
component labelled, a lock hashed before the run, and nulls published. That is
this decision.

## Decision

Adopt a first synthetic milestone, **VEE-0 steering**, with these parts. This
ADR names them; it does not implement them.

1. **Kinematic planar body `flymsg.arena` behind `closedloop.Body`.** Integrate
   yaw rate and forward speed on the plane; emit B6 v2 `pose.BodyState` (6-DoF
   with _z_ and the unused rotations held). SI units at the boundary. No MuJoCo
   in this loop. The adapter implements `reset` / `step` and, for checkpoints,
   `snapshot` / `restore` as `FlyGymBody` does (those two methods are required
   by `closedloop.run` when `checkpoint_dir` is set; they are not on the
   `Body` protocol itself). Compiled actuators are engineered names of this
   body. `pose.ActuatorRef` today admits units `N`, `N*m` and `rad` only
   (`pose.py`); if a kinematic command cannot be named in that set, follow-up
   PR 3 records an explicit engineered unit extension rather than overloading
   an existing unit. `pose.command` still refuses every NeuroMechFly motor-map
   row; a synthetic `closedloop.run` checks commands against the body's
   compiled actuator table only.

2. **Full MaleCNS in `CpuRuntime`.** The neural model is the existing LIF
   (Shiu et al. 2024, _Nature_, doi:10.1038/s41586-024-07763-9) on the 165,122
   traced neurons of MaleCNS v1.0 (Berg et al. 2026, _Cell_,
   doi:10.1016/j.cell.2026.08.015), VNC included. No second executor, tick or
   scheduler. Duration on the order of 1–2 s of simulated time, headless.

3. **Geometric visual stimulus via `flymsg.optics`.** `optics.sample` already
   projects dark `optics.Sphere` objects onto measured MaleCNS columns (Zhao
   et al. 2025, _Nature_, doi:10.1038/s41586-025-09276-5). The milestone uses
   that geometry (a lateral dark sphere; a bar only if it is expressed as
   existing geometric primitives without a second sampler). The transducer
   remains engineered (Poisson drive from coverage, as in the present
   fixture). Image-to-column sampling is out of scope.

4. **Engineered descending-neuron decoder.** In a declared control window the
   decoder reads spike rates of named descending types and maps them to
   (yaw, forward) commands of the kinematic body: DNa01 / DNa02 for steering,
   oDN1 for forward speed. Gains are **declared per run in the lock and the
   record, with no defaults** in code or docs. BodyId and side for those types
   in MaleCNS are not asserted here; follow-up PR 2 inventories them. MDN
   (backward walking; Bidaye et al. 2014, _Science_,
   doi:10.1126/science.1249964) and DNp01 remain listed for a later decoder
   version, not this milestone. The decoder is not a motor map and does not
   relabel `validation/motor_map.yaml`. Issue #31: this is an engineered
   readout, not a connectome-derived controller.

5. **Two extra controls, preferably as fixture runs.** In addition to the five
   `closedloop.ARMS`:
   - **script:** the same stimulus mapped to (yaw, forward) by a fixed rule,
     with no connectome and no `CpuRuntime`;
   - **wiring-null:** the intact loop on a degree-preserving shuffle of the
     traced graph (`wiring.shuffle_targets`; the same permutation family as
     `flymsg wiring-null` / N1, [related](related.md), [nulls](nulls.md)).

   **Preferred:** keep both as separate fixture runs that call `closedloop.run`
   (or, for the script, a declared non-connectome path) without changing
   `closedloop.ARMS` or bumping `flymsg.closedloop/v1`. The five-arm record
   stays parseable; replay parity, silenced-arm rules and existing tests stay
   intact. The extra runs carry their own arm name in the experiment config
   and lock, not in `closedloop.Record.arm`.

   **Alternative, not preferred:** extend `ARMS` and version the record
   (`flymsg.closedloop/v2`). That would touch `closedloop.py`,
   `closedloop_experiment.py` (which currently requires
   `cfg["arms"] == list(closedloop.ARMS)`), every v1 parser, and the module-
   boundaries work that still has PRs 4–8 open. Do that only if a single
   seven-arm record is required to compare ticks; this milestone does not
   require it.

6. **Protocol lock before the run.** A YAML lock with a canonical content hash
   is committed before any counted run (the existing lock-codec / prereg
   path). The lock names the decoder gains, DN bodyIds, stimulus geometry,
   clock, seed, duration, evidence table, arms/fixture runs and the null rule.
   A run whose config does not match the lock refuses.

7. **Pre-registered null rule; nulls are published.** The lock states, before
   the run, what counts as a null (at least: intact steering indistinguishable
   from the script, and/or from the wiring-null, under a named metric; intact
   equal to disconnected, as the body-wiring ADR already requires, is reported
   as observed). A null, a negative, or an indeterminate outcome is archived
   and documented. It is not rerun with a new gain to manufacture a difference.

## Evidence labels

Every component of a counted run carries one of `closedloop.STATUSES`. A
biological run still refuses unless every `closedloop.COMPONENTS` entry is
`measured`; this milestone is synthetic.

| Component                         | Status     | Note                                                                                                                         |
| --------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------- |
| MaleCNS wiring                    | measured   | Traced graph; not a claim that the decoder uses it correctly                                                                 |
| LIF / `CpuRuntime`                | engineered | Shiu et al. 2024 parameters; battery 29/29 is a model check, not this behaviour                                              |
| Column geometry (`flymsg.optics`) | measured   | Zhao et al. 2025 directions on MaleCNS columns                                                                               |
| Eyemap → body registration        | unmapped   | No sourced `pose.Registration` (#179); the fixture may use a declared test-only registration as today's closed-loop tests do |
| Visual transducer                 | engineered | Coverage → Poisson rates; not a photoreceptor                                                                                |
| DN identity (bodyId, side)        | unmapped   | Until PR 2 inventories them against MaleCNS types                                                                            |
| DN decoder and its gains          | engineered | Declared per run; no default                                                                                                 |
| Kinematic body `arena`            | synthetic  | Planar integrator, not a physical fly                                                                                        |
| Muscle → actuator map             | unmapped   | Unused by this milestone; `validation/motor_map.yaml` unchanged                                                              |
| Script control                    | synthetic  | No connectome                                                                                                                |
| Wiring-null control               | synthetic  | Degree-preserving shuffle of the measured graph                                                                              |

`closedloop.COMPONENTS` today is exactly `(registration, transducer, motor_map, body)`.
The decoder is a `closedloop.run` callable, not a fifth component. **Preferred:**
declare decoder evidence in the experiment lock and record notes without
changing `COMPONENTS` or the v1 evidence pair list. Adding `decoder` to
`COMPONENTS` would be a record version, same cost as extending `ARMS`.

## What is not claimed

This milestone does not claim that:

- the fly perceives, steers, walks, flies or escapes;
- MaleCNS, T4/T5, LC cells or descending neurons implement the behaviour;
- the decoder, gains, or kinematic body are biological;
- world→sensory or muscle→actuator maps exist;
- VEE-0, VEE-1 or VEE-2 of the [sensorimotor plan](sensorimotor-environment-plan.md)
  is done (G2 registration, G3 transduction and G4 motor map remain open);
- a motion that appears only in the intact arm is a connectome-derived
  mechanism, unless the script and wiring-null arms fail to produce it under
  the locked rule;
- Odyssey, Eon, FlyGym 2.1.0's `flygym_demo.complex_terrain.HybridTurningController`,
  or any learned policy is reproduced or endorsed.

Words such as "upload" or "living fly" are out of scope.

## Public demos (factual)

These notes are context for why the extra controls exist. They are not a
comparison of unpublished methods and not a claim about flymsg's results.

**Eon Systems** (public post, 2026-03-10,
<https://eon.systems/updates/embodied-brain-emulation>): a Shiu et al. LIF on
FlyWire (central brain, without VNC), flyvis visual input (Lappalainen et al.
2024, _Nature_, doi:10.1038/s41586-024-07939-3) described there as piped in,
NeuroMechFly in MuJoCo, brain–body sync every 15 ms, and a readout from a small
set of descending neurons (DNa01/DNa02 steering, oDN1 forward, MN9 feeding,
antennal cells for grooming). The same post describes the maps as somewhat
arbitrarily chosen by hand and the vision as somewhat decorative. The public
repository `eonsystemspbc/fly-brain` (GPL-2.0) contains the LIF brain, not the
body loop. flymsg is MIT; Eon code is not copied.

**Odyssey** (public post, 2026-10-17,
<https://x.com/odysseyml/status/2111589148146749616>): «We placed the fruit fly
brain inside Odyssey-3, a frontier world model. The lil' guy is now flying
around totally imagined, simulated worlds all by itself». Odyssey-3 is
described by its authors as an autoregressive diffusion transformer trained on
visual observations, with a learned action decoder for physical systems
(<https://odyssey.systems/introducing-odyssey-3>). On 2026-10-19 the public
writing index (<https://odyssey.systems/writing>) listed no article, paper or
code about a fly. Which brain, which neurons, which loop rate, whether
generated frames enter a visual system, and whether a physical body exists are
not stated in those public pages. This ADR asserts nothing beyond that public
text.

flymsg's difference, if any, is not "the fly moves". It is a closed loop on
the full male CNS, every component labelled, with controls that can show that
steering does not need the connectome.

## Alternatives

| Alternative                                             | Problem                                                                                                                    | Verdict                                     |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| NeuroMechFly + DN decoder as milestone 1 (option A)     | FlyGym's turning controller can walk without the connectome; more parts to qualify; medium overlap with the G4 / body lane | Deferred as milestone 2, after this fixture |
| VNC motoneuron → muscle → NeuroMechFly joint (option B) | Muscle → actuator is unmapped (#19, #35); this is the existing G4 lane                                                     | Left to G4; not this ADR                    |
| World-model / generated RGB closed loop (option D)      | No physically defined stimulus; `optics` samples geometry, not images; a second clock and an external API                  | Rejected                                    |
| Fill motor-map or registration rows to "see" an effect  | A biological-looking run without evidence; refused by the body-wiring ADR                                                  | Rejected                                    |
| Learned controller or default DN gains                  | Issue #31; gains that exist only to manufacture steering                                                                   | Rejected                                    |
| Extend `closedloop.ARMS` / record v2 for the extra arms | Touches the v1 record and in-flight module-boundaries PRs                                                                  | Not preferred; fixture runs first           |
| Kinematic planar body + engineered DN decoder           | Synthetic only; less spectacle; same evidence limits as A with fewer parts                                                 | Adopted as milestone 1, pending acceptance  |

FlyBody (Vaxenburg et al. 2025, _Nature_, doi:10.1038/s41586-025-09029-4)
stays unselected (#19, #35).

## Consequences, risks, rollback

**Consequences.** After acceptance, code PRs may add `arena`, the decoder, a
lock and a fixture. Until then, only this document, its catalog line and the
changelog entry exist. Existing closed-loop records, M0 v1, B6 v2, `CpuRuntime`
numerics, `validation/motor_map.yaml` and archived results are unchanged.
Rendering still cannot enter the loop
([WebXR ADR](adr-virtual-experimental-environment.md)).

**Risks.**

- The honest outcome may be a published null: T4/T5 are neither, so steering
  may not depend on the stimulus or the wiring.
- DN type → MaleCNS bodyId may be incomplete or ambiguous until PR 2.
- `pose.ActuatorRef` units may not name kinematic commands without an
  engineered extension.
- Putting a new module at `src/flymsg/arena.py` can collide with
  module-boundaries PR 8 (leaf package moves). See Coordination.
- Extending `ARMS` or `COMPONENTS` would collide with `closedloop.py` /
  `closedloop_experiment.py` and with that same PR sequence.
- A kinematic demo is easy to over-claim in prose. The evidence table and the
  "not claimed" list are the defence.

**Rollback.** This PR is docs only: revert `docs/adr-dn-arena.md`, the catalog
row, the README index row and the changelog bullet. After later code PRs, drop the
arena fixture and
leave `closedloop.ARMS` and `flymsg.closedloop/v1` in place if the preferred
fixture-run option was used. A record version, if ever cut, is a new schema
and does not rewrite v1.

## Planned follow-up (PRs 2–7)

None of these is authorized by this Proposed ADR. PR 3 and later wait on owner
acceptance. Each later PR also updates `CHANGELOG.md`.

| #   | Content                                                                                                                                         | Touches                                                                                    |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 2   | DN inventory in MaleCNS: bodyId and side for DNa01, DNa02, oDN1, MDN, DNp01, with sources; `engineered` gain rows in `validation/evidence.yaml` | `docs/leads.md` or a new doc; `validation/evidence.yaml`                                   |
| 3   | `flymsg.arena`: kinematic body behind `closedloop.Body`, pose v2, SI, tests (rest, analytic steering, checkpoint)                               | `src/flymsg/arena.py` (or the body-layer package; see Coordination), `tests/test_arena.py` |
| 4   | Engineered DN decoder: windowed rates → (yaw, forward); gains only from the lock/record                                                         | `arena` or `dn_decoder.py` plus tests                                                      |
| 5   | Script and wiring-null controls as fixture runs (preferred), not an `ARMS` / record bump                                                        | fixture only; `closedloop.py` only if the alternative in Decision 5 is chosen after review |
| 6   | Lock + experiment config: hash, seed, null rule **before** the run                                                                              | `validation/`, `examples/`, possibly `closedloop_experiment.py`                            |
| 7   | Run and results, including a null: trajectories per arm, doc page                                                                               | `results/dn-arena/v1/`, `docs/`                                                            |

An optional later PR may show the kinematic trajectory next to neural activity
in the viewer (`viz.py`; H2,
[#24](https://github.com/gianlucamazza/flymsg/issues/24),
[#177](https://github.com/gianlucamazza/flymsg/issues/177)). It is not part of
this milestone.

Milestone 2, only after 1: the same decoder toward FlyGym 2.1.0's
`flygym_demo.complex_terrain.HybridTurningController` and NeuroMechFly
(option A), still `engineered`, with the same controls. Not this ADR.

## Coordination

The [module-boundaries ADR](adr-module-boundaries.md) is accepted (2026-10-18).
PRs 2–3 of that sequence have landed (lock codec, stimulus primitive). **PRs
4–8 are still pending.** PR 8 optionally moves modules into leaf packages with
flat facades; the target **body** layer already lists `embodiment`, `pose`,
`closedloop`, `flygym_body`, `jump`, `loop` and `ttm`.

Before opening follow-up PR 3, check whether that PR 8 is near. If it is,
`arena` goes into the destination body-layer package rather than as a new flat
`src/flymsg/arena.py`. If it is not, a flat module plus a later facade is
acceptable. This Proposed ADR does not pick a path and does not move files.

Module-boundaries PR 7 reorganises documentation links and Pages stems. This
file is not added to `pages.PAGES` here (docs-only; no `src/` change). The
catalog therefore points at the GitHub blob, as for other docs that are not
built site pages. Pages registration can follow acceptance.

## Invariants

- No change to M0 v1, B6 v2, `sim.Params`, `CpuRuntime` numerics, archived
  protocols and results, `closedloop.ARMS`, `flymsg.closedloop/v1` or
  `validation/motor_map.yaml` in this PR, and none implied by acceptance
  without a later reviewed code PR.
- No artificial gain, default DN gain, learned controller, force boost or
  enlarged motion to manufacture a closed-loop effect.
- No guessed transfer function, registration or actuator row.
- A biological run still refuses. This milestone cannot become biological by
  renaming statuses.
- Rendering on or off changes no number.

## Acceptance (owner)

- Status remains Proposed until Gianluca Mazza accepts it. Acceptance is an
  explicit owner act, not a merge of this draft PR by itself.
- After acceptance, implementation still proceeds one PR at a time (2–7),
  with PR 3 gated on the module-boundaries coordination above.
- The evidence table, the "not claimed" list, the lock-before-run rule and
  the published-null rule are not optional in later PRs.
- Full CI green on this docs-only change (`tests.yml`: ruff, prettier 3.8.1
  on all `.md`, non-slow pytest).
