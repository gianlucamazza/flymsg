# ADR: graded eye in the closed loop (VEE-1 visual input)

Status: **accepted** by Gianluca Mazza, 2026-10-19 (proposed the same day).
Acceptance authorizes `vee1-1` through `vee1-3`, one reviewed PR at a time. It changes
no code in this commit and authorizes no lock or run: `vee1-4` needs its own approval.

Scope: replace the closed loop's spiking photoreceptor drive with the graded visual
pathway that T4/T5 versions 2–4 already run open loop. It supplements the accepted
[body-wiring](adr-body-wiring.md), [runtime](runtime.md),
[module-boundaries](adr-module-boundaries.md) and
[DN-arena](https://github.com/gianlucamazza/flymsg/blob/main/docs/adr/adr-dn-arena.md)
decisions without editing them. DN-arena Decision 3 (Poisson drive from coverage)
stays the rule for that milestone's version 1; this ADR is the input of a later
version.

## Context

`closedloop.run` turns a transducer's rates into Poisson counts and schedules them as
integer kicks (`closedloop.py`, input phase; record `flymsg.closedloop/v1`,
`Tick.input_counts`). `CpuRuntime` accepts only nonnegative integer kicks, at
construction and in `schedule_inputs` (`runtime.py`). The transducer sets how a
stimulus moves those rates (the synthetic fixture raises its rate with coverage; a
photoreceptor drive lowers it in the dark).

In the one experiment that drove spiking photoreceptors through the eye, T4/T5 version 1,
contrast did not pass the lamina: in a post-verdict exploratory count the photoreceptors
fired about 370,000 spikes per sweep and the lamina stayed silent, because the
photoreceptor → LMC synapses are inhibitory onto spiking LMCs ([eye](../reference/eye.md)). Later
versions made the pathway graded:

- photoreceptors receive a real-valued drive in Poisson-kick units, `gain × (1 −
coverage)` (`eye.photoreceptor_kicks`), with the gain set so full light holds a
  photoreceptor at a stated depolarization (`t4t5.photoreceptor_gain`);
- from version 2, photoreceptors and L1–L3 release graded transmitter (`sim.Graded`,
  `t4t5.graded_spec`), at release rates calibrated per lock; from version 3, Mi1, Tm3,
  Mi4, Mi9 and C3 too (`graded_medulla`);
- version 4 anchors each medulla type's measured range (Groschner et al. 2022 traces)
  at its own settled dark potential over six 200 ms dark passes, scans a lamina →
  medulla gain and sets Behnia et al. 2014's delays through `sim.Membrane`.

Version 4's result is **robust: neither**. The graded path carries the edge into the
medulla: swings grow to about ±10 mV at gain 16 with LMC release 200 Hz. T4 fires
only at medulla release 200 Hz, without the ON/OFF split or the measured direction;
T5 is silent ([eye](../reference/eye.md), version 4). Graded transport is not visual selectivity.

`CpuRuntime` already runs `Graded` and per-neuron `Membrane`, and its checkpoints
cover graded state (release ring, voltage sums). What it lacks is a real-valued input;
what the closed loop lacks is a record that can carry one.

## Decision

1. **Real-valued input drive in `CpuRuntime`.** Add an explicit input encoding:
   `counts` (today's nonnegative integer Poisson counts) or `kick_equivalent`
   (nonnegative finite values per step and input, applied by the existing kernel line
   `v += kick × drive`). The drive is the float32 value version 4 delivers
   (`(gain × light).astype(float32)`, `t4t5.protocol`), stored and applied as that
   float32 value widened to float64, so the kernel's rounding matches `sim.run`; a
   higher-precision transduction would be a separate decision. The encoding is a
   required constructor argument, enters the checkpoint identity, and `schedule_inputs`
   refuses the other encoding's dtype. `counts` stays bit-identical to today.

2. **Closed-loop record version 2.** `flymsg.closedloop/v2` carries `input_encoding`
   and `Tick.input_drive` (integers under `counts`, finite floats under
   `kick_equivalent`), and binds the visual pathway's configuration hash (graded
   specification, timing, dark anchors) into the run identity. Replay replays the
   recorded drive; `replay_parity` compares it exactly. A replay, and a checkpoint
   resume, refuse before any step when the encoding or the pathway hash differs from
   the recorded run's (today replay admission checks only clock, length and input ids),
   with tests for each refusal. Version 1 records keep parsing
   with the version 1 parser and are never rewritten. `closedloop.ARMS` and
   `COMPONENTS` do not change. The transducer of a `kick_equivalent` run returns drive
   per input and step, not a rate; no Poisson draw is made for it, and the input dead
   time (`input_gap_steps`) does not apply to it, while `counts` keeps its dead-time
   filtering and its resume reconstruction from the recorded counts.

3. **One visual-pathway builder, extracted from `t4t5`.** The configuration, timing
   and dark-anchor preparation now inside `t4t5.protocol` move into an importable
   builder that both `t4t5` and the closed loop call. Its outputs for every version 4
   configuration are checked bit for bit against the current code before any caller
   switches; the version 4 lock and archived results do not change.

4. **Dark anchors before the loop, not inside it.** For a configuration, the six dark
   passes run once, open loop, before `closedloop.run` starts, exactly as version 4
   runs them; their anchors and their hash enter the run identity. The loop then starts
   from a fresh state, as version 4's stimulus runs do. No anchor is recomputed during
   a run.

5. **Host only.** The native lane validates `floor(count) == count` for dense and
   sparse inputs (`native/lif.h`), so a `kick_equivalent` run does not go to the
   console until a native input contract and a requalification exist. That is a later
   decision.

6. **No configuration is chosen here.** A lock that uses this input names its
   configurations from the version 4 envelope (photoreceptor response, LMC and medulla
   release rates, lamina → medulla gain) and states its verdict over them, as the
   envelope rule requires. This ADR does not pick one.

## Evidence labels

| Component                                      | Status     | Note                                                                   |
| ---------------------------------------------- | ---------- | ---------------------------------------------------------------------- |
| Column geometry and coverage                   | measured   | Zhao et al. 2025 directions; acceptance 8.23° (Gonzalez-Bellido 2011)  |
| Photoreceptor drive gain                       | engineered | Set from a stated depolarization; no measured transduction for the LIF |
| Graded release rates and lamina → medulla gain | engineered | Scanned over the version 4 envelope                                    |
| Medulla ranges and dark potentials             | measured   | Groschner et al. 2022 traces, anchored at the settled dark potential   |
| Mi1/Tm3, Tm1/Tm2 delays                        | measured   | Behnia et al. 2014                                                     |
| Eyemap → body registration                     | unmapped   | #179, unchanged                                                        |

A biological run still refuses: the registration and the motor map stay unmapped.

## What is not claimed

This input does not make the eye selective: version 4 is `neither`. It does not close
G2, G3 or G4, and it does not claim that steering in a closed loop is visually driven.
It removes one known blocker (contrast stopping at the lamina) from the closed loop's
input.

## Alternatives

| Alternative                                                     | Problem                                                                                                 | Verdict                   |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------- |
| Keep Poisson photoreceptor drive                                | Did not pass the lamina in T4/T5 v1                                                                     | Kept only for DN-arena v1 |
| Rate-coded LMC drive (skip photoreceptors)                      | Bypasses the measured lamina wiring; a new engineered transfer with no source                           | Rejected                  |
| A trained connectome-constrained eye (flyvis, Lappalainen 2024) | A second executor and clock in the loop; its units are not the LIF's; trained weights replace the graph | Rejected                  |
| Quantize the graded drive to integer counts                     | Changes version 4's numbers; a hidden rounding rule                                                     | Rejected                  |
| Recompute dark anchors inside the loop                          | Anchors would follow the body's motion; not version 4's protocol                                        | Rejected                  |
| Extend record v1 with an optional float field                   | A v1 record would mean two things                                                                       | Rejected; version 2       |

## Consequences, risks, rollback

**Consequences.** `runtime`, `closedloop` and `t4t5` change in reviewed steps; existing
records, locks and archived results do not.

**Risks.**

- The visual signal may still not reach the descending neurons: version 4's T4 is not
  selective and its anchored dark potentials lie up to 113 mV from rest at gain 16.
- Cost: version 4's campaign took 18.9 h for 96 open-loop runs plus 72 dark passes; a
  closed loop adds per-tick work and cannot batch on the console.
- The builder extraction must stay bit-identical; it is gated by a parity test over all
  version 4 configurations before any caller switches.

**Rollback.** Each step is its own PR. Reverting the closed-loop caller leaves the
`counts` path, record version 1 and DN-arena version 1 untouched.

## Planned follow-up (`vee1-1` … `vee1-4`)

| Step   | Content                                                                         | Gate                                                                  |
| ------ | ------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| vee1-1 | Visual-pathway builder extracted from `t4t5.protocol`                           | Bit-identical builder outputs for every version 4 configuration       |
| vee1-2 | `CpuRuntime` input encoding (`counts` / `kick_equivalent`), checkpoint identity | `counts` bit-identical; float drive equals `sim.run` with float kicks |
| vee1-3 | `flymsg.closedloop/v2`: `input_drive`, encoding, pathway hash; v1 parser kept   | v1 records parse; replay parity on float drive; resume equality       |
| vee1-4 | A DN-arena version 2 lock on the graded input (separate lock, owner approval)   | Lock before run; envelope over version 4's configurations             |

Implementation goes to the agents named in issue #265; reviews are cross-vendor.

## Implementation status (2026-10-20)

| Step   | State                                                                                                                                                               |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| vee1-1 | Merged (#280): `flymsg.visual_pathway`; the 12 version 4 configurations give identical `sim.run` arguments before and after (digest `4844ff67…`)                    |
| vee1-2 | Merged (#274): `CpuRuntime(input_encoding=)`; `kick_equivalent` equals `sim.run` bit for bit; the native lane refuses it                                            |
| vee1-3 | Merged (#281): `flymsg.closedloop/v2`; v1 bytes pinned by golden hashes; replay and resume refuse a different encoding or pathway                                   |
| vee1-4 | Lock merged (#284, owner approval 2026-10-20); counted run from `ec3d080`: `depends` (gain 1 uninformative, gains 4 and 16 null), [DN arena](../result/dn-arena.md) |
