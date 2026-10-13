# Roadmap: what the model covers, and what waits on outside evidence

Status on 2026-10-13. This page is the index. Each verdict is recorded on the linked page,
and the table adds none. What remains open needs a measurement from an animal, a published
map, hardware, or a lock that is written and not yet run.

The [integrity audit](integrity-audit-2026-10-13.md) records the numerical/provenance
baseline and the accepted corrections. [Run integrity](run-integrity.md) specifies
immutable executions, checkpoint compatibility and explicit electrical numerical modes.
[Approximations](approximations.md) lists every simplification of the model with its status
and what would remove it.

## Results

| Result                                     | Verdict                                                            | Record                                                                                            |
| ------------------------------------------ | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Validation battery, criterion v4           | 29/29 at `w_syn` 0.192, replicated                                 | [validation](validation.md)                                                                       |
| N1, one degree-preserving shuffle          | 5/29, all of them `stability`                                      | [related](related.md#n1-specific-checks-need-the-measured-partners)                               |
| Four null families, 20 draws               | the one-hop headline sits above every draw                         | [nulls](nulls.md)                                                                                 |
| Engine against Shiu et al. brian2          | agrees within noise (r ≥ 0.998)                                    | [comparison](comparison.md#engine-check)                                                          |
| Dimorphism T1–T4                           | courtship runs through fru/dsx; escape and feeding do not          | [dimorphism](dimorphism.md)                                                                       |
| Held-out ORN_DM1 → DM1_lPN                 | fails specific and stability                                       | [benchmarks](benchmarks.md)                                                                       |
| Kenyon cell sparseness v1–v5               | dense or silent, never sparse                                      | [model](model.md#kenyon-cell-sparseness-diagnostic-2026-10-13)                                    |
| KC → MBON11 depression v1                  | inconsistent: both odors go silent                                 | [model](model.md#dopamine-gated-depression-at-kenyon-cell-to-mbon11-synapses-optional-2026-10-13) |
| One-bit looming jump                       | silence fails                                                      | [behavior](behavior.md#result-2026-10-11)                                                         |
| Residual partner scan v2, replicated as v3 | DNp02 and DNp06                                                    | [behavior](behavior.md#residual-partner-scan)                                                     |
| Partner follow-up v1                       | the left mirror replicates; DNp06 alone reaches the jump bit       | [behavior](behavior.md#residual-partner-follow-up)                                                |
| T4/T5 through the eye v1                   | neither                                                            | [eye](eye.md#t4t5-direction-selectivity-through-the-eye-lock-2026-10-13)                          |
| T4/T5 v2                                   | robust: neither; contrast crosses the lamina, stops in the medulla | [eye](eye.md#t4t5-version-2-graded-photoreceptors-and-lamina-lock-2026-10-13-84-97)               |
| NeuroMechFly jump v1                       | short                                                              | [embodiment](embodiment.md#a-ttm-driven-jump-of-neuromechfly-lock-2026-10-13-90-94)               |
| Male vs female synapse counts              | median 1.81× over matched types, a reconstruction difference       | [comparison](comparison.md)                                                                       |
| Published sugar set, FAFB LB3 split        | 14 sugar-like and 6 LB3d-like neurons                              | [comparison](comparison.md)                                                                       |
| Motor map                                  | every row `unmapped`                                               | [`validation/motor_map.yaml`](../validation/motor_map.yaml)                                       |
| Held-out behavior milestone                | no eligible case left in the frozen partition                      | [validation](validation.md)                                                                       |

## Brain coverage

Numbers from `scripts/brain_coverage.py`, which reads `data/` and changes nothing.

| Part                    | In the model                                                                                                                                                                                                                                                           | Left out, and why                                                                                                                                                                                                                                                            |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Neurons                 | All 165,122 traced MaleCNS neurons, brain and VNC                                                                                                                                                                                                                      | Untraced fragments (not in the release's neuron list)                                                                                                                                                                                                                        |
| Chemical synapses       | 124,025,046, signed by the presynaptic transmitter: 59.24% excitatory, 38.16% inhibitory                                                                                                                                                                               | 2.61% leave neurons with sign 0 ([model](model.md#synapse-sign)): 3,602 neurons whose transmitter is unclear or missing (1.65%) and 541 modulatory ones (0.95%)                                                                                                              |
| Unsigned, cross-checked | —                                                                                                                                                                                                                                                                      | Of the 3,602, 1,381 match a FlyWire type; 540 of those types are at least 90% one transmitter, and 288 neurons would get a fast one (0.34% of synapses). Not applied: the gain is small and the FlyWire label is a second prediction, from a female brain, not a measurement |
| Electrical synapses     | Optional (`sim.Gap`), none by default; a spike crosses when the lock sets `spike_mv` and `spike_ms`. Kenyon cell v4 scanned subthreshold coupling; v5, with measured coupling and eLN spikelets, stayed silent                                                         | Not visible in EM at this resolution; identified pairs have no conductance a LIF can use ([#85](https://github.com/gianlucamazza/flymsg/issues/85))                                                                                                                          |
| Neuromodulation         | None as a fast sign; one optional, locked rule: dopamine-gated depression at KC → MBON11 (Hige et al. 2015); v1 inconsistent, because the model's Kenyon cell code is not sparse                                                                                       | No per-type gain or time constant measured outside a few synapses ([#85](https://github.com/gianlucamazza/flymsg/issues/85))                                                                                                                                                 |
| Eyes                    | Every column with a measured viewing direction (`flymsg eye`: 843 R, 835 L); photoreceptor terminals and the column grid are in the volume: 875 (L) and 892 (R) columns; R7 and R8 map to 533–698 columns per side; R1–R6 to 182 (L) and 380 (R), many being fragments | The default stimulus is still Poisson spikes into a named type. Column directions, looming and edge coverage, and graded photoreceptor kicks exist; the gain is a compensation the lock states ([eye](eye.md), [#84](https://github.com/gianlucamazza/flymsg/issues/84))     |
| Other sense organs      | Sensory axons enter as neurons (2,635 ORN, 672 Johnston's organ, VNC sensory)                                                                                                                                                                                          | Their cell bodies and transduction are in the periphery, outside the volume                                                                                                                                                                                                  |
| 3D view                 | The scene's neurons at source resolution; 114 neuropil shells; every soma in the volume as a point (140,024)                                                                                                                                                           | 25,098 neurons without a soma in the volume, mostly sensory                                                                                                                                                                                                                  |

## Realism plan

Each step uses sourced values only, stays optional until validated, is locked before its run,
and is judged against a measurement it was not built from. Ordered by how much realism it adds
and how much evidence exists.

| Step | What                                                                                                                                                                                                                                                                             | Evidence                                                                                                  | Independent test                                                                            |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| P1   | Eye ([#84](https://github.com/gianlucamazza/flymsg/issues/84)): directions, stimuli, graded input done; T4/T5 v1 neither: the spiking lamina cannot invert contrast; v2 robust neither over 17 configurations: graded L1–L3 carry contrast, the spiking medulla does not pass it | Zhao et al. 2025, Nern et al. 2025, Lappalainen et al. 2024                                               | T4/T5 direction selectivity (Maisak et al. 2013); GF size/velocity split (Ache et al. 2019) |
| P2   | Kenyon cell sparseness ([#95](https://github.com/gianlucamazza/flymsg/issues/95)): v1–v5 dense or silent, never sparse. v4 used subthreshold coupling and it drained PNs. v5, with the measured coupling and eLN spikelets of 0–2 ms, stayed silent                              | KC→KC synapses axo-axonal (Eichler et al. 2017); APL non-spiking                                          | 5–10% of KCs per odor (Honegger et al. 2011)                                                |
| P3   | Odors as receptor response vectors ([#96](https://github.com/gianlucamazza/flymsg/issues/96)): `flymsg odor` (done)                                                                                                                                                              | DoOR (Münch & Galizia 2016), Hallem & Carlson 2006                                                        | KC overlap between odors; KC → MBON11 v2 (#85)                                              |
| P4   | Body and jump: FlyGym body, TTM actuator, open and closed loop built; jump v1 short (one leg, no TLM) ([#90](https://github.com/gianlucamazza/flymsg/issues/90), [#94](https://github.com/gianlucamazza/flymsg/issues/94))                                                       | Zumstein et al. 2004, Allen & Murphey 2007                                                                | Escape takeoff velocity ≈ 0.48 m/s (Card & Dickinson 2008)                                  |
| P5   | Non-spiking neurons for the documented types ([#97](https://github.com/gianlucamazza/flymsg/issues/97)): engine class done (`sim.Graded`); no Drosophila release curve (only Calliphora R → LMC), so locks scan the curve over the measured voltage ranges                       | Zheng et al. 2006, Juusola et al. 2016 (operating ranges); Amin et al. 2020 (APL); photoreceptors, lamina | Known graded responses (e.g. L1/L2)                                                         |

Still outside the default model: a gap-junction list, per-type neuromodulation
([#85](https://github.com/gianlucamazza/flymsg/issues/85)) and per-type membrane parameters.
`sim.Gap` can express a caller-stated junction, and a spikelet term when the same lock
sets `spike_mv` and `spike_ms`. `sim.Graded` can express a caller-stated release curve.
`sim.Membrane` can express caller-stated per-neuron membrane and threshold parameters. All
three stay off unless a lock names them.

## Done model-side

| Item                                                                    | Where                                                                                             |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Engine parity with Shiu et al. 2024 (brian2)                            | [model](model.md)                                                                                 |
| Calibration battery 29/29; held-out ORN_DM1 fails                       | [validation](validation.md), [benchmarks](benchmarks.md)                                          |
| Sensitivity grid (#28)                                                  | [validation](validation.md)                                                                       |
| One-bit looming loop; DNp01 silence check fails                         | [behavior](behavior.md)                                                                           |
| Residual `TTMn_R` drive: DNp02 and DNp06, replicated (#20)              | [behavior](behavior.md#result-of-version-3-2026-10-12)                                            |
| KC → MBON11 depression v1 run: inconsistent (#85)                       | [model](model.md#dopamine-gated-depression-at-kenyon-cell-to-mbon11-synapses-optional-2026-10-13) |
| Left mirror replicates; DNp06 alone sufficient at 200 Hz (#76)          | [behavior](behavior.md#residual-partner-follow-up)                                                |
| M0 interface, M1 jump body, M2 closed loop (engineering)                | [embodiment](embodiment.md)                                                                       |
| Eye map, column stimuli, graded photoreceptor kicks                     | [eye](eye.md)                                                                                     |
| Odors as DoOR receptor vectors                                          | [data](data.md#odor-responses-flymsg-odor)                                                        |
| Graded neurons and electrical synapses; spikelets when a lock sets them | [model](model.md#electrical-synapses-optional-2026-10-13)                                         |
| T4/T5 v1 neither; v2 robust neither                                     | [eye](eye.md)                                                                                     |
| NeuroMechFly jump v1 short; closed loop cuts input at takeoff           | [embodiment](embodiment.md)                                                                       |
| R0 incremental CPU runtime; native executor matches the oracle          | [runtime](runtime.md)                                                                             |
| Archived outputs; figures redraw from a clone                           | [`results/`](../results/README.md)                                                                |

## Blocked on evidence

| Issue                                                                                                                 | Blocked by                                                                                                                                                               | Unblocked by                                                                                                                          | Ready when it arrives                                                                                                                      |
| --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| [#34](https://github.com/gianlucamazza/flymsg/issues/34) M2                                                           | No measured LC4 tuning: the transducer's gain and ceiling are stated by the caller                                                                                       | LC4 or LPLC2 responses to looming with trial variability, mapped to MaleCNS bodyIds (anchors: von Reyn et al. 2014, Ache et al. 2019) | `sensory_runtime.schedule_sensory_drive`, the closed loop with its three controls                                                          |
| [#84](https://github.com/gianlucamazza/flymsg/issues/84) eye                                                          | No measured Drosophila release curve. The column → direction table exists. T4/T5 v2: robust neither; the signal stops at the spiking medulla                             | The v2 envelope, judged against Maisak et al. 2013, or a measured photoreceptor and LMC release curve                                 | [eye](eye.md): geometry, `eye.edge_coverage`, `sim.Graded`, `validation/t4t5.yaml` v2                                                      |
| [#85](https://github.com/gianlucamazza/flymsg/issues/85) electrical, modulation                                       | No junctional conductance; no gap-junction list; no per-type modulatory effect                                                                                           | Paired recordings with conductance and input resistance; a ShakB puncta map on MaleCNS bodyIds; receptor maps with measured effects   | `sim.Gap` (off by default; a spike crosses when the lock sets `spike_mv` and `spike_ms`) and the sign table with its documented exclusions |
| [#19](https://github.com/gianlucamazza/flymsg/issues/19), [#35](https://github.com/gianlucamazza/flymsg/issues/35) M3 | No published assignment of a MaleCNS motor neuron to a FlyBody actuator; FlyBody has no tergotrochanter joint (FlyGym's NeuroMechFly has the coxa-trochanter joint, #90) | A muscle-level map for `TTMn_L` and `TTMn_R` with force and timing, and a body that has the joint                                     | `validation/motor_map.yaml` (fail-closed, every row `unmapped`), the M0 contracts, the timestep rules                                      |
| [#36](https://github.com/gianlucamazza/flymsg/issues/36) M4                                                           | No held-out animal measurement for a model prediction                                                                                                                    | An animal test of the predictions below, pre-registered before the data are seen                                                      | The predictions, the frozen partition, the behavior lock                                                                                   |

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

- Integrity corrections are implemented under the accepted ADRs; the full validation
  record is maintained in the [audit](integrity-audit-2026-10-13.md). Archived results and
  already registered boundary-reset protocols preserve their original physics.

- T4/T5 v2: robust neither ([eye](eye.md)); graded L1–L3 carry contrast and the spiking medulla does not pass it.
- Kenyon cell sparseness v5: none
  ([model](model.md#kenyon-cell-sparseness-diagnostic-2026-10-13)). At the measured
  coefficients eLN → PN coupling, with spikelets of up to 2 ms, leaves Kenyon cells silent.
- [#24](https://github.com/gianlucamazza/flymsg/issues/24) viewer benchmark:
  `scripts/bench_viewer.py` is ready and refuses a loaded machine; the baseline waits for an
  idle one.
