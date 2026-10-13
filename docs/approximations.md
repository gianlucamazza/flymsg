# Approximations: what the model simplifies, and why it stays

Status on 2026-10-13. Every simplification of the model in one place, each with its status
and what would remove it. Nothing here is new: each row restates a page or a lock, which
stays the authority. The [roadmap](roadmap.md) holds the verdicts.

Status words:

- **measured**: the value is taken from a cited measurement;
- **scanned**: the quantity is not measured, so a lock runs its whole plausible range and
  reports whether the verdict depends on it;
- **selected**: chosen among stated variants by model selection, then replicated on fresh
  seeds;
- **compensation**: a structural simplification the lock or page names;
- **blocked**: removing it needs a measurement, a published map or hardware that does not
  exist yet (issue linked).

None of these can be removed by writing code alone. A value invented to fill a gap would be a
new, unsourced approximation. Sources that could lift some of them are collected in
[leads](leads.md).

## Neurons and dynamics

| Simplification                                                                                                      | Status                       | Removed by                                                                                                              | Source                                                           |
| ------------------------------------------------------------------------------------------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Point leaky integrate-and-fire neurons, no morphology or compartments                                               | compensation                 | Per-type passive and active properties measured at scale; none exist for most of the 165,122 neurons                    | [model](model.md#dynamics)                                       |
| One parameter set for every neuron (τ_m 20 ms, τ_syn 5 ms, v_th −45 mV, t_ref 2.2 ms)                               | measured (Shiu et al. 2024)  | Per-type values; the same gap as above                                                                                  | [model](model.md#parameters)                                     |
| One synaptic delay, 1.8 ms, for every connection                                                                    | measured (Shiu et al. 2024)  | Per-connection delays from conduction distances and measured velocities                                                 | [model](model.md#parameters)                                     |
| Every neuron spikes by default; graded (non-spiking) neurons only inside a lock (photoreceptors, L1–L3 in T4/T5 v2) | compensation; curves scanned | A Drosophila voltage-to-release curve ([#97](https://github.com/gianlucamazza/flymsg/issues/97)), **blocked: evidence** | [model](model.md#graded-non-spiking-neurons-optional-2026-10-13) |
| Fixed step of 0.1 ms; discrete events act at step boundaries                                                        | measured step (Shiu et al.)  | Not a biological gap; finer steps change cost, not the model                                                            | [model](model.md#dynamics)                                       |
| Input arriving in a neuron's own spike step is lost to the reset (about 1% at 100 Hz)                               | compensation (brian2 parity) | A model change, then a new validation run                                                                               | [model](model.md#dynamics)                                       |

## Synapses

| Simplification                                                                                       | Status                                      | Removed by                                                                                                                                           | Source                                                                                            |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Weight = synapse count × `w_syn`; no per-synapse strength                                            | compensation                                | Measured unitary strengths per connection type                                                                                                       | [model](model.md#dynamics)                                                                        |
| `w_syn` 0.192 mV: Shiu's 0.275 divided by 1.43, the lower quartile of the MaleCNS/FAFB density ratio | selected (29/29, replicated on fresh seeds) | A measured MaleCNS-specific scale                                                                                                                    | [model](model.md#synapse-weight-scaled-for-synapse-density)                                       |
| Sign from the predicted transmitter; glutamate and histamine inhibitory everywhere                   | measured receptor classes, applied per type | Receptor identity per postsynaptic type                                                                                                              | [model](model.md#synapse-sign)                                                                    |
| 4,143 neurons with sign 0 (unclear transmitter or modulatory), 2.61% of synapses                     | compensation                                | Better transmitter predictions; re-signing from FlyWire types would cover 0.34% of synapses and was judged not worth it                              | [model](model.md#synapse-sign)                                                                    |
| No short-term facilitation or depression; one optional plasticity rule (KC → MBON11)                 | compensation                                | Measured dynamics per synapse type                                                                                                                   | [model](model.md#dopamine-gated-depression-at-kenyon-cell-to-mbon11-synapses-optional-2026-10-13) |
| Neuromodulators have no fast effect (sign 0)                                                         | compensation                                | Per-type gains and time constants ([#85](https://github.com/gianlucamazza/flymsg/issues/85)), **blocked: evidence**                                  | [model](model.md#synapse-sign)                                                                    |
| No electrical synapses by default; optional `sim.Gap` inside a lock                                  | compensation; coefficients measured (KC v5) | A gap-junction list on MaleCNS bodyIds and junctional conductances ([#85](https://github.com/gianlucamazza/flymsg/issues/85)), **blocked: evidence** | [model](model.md#electrical-synapses-optional-2026-10-13)                                         |

## Input and senses

| Simplification                                                                                     | Status                       | Removed by                                                                                                                       | Source                               |
| -------------------------------------------------------------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| Default stimulus: Poisson spikes into a named type, one kick of 48.1 mV per input spike            | measured scale (Shiu et al.) | Sensory transduction models for each organ                                                                                       | [model](model.md#stimulus-and-rates) |
| Odors: DoOR responses are normalised; the rate for a response of 1 (100 Hz) is stated by each lock | compensation                 | Absolute ORN firing rates per odorant and receptor                                                                               | [model](model.md#stimulus-and-rates) |
| Eye: linear photoreceptors without adaptation; only columns with a viewing direction are driven    | compensation (T4/T5 v2 lock) | Measured Drosophila photoreceptor transduction ([#84](https://github.com/gianlucamazza/flymsg/issues/84)), **blocked: evidence** | [eye](eye.md)                        |
| Sensory cell bodies and transduction are outside the volume                                        | compensation                 | Not in the connectome                                                                                                            | [roadmap](roadmap.md)                |

## Body

| Simplification                                                                                        | Status                              | Removed by                                                                                                                                                      | Source                      |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| M1/M2: one-degree-of-freedom body, engineered decoder and transducer gains                            | compensation (labelled engineering) | Measured LC4 tuning ([#34](https://github.com/gianlucamazza/flymsg/issues/34)) and a motor map, **blocked: evidence**                                           | [embodiment](embodiment.md) |
| No general motor map: every row of `validation/motor_map.yaml` is unmapped                            | blocked                             | Independent motor-neuron → muscle evidence ([#19](https://github.com/gianlucamazza/flymsg/issues/19), [#35](https://github.com/gianlucamazza/flymsg/issues/35)) | [embodiment](embodiment.md) |
| NeuroMechFly jump: open loop, TTM only, twitch shape not measured, female body with a male connectome | compensation (jump3d lock)          | The femur-tibia extensor force and the other legs' drive, both unmeasured                                                                                       | [embodiment](embodiment.md) |

## Numerics of electrical synapses

| Simplification                                                                                                       | Status                        | Removed by                                                                                                                             | Source                            |
| -------------------------------------------------------------------------------------------------------------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| Registered protocols (KC v5, T4/T5 v2) keep boundary-only refractory reset; new configurations use continuous clamps | compensation (protocols kept) | A new prospective lock for any rerun under continuous clamps                                                                           | [run integrity](run-integrity.md) |
| The native executor refuses refractory electrical fixtures; GPU and console are not qualified                        | blocked                       | Physical hardware ([#39](https://github.com/gianlucamazza/flymsg/issues/39), [#40](https://github.com/gianlucamazza/flymsg/issues/40)) | [runtime](runtime.md)             |

## Per-lock compensations

Each lock lists its own; the file is the authority.

| Lock                                                        | Count | Main items                                                                                                                     |
| ----------------------------------------------------------- | ----: | ------------------------------------------------------------------------------------------------------------------------------ |
| [`kc_sparseness.yaml`](../validation/kc_sparseness.yaml) v5 |     5 | Cholinergic ALLN class stands in for eLNs; somatic coefficients; no rectification; rectangular spikelet; step boundaries       |
| [`mb_plasticity.yaml`](../validation/mb_plasticity.yaml) v1 |     7 | Eligibility window shape, all-or-none pulses, both sides, no recovery, odors as ORN types                                      |
| [`t4t5.yaml`](../validation/t4t5.yaml) v2                   |     9 | Threshold-linear release, symmetric LMC release, scanned LMC rate, linear photoreceptors, one time constant, mirrored left eye |
| [`jump3d.yaml`](../validation/jump3d.yaml) v1               |     6 | Open loop, held posture, fixed moment arm, twitch shape, TTM only, female body                                                 |

## What this means for the results

The validation battery passes 29/29 with the defaults; the held-out ORN_DM1 test, the
DNp01 silence check and Kenyon cell sparseness (v1–v5) fail. The model is a connectome-
constrained hypothesis generator, not a validated fly: biological validation (M4,
[#36](https://github.com/gianlucamazza/flymsg/issues/36)) is blocked on an independent
held-out benchmark.
