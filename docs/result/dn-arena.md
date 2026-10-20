# DN arena

The synthetic steering fixture of the [DN-arena ADR](../adr/adr-dn-arena.md): the full
MaleCNS v1.0 connectome in a closed loop with the kinematic planar body `flymsg.arena`,
an engineered descending-neuron readout (`flymsg.dn_decoder`) and a lateral dark
sphere. Version 1 drives the photoreceptors with Poisson rates; version 2 drives the
graded visual pathway of T4/T5 version 4. Version 3 is a draft lock and has not run;
it is described below. Lock:
[`validation/dn_arena.yaml`](https://github.com/gianlucamazza/flymsg/blob/main/validation/dn_arena.yaml)
(issue #263). Neuron identities: [DN inventory](../dn-arena-inventory.md).

![DN arena: intact heading change against 39 wiring nulls](../img/dn-arena.svg)

## Version 2 result: depends

**Envelope verdict: `depends`.** The three configurations do not share a verdict. At
lamina-to-medulla gain 1 the six decoder neurons fire no spike in the intact arm, so
the lock's no-go makes it `uninformative`. At gains 4 and 16 the readout fires, and the
intact heading change lies inside the range of the 39 wiring-null shuffles: `null`.
No configuration gives a `difference`.

| Gain | Intact (rad) | Disconnected | Shuffled | Replay | Silenced | Wiring null min, median, max | Intact decoder spikes             | Verdict       |
| ---: | -----------: | -----------: | -------: | -----: | -------: | ---------------------------- | --------------------------------- | ------------- |
|    1 |            0 |            0 |        0 |      0 |        0 | −1.955, 0, 1.745             | none                              | uninformative |
|    4 |       −0.628 |       −0.663 |   −0.663 | −0.628 |        0 | −1.955, 0, 1.745             | DNa02 R 20, DNa02 L 3             | null          |
|   16 |        0.175 |        0.244 |    0.244 |  0.175 |        0 | −1.990, 0, 1.710             | DNa02 L 22, DNa02 R 21, DNa01 L 1 | null          |

Heading change is the unwrapped heading from 200 to 1,000 ms; positive turns left,
toward the sphere. The script control turns 1.396 rad toward the darker eye in every
configuration (intact minus script: −1.396, −2.025, −1.222 rad). Replay parity holds in
all three. oDN1 never fires, so the forward command is 0 in every intact arm.

What the numbers say, within the lock:

- The intact readout is small: 23 and 44 decoder spikes in one second, against up to
  71 in single shuffles. The intact turn has opposite signs at gains 4 and 16.
- Disconnected and intact differ by at most 0.07 rad. The body's feedback changes the
  readout by a few spikes; this alone does not say what in the open-loop input drives
  it (see the drive test below).
- Shuffled equals disconnected, as in version 1. With a static sphere the disconnected
  input is the same at every tick, so permuting its order changes nothing: the arm is
  degenerate by construction for this stimulus. It is reported and outside the
  verdict.

Archived tables:
`results/dn-arena/v2.executions/edd21a61…/output/` (`results.csv`, `verdict.json`,
`manifest.json`). The 133 closed-loop records (3.5 GB gzipped JSON) stay in the run
directory; `results.csv` carries the sha256 of each record's canonical JSON, and the run
is deterministic. The run was made from clean `main` at `ec3d080`, with 4 workers, in
5 h 23 min of wall time under load. As the lock's data rule requires, it is archived as
it is and will not be rerun with new configurations, gains, geometry or seeds.

### Where the null range comes from (exploratory, after the verdict)

This reading uses only the archived `results.csv`. It does not change the verdict.

In each configuration, 30 or 31 of the 39 shuffles give a heading change of 0. The
same six seeds give every change larger than 0.5 rad in all three configurations (7308,
7316, 7317, 7323, 7327, 7333), and seed 7323 sets the minimum at every gain. In each of
them one decoder neuron dominates with 24 to 71 spikes; oDN1 L adds at most 2. The
dominant neuron's count changes by at most 4 spikes between gains 1, 4 and 16, so that
activity belongs to the shuffled graph more than to the visual gain. The test asks
whether the intact turn falls outside that band, and the intact readout is weaker than
the band's ends. With one stimulus, one decoder cell and 39 nulls, this fixture cannot
separate a small connectome-dependent turn from the shuffled graphs' own activity.

### Why the intact readout does not follow the sphere (exploratory, after the verdict)

Four post-verdict diagnostics, written after the verdict and not scored. Each is one
open-loop second with the body at its reset pose, on the lock's anchored pathway; the
locked sphere reproduces the archived disconnected arm spike for spike, and on the
null graphs the open loop reproduces the archived null counts within one spike.

**Drive test** (`scripts/dn_arena_v2_exploratory.py`). Decoder spikes of the intact
graph:

| Gain | Sphere left (locked)        | Sphere right (mirrored) | No sphere        | Dark |
| ---: | --------------------------- | ----------------------- | ---------------- | ---- |
|    4 | DNa02 R 21, L 3             | DNa02 R 22, L 0         | DNa02 R 20, L 1  | none |
|   16 | DNa02 R 18, L 21, DNa01 L 1 | DNa02 R 24, L 18        | DNa02 R 18, L 23 | none |

Light switches the readout on, but where the sphere is barely matters: mirroring it
changes the yaw readout (left minus right decoder spikes) by 4 at gain 4 and 10 at
gain 16, against a side bias of −19 and +5 with no sphere at all.

**Layer tally** (`scripts/dn_arena_v2_layers.py`). From the medulla to the DN types, the
right hemisphere fires more under every drive, darkness included: at gain 4 under the
locked sphere, Mi/Tm/TmY 28,172 against 15,181 spikes, T4/T5 16,464 against 5,783,
LC/LPLC 3,332 against 1,024, DN types 1,229 against 507. The six decoder neurons follow
it at gain 4 (21 right, 3 left) but not at gain 16 (18 right, 22 left). Mirroring the
sphere moves the mean photoreceptor potential of each eye by less than 1 mV (−0.46 mV
left, +0.73 mV right) and the spikes of each stage from the medulla to the DN types by at most
4.2%.

**Input balance** (same setup). The arena's input photoreceptors are those MaleCNS v1.0
assigns to a column with a lens: 2,251 in the right eye (747 columns) and 1,652 in the
left (651 columns), with 84,411 against 63,251 synapses onto L1–L3 (+33% on the right).
The imbalance is in the reconstruction before our selection: 2,474 traced right-eye
photoreceptors against 1,733 left, of which 201 and 70 receive no column; no side-dependent
filter in `flymsg.eye` or `dn_arena` adds to it. Neuron counts per side are balanced downstream (L1–L5 4,466 and
4,417; T4/T5 6,795 and 6,790). Under uniform light the right lamina therefore receives
a third more drive. At gain 4 this matches the readout's rightward bias, which the
mirror does not reverse; at gain 16 the mirror does reverse it (+4 to −6), so there the
sphere's side acts, weakly. These diagnostics show the imbalance and its downstream
asymmetry; they do not prove it is the only cause of the readout's side.

**Null graphs in darkness** (`scripts/dn_arena_v2_nulls_dark.py`, gain 4). The six
shuffles that set every null change above 0.5 rad fire 84 to 208 decoder spikes with
zero drive, more than under the sphere (24 to 69). Six shuffles silent in the run (7300,
7301, 7303, 7306, 7309, 7311) fire 22 to 145 in darkness and fall silent under light.
The intact graph fires none in darkness. The shuffled graphs' decoder activity is
therefore tonic, and light suppresses and reshapes it rather than creating it.

**Signed paths** (`scripts/dn_arena_v2_paths.py`, no simulation). A linear signed walk
from each eye reaches the decoder neurons in 2–3 synapses with similar weight from both
eyes, and the sign of the yaw proxy for a left sphere alternates from hop to hop (hops 2
to 6: minus, minus, plus, minus, plus). The anatomy gives no consistent lateral steering
expectation at this level of description. A linear walk ignores thresholds, graded
dynamics and delays.

**Reading.** The v2 score compares one stimulus's heading change across graphs.
Three things dominate it that have nothing to do with the sphere's side: the
reconstruction's eye imbalance, the shuffled graphs' tonic activity, and a stimulus that
moves each eye's input by under 1 mV. The verdict stands as locked. A test of steering
by the connectome needs a score that cancels stimulus-independent bias, such as the
contrast between the sphere and its mirror on the same graph with nulls scored the same
way, and a stimulus strong enough to move the lamina. That would be a new lock version
with owner approval; it is not a rerun of version 2.

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
lamina ([eye](../reference/eye.md)). The DN-arena ADR kept the Poisson drive for version 1
(Decision 3), and the lock's no-go turned the outcome into an explicit
`uninformative` rather than a false null. With hindsight, the T4/T5 version 1 result
already predicted this outcome before the lock. The lock cites that version only for
its 100 Hz rate (`transducer.rate_from`), not as a prediction of a silent readout.

## Version 2 lock

`validation/dn_arena.yaml` version 2 is the graded-input lock (`vee1-4`), approved by
the owner and merged on 2026-10-20 (#284), lock hash `1426386c…`. It keeps the MaleCNS
graph, the kinematic body, the lateral dark sphere and the six decoder neurons. The
drive is the kick-equivalent of T4/T5 version 4, `float32(gain * (1 - coverage))`, over
three configurations: lamina-to-medulla gains 1, 4 and 16 at that version's midpoints
and 200 Hz release, the configurations where T4 fires most
([T4 spikes per configuration](../img/t4-spikes.svg)). One decoder cell uses 2 °/s per
Hz of yaw and 0.2 mm/s per Hz of forward. Each graph is dark-anchored before its loop; a
wiring null (seeds 7300–7338) keeps the intact photoreceptor release rate and drive gain
and anchors on its own shuffled graph. A timing-only smoke (no spike, command or heading
read) estimated about 3 h for the run with 4 workers; under load it took 5 h 23 min.

## Version 3 (draft lock, not run)

`validation/dn_arena.yaml` version 3 is a draft (`content_sha256` `7ed0e04d…`). It has
no counted run and no results. The stimulus replaces version 2's static sphere with a
moving dark bar (`optics.Bar` through `closedloop.optical_bars`): width 10.5°, height
48°, a 22.5° sweep at 25°/s, visible from 100000 to 1000000 µs, on a cylinder of
radius 0.1 m whose axis passes through the body's reset position. The left bar's
centre moves from body azimuth −56.25° to −33.75° (rightward, toward the midline); the
mirror is that sweep reflected, from +56.25° to +33.75°. The score, per configuration
and input set, is the mirrored contrast: half the left-minus-mirror change in heading.
It is `null` when that contrast lies inside the 39 wiring-null contrasts (seeds
7400–7438, inclusive) and `difference` otherwise. A negative contrast outside the range
is reported as `difference (wrong sign)`. A configuration is `uninformative` when the
six decoder neurons fire no spike in the intact arm on both sides. The claim's envelope
reads only the `all` input set (`robust: <verdict>`, `depends`, or `uninformative`).
The `paired` set — inputs whose column has a mirror column with a viewing direction
and at least one input — gets the same verdicts, reported as sensitivity outside the
claim. Configurations are lamina-to-medulla gains 4 and 16. One shuffled pathway is
dark-anchored once and serves both sides. A timing-only smoke (no spike, command or heading read) measured 222 s per
anchored pathway, 185 s per 1 s arm and 79 s per record, 4.9 GB per process: about
9 h with 4 workers on an idle host, up to about 16 h under load. The lock awaits owner
approval.

## What follows

- Version 3 is a draft and has not run. A different stimulus, decoder or null count
  would be a new lock with its own approval, not a rerun of version 2.
- Steering by the connectome needs a readout that the shuffled graphs do not match.
  This fixture's six neurons and one second do not give one. The diagnostics above name
  what a further version would have to change: a mirrored-stimulus contrast scored on
  every graph, a stimulus that moves the lamina, and the reconstruction's eye imbalance
  stated as a limit or compensated by a named rule. A body that is not
  kinematic needs the motor and proprioceptive interfaces proposed in #288.
- Nothing here is a claim about steering, the descending neurons or flight. The
  components keep the statuses of the ADR's evidence table; `validation/evidence.yaml`
  is unchanged.
