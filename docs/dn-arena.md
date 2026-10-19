# DN arena

Version 1 of the synthetic steering fixture of the [DN-arena ADR](adr-dn-arena.md):
the full MaleCNS v1.0 connectome in a closed loop with the kinematic planar body
`flymsg.arena`, an engineered descending-neuron readout (`flymsg.dn_decoder`) and an
engineered photoreceptor drive from a lateral dark sphere. Lock:
[`validation/dn_arena.yaml`](https://github.com/gianlucamazza/flymsg/blob/main/validation/dn_arena.yaml)
v1 (issue #263). Neuron identities: [DN inventory](dn-arena-inventory.md).

## Version 1 result: uninformative

**Envelope verdict: `uninformative`.** At every cell of the gain envelope (yaw gain
0.5, 2 and 8 °/s per Hz × forward gain 0.05 and 0.2 mm/s per Hz), the six decoder
neurons (DNa01 L/R, DNa02 L/R, oDN1 = `DNg97` L/R) fired no spike in the intact arm.
The lock's no-go therefore applies: with a silent readout, the decoder sends no
command, and the comparison with the 39 wiring-null shuffles is empty.

| Arm or control                                        | Heading change, 200–1,000 ms (rad) | Decoder spikes |
| ----------------------------------------------------- | ---------------------------------: | -------------: |
| intact                                                |                                  0 |              0 |
| disconnected                                          |                                  0 |              0 |
| shuffled (equal to disconnected, outside the verdict) |                                  0 |              0 |
| replay (parity passed)                                |                                  0 |              0 |
| silenced                                              |                                  0 |              0 |
| wiring null, 39 seeds per cell (min, median, max)     |                            0, 0, 0 |              0 |
| script (no connectome)                                |                              1.396 |              — |

Every cell gives the same numbers. The script control turns toward the darker eye at
100 °/s from 200 ms on: 0.8 s × 100 °/s = 80° = 1.396 rad. It shows that the body, the
stimulus geometry and the score respond as locked. Replay parity holds in all six cells.

Archived tables:
`results/dn-arena/v1.executions/df21c26c…/output/` (`results.csv`, `verdict.json`,
`manifest.json`). The 265 full closed-loop records (2.2 GB gzipped JSON) stay in the
run directory. `results.csv` carries the sha256 of each record's canonical JSON, and
the run is deterministic, so a rerun of the same commit reproduces them. The run was
made from clean `main` at `1043368`, with 4 workers, in 1 h 48 min of wall time under
load. As the lock's data rule requires, it is archived as it is and will not be rerun
with new gains, geometry or seeds.

## Why the readout is silent (exploratory, after the verdict)

This section was written after the verdict. It does not change it and is not scored.
One open-loop second at full light drove every input photoreceptor at 100 Hz, the
upper bound, since the sphere only lowers rates. The run used Poisson seed 7000 and
the lock's 22-step dead time
(`scripts/dn_arena_v1_exploratory.py`).

| Class                | Neurons | Active |  Spikes |
| -------------------- | ------: | -----: | ------: |
| Input photoreceptors |   3,903 |  3,903 | 321,261 |
| Lamina L1–L5         |   8,883 |      0 |       0 |
| Mi / Tm / TmY        |  37,631 |      0 |       0 |
| T4 / T5              |  13,585 |      0 |       0 |
| LC / LPLC            |   4,674 |      0 |       0 |
| DN\* types           |   1,342 |      0 |       0 |
| Whole brain          | 165,122 |  3,903 | 321,261 |

Only the photoreceptors fire. All 64,171 of their output synapses in the model are
inhibitory: their transmitter is histamine, and the model gives histamine a negative
sign. In a LIF network with no other drive and no tonic activity, inhibition alone
never brings a neuron to threshold. The silence is therefore structural. It holds for
any photoreceptor rate, any gain and any stimulus geometry. The decoder neurons are
only 2–3 synapses from the inputs, so the distance is not the cause.

This is the blocker T4/T5 version 1 had already shown: contrast stopped at the
lamina ([eye](reference/eye.md)). The DN-arena ADR kept the Poisson drive for version 1
(Decision 3), and the lock's no-go turned the outcome into an explicit
`uninformative` rather than a false null. With hindsight, the T4/T5 version 1 result
already predicted this outcome before the lock. The lock cites that version only for
its 100 Hz rate (`transducer.rate_from`), not as a prediction of a silent readout.

## What follows

- In the fly, photoreceptors hyperpolarize LMCs through graded, sign-inverting
  transmission. The [graded eye ADR (VEE-1)](adr-vee1-graded-eye.md) replaces the
  spiking photoreceptor drive with the graded pathway of T4/T5 versions 2–4
  (`vee1-1` to `vee1-3`).
- A DN-arena version 2 needs its own lock (`vee1-4`) with owner approval. Version 4 of
  T4/T5 is `robust: neither`, so the graded pathway carries the edge into the medulla
  but is not yet selective. Version 2 may also be uninformative, and its lock has to
  say so before any run.
- Nothing here is a claim about steering, the descending neurons or flight. The
  components keep the statuses of the ADR's evidence table; `validation/evidence.yaml`
  is unchanged.
