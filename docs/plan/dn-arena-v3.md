# DN arena version 3: design proposal

Status: **accepted** by the owner on 2026-10-20 (#293), with the sensitivity run at both
gains. It is a design, not a lock, and it authorizes no run. Version 2's verdict
(`depends`, [DN arena](../result/dn-arena.md)) stands. This would be a new lock version,
not a rerun of version 2.

## Why a version 3

The version 2 post-verdict diagnostics ([DN arena](../result/dn-arena.md)) name three
things that dominate its score and do not depend on the sphere's side:

1. **Eye imbalance in the reconstruction.** 2,474 traced right-eye photoreceptors
   against 1,733 left; after column assignment and lens eligibility, 2,251 against
   1,652 inputs with 84,411 against 63,251 synapses onto L1–L3. Berg et al. 2025
   (MaleCNS v1.0, bioRxiv 10.1101/2025.10.09.680999) attribute missing R1–R6 to "sample
   artefacts on the edge of the volume" and exclude photoreceptors from some analyses
   "as many are missing in the male CNS". No side-dependent filter in `flymsg.eye` or
   `flymsg.dn_arena` adds to it.
2. **Tonic activity of the shuffled graphs.** Every shuffle tested fires decoder
   neurons in darkness (22–208 spikes); the intact graph fires none. The null band is
   that activity, reshaped by light.
3. **A weak, unsourced stimulus.** The static 2 mm sphere at 10 mm moves each eye's mean
   photoreceptor potential by under 1 mV. No source states that a static sphere evokes
   DNa01/DNa02 asymmetry.

## Decisions proposed

### 1. Score: a mirrored contrast on every graph

For each graph `g` (intact and each wiring null) and configuration, run the stimulus
and its mirror image across the sagittal plane from identical fresh states:

`C_g = [Δθ_g(stimulus) − Δθ_g(mirror)] / 2`

Stimulus-independent bias cancels: the eye imbalance's effect under uniform light, and
a shuffled graph's tonic turning. The intact contrast is compared with the 39 wiring
nulls' contrasts, inclusive range, as in version 2. Its sign is predicted beforehand:
toward the stimulus (Collie et al. 2025, below), which is positive for a stimulus on
the left. A `difference` with the wrong sign is reported as such. The no-go stays: a
configuration is `uninformative` when the decoder fires no spike in either intact run.

### 2. Stimulus: the sourced moving dark bar

Collie et al. (bioRxiv 10.1101/2025.04.23.650240 v1; Neuron 2026) is the only study
found in which a visual object evokes a right–left DNa02 asymmetry that predicts
rotational velocity. It also matches this connectome: head-fixed **male** flies walking
on a ball. Verified verbatim in the Results and figure legends:

- "Green: responses of DNa02 on the right, minus responses of DNa02 on the left (mean ±
  s.e.m., n = 11 flies)" (Fig. 2e).
- "visual responses in DNa02 could predict the fly's rotational velocity in response to
  motion pulse stimuli (Fig. 2f, Fig. S4)".
- "Motion stimuli spanned the front 100° for AOTU019 and 180° for AOTU025, with all
  pulses traversing 22.5° of azimuth" (Fig. 1f).
- "In general, flies turned toward the object's position (e.g., rightward turns for
  stimuli on the right), with a notable exception near the midline, where flies instead
  tended to follow the direction of motion" (Fig. 3a).

The object is "a dark vertical bar (10.5°) on a bright background" in a 48°-tall arena,
sweeping at 25 or 75 °/s. These Methods numbers come from an extraction of the full text
and must be checked verbatim in the PDF before a lock cites them.

Proposed stimulus: one 10.5°-wide, 48°-tall dark bar, sweeping 22.5° of azimuth at
25 °/s (0.9 s) away from the midline, centred at 45° on one side, and its mirror on the
other. The sweep stays off the midline, where Collie's flies follow motion direction
rather than position. The bar moves in world coordinates around the start position, so
the body's turns change its retinal position (closed loop).

