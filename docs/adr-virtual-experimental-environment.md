# ADR — Virtual Experimental Environment (VEE) and optional WebXR viewer

**Status:** Proposed, 2026-10-14. **Scope:** observability architecture and research gates. No new claims of biological validation.

## Context

FlyMSG already has: `CpuRuntime` online stepping, M0 sensor/body/clock contracts, M2 exploratory feedback, a NeuroMechFly jump experiment, a mapped eye geometry, and an independent three.js anatomy/replay viewer. This project must not duplicate their functionality.

Crucially, the current looming one-bit behavior fails its DNp01-silencing control, T4/T5 v1–v3 do not recover direction selectivity, the NeuroMechFly jump is short, and `validation/motor_map.yaml` has no mapped physical actuators. A visually immersive scene cannot remove those limitations. See [embodiment](embodiment.md), [eye](eye.md), [behavior](behavior.md), and [roadmap](roadmap.md).

We need two orthogonal features:

- A **headless, evidence-gated virtual experimental environment** generating measurable sensory inputs and controlled sensorimotor interactions.
- An **optional immersive *observer*** of already-produced neuron anatomy and simulation replay, independent of the scientific engine.

## Decision

1. Reuse the existing `StimulusFrame → SensoryEncoder → NeuralStepper → MotorDecoder → Body → Sensor` proposal and the accepted M0 contracts for all future VEE research. Do not introduce a second scheduler, physics integrator, experiment manifest, or neural simulation.
2. The presentation layer is strictly downstream of immutable scene/replay outputs. The viewer must **never** synthesize spikes, rewrite a manifest, reconfigure `sim.Params`, select a hypothesis, or silently label engineered mappings as biological.
3. Add a **small opt-in WebXR observer** to the existing three.js viewer (`?xr=1`). It uses the same geometry and replay timestamps as desktop. Support is feature-detected; immersive sessions require user action; desktop rendering remains the default.
4. While immersive, render using Three.js's native stereo XR path; do not route an unqualified desktop EffectComposer through a headset. No invented stereo pipeline, display-to-neuron interpretation, controller locomotion, or hardware-specific claims.
5. Build any future headless arena against independent evidence (verified optical geometry, sensory transfer, motor evidence and falsification datasets). Keep this research work gated until the relevant inputs are available.
6. Do not introduce a second framework, duplicate event transport or bridge through a mock biology layer solely to make a demo look complete.

## Invariants

- **Causality:** no rendering or headset clock may enter the scientific simulation update path. XR must only read already-produced scene/replay state.
- **Numerical parity:** the same simulation configuration and seed produce the same scientific outputs regardless of viewer mode, including in headless execution. Scientific CI continues to run without WebXR or physical hardware.
- **Provenance:** experiments retain immutable manifests, seeds, dataset hashes, coordinate frames, SI units and timestamp ordering. Viewer configuration is presentation metadata, not scientific provenance.
- **Reference frames:** the exported scene uses micrometres; headset coordinates are metres. A display-only transform may scale/translate the entire scene but never write back to scientific position data.
- **Session lifecycle:** native `immersive-vr` support check, explicit start, proper end/restore, XR-specific render path, and informative failure status. No mandatory XR dependency for desktop.
- **Resource ownership:** the existing renderer, scene and replay buffers remain single-owned. No extra rendering engine or background clock.
- **Evidence:** sensor encoders and actuator mappings must be accompanied by published measurement and a held-out protocol; an unsupported mapping stays `unmapped`.

## Alternatives and decision

| Alternative | Benefit | Problem | Verdict |
| --- | --- | --- | --- |
| Independent Unity/Unreal application | Rich tools | Duplicate data and rendering pipelines | Rejected |
| Rebuild the CNS viewer in a VR framework | Native interactions | Geometry/LOD, shaders and CI duplicated | Rejected |
| WebXR on existing Three.js viewer | Minimal duplication | Hardware must still be qualified | Adopt as opt-in observer |
| Couple scene animation directly into the LIF motor loop | Easy-looking closed loop | Confuses animation with biological stimulus/actuation | Rejected |
| Headless arena using existing M0/M2 contracts | Reproducibility and testable science | Sensory/motor evidence still required | Research direction, not asserted complete |

## Current PR boundary

Included:
- Opt-in read-only WebXR support for the existing viewer, with native session lifecycle and conventional desktop fallback.
- Explicit separation between XR rendering and the existing post-processing pipeline.
- Unit tests of WebXR capability/activation, failures, and state restoration.
- Documentation and roadmap gates.

Not included:
- New sensors, LC4 transfer functions, artificial muscle controllers, new physics backends, locomotion controls, real-time full-CNS execution, new scored results, or a new VEE runtime.
- Claims of headset compatibility without a physical test. A device smoke test remains a release gate.

## VEE research contract (future, not implemented here)

`Protocol v1` should name: source geometry/stimulus and units, coordinate frames, deterministic timebase, documented `SensoryEncoder` type and source, `NeuralStepper` version, controlled `Body` backend, `MotorDecoder` evidence and failure-on-unmapped policy, immutable seed/config/manifest, defined observables, and independent pre-registered negative controls. It should reuse `flymsg experiment` and M0 rather than invent another file schema.

Candidate studies:
1. Open-loop moving-edge/looming stimuli mapped through measured eye directions, tested against T4/T5 and LC4/LPLC2 recordings; use the existing failed results as a fixed baseline.
2. Connected versus disconnected, replayed and shuffled feedback with causal ordering tests.
3. Bilateral TTM/jump studies **only** with sourced muscle-to-actuator mapping and independent movement measurements.

Each claim is conditional on held-out animal evidence and must report failures. No exploration chosen after inspecting results can be promoted into a confirmatory result.

## Acceptance gates

### WebXR observer

- On ordinary URLs with no `?xr=1`: *zero new controls* and original desktop rendering, timestamps, export and selection paths.
- On unsupported or denied devices: clear status and unchanged desktop usability, without a session request during load.
- On supported devices: user-activated enter/exit, correct clean restoration of root transform and camera state, one renderer/animation loop and headset stereoscopy.
- No changes to `activity.bin`, `scene.json`, `sim`, validation locks, or any scored result.
- Automated tests for pure logic and session lifecycle pass; **hardware qualification still required** for framerate, visual alignment, stereo, menu/browser interoperability and context restoration.

### Scientific arena (separate follow-up)

- Fully headless replay and open/closed-loop controls using frozen clocks and seed provenance.
- Valid sensory gain and retinal mapping against independent data, with uncertainties and pre-registered thresholds.
- Motor mapping remains fail-closed until verified; No-Go if unavailable.
- Published performance factors (simulation time / wall clock, RAM, p95 timing), numerical stability and biological falsification. No unsupported real-time promise.

## Consequences

Positive: the viewer gains an immersive inspection mode without a new app; the research roadmap remains honest and auditable. Negative: immersive performance on target headsets is not guaranteed and the VEE biology remains blocked on measurements. These are explicit release/research gates rather than technical debt.

## References

- [3D viewer](viz.md)
- [Embodiment / M0, M2 and NeuroMechFly](embodiment.md)
- [Eye geometry and failed T4/T5 protocols](eye.md)
- [Roadmap and falsification gates](roadmap.md)
- [Three.js WebXR overview](https://threejs.org/manual/en/webxr.html)
- [WebXR Device API](https://www.w3.org/TR/webxr/)
