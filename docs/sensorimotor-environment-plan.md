# FlyMSG sensorimotor environment — evidence-gated completion plan

**Status:** proposed on 2026-10-14. **Baseline:** `main` at `8d0660b4ccce27b68f282fa89b1004b4b5323f0d`. **Tracking:** #176, #31. **Related observer:** draft PR #175 and #177.

## Goal and explicit levels of completion

Build a reproducible, fully headless sensorimotor experiment in which a physically defined stimulus is sampled from a fly's current pose, propagated into the MaleCNS neural runtime using a defensible sensory map, decoded through an evidence-backed motor pathway into the same physical body, and affects a later sensory sample. An optional 3D/WebXR viewer can inspect the outputs but cannot change them.

Declare three distinct outcomes; never collapse them into one marketing claim:

- **E0 — Geometry/infrastructure qualified:** the world, 6-DoF pose, visual projection, timebase and trace are internally correct, replayable and tested. This says nothing about biologically correct perception.
- **E1 — Biological interfaces qualified:** at least one sensory transfer and one neuron-to-muscle-to-actuator path have cited, independently checked evidence and work in the integrated loop. All other channels remain explicitly unmapped. This is not yet evidence of accurate whole-animal behavior.
- **E2 — Sensorimotor biological prediction validated:** a prospectively registered, independent held-out animal benchmark with controls is passed. A failure, indeterminate result or missing dataset **does not** satisfy E2.

**E0 is independently deliverable. E1 and E2 can be blocked by outside evidence.** A synthetically coupled demo is a numerical/engineering fixture, not a completion substitute for E1.

The first scoped task is an approaching dark disc with unilateral/bilateral stimulation, the LC4/LPLC2 → GF/descending → TTMn/muscle escape pathway, and a physically simulated takeoff. Compare the two sides, timing and kinematics. No requirement to model free flight, six-leg walking, all motor pathways, conscious experience or real-time full-CNS execution.

## Existing source of truth: reuse, do not duplicate

- **Runtime:** `flymsg.sim` and `flymsg.runtime.CpuRuntime`; preserve B2 batch/incremental parity and the 100 µs neural tick. No competing neural executor or neural clock.
- **Embodiment:** `flymsg.embodiment` (M0 schema `flymsg.embodiment/v1`), `flymsg.jump`, `flymsg.loop`, `flymsg.jump3d`, `flymsg.ttm` and `flygym==2.1.0` / MuJoCo, including the published force evidence already used by the TTM experiment. M0's `BodyState` and `MotorCommand` are **scalar/point-mass contracts**, not yet generic 6-DoF flight/leg contracts. Do not pretend otherwise.
- **Vision:** `flymsg.eye.columns`, `photoreceptors`, `angular_distance_deg`, `disk_coverage` and the published MaleCNS/eyemap coordinates. `eye.photoreceptor_kicks` currently requires an unmeasured gain. Existing T4/T5 results v1–v3 are negative; v4 is locked but not yet scored in the baseline.
- **Stimuli:** `flymsg.sensory` and `flymsg.sensory_runtime` are exploratory (engineered Poisson drive, not measured LC4 tuning). Keep them as named comparison baselines, not as an implicit retina.
- **Motor:** `flymsg.motor_map` and `validation/motor_map.yaml` remain fail-closed for their current FlyBody assignments. The targeted NeuroMechFly TTM twitch route is a distinct, explicitly sourced experimental path; it must not silently authorize unrelated actuators.
- **Experiments:** B3 locks, B4 manifests, `flymsg.workbench`, run integrity, `validation/evidence.yaml` and existing figures/traces. Reuse and version any needed schema; never create an alternate registry, run database, output identity, scheduler or metric generator.
- **Presentation:** the existing three.js viewer and optional XR observer in draft PR #175; XR is not a sensor and cannot write physics or neural state.

Existing issues owning constraints: #19, #31, #34, #35, #36, #84, #97, #140, #176 and #177. Closed development/research issues #43–#54 have already delivered infrastructure or explicit negative/blocking outcomes; do not reopen their completed work merely to rename it.