This needs a new optical primitive: `flymsg.optics` measures dark spheres only. A
vertical bar is a different silhouette; a stack of spheres would only approximate it,
so it is not an option. The primitive gets its own PR, coverage tests against numerical
integration (as the sphere's Rice check), and a configuration hash.

Alternatives considered:

| Stimulus                         | Problem                                                                | Verdict          |
| -------------------------------- | ---------------------------------------------------------------------- | ---------------- |
| Version 2 sphere, contrast only  | Under 1 mV per eye; no source for steering to a static sphere          | Rejected         |
| Large static hemifield           | No source for a DN response; a luminance step, not an object           | Rejected         |
| Sphere radius envelope (2–10 mm) | Three times the cost and still unsourced                               | Rejected         |
| Wide-field grating rotation      | Optomotor drive needs T4/T5 direction selectivity, absent in version 4 | Deferred to #140 |

### 3. The eye imbalance: kept and stated, with a declared sensitivity run

- **Primary analysis:** the reconstruction as it is, no compensation. The mirrored
  contrast removes its first-order effect.
- **Sensitivity analysis** (reported, outside the verdict): the inputs restricted to the
  638 mirror pairs of lens columns with inputs on both sides (removing 18 left and 185
  right inputs). The mirror convention is the repository's `(L, hex1, hex2) ↔ (R, hex1,
hex2)` with negated azimuth, a stated symmetry assumption ([eye](../reference/eye.md)).
- **Not used:** a per-eye or per-column drive gain. Either would be an engineered
  compensation that cannot restore missing wiring, and the repository refuses unsourced
  gap-filling ([approximations](../reference/approximations.md)).

An idealized hexagonal template, as in Lappalainen et al. 2024 (Nature 634:1132), would
replace the measured lamina with invented connectivity. It is out of scope for a
connectome-only fixture.

### 4. What stays from version 2

The MaleCNS graph and graded pathway of T4/T5 version 4 stay, as do the decoder cell
(2 °/s per Hz yaw, 0.2 mm/s per Hz forward), the five arms, 39 wiring nulls with intact
rate and gain and their own anchors, replay parity and the data rule. The
configurations are lamina-to-medulla gains 4 and 16. Gain 1 is left out because version
2's intact readout was silent there, and the lock will say so.

With a moving bar, the `shuffled` arm no longer equals `disconnected`: it permutes a
changing sequence.

## Cost

Version 2: 132 loops took 5 h 23 min with 4 workers.

| Part                                                      | Loops | Estimate |
| --------------------------------------------------------- | ----: | -------: |
| Primary: 2 configurations × 2 sides × (5 arms + 39 nulls) |   176 |     ~7 h |
| Sensitivity: the same on paired columns                   |   176 |     ~7 h |

The sensitivity half can be limited to gain 16 (88 loops, ~3.5 h).

## Limits

- Collie's flies were aroused by optogenetic P1 activation. The model has no arousal
  state.
- The graded pathway has no direction selectivity (T4/T5 version 4, robust neither).
  The bar can act only through position and luminance.
- The body is kinematic and planar; Collie's flies walked on a ball.
- Synthetic, as version 2: a `difference` would be a synthetic difference, not a
  biological mechanism.

## Steps

| Step | Content                                                          | Gate                                                  |
| ---- | ---------------------------------------------------------------- | ----------------------------------------------------- |
| v3-0 | Verbatim check of Collie's Methods numbers in the PDF            | Quotes in the lock; any mismatch changes the stimulus |
| v3-1 | `optics` vertical bar primitive, moving in world coordinates     | Coverage within tolerance of numerical integration    |
| v3-2 | `dn_arena` version 3 code: sides, contrast, paired-column inputs | Version 2 code paths and hashes unchanged             |
| v3-3 | Lock draft with a timing-only smoke                              | Owner approval; merging authorizes the run            |
