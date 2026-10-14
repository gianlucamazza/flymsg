# Sensorimotor environment: an evidence-gated plan

Status: proposed, 2026-10-14. Tracking:
[#176](https://github.com/gianlucamazza/flymsg/issues/176) (umbrella) and
[#31](https://github.com/gianlucamazza/flymsg/issues/31) (embodiment). This plan is subordinate
to the roadmap's [completion plan](roadmap.md#completion-plan): flymsg is complete when a
model prediction passes an independent held-out benchmark (M4,
[#36](https://github.com/gianlucamazza/flymsg/issues/36)). It adds the gates a headless
sensorimotor experiment needs on the way there and states no result.

## Goal and grades

A physically defined stimulus is sampled from the fly's current pose, sent into the MaleCNS
network through a defensible sensory map, decoded through an evidence-backed motor path into the
same body, and changes a later sensory sample. The 3D viewer and its optional XR observer
([#175](https://github.com/gianlucamazza/flymsg/pull/175),
[#177](https://github.com/gianlucamazza/flymsg/issues/177)) read the outputs and never change
them.

Three grades, never merged into one claim:

- **VEE-0, geometry and infrastructure.** World, 6-DoF pose, optical projection, time base and
  traces are correct, replayable and tested. Nothing about biological perception.
- **VEE-1, biological interfaces.** At least one sensory transfer and one neuron → muscle →
  actuator path rest on cited, checked evidence and work in the loop; every other channel stays
  explicitly unmapped.
- **VEE-2, a held-out prediction.** A preregistered, independent animal benchmark with controls
  is passed. A failure, an indeterminate result or a missing dataset does not satisfy it.

VEE-0 can be delivered from inside the project; VEE-1 and VEE-2 can be blocked by evidence that
does not exist. A synthetically coupled demo is an engineering fixture, never a substitute for
VEE-1. The names avoid the embodiment sequence E1–E6 ([embodiment](embodiment.md)).

The first task is an approaching dark disc, one side or both, through LC4/LPLC2 → giant fiber
→ TTMn → TTM to a simulated take-off, comparing sides, timing and kinematics. Free flight,
walking and real-time whole-CNS execution are out of scope.

## What is reused

- **Runtime:** `flymsg.sim` and `flymsg.runtime.CpuRuntime` with the 100 µs neural tick and
  batch/incremental parity ([runtime](runtime.md), accepted). No second executor or clock.
- **Embodiment:** `flymsg.embodiment` (M0, `flymsg.embodiment/v1`, accepted for the synthetic
  fixture), `jump`, `loop`, `jump3d`, `ttm`, and `flygym==2.1.0` with MuJoCo. M0's `BodyState`
  and `MotorCommand` are scalar, point-mass contracts, not 6-DoF ones.
- **Vision:** `flymsg.eye` (`columns`, `photoreceptors`, `angular_distance_deg`,
  `disk_coverage`) over the measured column directions; `eye.photoreceptor_kicks` takes an
  unmeasured gain. T4/T5 status is on [eye](eye.md): v1–v3 neither, v4 locked. No vision path
  from the body pose exists yet ([embodiment](embodiment.md)).
- **Stimuli:** `flymsg.sensory` and `sensory_runtime` are exploratory Poisson drive, kept as a
  named circuit-only baseline, never as a retina.
- **Motor:** `validation/motor_map.yaml` stays fail-closed; the NeuroMechFly TTM route of
  jump3d is a separate, sourced experimental path. jump3d v1 left the ground at a speed of 0.06–0.07 m/s
  with the TTM alone; Card & Dickinson 2008 measured 0.48 ± 0.01 m/s for escape take-offs
  ([leads](leads.md)).
- **Experiments and evidence:** locks, manifests, the run store ([run integrity](run-integrity.md)),
  `validation/evidence.yaml`, the [replication](replication.md) package and the
  [scientific fidelity](scientific-fidelity.md) stages SF2–SF5. Versioned, never duplicated.
- **Presentation:** the existing viewer, including graded potentials
  ([viz](viz.md#graded-neurons)); XR is not a sensor.

Earlier embodiment work (#43–#54, issues and pull requests) delivered infrastructure or
recorded negative and blocking outcomes; it is not reopened to rename it.

## Gates

Step-by-step checklists, delivery slices and the risk register live in
[#176](https://github.com/gianlucamazza/flymsg/issues/176).

| Gate | What                                     | Exit                                                                                           | Issues                                                                                                                                                                                                                                   |
| ---- | ---------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G0   | Inventory and an eligible question       | Contracts, sources and limits listed; held-out data found, or VEE-2 marked blocked             | [#176](https://github.com/gianlucamazza/flymsg/issues/176), [#36](https://github.com/gianlucamazza/flymsg/issues/36)                                                                                                                     |
| G1   | Versioned 6-DoF body and eye contract    | B6 v2 schemas with frame, unit and boundary-time tests; M0 v1 and its fixtures unchanged       | [#178](https://github.com/gianlucamazza/flymsg/issues/178)                                                                                                                                                                               |
| G2   | Optical projection onto measured columns | Deterministic per-column optical traces from the eye's pose, with geometric tests              | [#179](https://github.com/gianlucamazza/flymsg/issues/179)                                                                                                                                                                               |
| G3   | Visual transfer to target neurons        | Checked physiology, or a documented no-go; a Poisson LC4 drive stays a circuit-only baseline   | [#84](https://github.com/gianlucamazza/flymsg/issues/84), [#97](https://github.com/gianlucamazza/flymsg/issues/97), [#140](https://github.com/gianlucamazza/flymsg/issues/140), [#34](https://github.com/gianlucamazza/flymsg/issues/34) |
| G4   | TTMn → muscle → actuator                 | One documented motor path passes actuation checks; jump3d v2 judged on take-off velocity first | [#19](https://github.com/gianlucamazza/flymsg/issues/19), [#35](https://github.com/gianlucamazza/flymsg/issues/35), [#90](https://github.com/gianlucamazza/flymsg/issues/90)                                                             |
| G5   | Pose-dependent closed loop               | Pose → optical input causality measured; neural and behavioral effect pass/fail/indeterminate  | [#180](https://github.com/gianlucamazza/flymsg/issues/180), [#34](https://github.com/gianlucamazza/flymsg/issues/34)                                                                                                                     |
| G6   | Preregistered falsification              | A formally scored held-out result (SF3/SF4), pass or fail                                      | [#36](https://github.com/gianlucamazza/flymsg/issues/36)                                                                                                                                                                                 |
| G7   | Reliability and performance              | Headless replay, measured throughput, cold-clone reproduction ([replication](replication.md))  | [#151](https://github.com/gianlucamazza/flymsg/issues/151), [#177](https://github.com/gianlucamazza/flymsg/issues/177)                                                                                                                   |

G3 follows the roadmap's next step for #34: a transducer that predicts the giant fiber
potential from LC4 and LPLC2 (von Reyn et al. 2017; Ache et al. 2019), validated on the giant
fiber. G6 follows the roadmap's first held-out benchmark for #36 (Pacheco et al. 2021); a
looming-escape benchmark is a later candidate, blocked until G0 finds eligible data.

## No-go rules

- No retinal data: no mechanistic sensory claim, and no silent swap to Poisson LC4 drive.
- Male connectome, female body: the mismatch is recorded, not compensated by a guess.
- An unmapped muscle gets no command; TTM-only motion is a partial experiment.
- No closed-loop effect at physical scale: the null is published, not a raised gain.
- No independent held-out data: VEE-2 is blocked; no test is built after seeing results.
- Too slow for live XR: run headless and replay immutable outputs.
- An incompatible schema or library needs an explicit version decision and parity tests, not
  a shim.

## References

- von Reyn et al. 2014, doi:10.1038/nn.3741 (looming coverage; [provenance](provenance.md));
  von Reyn et al. 2017 and Ache et al. 2019, doi:10.1016/j.cub.2019.01.079 (LC4 and LPLC2
  inputs to the giant fiber; [leads](leads.md)).
- Card & Dickinson 2008, doi:10.1242/jeb.012682 (escape take-off velocity; [leads](leads.md)).
- New physiological parameters enter `validation/evidence.yaml` and a versioned lock, not this
  page.