## Critical path and acceptance gates

### G0 — Freeze a factual inventory and a falsifiable initial question

**Depends on:** none. **Owner:** #176, #31, #36.

1. Record the exact implementation and documented status of every contract, version, scientific source, existing fixture and limitation in a single inventory with module and test references.
2. Freeze the initial task's stimulus geometry, target cell identities and body posture; list sex/morphology mismatches and data/reconstruction coverage separately.
3. Identify an actually independent animal dataset with raw trial identifiers, experimental conditions, licensing, treatment/genotype, units, uncertainty and permissible development/holdout split. If none is eligible, mark E2 **blocked**, not “almost validated”.
4. Identify which observables are sensory (angle per column, graded response, LC4/LPLC2/GF activity), motor (TTMn and its muscle), and behavioral (takeoff latency, 3D trajectory, velocity and control differences). Lock a hypothesis only after eligibility is checked.
5. Preserve all frozen historic protocols and negative results. The already-inspected looming case is **calibration**, never retroactively held out.

**Exit:** reviewable inventory and question, source-to-parameter records, explicit eligible/blocked decisions, no changes to model defaults or historical outputs.

### G1 — Introduce a versioned 6-DoF environment/eye/body contract

**Depends on:** G0 inventory. **Proposed engineering issue:** separate from #34's previously completed synthetic loop.

The M0 v1 `BodyState(position_m, velocity_m_s)` and `MotorCommand(force_n)` do not express an articulated fly, orientation-dependent vision or joint torques. Add a **deliberate B6 v2 contract** alongside the frozen v1 semantics. No transparent coercion of v1 scalar state into 3D and no retrofit of archived traces.

- Pose: world-frame SI position (m), orientation (document quaternion order and handedness), linear/angular velocity (m/s, rad/s), exact integer timestamp, frame name and body-model identity.
- Sensory samples: explicit eye location/orientation derived from the articulated head/body, stimulus type, units, column/receptor IDs, missing-data masks and timestamps.
- Actuator commands: verified motor-neuron bodyId, side, target muscle, target MuJoCo actuator/joint ID, torque/force units, latency and evidence reference. No arbitrary newton scalar silently issued to an unrelated joint.
- Coordinate conversion: FlyGym's `mm` and `g` conventions to SI, plus MaleCNS's left/right, eye azimuth/elevation and viewer micrometre conventions. All transforms pure, named and invertible where applicable.
- Scheduler: reuse `CpuRuntime` and MuJoCo physics. At any boundary `t`, only body state available at `t` may affect input delivered at `t + latency`; motor spikes may only act at a future eligible control/body boundary. Clock ratios and buffer boundaries are exact integer microseconds, never silently rounded.
- Resource lifecycle: fail on mismatched model/data IDs, missing maps, invalid units/frames, unsupported timestep ratios, nonfinite state, nonmonotonic events or body/runtime exceptions. Record failure artifacts without presenting a partial run as complete.

**Exit:** versioned schemas and contract tests; identity, round-trip, left/right, transform and boundary-time tests; v1 fixture and batch parity unchanged; no real-animal or scientific claim.

### G2 — Implement a deterministic visual forward model of the environment

**Depends on:** G1, existing eye-map source. **Scope:** physical optics, not invented photoreceptor physiology.

Reuse FlyGym 2.1's existing world/scene composition and, where qualified, its CPU vision support. Do not implement a second physics engine or copy the old FlyGym 1.x Gymnasium vision API into v2. The sensory prediction should use the existing *MaleCNS measured-direction column map* rather than silently swapping to FlyGym's approximate 721-ommatidium lattice.

Given an immutable geometric stimulus definition, world/object pose and eye pose at `t`:

