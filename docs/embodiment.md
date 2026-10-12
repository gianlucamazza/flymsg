# Embodiment: M0 coupling ADR and v1 roadmap

Status: accepted for the synthetic M0 fixture. Implements [#32](https://github.com/gianlucamazza/flymsg/issues/32); informs architecture [#30](https://github.com/gianlucamazza/flymsg/issues/30) and experiment infrastructure [#27](https://github.com/gianlucamazza/flymsg/issues/27).

## Context and decision

The LIF simulator produces neural activity, not physical motor commands. Introduce a separate, standard-library-only `flymsg.embodiment` module with frozen, versioned data contracts and a structural `Body` protocol. Do not change `sim.Params`, neural integration or preregistered experiments. No physics runtime dependency is required.

M0 is an executable coupling fixture. It consumes an explicit stream of synthetic motor events and records synthetic sensor-to-neuron events. It does **not** feed those events back into the existing LIF loop. Online neural stepping, a real sensory encoder, gravity/contact, verified motor mapping and closed-loop experiments belong to later milestones.

## Contracts

| Contract       | Meaning                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `Provenance`   | Dataset name, SHA-256, source commit, seed, `flymsg.embodiment/v1`, `flymsg.clock/us-v1`                                      |
| `SpikeEvent`   | Dataset `bodyId` and integer microsecond timestamp; matrix row indices must be explicitly resolved by an adapter              |
| `Clock`        | Neural, body, control periods and command latency, in integer microseconds                                                    |
| `MotorCommand` | World +x force in newtons, timestamp and original source events                                                               |
| `BodyState`    | End-of-step timestamp, +x position in metres, velocity in metres/second                                                       |
| `SensorSample` | End-of-step timestamp, unique name, value in metres, `world/+x` frame                                                         |
| `Trace`        | Provenance, clock, decoder/encoder maps, control commands, every body state, every sensor sample and generated feedback event |

Fixture `bodyId`s are synthetic. A run on MaleCNS would take its motor neurons from [`validation/motor_map.yaml`](../validation/motor_map.yaml), where every row is `unmapped` today, so no real motor command can be issued. The force gain is newtons per event, held for one control interval. It is an engineered decoder, not a neuromuscular inference. The mock sensor encoder emits one event per body tick with positive position; this arbitrary fixture rule is not a biological sensory model. The seed is recorded but the fixture has no random sampling. The supplied dataset digest must match the expected digest; callers are responsible for hashing their actual dataset files.

## Clock and ordering

Default neural period is 100 microseconds (0.1 ms); body and control periods are 1000 microseconds. Require positive integer periods, body divisible by neural, control divisible by body, and latency on the neural grid. Unsupported ratios fail rather than silently round. Duration must be a positive multiple of the control period.

At control time `t`, consume all remaining events with `event.time_us + latency_us <= t`, retaining input order, including ties. Sum gains and hold that force over body steps until the next control boundary. A control interval with no newly eligible events commands zero force. This gives delivery time `ceil((event time + latency)/control period) * control period`. Additional quantisation delay is less than one control period; source timestamps are never changed. An event that cannot be delivered before run end fails preflight, so no trailing spikes are silently discarded.

Advance the body over `[t, t + body_us]` with semi-implicit Euler in the mock, then sample sensors at the end of the step. Generated sensory events carry that end timestamp; a future online neural adapter must define the subsequent input application phase explicitly. Initial mock position and velocity are zero. Zero force preserves an initially stationary body; it does not stop an already moving body.

## Failure and provenance policy

Validate the entire event stream, maps, digest and versions before any actuator call. Reject unordered/off-grid timestamps, unknown motor IDs, nonfinite gains and missing sensor mappings. After each body step, validate finite state and exact end timestamp, then require exactly the mapped sensors with valid units, frames and values. Any exception raised inside a body adapter call is re-raised as `ContractError`, with the original as its cause; the run stops and no further actuator call is made. A failed run must be discarded and the body reset; this contract cannot roll back a physical step already executed and is not a hardware safety controller.

`Trace.to_dict()` is JSON serializable. Store it as an artifact and include its hash and `asdict(trace.clock)` / mapping configuration in the existing `flymsg.run_manifest/v1` config or extra fields. Keep the existing manifest schema unchanged. The fixture is exploratory, not preregistered evidence; this metadata is intended to compose with #27, not implement that entire workbench.

## Executable example

```python
import json

from flymsg.embodiment import MockBody, Provenance, SpikeEvent, run_fixture

trace = run_fixture(
    (SpikeEvent(10, 0), SpikeEvent(10, 1000)),
    duration_us=4000,
    provenance=Provenance("synthetic", "a" * 64, "fixture", 7),
    expected_dataset_sha256="a" * 64,
    motor_map={10: 2.0},
    sensor_map={"position": 20},
    body=MockBody(),
)
print(json.dumps(trace.to_dict(), sort_keys=True))
```

## Acceptance and limits

`uv run pytest tests/test_embodiment.py` checks that the default neural tick is `sim.Params.dt`, repeatable round trips, analytical first-step units, exact event conservation/order, equal-time events, explicit latency, force holding, stationary baseline and fail-closed input/runtime handling. Existing CI discovers these tests automatically. Floating-point body integration is repeatable within one runtime; cross-platform bitwise physics equivalence is not promised. No connectome download is needed.

This fixture intentionally retains the complete trace in memory and scans the motor stream once. It is not a benchmark of full-CNS runtime or streaming storage. Backend-specific physical constraints and coordinate conversions must be introduced with their own contracts and acceptance tests.

## Embodied v1 roadmap

Proposed 2026-10-12 (PRs #42 and #47); the target interfaces below are not implemented
classes. Three issue series describe this path: the M milestones of [#31](https://github.com/gianlucamazza/flymsg/issues/31), the E gates, and
the research workstreams. They overlap, so this table is the one map between them. The
research workstreams were filed as R1–R4, which collides with runtime R1–R2 ([#39](https://github.com/gianlucamazza/flymsg/issues/39), [#40](https://github.com/gianlucamazza/flymsg/issues/40));
here they are research A–D.

| Step                     | Issues                                                                                                                                                                                                                                             | Status                                                                                                                         |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Online neural stepping   | E1 [#43](https://github.com/gianlucamazza/flymsg/issues/43), runtime R0 ([runtime](runtime.md))                                                                                                                                                    | done in v0.8.21: `CpuRuntime` runs in blocks through checkpoint and restore and matches `sim.run` bit for bit, also on MaleCNS |
| Looming stimulus and LC4 | E2 [#44](https://github.com/gianlucamazza/flymsg/issues/44), M2 [#34](https://github.com/gianlucamazza/flymsg/issues/34), research A [#49](https://github.com/gianlucamazza/flymsg/issues/49)                                                      | exploratory encoder and runtime bridge in v0.8.23 (below); no LC4 tuning data, no bodyId map                                   |
| Closed loop on the body  | E3 [#45](https://github.com/gianlucamazza/flymsg/issues/45), E5 [#52](https://github.com/gianlucamazza/flymsg/issues/52), M1 [#33](https://github.com/gianlucamazza/flymsg/issues/33), M2 [#34](https://github.com/gianlucamazza/flymsg/issues/34) | open; M0 records feedback but does not feed it to the neural runtime                                                           |
| Motor map                | E4 [#46](https://github.com/gianlucamazza/flymsg/issues/46), research B [#50](https://github.com/gianlucamazza/flymsg/issues/50), M3 [#35](https://github.com/gianlucamazza/flymsg/issues/35)                                                      | blocked: `validation/motor_map.yaml` has no mapped row                                                                         |
| Physical body            | E4 [#46](https://github.com/gianlucamazza/flymsg/issues/46), research C [#51](https://github.com/gianlucamazza/flymsg/issues/51), M3 [#35](https://github.com/gianlucamazza/flymsg/issues/35)                                                      | open; FlyBody not selected ([#19](https://github.com/gianlucamazza/flymsg/issues/19))                                          |
| Falsification            | research D [#53](https://github.com/gianlucamazza/flymsg/issues/53), M4 [#36](https://github.com/gianlucamazza/flymsg/issues/36)                                                                                                                   | blocked on the steps above; existing calibration tasks are not held-out evidence                                               |
| Observability            | E6 [#54](https://github.com/gianlucamazza/flymsg/issues/54), workbench [#27](https://github.com/gianlucamazza/flymsg/issues/27)                                                                                                                    | open; run manifests exist (`flymsg.run_manifest/v1`)                                                                           |

### Objective

Connect an externally generated sensory stream to the MaleCNS LIF network, decode measured motor activity into a body action, and feed body state back into sensory input. Do not claim a biologically realistic animal until independent experimental checks pass.

### Invariants

1. Preserve the existing `sim` numerical reference and preregistered validation battery.
2. Every sensor-to-neuron and neuron-to-actuator mapping carries a citation, dataset version, units, confidence and explicit `unmapped` fallback.
3. No invented neuromuscular mapping is promoted from an engineering fixture to a biological claim.
4. Events have monotonic integer microsecond timestamps, stable ordering and deterministic seed provenance.
5. Separate open-loop, sham feedback, shuffled mappings, silencing and held-out tests.
6. Stop safely on invalid mappings, late events, nonfinite physical state or clock drift; never silently discard spikes.

### Interfaces

- `StimulusFrame(time_us, modality, payload, coordinate_frame, provenance)`
- `SensoryEncoder.encode(frame) -> tuple[SpikeEvent, ...]`
- `NeuralStepper.advance(until_us, incoming_spikes) -> tuple[SpikeEvent, ...]`
- `MotorDecoder.decode(spikes, interval_us) -> tuple[MotorCommand, ...]`
- `Body.step(commands, until_us) -> BodyState`
- `Sensor.read(body_state, until_us) -> tuple[StimulusFrame, ...]`

These are target interfaces, not implemented classes. The existing `flymsg.embodiment` v1 contracts should be reused or versioned, not silently broken.

### Delivery sequence

#### E1 — Neural online stepping

- Refactor LIF execution to pause/resume without changing spike ordering.
- Compare concatenated online steps with batch execution at identical seeds, bit-for-bit on the supported runtime.
- Add adversarial boundary, refractory, delay-ring and input-order tests.

#### E2 — Stimulus layer

- Implement a synthetic, deterministic looming angular-size/velocity waveform with documented geometry and sampling.
- Implement a separately validated LC4 encoder; do not label a generic rate heuristic as biologically measured.
- Compare against constant-rate Poisson baseline and a time-shuffled control.

#### E3 — Physical loop

- Reuse M0 clocks, provenance and fail-closed contracts.
- Use `MockBody` first; feedback must reach the actual neural stepper, not only a trace.
- Make mapping confidence and absence explicit; refuse unmapped MaleCNS motor actuation.

#### E4 — Biological actuator and body

- Map a specific motor pathway to a physical actuator only after sourcing muscle/kinematic evidence.
- Evaluate FlyBody/MuJoCo separately for physics, sex/morphology mismatch, licensing and Python environment isolation.
- Compare closed-loop behavior with independent experimental recordings, not the calibrated looming task alone.

### E2 exploratory looming encoder

Added in v0.8.23 (PR #47). Exploratory, not validated perception.

`flymsg.sensory.encode_looming` turns a circular object of radius `r`, approaching along the
viewing axis at constant speed `v` from distance `d0`, into timestamped drive samples on an
integer-microsecond grid. The distance is `d(t) = d0 - vt`, the angular size `2 atan(r/d)` and
the expansion rate its derivative, `2rv / (d² + r²)`. The rate is
`min(max_rate, baseline + gain × expansion)`. Gain and ceiling have no measured value, so the
caller states both; there is no default. A sample holds until the next one.

`flymsg.sensory_runtime.schedule_sensory_drive` draws seeded Poisson counts from those rates
and schedules them on a `CpuRuntime` at its current step boundary. The neural tick and the
number of input columns come from the runtime, so a rate cannot be scaled by the wrong step.

This is not a measured LC4 tuning curve, a retinal model or a sensor-to-bodyId map. The
`sim`, `validate` and `behavior` paths are unchanged, and the 29/29 calibration checks and the
failed held-out and silence checks are not evidence for this encoder. Before E2 can pass it
needs LC4/LPLC2 tuning data with uncertainty, a map from samples to MaleCNS sensory bodyIds,
and a comparison with the constant-rate Poisson drive and a time-shuffled control.

### Evidence each step needs

From the research plan of PR #47. A step that lacks its evidence keeps the synthetic label.

- **Looming transduction.** What LC4 encodes (angular size, expansion, contrast,
  time-to-collision), over which stimulus regime, with what trial-to-trial variability; whether
  LC4 and LPLC2 are interchangeable. Record DOI, data accession, licence, fly sex, genotype,
  stimulus geometry and contrast, neural identity, recording modality and sampling, latency
  distribution, replicates, confidence intervals and whether raw trials are available. Hold
  out animals or trials before any fit. Anchors: von Reyn et al. 2014 (doi:10.1038/nn.3741),
  Ache et al. 2019 (doi:10.1016/j.cub.2019.01.079).
- **Motor map.** Which TTMn bodyIds innervate which jump muscles, bilaterally, with measured
  activation, force and timing. Record bodyId, cell type, muscle, laterality, source,
  anatomical evidence, confidence, units, morphology sex and the FlyBody actuator with its
  commit. Without evidence a row stays `unmapped` and the command fails.
- **Physical body.** Pin FlyBody and MuJoCo, isolate them from the Python 3.13 runtime,
  record the morphology and sex mismatch, and validate timebase, units, contacts and
  integration stability before comparing kinematics with independent recordings. A walking
  policy is not a connectome motor decoder.
- **Falsification.** Freeze protocols and seeds before running: real against shuffled
  connectome, looming against matched non-looming controls, intact against bilateral DNp01
  silencing, feedback against matched open loop, and sensitivity over parameters, seeds and
  datasets. Report effect sizes, intervals, failure thresholds and every negative result.

### Acceptance gates

- E1: batch/stream parity on synthetic and MaleCNS fixtures; no regressions.
- E2: replayable timestamped stimuli, calibrated response and negative controls.
- E3: closed-loop causal feedback test that fails when feedback is disconnected.
- E4: measured motor map and held-out behavioral performance, with failures reported.
- Performance: publish real-time factor, memory and latency distribution; do not claim real-time until measured.

### Existing evidence and blockers

- `docs/embodiment.md`: M0 produces synthetic sensory events but does not feed them into LIF.
- `validation/motor_map.yaml`: all real actuators unmapped.
- `docs/behavior.md`: one-bit looming feedback exists but GF silencing fails.
- `docs/benchmarks.md`: held-out olfactory specificity/stability fails.
- `docs/model.md`: absent gap junctions, plasticity and cell-specific parameters must not be invented to force a pass.
