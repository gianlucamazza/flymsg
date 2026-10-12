# Embodied v1: implementation contract

Status: proposed; M0 remains the only implemented body fixture.

## Objective
Connect an externally generated sensory stream to the MaleCNS LIF network, decode measured motor activity into a body action, and feed body state back into sensory input. Do not claim a biologically realistic animal until independent experimental checks pass.

## Invariants
1. Preserve the existing `sim` numerical reference and preregistered validation battery.
2. Every sensor-to-neuron and neuron-to-actuator mapping carries a citation, dataset version, units, confidence and explicit `unmapped` fallback.
3. No invented neuromuscular mapping is promoted from an engineering fixture to a biological claim.
4. Events have monotonic integer microsecond timestamps, stable ordering and deterministic seed provenance.
5. Separate open-loop, sham feedback, shuffled mappings, silencing and held-out tests.
6. Stop safely on invalid mappings, late events, nonfinite physical state or clock drift; never silently discard spikes.

## Interfaces
- `StimulusFrame(time_us, modality, payload, coordinate_frame, provenance)`
- `SensoryEncoder.encode(frame) -> tuple[SpikeEvent, ...]`
- `NeuralStepper.advance(until_us, incoming_spikes) -> tuple[SpikeEvent, ...]`
- `MotorDecoder.decode(spikes, interval_us) -> tuple[MotorCommand, ...]`
- `Body.step(commands, until_us) -> BodyState`
- `Sensor.read(body_state, until_us) -> tuple[StimulusFrame, ...]`

These are target interfaces, not implemented classes. The existing `flymsg.embodiment` v1 contracts should be reused or versioned, not silently broken.

## Delivery sequence
### E1 — Neural online stepping
- Refactor LIF execution to pause/resume without changing spike ordering.
- Compare concatenated online steps with batch execution at identical seeds, bit-for-bit on the supported runtime.
- Add adversarial boundary, refractory, delay-ring and input-order tests.

### E2 — Stimulus layer
- Implement a synthetic, deterministic looming angular-size/velocity waveform with documented geometry and sampling.
- Implement a separately validated LC4 encoder; do not label a generic rate heuristic as biologically measured.
- Compare against constant-rate Poisson baseline and a time-shuffled control.

### E3 — Physical loop
- Reuse M0 clocks, provenance and fail-closed contracts.
- Use `MockBody` first; feedback must reach the actual neural stepper, not only a trace.
- Make mapping confidence and absence explicit; refuse unmapped MaleCNS motor actuation.

### E4 — Biological actuator and body
- Map a specific motor pathway to a physical actuator only after sourcing muscle/kinematic evidence.
- Evaluate FlyBody/MuJoCo separately for physics, sex/morphology mismatch, licensing and Python environment isolation.
- Compare closed-loop behavior with independent experimental recordings, not the calibrated looming task alone.

## Acceptance gates
- E1: batch/stream parity on synthetic and MaleCNS fixtures; no regressions.
- E2: replayable timestamped stimuli, calibrated response and negative controls.
- E3: closed-loop causal feedback test that fails when feedback is disconnected.
- E4: measured motor map and held-out behavioral performance, with failures reported.
- Performance: publish real-time factor, memory and latency distribution; do not claim real-time until measured.

## Existing evidence and blockers
- `docs/embodiment.md`: M0 produces synthetic sensory events but does not feed them into LIF.
- `validation/motor_map.yaml`: all real actuators unmapped.
- `docs/behavior.md`: one-bit looming feedback exists but GF silencing fails.
- `docs/benchmarks.md`: held-out olfactory specificity/stability fails.
- `docs/model.md`: absent gap junctions, plasticity and cell-specific parameters must not be invented to force a pass.