1. Transform object geometry into the *fly eye* frame (not the spectator camera).
2. Calculate visual angular position, angular extent, change/expansion and dark/bright coverage for each mapped retinal column; explicitly mask unmapped columns and preserve left/right provenance.
3. Reuse `eye.disk_coverage` or document a prospective geometry change after quantitative tests. Never choose acceptance angles/gains because they make downstream spikes appear.
4. Verify a stationary scene at fixed pose, monotonic expansion on an approaching disc, mirror symmetry on a deliberately mirrored fixture, head/body rotation effects, occlusion, out-of-field coverage, timestamps and event ordering.
5. Compare the analytic projection against an independently rendered FlyGym camera on the **same** geometry where a v2 CPU sensor path is available. Record discrepancies; a second renderer is not required to run FlyMSG.

**Exit:** deterministic per-column optical traces tied to real pose and immutable source geometry, with geometric unit tests and reconstruction-coverage report. This **does not** qualify neuronal LC4/LPLC2 perception.

### G3 — Validate the biological visual transfer to target neurons

**Depends on:** G2; existing #84, #97 and #140. **Research blockers:** measured transfer and suitable independent recordings.

Two separate readout paths must stay distinguishable:

- **Mechanistic path (required for E1):** projected luminance → mapped MaleCNS photoreceptors/graded lamina and medulla → candidate LC4/LPLC2/GF pathway, using only justified release dynamics and neuron identity.
- **Circuit-only baseline:** externally imposed LC4/LPLC2 spike/Poisson stimulus. This remains useful for downstream circuit tests but **does not count** as end-to-end vision.

Freeze stimulus ranges, timing, contrast, neural targets and uncertainties from experimental evidence (e.g. Ache et al. 2019 for LC4/LPLC2 size-versus-speed contributions, von Reyn et al. 2014 for the escape regime). Do not treat calcium amplitude as directly measured spike rate. T4/T5 direction selectivity is an informative additional retinal-circuit test, but only a genuine circuit dependency if the initial task requires that pathway.

- Verify membrane/release sign, gain sensitivity, first-spike/voltage latencies and their uncertainty; benchmark zero input, non-looming controls, bilateral asymmetry and perturbed/shuffled optic mapping.
- Keep unknown per-type release curves as unknown rather than calibrating on a scoring partition; a prospectively defined uncertainty envelope is allowed as an **uncertainty analysis**, not as a claimed measurement.
- Require an independent review of sensory evidence before any neuron-level “qualified” label.

**Exit:** independent physiology checks passed, or a documented no-go. T4/T5 and prior olfactory failures remain in the record.

### G4 — Qualify TTMn-to-muscle-to-actuator commands

**Depends on:** G1; #19, #35 and existing #90/#94 implementation and evidence.

Use FlyGym 2.1 / MuJoCo already pinned by FlyMSG, not a new FlyBody process, Unity model or imitation-learning controller. Use `jump3d` and `ttm` as the measured baseline; distinguish the sourced TTM twitch from assumptions about twitch decay, spike summation, lever arm and inactive muscles. Preserve the known **short-jump** outcome.

- Audit TTMn left/right bodyIds → TTM → mesothoracic coxa–trochanter joints against the published anatomy and the actual compiled model. Record mismatch with the female physical body; no invented cross-sex correction.
- Determine whether additional muscles (including the TLM/femur–tibia extensor) have measured neuron identities, force/timing and valid physical targets. Missing assignments remain `unmapped`; do not extend the action model by choosing a plausible torque.
- Fix actuator identity, force/torque direction, origin, moment arm, latency, body mass and contact behavior in a prospectively versioned protocol with units and evidence.
- Test impulses, bilateral/asymmetric activation, no-command motion, delayed command boundaries, contact/takeoff criteria, force/energy bounds and source provenance.

**Exit:** one or more **documented** motor paths pass actuation checks. If the available path cannot reproduce the required takeoff regime, report a failed prediction or blocked mechanism; do not add an ad-hoc learned controller.

### G5 — Close the pose-dependent sensor–neural–motor–body loop

**Depends on:** G2 + G3 + G4; reuse M2/#34 and E5/#52 behavior and fixtures rather than building a second loop.

