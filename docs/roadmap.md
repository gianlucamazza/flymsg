# Roadmap: what the model covers, and what waits on outside evidence

Status on 2026-10-13. flymsg has answered the questions the connectome and the model can
answer by themselves. What remains open needs a measurement from an animal, a published map,
or hardware. This page lists what of the brain the model uses, each open item, what would
unblock it, and what is ready for when it arrives. Nothing here is a result.

## Brain coverage

Numbers from `scripts/brain_coverage.py`, which reads `data/` and changes nothing.

| Part                    | In the model                                                                                                                                                                                                                                                           | Left out, and why                                                                                                                                                                                                                                                            |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Neurons                 | All 165,122 traced MaleCNS neurons, brain and VNC                                                                                                                                                                                                                      | Untraced fragments (not in the release's neuron list)                                                                                                                                                                                                                        |
| Chemical synapses       | 124,025,046, signed by the presynaptic transmitter: 59.24% excitatory, 38.16% inhibitory                                                                                                                                                                               | 2.61% leave neurons with sign 0 ([model](model.md#synapse-sign)): 3,602 neurons whose transmitter is unclear or missing (1.65%) and 541 modulatory ones (0.95%)                                                                                                              |
| Unsigned, cross-checked | —                                                                                                                                                                                                                                                                      | Of the 3,602, 1,381 match a FlyWire type; 540 of those types are at least 90% one transmitter, and 288 neurons would get a fast one (0.34% of synapses). Not applied: the gain is small and the FlyWire label is a second prediction, from a female brain, not a measurement |
| Electrical synapses     | None                                                                                                                                                                                                                                                                   | Not visible in EM at this resolution; identified pairs have no conductance a LIF can use ([#85](https://github.com/gianlucamazza/flymsg/issues/85))                                                                                                                          |
| Neuromodulation         | None as a fast sign; one optional, locked rule: dopamine-gated depression at KC → MBON11 (Hige et al. 2015); v1 inconsistent, because the model's Kenyon cell code is not sparse                                                                                       | No per-type gain or time constant measured outside a few synapses ([#85](https://github.com/gianlucamazza/flymsg/issues/85))                                                                                                                                                 |
| Eyes                    | Every column with a measured viewing direction (`flymsg eye`: 843 R, 835 L); photoreceptor terminals and the column grid are in the volume: 875 (L) and 892 (R) columns; R7 and R8 map to 533–698 columns per side; R1–R6 to 182 (L) and 380 (R), many being fragments | No eye encoder: stimuli enter as Poisson spikes into a named cell type such as LC4 ([#84](https://github.com/gianlucamazza/flymsg/issues/84))                                                                                                                                |
| Other sense organs      | Sensory axons enter as neurons (2,635 ORN, 672 Johnston's organ, VNC sensory)                                                                                                                                                                                          | Their cell bodies and transduction are in the periphery, outside the volume                                                                                                                                                                                                  |
| 3D view                 | The scene's neurons at source resolution; 114 neuropil shells; every soma in the volume as a point (140,024)                                                                                                                                                           | 25,098 neurons without a soma in the volume, mostly sensory                                                                                                                                                                                                                  |

## Realism plan

Each step uses sourced values only, stays optional until validated, is locked before its run,
and is judged against a measurement it was not built from. Ordered by how much realism it adds
and how much evidence exists.

| Step | What                                                                                                                                                                  | Evidence                                                         | Independent test                                                                            |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| P1   | Eye ([#84](https://github.com/gianlucamazza/flymsg/issues/84)): column directions (done), stimulus per column, graded input                                           | Zhao et al. 2025, Nern et al. 2025, Lappalainen et al. 2024      | T4/T5 direction selectivity (Maisak et al. 2013); GF size/velocity split (Ache et al. 2019) |
| P2   | Kenyon cell sparseness ([#95](https://github.com/gianlucamazza/flymsg/issues/95)): v1: KC → KC explains density, not the 95% odor overlap; next, antennal-lobe spread | KC→KC synapses axo-axonal (Eichler et al. 2017); APL non-spiking | 5–10% of KCs per odor (Honegger et al. 2011)                                                |
| P3   | Odors as receptor response vectors ([#96](https://github.com/gianlucamazza/flymsg/issues/96))                                                                         | DoOR (Münch & Galizia 2016), Hallem & Carlson 2006               | KC overlap between odors; KC → MBON11 v2 (#85)                                              |
| P4   | Body and jump: FlyGym backend ([#90](https://github.com/gianlucamazza/flymsg/issues/90)), TTM actuator ([#94](https://github.com/gianlucamazza/flymsg/issues/94))     | Zumstein et al. 2004, Allen & Murphey 2007                       | Escape takeoff velocity ≈ 0.48 m/s (Card & Dickinson 2008)                                  |
| P5   | Non-spiking neurons for the documented types ([#97](https://github.com/gianlucamazza/flymsg/issues/97))                                                               | Papadopoulou et al. 2011 (APL); photoreceptors, lamina           | Known graded responses (e.g. L1/L2)                                                         |

Blocked outside the model: gap junctions and neuromodulation
([#85](https://github.com/gianlucamazza/flymsg/issues/85)), per-type membrane parameters.

## Done model-side

| Item                                                           | Where                                                                                             |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Engine parity with Shiu et al. 2024 (brian2)                   | [model](model.md)                                                                                 |
| Calibration battery 29/29; held-out ORN_DM1 fails              | [validation](validation.md), [benchmarks](benchmarks.md)                                          |
| Sensitivity grid (#28)                                         | [validation](validation.md)                                                                       |
| One-bit looming loop; DNp01 silence check fails                | [behavior](behavior.md)                                                                           |
| Residual `TTMn_R` drive: DNp02 and DNp06, replicated (#20)     | [behavior](behavior.md#result-of-version-3-2026-10-12)                                            |
| KC → MBON11 depression v1 run: inconsistent (#85)              | [model](model.md#dopamine-gated-depression-at-kenyon-cell-to-mbon11-synapses-optional-2026-10-13) |
| Left mirror and direct drive of the pair, locked (#76)         | [behavior](behavior.md#residual-partner-follow-up)                                                |
| M0 interface, M1 jump body, M2 closed loop (engineering)       | [embodiment](embodiment.md)                                                                       |
| R0 incremental CPU runtime; native executor matches the oracle | [runtime](runtime.md)                                                                             |
| Archived outputs; figures redraw from a clone                  | [`results/`](../results/README.md)                                                                |

## Blocked on evidence

| Issue                                                                                                                 | Blocked by                                                                                                                                                               | Unblocked by                                                                                                                              | Ready when it arrives                                                                                 |
| --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| [#34](https://github.com/gianlucamazza/flymsg/issues/34) M2                                                           | No measured LC4 tuning: the transducer's gain and ceiling are stated by the caller                                                                                       | LC4 or LPLC2 responses to looming with trial variability, mapped to MaleCNS bodyIds (anchors: von Reyn et al. 2014, Ache et al. 2019)     | `sensory_runtime.schedule_sensory_drive`, the closed loop with its three controls                     |
| [#84](https://github.com/gianlucamazza/flymsg/issues/84) eye                                                          | No luminance → photoreceptor gain for a spiking LIF; no MaleCNS column → viewing-direction table                                                                         | A registration of the MaleCNS grid to the FAFB eye map (Zhao et al. 2025) and a graded-input mode, with the gain stated as a compensation | The column grid and the photoreceptor-to-column assignment (`scripts/brain_coverage.py`)              |
| [#85](https://github.com/gianlucamazza/flymsg/issues/85) electrical, modulation                                       | No junctional conductance; no gap-junction list; no per-type modulatory effect                                                                                           | Paired recordings with conductance and input resistance; a ShakB puncta map on MaleCNS bodyIds; receptor maps with measured effects       | The sign table and its documented exclusions                                                          |
| [#19](https://github.com/gianlucamazza/flymsg/issues/19), [#35](https://github.com/gianlucamazza/flymsg/issues/35) M3 | No published assignment of a MaleCNS motor neuron to a FlyBody actuator; FlyBody has no tergotrochanter joint (FlyGym's NeuroMechFly has the coxa-trochanter joint, #90) | A muscle-level map for `TTMn_L` and `TTMn_R` with force and timing, and a body that has the joint                                         | `validation/motor_map.yaml` (fail-closed, every row `unmapped`), the M0 contracts, the timestep rules |
| [#36](https://github.com/gianlucamazza/flymsg/issues/36) M4                                                           | No held-out animal measurement for a model prediction                                                                                                                    | An animal test of the predictions below, pre-registered before the data are seen                                                          | The predictions, the frozen partition, the behavior lock                                              |

## Blocked on hardware

| Issue                                                       | Blocked by                                                  | Ready                                               |
| ----------------------------------------------------------- | ----------------------------------------------------------- | --------------------------------------------------- |
| [#39](https://github.com/gianlucamazza/flymsg/issues/39) R1 | GPU parity needs a D3D12 hardware adapter; CI has only WARP | The HLSL shader, DX12 host and fixtures build in CI |
| [#40](https://github.com/gianlucamazza/flymsg/issues/40) R2 | A physical Series S console                                 | The UWP worker, job assets, runbook                 |

## What an animal test could check

Model predictions on MaleCNS, stated so that an experiment could test them. None is a claim
about the fly.

- **Escape without the giant fiber.** With both DNp01 silenced, looming still drives `TTMn`
  in the model. Flies without a functional giant fiber still take off from looming, through
  slower takeoffs (von Reyn et al. 2014); the model is consistent with that, which is not a
  test.
- **DNp02 and DNp06.** In the model, with DNp01 silenced, silencing either DNp02 or DNp06
  removes every `TTMn_R` spike (twelve seeds, scan v2 and v3). For an animal: with the giant
  fiber silenced, silencing DNp02 or DNp06 should abolish the remaining looming-evoked
  takeoffs. The follow-up (#76) adds the side and whether the pair is sufficient.
- **Left and right differ.** The residual drive is weaker on the left in this animal. One
  connectome cannot say whether that is individual variation or a population bias.

## Open model-side

- [#24](https://github.com/gianlucamazza/flymsg/issues/24) viewer benchmark:
  `scripts/bench_viewer.py` is ready and refuses a loaded machine; the baseline waits for an
  idle one.
