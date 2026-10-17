# ADR: an optional WebXR observer, apart from the experimental environment

Status: accepted as an experimental, opt-in observer, 2026-10-14; unqualified on any headset
([#177](https://github.com/gianlucamazza/flymsg/issues/177)). The sensorimotor arena it is kept
apart from is planned in the [sensorimotor environment plan](sensorimotor-environment-plan.md)
([#176](https://github.com/gianlucamazza/flymsg/issues/176)). No biological claim.

## Context

flymsg has an incremental runtime (`CpuRuntime`), the M0 sensor, body and clock contracts
(accepted for the synthetic fixture), an exploratory M2 feedback loop, a NeuroMechFly jump, the
measured eye geometry and a three.js viewer of anatomy and replays ([viz](viz.md)). The one-bit
looming jump fails its DNp01 silencing check, T4/T5 v1 is neither and v2–v4 are robust
neither ([eye](eye.md)), the NeuroMechFly jump is short and `validation/motor_map.yaml` maps no
actuator. An immersive view changes none of that.

Two things must stay apart: a headless, evidence-gated experimental environment that produces
sensory input and closes a loop, and an optional immersive observer of outputs that already
exist.

## Decision

1. The observer reads immutable scene and replay outputs only. It never synthesises spikes,
   rewrites a manifest, changes `sim.Params` or labels an engineered mapping as biological.
2. The existing viewer gains `?xr=1`: support is feature-detected, a session starts and ends
   only on the reader's action, and the desktop view stays the default. The same geometry and
   replay timestamps are shown.
3. In a session three.js renders the two eye views directly. The desktop composer (multisampled
   scene target, bloom) is not run against the headset framebuffer, so XR shows the emissive
   glow without the bloom halo and without MSAA.
4. Any future arena reuses the M0 contracts, `CpuRuntime` and the existing manifests; no second
   scheduler, physics integrator, manifest or simulator. Its gates are the plan's.

## Invariants

- **Causality:** no rendering or headset clock enters the simulation. The viewer never runs the
  simulation, so scientific outputs do not depend on the viewer mode by construction.
- **Reference frames:** the scene is in micrometres, the headset in metres; a display-only
  transform scales and places the whole scene and writes nothing back.
- **Lifecycle:** a support check, an explicit start, an end that restores the root, the
  desktop camera (position, orientation, field of view, zoom) and the orbit controls, and a
  status message on failure. Installing the observer never delays the first desktop frame.
- **Ownership:** one renderer, one animation loop, one set of replay buffers.

## Alternatives

| Alternative                                 | Problem                                           | Verdict         |
| ------------------------------------------- | ------------------------------------------------- | --------------- |
| A separate Unity or Unreal application      | Duplicate data and rendering pipelines            | Rejected        |
| Rebuilding the viewer in a VR framework     | Geometry, levels of detail and shaders duplicated | Rejected        |
| WebXR in the existing three.js viewer       | Hardware still to qualify                         | Adopted, opt-in |
| Scene animation coupled into the motor loop | Confuses animation with stimulus and actuation    | Rejected        |

## Acceptance

- Without `?xr=1`: no new control, unchanged rendering, export and selection.
- Unsupported, failing or denied XR: a status message, no session request on load, the desktop
  view unchanged.
- Session state: enter and exit restore the root, camera and controls; tested in
  `tests/js/xr.test.mjs` with a mock renderer.
- On hardware ([#177](https://github.com/gianlucamazza/flymsg/issues/177)): stereo, scale and
  orientation, frame times against the stereo budget, levels of detail under head motion,
  session end from the headset menu, context loss. Until then no device is called supported.

## References

- [three.js WebXR basics](https://threejs.org/manual/pages/webxr-basics.html)
- [WebXR Device API](https://www.w3.org/TR/webxr/)