Run one authority for time, neural steps and physics. Each iteration must read the current articulated pose, derive optical inputs from the *new pose*, apply evidence-gated sensory transfer, step the unchanged neural network, decode valid motor events, integrate the body and observe the changed pose at a **later** time.

- Do not reuse the one-bit “cut stimulus after takeoff” mechanism as a fake camera.
- Require controls: open-loop fixed pose, feedback disconnected, recorded-input replay, shuffled input, silenced target circuit, no stimulus, mirrored side, and wiring/motor controls only where scientifically justified.
- Paired stochastic input streams must be traceable across arms; preserve input counts for exact replay instead of relying on a shared seed alone.
- Verify that observed body motion changes subsequent **column optical input**, and separately test whether it significantly changes downstream neuronal/motor behavior. Previous M2 movement of roughly 10 µm caused no detectable input difference at its physical scale; avoid amplifying gain to force an effect.
- Compare batch and incremental stepping on frozen identical stimuli, assert causal ordering at every clock boundary, record resolved bodyIds and typed events, and verify exact replay/hash identity on the supported deterministic platform.
- Prove rendering/XR on/off and frame-rate changes do not affect any scientific output.

**Exit:** measurable pose → optic input causality in the integrated system; neuronal and behavioral effect recorded as pass/fail/indeterminate, never assumed. Full E1 requires the previously qualified sensory and motor mappings.

### G6 — Preregister and execute independent falsification

**Depends on:** G3–G5, independently eligible data; tracked by #36 and scientific-fidelity SF3/SF4.

- Freeze source files/DOIs, versions/hashes, stimulus parameters, blinded calibration/holdout split, primary metric, uncertainty model, effect-size thresholds, seeds, null distributions, sample-size rule and multiple-comparison policy **before** scoring.
- Report onset/latency, left-right outcomes, GF/TTMn recruitment, takeoff timing, velocity vector, displacement and failure probability with uncertainty. Declare which are direct measurements versus inferred/simulated.
- Include biologically meaningful controls where comparable data exist: appropriate silencing, perturbations, no-looming/contrast controls, and intact/shuffled network.
- Prevent resubmission of an already-inspected calibration condition as a new held-out result. If no eligible dataset exists, stop at E1 and preserve the blocked E2 record.
- Archive all attempted arms, negative results, immutable manifest and independent reproduction instructions.

**Exit:** an independently reproducible, formally scored result. E2 succeeds **only** if its preregistered criterion is met; a well-executed failure is still a valid scientific artifact, not a software failure.

### G7 — Reliability, performance and release engineering

**Depends on:** G1–G6 as available. Observability uses the existing manifest, immutable run lifecycle, tracing, viewer bundle and benchmark utilities.

- Unit and property tests for transforms, units, side asymmetry and geometry; schedule/checkpoint/exception tests for the B6 v2 integration.
- Small synthetic fixtures may prove *software behavior*, explicitly without being called biological validation. Full MaleCNS+FlyGym scenarios run separately, pinned to source/data/CPU/GPU and captured as immutable artifacts.
- Measure simulated milliseconds per wall-clock second, peak RAM/VRAM, p50/p95/p99 step latency, sensor cost and end-to-end trace volume on pinned hardware. Real time is **not** a release requirement unless measured and explicitly requested.
- Support headless batch/replay first; only then provide visual overlays for stimulus pose, eye coverage, neural activity, motor force and body trajectory through the existing viewer. Any WebXR release qualification remains in #177 and is **not** a dependency for E0–E2.
- No duplicate adapters, secret fallbacks, copied protocol execution logic, implicit NaN-to-zero for mapped science, dead feature flags, or unversioned breaking changes.
- CI: existing Ruff/pytest/JS/Markdown checks stay green; add targeted deterministic tests and independent-data jobs only when inputs and licenses allow.

**Exit:** cold-clone reproduction procedure, explicit unsupported configurations, saved measurements, zero regressions and an independent reviewer able to repeat the declared outputs.

## Delivery slices (each independently reviewable)

1. **PR-S0 (documentation/decision):** this plan, exact inventory, primary hypothesis/data eligibility and B6-v2 decision record. No simulation changes.
2. **PR-S1 (contracts):** B6 v2 types and tests, immutable frame/time conversion and provenance; v1 unchanged.
3. **PR-S2 (optical geometry):** world/object/eye projection using existing MaleCNS eye map, cross-check against FlyGym v2 rendering and unit tests. E0 candidate.
4. **PR-S3 (sensory evidence):** measured pathway-specific transfer and physiological controls, or explicit evidence no-go without unverifiable code.
5. **PR-S4 (motor evidence):** cited TTM/TLM path where available, explicit fail-closed actuator test, no unsupported movement.
6. **PR-S5 (causal integration):** unified 3D closed loop, paired controls, checkpoint/replay, side-specific effect measurements. E1 candidate once G3/G4 are qualified.
7. **PR-S6 (science/reporting):** frozen independent benchmark, uncertainty, figures and replication package. E2 candidate only upon a passing evaluation.
8. **Optional PR-S7 (viewer):** read-only overlay on the existing 3D interface. Do not make UX/VR an experimental prerequisite.

A slice may explicitly end with **no-go** when its measured prerequisites are absent; do not disguise that as unfinished engineering or substitute a guessed mapping. No calendar completion date can be justified until the data/evidence inventory resolves G0.

## Critical dependencies and owners

- **#176** is the sensorimotor umbrella; this document is its definition of completion.
- **#31 / #34** own M0–M4 and the existing closed-loop limitations.
- **#84 / #97 / #140** own the eye and non-spiking/medulla physiology; do not duplicate their mechanistic experiments.
- **#19 / #35** own muscle/actuator evidence and body-selection limitations.
- **#36** owns prospective held-out neuromechanical validation.
- **PR #175 / #177** own the immersive *observer*, not the scientific runtime.
- The new narrowly scoped VEE engineering issues introduced with this plan track B6 v2, 3D optical projection and causal 3D runtime acceptance separately.

## Risk register and non-negotiable no-go decisions

- **Retinal data insufficiency:** block mechanistic sensory claim; do not silently replace receptor processing with LC4 Poisson stimulation.
- **Male connectome versus female morphology:** document anatomical mismatch and sensitivity; no guessed compensation.
- **Incomplete motor muscle map:** refuse unmapped actuator commands. TTM-only motion is a documented partial experiment, not full behavior.
- **No closed-loop effect at physical scale:** publish null result, not an artificially raised gain.
- **No independent held-out data:** block E2; do not create a new test by inspecting results first.
- **Performance too slow for live VR:** run headless and replay immutable outputs. WebXR remains independent and unqualified until hardware tests.
- **Incompatible schema/library:** require explicit contract/version decision and actual parity tests before a change; do not add compatibility shims for an unsupported API.

## Primary references

- [FlyMSG architecture](architecture.md), [embodiment](embodiment.md), [eye](eye.md), [scientific fidelity](scientific-fidelity.md), [run integrity](run-integrity.md), [roadmap](roadmap.md).
- [VEE architecture draft PR #175](https://github.com/gianlucamazza/flymsg/pull/175), [sensorimotor umbrella #176](https://github.com/gianlucamazza/flymsg/issues/176).
- [FlyGym v2.1.0 release and API migration](https://github.com/NeLy-EPFL/flygym/releases/tag/v2.1.0) (April 2026 major v2 rewrite; June 2026 native MjSpec 2.1.0).
- [von Reyn et al. 2014, action-selection timing](https://doi.org/10.1038/nn.3741).
- [Ache et al. 2019, LC4/LPLC2 looming size/velocity inputs to giant fiber](https://doi.org/10.1016/j.cub.2019.01.079).
- Published details of any other new physiological parameters must enter `validation/evidence.yaml` and a versioned protocol rather than remaining only in this plan.
