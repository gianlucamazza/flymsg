# Validation

`flymsg validate` checks the simulator against circuits whose function is known from
experiments. `flymsg calibrate` runs the same battery over a parameter grid. Code:
`src/flymsg/validate.py`; the full battery also runs as a slow test
(`uv run pytest -m slow`).

## Current status

The scored picture is the index on the [roadmap](roadmap.md#results). This page is the
validation battery: its protocol, how the defaults were chosen, and the
[findings log](#findings-log). Notes kept as they were written on the day are the
[status log](#status-log). A later note supersedes an earlier one where they disagree.

- **Criterion v4, 29/29 with the defaults** (`w_syn` 0.192, no adaptive threshold) at seeds
  0–2, at seeds 0–9 (model selection) and at fresh seeds 10–19 with fresh control draws
  (replication).

- **N1** drops the same battery to 5/29 on one degree-preserving shuffle
  ([related](related.md#n1-specific-checks-need-the-measured-partners)).
- **Held-out** ORN_DM1 → DM1_lPN fails specific and stability
  ([benchmarks](benchmarks.md)).
- **One-bit looming jump** fails the DNp01 silence check. The residual drive is DNp02 and
  DNp06 ([behavior](behavior.md)).

- **Cases:** looming escape, Giant Fiber output, P1 courtship drive, pIP10 song pathway,
  sugar → MN9, and bitter → MN9 as a negative case.
- **Kinds of check:** positive, specific (class-matched control for sensory stimuli), latency
  order, dose-response, stability, negative.
- **How the defaults were reached:** calibrate-v2 and calibrate-v3 tuned an adaptive threshold
  while `w_syn` stayed at Shiu's FAFB value. Once MaleCNS's higher synapse density was found,
  a pre-registered model selection and a replication chose the density-scaled weight with no
  compensation. The sections below keep the whole history, and the findings log keeps every
  negative result.

## Status log

These notes stay in the order they were added.

- **N1** (2026-10-11, [related](related.md#n1-specific-checks-need-the-measured-partners)).
  One degree-preserving shuffle of `post`, seed 0, the same defaults and criterion v4,
  seeds 0–2. The traced graph passes 29/29. The shuffle passes 5/29, and those five are
  the `stability` check of every case: activity still dies out. All 7 `specific` checks
  fail on the shuffle. `positive`, `order`, `dose` and `negative` fail too. `w_syn` stays
  0.192. The permutation was not replaced.
- **Null families** (protocol v1, 2026-10-11, [nulls](nulls.md)). Four shuffle families,
  **20 draws** each, seeds 0–19, MaleCNS v1.0. The headline (sum of seven specific `max`
  weights = 4077) sits above every draw of every family (_p_ = 1/21): degree-preserving
  null mean 21.40 (_z_ = 190.4), cell-type-preserving 3196.3 (_z_ = 3.44),
  weight-within-type 679.75 (_z_ = 31.6), sign 1314.3 (_z_ = 6.59). Four one-hop
  pathways are 0 on the real graph (LC4_R → TTMn, P1 → dPR1, sugar → MN9, bitter → MN9);
  bitter is not below the nulls. N1 is not redrawn. Hypotheses and thresholds are in
  [`validation/preregistration.yaml`](../validation/preregistration.yaml).
- **Held-out manifest** (2026-10-11, [benchmarks](benchmarks.md)). Calibration, exploratory
  and held-out cases were partitioned before the run. ORN_DM1 → DM1_lPN fails: positive
  passes at 284.4 Hz, specific fails against a 185.6 Hz olfactory control, and 4894
  neurons stay active (limit 100). The reported ORN_V case fails the same way and does
  not decide. Both sensitivity corners fail the same two checks: at `w_syn` 0.275 the
  control is 200 Hz and 7797 neurons stay active; at `th_jump` 2 the control is 105.6 Hz
  and 2669 stay active. Neither corner replaces the scored result. `w_syn` stays 0.192.
- **One-bit looming jump** (2026-10-11, [behavior](behavior.md)). The closed-loop task was
  frozen before the run. `LC4_R` drives the network; the third `TTMn_R` spike cuts that
  drive. The claim is a calibration feasibility check on the looming case, with jump,
  feedback, DNp01 silence, and a decoder-prefix check. FlyBody is not embedded. The
  closed loop fails silence: with both DNp01 neurons silenced, TTMn_R still reaches
  3 spikes in every seed. Jump, feedback, and the decoder prefix pass. `w_syn` stays 0.192.
- **No biological extension** (2026-10-11, [model](model.md)). Cell-type parameters, gap
  junctions, short-term synaptic dynamics and compartments are not added. None has a
  parameter that transfers into this LIF without being tuned on the behaviour it would
  explain. The silence failure is not a missing giant-fiber gap junction. `TTMn_R` still
  fires, so some other partner still drives it, and that partner is not named.
  Neuromodulation and associative learning were closed as blocked: the evidence was
  absent. On 2026-10-13 one measured rule, the dopamine-gated depression at Kenyon cell →
  MBON11 (Hige et al. 2015), was added as an optional protocol, locked before its run (#85).
- **No held-out behavior remains eligible** (2026-10-11). The frozen partition already
  assigned every mapped behavior to calibration, or listed it as exploratory and
  disqualified it in the same note. The one-bit loop is not that protocol and failed
  silence. No exploratory row is promoted, and no new run is added. The five milestone
  boxes stay empty.
- **No scientific task is queued** (2026-10-12). The validated-behavior milestone stays
  unmet. A later held-out case, a name for the unnamed `TTMn_R` partner, an animal test
  of `gf_required_for_the_jump_bit`, a neuromodulation table, a learning rule, or a body
  each need evidence that is not in this repository. Each would be a new issue and a new
  version. The runs stay unqueued.
- **Two documentary issues** (2026-10-12,
  [#19](https://github.com/gianlucamazza/flymsg/issues/19),
  [#20](https://github.com/gianlucamazza/flymsg/issues/20)). They do not run and they do
  not edit version 1. #19 records the FlyBody re-read at `d015e9b`: the same timesteps,
  59 named walking actuators, and no MaleCNS motor map. #20 records that the residual
  `TTMn_R` partner stays unnamed, and that the synapse list read the same day cannot
  choose the next silencing. `w_syn` stays 0.192.
- **Numeric lock** (2026-10-12). numba is 0.68.0 and llvmlite is 0.50.0. The unit suite
  matches the NumPy reference kernel. The scored runs were not repeated, so their
  manifests stay on numba 0.67.0.
- **Residual partner scan** (2026-10-12, [behavior](behavior.md#residual-partner-scan)).
  Version 1 verdict: none. Silencing DNp02 or DNp06 with both `DNp01` removes every `TTMn_R`
  spike on six seeds, but each null (p 0.036, 0.041) contained the other unit; the threshold
  was 0.025. Version 2 excludes every screen pass from the null and confirms on seeds 20–22;
  fixed before its run. `w_syn` stays 0.192.
- **Residual partner scan v2** (2026-10-12, [behavior](behavior.md#result-of-version-2-2026-10-12)).
  Verdict: names_partner: DNp02, DNp06 (p 0.001 each against 0.025; 0 `TTMn_R` spikes on
  seeds 20–22). Model-side, and fixed after v1 was seen; `gf_required_for_the_jump_bit` stays
  `unverified`.
- **Residual partner scan v3** (2026-10-12, [behavior](behavior.md#result-of-version-3-2026-10-12)).
  A replication of v2 with every rule unchanged and fresh confirm seeds 30–32, locked before
  its run: names_partner: DNp02, DNp06 again (p 0.001 each). The v2 naming replicates;
  model-side.

## Protocol

Every case stimulates a population with Poisson input at 100 Hz for 300 ms, runs 600 ms in
total and uses 3 seeds (0, 1, 2). Silencing tests stop at the end of that 300 ms stimulus:
the rates in the scored window are identical to the 600 ms run. For each target type the
**best neuron** (highest mean
stimulus-window rate over seeds) is scored; many targets are bilateral pairs and a unilateral
stimulus drives one side (LC4_R → DNp01_R and TTMn_R). Three kinds of check:

| Kind      | Passes when                                                             | Why                                                                     |
| --------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| positive  | the best neuron fires ≥ 3 spikes in the 300 ms window in ≥ 2 of 3 seeds | the known pathway carries the signal, even as a weak or labile response |
| specific  | its rate ≥ 3 × the control rate + 2 Hz                                  | the response needs the specific wiring, not just any drive of that size |
| stability | ≤ 100 neurons still fire from 400 ms (stim end + 100 ms) to 600 ms      | no self-sustained runaway                                               |

The control stimulates the same number of random neurons, matching the stimulus' superclass
mix (e.g. 55 `visual_projection` neurons for LC4_R), and excludes the stimulated neurons, the
targets and every neuron with a direct connection of ≥ 5 synapses onto a target. Draws use a
fixed seed, so a run is reproducible. The report also gives each target's median first-spike
latency (descriptive, not checked).

**Criterion v3** (fixed 2026-09-21 before running it; the defaults `w_syn` 0.275 and
`th_jump` 6 are not retuned for it, and a failure is recorded as a finding; the engine fix
found afterwards required a separate, also pre-registered, calibrate-v3) adds two
quantitative checks to v2:

| Kind  | Passes when                                                                                                                                                                                   | Why                                                                                   |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| order | for targets that are successive stages of one pathway (LC4 → DNp01 → TTMn, P1 → pIP10 → dPR1), the earlier stage fires first in ≥ 2/3 of the seeds where both fire                            | signals must travel along the chain, not reach the later stage by another route first |
| dose  | the best target neuron's rate, at input rates 25 / 50 / 100 / 200 Hz, never drops by more than one spike per window (3.3 Hz) from one rate to the next, and is higher at 200 Hz than at 25 Hz | a feed-forward sensorimotor pathway should respond more to stronger input             |

For each target the report also gives the share of its peak reached at 100 Hz, next to
Shiu et al.'s calibration (100 Hz sugar input gives ~80 % of maximal MN9 firing); this is
descriptive, not a check.

**Criterion v4** (fixed 2026-09-21 before running it) changes v3 in two ways:

- **Class-matched control for sensory stimuli.** When the stimulus is sensory (superclass
  ending in `sensory`), the control matches `class` (e.g. gustatory) instead of superclass,
  so a taste stimulus is compared with other taste neurons, not with any labial sense.
- **A negative case.** Bitter GRNs (right LB1a–d, 19 neurons) → MN9 passes when MN9's rate
  under bitter input is below 1/3 of its rate under sugar input in the same battery: bitter
  suppresses proboscis extension (Shiu et al. 2024, Fig. 3). Chosen by the same two-evidence
  rule as sugar (see below).

The battery is also run with **10 seeds** instead of 3 for model selection: positive then
needs ≥ 7/10 seeds, order ≥ 2/3 of the seeds where both fire; specificity, dose and
stability use 10-seed means, reported with bootstrap 95 % intervals.

**Model selection** (fixed before running): candidates A = `w_syn` 0.275, `th_jump` 2 (the
calibrate-v3 default) and B = `w_syn` 0.275 / 1.81 = 0.152, `th_jump` 0 (the published model
at MaleCNS synapse density, no compensation); B with the density ratio at its interquartile
bounds (1.43, 2.43: `w_syn` 0.192, 0.113) is reported as sensitivity, not eligible. The model
passing more v4 checks at 10 seeds becomes the default; on a tie B wins (fewer compensations).
Everything downstream is then re-run with the winner.

**Replication of B−** (fixed 2026-09-22, before running it; `flymsg select-model
--replication --seed0 10 --control-seed 1`): A (`w_syn` 0.275, `th_jump` 2) and B− (`w_syn`
0.275 / 1.43 = 0.192, `th_jump` 0) run criterion v4 on fresh simulation seeds 10–19 and fresh
control draws (generator seed 1 instead of 0). B− becomes the default unless A passes more
checks (a tie goes to B−, which has no compensation). What this guards against is luck in the
seeds and control draws; it does not undo that B− was noticed among four variants.

**Why spikes and a ratio, not a rate threshold** (criterion v2, fixed 2026-09-21 before
`calibrate-v2`): the adaptive threshold caps steady rates at about
`(drive − 7 mV) / (th_jump · τ_th)`, so the first criterion (target ≥ 20 Hz, control < 20 Hz)
penalised adaptation itself: raising `th_jump` lowered every target's rate regardless of wiring.
See the findings log.

## Cases

| Case                          | Stimulus                                | Targets                   | Evidence                                                                                                                                                                                      |
| ----------------------------- | --------------------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| looming escape                | LC4_R (55 neurons)                      | DNp01 (Giant Fiber), TTMn | LC4/LPLC2 drive the GF, which drives the jump muscle motor neuron (von Reyn et al. 2014; Ache et al. 2019)                                                                                    |
| giant fiber output            | DNp01 (2)                               | TTMn                      | GF → TTMn (King & Wyman 1980); the cholinergic component alone still drives TTM, with long latency, in `shak-B²` flies lacking the gap junctions (Blagburn et al. 1999; Allen & Murphey 2007) |
| P1 courtship drive            | P1 (86)                                 | pIP10, dPR1               | P1 activation elicits courtship song through pIP10 (von Philipsborn et al. 2011)                                                                                                              |
| pIP10 song pathway            | pIP10 (2)                               | dPR1                      | pIP10 and dPR1 are courtship song neurons (von Philipsborn et al. 2011); 337 synapses pIP10 → dPR1 here                                                                                       |
| sugar feeding                 | sugar GRNs, right (LB3b_R + LB3c_R, 17) | MN9                       | sugar GRNs drive proboscis extension; MN9 moves the proboscis (Gordon & Scott 2009); the headline case of Shiu et al. 2024                                                                    |
| bitter feeding (negative, v4) | bitter GRNs, right (LB1a–d_R, 19)       | MN9                       | bitter input suppresses proboscis extension (Shiu et al. 2024, Fig. 3): MN9 must stay below 1/3 of its sugar rate                                                                             |

**P1** is not a cell type in MaleCNS. It is selected as the `pC1*` types whose literature
synonyms include pMP4/pMP-e (Yu et al. 2010; Cachero et al. 2010): 86 neurons, all male-specific
or potentially male-specific.

### Excluded on purpose

- **GF → DLMn** (flight muscle motor neurons): GF → PSI → DLMn depends on gap junctions. In
  `shak-B²` mutants, which lack them, GF stimulation elicits no DLM response at all, while the
  chemical GF → TTMn path survives. The chemical route in the connectome is DNp01 → IN18B034 →
  DLMn with only 23 synapses on the first hop, and DLMn reached 4.4 Hz. A chemical-only model
  cannot be expected to pass it.
- **pIP10 → vPR6, vMS11**: stay silent in the model although pIP10 synapses onto them (13 and
  20 synapses). The literature role of these connections is less clear, so they are not used as
  expectations.

### Selecting the sugar GRNs

MaleCNS names labellar GRNs by morphology (LB1a–e, LB2a–d, LB3a–d, LB4) without receptor
labels. A subtype is used as sugar-sensing only when two independent lines agree:

1. **Morphology ↔ receptor lines**: the gustatory connectome of MaleCNS matched LB3b and LB3c
   to Gr64f-GAL4 (sweet), LB3a to ppk28-GAL4 (water) and LB3d to Ir7c/ppk23-GAL4 (high salt)
   (bioRxiv 10.1101/2025.08.25.671814).
2. **Connectivity across sexes** (`compare.fingerprint`): the output profile of each male
   subtype over partner types named in the FAFB vocabulary (`flywireType`), compared by cosine
   with the sets Shiu et al. stimulated in FAFB v783 (20 of their 21 sugar IDs, 18 water, 20
   bitter; all FAFB type LB3 or LB1):

| male type          | sugar    | water    | bitter                 | receptor line |
| ------------------ | -------- | -------- | ---------------------- | ------------- |
| LB3a               | 0.58     | **0.90** | 0.03                   | water         |
| LB3b               | **0.77** | 0.65     | 0.04                   | sugar         |
| LB3c               | **0.96** | 0.77     | 0.01                   | sugar         |
| LB3d               | **0.90** | 0.71     | 0.02                   | high salt     |
| LB1a / LB1c / LB1e | ≤ 0.05   | ≤ 0.06   | **0.64 / 0.82 / 0.57** | bitter        |

The lines agree on LB3a, LB3b and LB3c, so the sugar set is LB3b + LB3c.

The **bitter** set follows the same rule. The gustatory connectome (Tastekin et al. 2025) matches
LB1a–d to Gr33a-GAL4, expressed in all bitter GRNs, and links LB1e to Ir94e (mild aversion
to some amino acids). Fingerprints against Shiu's FAFB sets (`flymsg compare --fingerprint LB1a LB1b LB1c LB1d
LB1e`): LB1a/b/c/d nearest bitter (0.64 / 0.87 / 0.82 / 0.84), LB1e nearest their Ir94e set
(0.92 vs 0.57 bitter). Both lines
agree: bitter = LB1a–d; LB1e is left out. LB3d disagrees and
is left out: FAFB types all these neurons as one LB3, so Shiu's sugar set, chosen by
connectivity clustering, may include LB3d-like (salt) neurons. MN9 (MN9_L, MN9_R; FAFB
CB0701) is scored as a type, so the best of the pair counts.

## Calibration

Grid: `w_syn` ∈ {0.2, 0.275, 0.35} × `th_jump` ∈ {2, 4, 6, 8, 12}, 3 seeds, criterion v2, ranked
by checks passed; ties go to the set closest to the published model (`w_syn` nearest 0.275,
then the smallest `th_jump`). Rule fixed before the run (commit `fc5c332`). Reproduce:
`flymsg calibrate --out runs/calibrate-v2.csv` (~45 min with 5 workers).

**Result (calibrate-v2): `w_syn` 0.275, `th_jump` 6 mV** — the default from `b6dc609` until
calibrate-v3 (first engine).

| w_syn \ th_jump | 2    | 4    | 6      | 8    | 12   |
| --------------- | ---- | ---- | ------ | ---- | ---- |
| 0.2             | 16   | 16   | 16     | 15 ¹ | 15 ¹ |
| 0.275           | 13 ² | 15 ³ | **16** | 16   | 16   |
| 0.35            | 12 ² | 12 ² | 13 ²   | 14 ² | 14 ² |

Checks passed out of 16. ¹ GF → TTMn below 3 spikes (7 and 6 Hz): strong adaptation plus weak
coupling. ² Self-sustained activity after LC4_R, P1 and/or pIP10. ³ P1 leaves 1,977 neurons
self-sustained.

Six sets pass everything, so the chosen point sits on a broad plateau rather than a knife
edge. The published `w_syn` survives unchanged; stronger coupling (0.35) runs away whatever the
adaptation, and the adaptive threshold is needed at 0.275 (`th_jump` 2 fails three stability
checks).

### calibrate-v3 (pre-registered 2026-09-21, before the run)

After the engine fidelity fix the defaults are re-derived on the same grid (`w_syn` ∈ {0.2,
0.275, 0.35} × `th_jump` ∈ {2, 4, 6, 8, 12}, 3 seeds) with criterion v3 (28 checks, five
cases) and the same ranking rule: most checks passed, then `w_syn` nearest 0.275, then the
smallest `th_jump`. The winner becomes the default whatever it is; failing checks are
reported, not engineered away. Reproduce: `flymsg calibrate --workers 6 --out
runs/calibrate-v3.csv` (~45 min).

**Result (calibrate-v3): `w_syn` 0.275, `th_jump` 2 mV**, 27/28 — the default in v0.3–v0.4.

| w_syn \ th_jump | 2      | 4    | 6    | 8    | 12   |
| --------------- | ------ | ---- | ---- | ---- | ---- |
| 0.2             | 27     | 26 ¹ | 26 ¹ | 26 ¹ | 24 ² |
| 0.275           | **27** | 27   | 26 ³ | 27   | 27   |
| 0.35            | 25 ⁴   | 25 ⁴ | 25 ⁴ | 27   | 26 ⁴ |

Checks passed out of 28. Every set fails sugar → MN9 specificity (control 3–26 Hz): no
parameter separates sugar from the labial mechanosensory drive of the control, so this is not
a calibration issue. ¹ MN9 below 3 spikes as well. ² TTMn and MN9 below 3 spikes. ³ 385
neurons self-sustained after LC4_R. ⁴ Self-sustained activity after P1, GF, LC4_R or sugar.

With the engine fixed, much less adaptation is needed (2 mV instead of 6). Stability is not
monotonic in `th_jump` (6 fails where 2, 4, 8 and 12 pass at `w_syn` 0.275), a sign that the
runaway regime depends on the seed near its edge, as already seen with P1.

## Sensitivity grid (a report, not a score)

[`validation/sensitivity.yaml`](../validation/sensitivity.yaml) (version 1, issue #28) fixes a
grid before it runs: `w_syn` at 0.8, 0.9, 1.0, 1.1 and 1.2 times the default, `th_jump` at 0
and 2 mV, seeds 0–4, the six battery cases at the battery protocol. For every cell, case,
target and seed it records the best target neuron's rate and first spike, how many neurons
fire during the stimulus, and how many still fire from 400 to 600 ms. `flymsg sensitivity
--run` writes every cell (`cells.csv`), whether each target holds at the v4 floor (3 spikes in
2/3 of the seeds, `holds.csv`), the spreads (`spreads.csv`), a figure (`rate.svg`) and a
manifest to `runs/sensitivity/v1/`.

In every cell the measured neuron of each target type is the one with the highest mean rate
over that cell's seeds, as in the battery, so two cells may read different neurons of one
type; `cells.csv` does not hide this, because the rows carry the type, not a neuron.

Two spreads are kept apart. The seed range at the default cell is noise from the Poisson
input; the range of the seed medians across cells is sensitivity to the two parameters.
Numerical implementation (CPU against the native and GPU lanes) and biological uncertainty
(parameters the LIF does not have) are outside this grid.

**Selection bias.** The defaults were chosen on the battery (model selection, criterion v4),
so the grid is centred where those cases pass by construction; a region where they hold says
how wide that optimum is, not that the model generalises. **Multiple comparisons.** Ten cells,
six cases, several targets and four metrics are read together; no cell is tested for
significance and no p-value is attached. Nothing is chosen from the grid, and `sim.Params`
keeps its defaults.

### Result of version 1 (2026-10-12)

Run from `a7a15a9` (clean), 60 jobs in 21 min. A target holds at a cell when its best neuron
reaches the v4 floor (3 spikes in 2/3 of the seeds):

| Case, target                     | `th_jump` 0: `w_syn` × 0.8 / 0.9 / 1.0 / 1.1 / 1.2 | `th_jump` 2: × 0.8 / 0.9 / 1.0 / 1.1 / 1.2 |
| -------------------------------- | -------------------------------------------------- | ------------------------------------------ |
| looming escape, DNp01 / TTMn     | all hold                                           | all hold                                   |
| giant fiber output, TTMn         | all hold                                           | no / yes / yes / yes / yes                 |
| P1 courtship drive, dPR1 / pIP10 | all hold                                           | all hold                                   |
| pIP10 song pathway, dPR1         | all hold                                           | all hold                                   |
| sugar feeding, MN9               | no / no / yes / yes / yes                          | no / no / no / yes / yes                   |
| bitter feeding, MN9 (negative)   | none hold                                          | none hold                                  |

Four positive cases hold across the whole grid, and the negative case has a median MN9 rate
of 0 in every cell. Sugar → MN9 is the narrow one: its median rate goes from 0 to 57 Hz across the grid
(30 Hz at the default, seed range 17 Hz), and with `th_jump` 2 it needs `w_syn` × 1.1. The
default cell sits at its edge, so the sugar pass of criterion v4 is not robust to a 10 % lower
coupling. Giant fiber → TTMn drops out only at the weakest corner. Activity after the stimulus
(400–600 ms) appears only at the edges: looming with `th_jump` 2 from × 1.0 (26–31 neurons),
P1 and sugar at × 1.2 with `th_jump` 0 (82 and 46). At the default cell no case persists.
Parameter spread exceeds seed spread for most rates (looming TTMn: 17–87 Hz across cells,
7 Hz across seeds); the giant-fiber TTMn latency is the exception, with a seed range (77 ms)
larger than the range of its medians. Figure: [rate per cell](img/sensitivity-rate.svg); files
in `results/sensitivity/v1/` (archived from `runs/`). Nothing is chosen from this grid.

## Timestep convergence (SF2, a check, not a score)

`validation/convergence.yaml` v1 (#148), locked 2026-10-14 before any run at another
timestep. The six cases of the sensitivity grid run with the default parameters at
dt = 0.1 ms (the default), 0.05 and 0.025 ms, seeds 0–4; delay and refractory period stay
whole numbers of steps at each. A response (case and target) converges at a timestep when
its holds verdict (the v4 floor) equals the finest timestep's and its seed-median target
rate differs from the finest seed median by at most the finest seed range, and never less
than one spike in the window (3.33 Hz, the measurement's resolution). The verdict is
`converged` if every response converges at 0.1 ms. Numerical error is judged against seed
variability, so no tolerance is chosen; Poisson input is drawn per step, so runs compare as
seed statistics, not spike for spike. `flymsg convergence --run` writes every cell, the
judgement and a report.

**Result of version 1 (2026-10-14): converged.** Run from `7c4d34d`, the lock commit, in one
attempt (5 min, 4 workers). All eight responses converge at 0.1 ms, and at 0.05 ms: holds
verdicts are identical at every timestep (the bitter negative stays silent), and every
seed-median target rate lies within the finest seed range of the finest median, the giant fiber
→ TTMn response exactly at it (16.7 against 10.0 Hz, range 6.7 Hz). What does not decide moves
more. From 0.1 to 0.025 ms the first spike shifts for TTMn under giant fiber output (35 → 82
ms), MN9 under sugar (40.5 → 66.4 ms) and dPR1 under pIP10 (12.9 → 7.4 ms), and the neurons
recruited by sugar fall from 439 to 155; the looming and P1 latencies agree within 0.7 ms. So
the battery's rates and verdicts do not depend on the 0.1 ms step, and first-spike latencies
and recruitment counts of weak pathways should not be read to better than the step's effect.
Outputs: `results/convergence/v1.executions/be1ac274…/output/`.

## Simple baselines (SF2, a report, not a score)

`validation/baselines.yaml` v1 (#148) was locked on 2026-10-15, before any battery run on a shuffle. It asks, response by response, whether the battery needs the measured wiring, or only what a degree-preserving shuffle keeps: each neuron's out-weights and the in-degree multiset.

- **Graphs.**
  - The battery's six cases and eight responses run with the default parameters and seeds 0–4.
  - They run on the measured connectome and on 199 shuffles, seeds 4000–4198. These are N1's configuration-model permutation of `post`, with seeds disjoint from N1, the null families and song.
- **Statistic.**
  - Per response, the statistic is the seed-median rate of the target's best neuron.
  - It gives an empirical p, with ties counted against the measured wiring. The tail is upper for positive cases and lower for the bitter negative.
  - Holm corrects over the eight responses at α = 0.05. With 199 draws the smallest p, 0.005, lies below Holm's first threshold of 0.00625.
- **Verdict.** A response is specific when its adjusted p is at most α. The verdict lists the specific and not specific responses, with no overall pass.
- **Reported, not deciding.** The share of shuffles on which a response holds (the v4 floor), the shuffles' 5th, 50th and 95th percentiles, latencies, and recruited and persistent counts.

<<<<<<< HEAD
`flymsg baselines --run` writes every cell, the judgement and a report. With `--backend console`, each graph's battery runs as one batch on the console worker, bit for bit with the CPU (see [runtime](runtime.md)). `--backend hybrid` runs the CPU workers and the console together on one queue of graphs. The manifest records the backend.
||||||| parent of 0a120f5 (Result: simple baselines v1 (#148, SF2): every positive response specific against 199 degree-preserving shuffles)
`flymsg baselines --run` writes every cell, the judgement and a report. Not yet run.
=======
`flymsg baselines --run` writes every cell, the judgement and a report.

**Result of version 1 (2026-10-15, run at `894a77a` on the CPU, 6 workers, seeds 0–4, 200 graphs): every positive response is specific.**

- **The run.** It was interrupted once and resumed from its checkpoint. One resume attempt with a different worker count was refused as another execution identity.
- **Positive responses.** No shuffle reaches the measured rate in any of the seven, so p = 0.005, the floor, and Holm gives 0.04 ≤ 0.05.
  - The shuffles' 95th percentile is 0 Hz for every target, against 210 Hz for DNp01 under looming, 70 Hz for TTMn, 16.7 Hz for TTMn under giant fiber output, 107 and 100 Hz for pIP10 and dPR1 under P1, 90 Hz for dPR1 under pIP10, and 30 Hz for MN9 under sugar.
  - At most 2 of the 199 shuffles hold any response at the v4 floor.
- **The bitter negative is not specific.** As the lock named in advance, both the measured wiring and the shuffles leave MN9 silent (p = 1).
- **Reported.** The measured connectome recruits more neurons than its shuffles' median: 1,081 against 249 under looming, 1,882 against 437 under P1, and 439 against 30 under sugar. Under giant fiber output the count is 2 in both, so that pathway is direct.

So every response the battery scores needs the measured partners, not only the out-weights and the in-degree multiset a degree-preserving shuffle keeps.

Outputs: `results/baselines/v1.executions/f89ed1c3…/output/`.
>>>>>>> 0a120f5 (Result: simple baselines v1 (#148, SF2): every positive response specific against 199 degree-preserving shuffles)

## APL and the odor contrast at KC claws (#85)

`validation/apl_claws.yaml` v1 was locked on 2026-10-15, before any run. It asks whether the model's APL equalises 3-octanol (OCT) and 4-methylcyclohexanol (MCH) at the Kenyon cells' input, as Prisco et al. 2021 measured (Figure 4B, Figure 4-figure supplement 1): with APL output intact the OCT/MCH contrast at KC claws is smaller than at PN boutons, and with it blocked the claw contrast rises to the boutons'.

- **Arms.** `on` is the default model; `off` removes every synapse from the two APL neurons, onto KCs and PN boutons alike, as TNT blocks APL release.
- **Drive.** The KC sparseness locks' DoOR odors at 100 Hz per unit response for 1 s, seeds 420–424.
- **Readouts.** Per seed and odor, the KCs' mean potential above rest over the odor window stands for the claws (point neurons have no claw compartment), and the ALPNs' spikes for the boutons. Each readout enters only through its own contrast c = (x_OCT − x_MCH)/(x_OCT + x_MCH): c_on and c_off for the claws, c_pn for the boutons in arm on.
- **No-go.** If the median c_pn is not positive, the claw depolarization is not positive for either odor in either arm in any seed, or any seed's contrast is undefined, the run is uninformative.
- **Verdict.** On the seed medians, _raises_ is `c_off > c_on` and _restores_ is `|c_off − c_pn| < |c_on − c_pn|`. Pass if both hold, partial if only raises does, fail if raises does not. The share of seeds in which each holds, the KC spiking fractions and c_on's sign are reported, not scored.

`flymsg apl-claws --run` writes every cell, the judgement and a report.

**Result of version 1 (2026-10-15, run at `fdef643`, seeds 420–424, 20 simulations in 14 min): uninformative, the no-go.**

- **APL intact.** The KCs' mean potential over the odor sits _below_ rest: −0.69 mV for OCT and −0.97 mV for MCH. Meanwhile 30–37% of KCs spike. APL's inhibition outweighs the PN drive for the average KC, so there is no positive claw depolarization to contrast, and the no-go applies.
- **APL output removed.** Every KC spikes for both odors, and the mean potential is 2.14–2.16 mV, so the threshold and reset clip the claw contrast to about zero (c_off ≈ −0.003). This is the clipping the lock names.
- **The PNs** carry the measured direction: OCT drives the ALPNs more than MCH (c_pn ≈ +0.04).
- **Outside the verdict.** The two relations hold in all five seeds: c_off > c_on, and c_off is nearer c_pn than c_on is. They mean little here, because c_on is a contrast of two potentials below rest. OCT holds the average KC less far below rest than MCH does, and that alone makes c_on negative.

So the model's APL inhibits KCs more strongly than claw imaging suggests, and without APL every KC fires. A claw-level test needs a readout that neither averages over hyperpolarized cells nor saturates: a new version.

Outputs: `results/apl-claws/v1.executions/b914035a…/output/`.

## Findings log

Negative and surprising results, kept so they are not rediscovered. Confirmatory results
that close an open route are kept here too.

**2026-10-14: Kenyon cell sparseness v8, within only with the variant set; v7 replicates.**
Seeds 95–97, v7 under the continuous clamp by the Taylor action. 8 of 10 arms of lLN2T+lLN1_bc
within (2.0–2.3% / 1.4–1.7% of Kenyon cells), the two E arms out by overlap at 65–66% against
64.6%; lLN2T alone not within (16–23%, 80–96% shared). Every arm within 19 cells of its v7
count; coupling moves no arm by more than 21 cells. Report:
`results/kc-sparseness/v8.executions/c714d0a3…/output/`.

**2026-10-14: T4/T5 v3, robust: neither.** Seed 94, 25 configurations of LMC × medulla release
rate, with Mi1, Tm3, Mi4, Mi9 and C3 graded over Groschner et al. 2022's in vivo voltages. No
T4 spike in any configuration. The edge reaches the medulla at ≤1.4 mV, at most about 5% of the
measured swings, with the measured sign only in Tm3, C3 and Mi9; from an LMC rate of 100 Hz
tonic lamina release holds Mi1 and Mi4 below release, Tm3 from 200 Hz. Report:
`results/t4t5/v3.executions/d85c3913…/output/`.

**2026-10-13: synapse weight rule v1, undecided.** Liu et al. 2022's 57 PN → LHN pairs of six
matched LHN types: Spearman ρ 0.567 (count) against 0.581 (density), Δρ +0.015 with a 95%
interval of −0.011 to +0.054. Count stays the rule. MaleCNS counts rank the measured
amplitudes at ρ 0.81 on the 13 nonzero pairs; density r² 0.80 against Liu et al.'s 0.77.
Report: `results/weight-rule/v1.executions/…/output/`.

**2026-10-13: T4/T5 through the eye v2, robust: neither.** Seed 93, 17 configurations of
graded photoreceptors and L1–L3 over the measured voltage ranges. No T4/T5 spike in any
configuration. The lamina now carries contrast (L1–L3 hyperpolarize by 14–33 mV under light);
Mi1, Tm3 and Mi4 never fire, and the OFF inputs fire only at LMC release rates of 200–400 Hz.
The signal stops at the spiking medulla. Report: `results/t4t5/v2/`.

**2026-10-13: Kenyon cell sparseness v7, within only with the variant set.** Seeds 92–94.
eLNs restricted to Eckstein et al. 2024's lLN2T (13 neurons): dense in every arm (16–23% of
Kenyon cells, 79–96% shared). With lLN1_bc too (43 neurons): 9 of 10 arms within, 1.5–2.2%
of Kenyon cells, 43–65% shared, above Hige et al. 2015's 30–33%. Coupling and spikelets move
no arm by more than 17 cells: the chemical contacts arm E removes make the difference.
Report: `results/kc-sparseness/v7.executions/f8549bf7414656b26cf37dcf99811142bb3b1b3a7743b79d5ebeda941457c3a5/output/`.

**2026-10-13: Kenyon cell sparseness v5, none.** Seeds 86–88. Measured asymmetric eLN ↔ PN
coupling (0.0021 / 0.0039), sister PNs at 0.013, eLN spikelets of 40 mV for 0–2 ms: every
coupled arm is silent (0.22–0.30% of Kenyon cells), as without coupling, whatever the
spikelet duration. At the measured coefficients the coupling is not the missing excitation.
Report: `results/kc-sparseness/v5/`. Figure: [v1–v5](img/kc-sparseness.svg).

**2026-10-13: TTM-driven NeuroMechFly jump v1, short.** Seeds 110–112. Takeoff at 28–32 ms,
0.05 m/s, range 0.3–0.5 mm against 28.6–37.75 mm: only the right TTMn fires before takeoff,
one twitch is below the force a jump needs, and the TLM is absent. Report:
`results/jump3d/v1/`. Figure: [drag-free range](img/jump-range.svg).

**2026-10-13: T4/T5 through the eye v1, neither.** Seeds 90–92, edges at 30°/s. No T4/T5
spike: photoreceptors fire, but their inhibitory (histaminergic) synapses cannot move silent
spiking lamina neurons; the fly's lamina is graded and tonically active. Report:
`results/t4t5/v1/`.

**2026-10-13: Kenyon cell sparseness v4, none.** Seeds 83–85. The cholinergic local neuron →
PN contacts as electrical synapses, coupling 0–1, sister PNs at 0.013: every coupled arm is
silent (≤ 0.3% of Kenyon cells), quieter as coupling grows; subthreshold coupling without
spikelets drains active PNs. Report: `results/kc-sparseness/v4/`. Figure:
[v1–v5](img/kc-sparseness.svg).

**2026-10-13: Kenyon cell sparseness v3, none.** Hige et al. 2015's odors from DoOR, seeds
80–82, bounds 1–17% and ≤ 64.6% shared. Default: 36% / 30% of Kenyon cells, 82–99% shared;
without fast KC → KC: 22.5% / 19.6%; without the cholinergic local neuron → PN chemical
contacts: 0.2%. Dense or silent, never sparse: the antennal-lobe electrical coupling the model
lacks is the missing piece. Report: `results/kc-sparseness/v3/`.

**2026-10-13: partner follow-up v1.** Seeds 40–42, locked before the run. Left mirror:
`replicates` (DNp02 p 0.001, DNp06 p 0.003). Direct drive at 200 Hz without LC4:
`single_sufficient: DNp06_R` (0 / 3–6 / 8–11 `TTMn_R` spikes for DNp02, DNp06, pair; matched
null mean 0.013, p 0.001). Report: `results/partner-followup/v1/`.

**2026-10-13: Kenyon cell sparseness v2, within E and F by undershoot.** Seeds 70–72.
Removing the chemical contacts of cholinergic local neurons onto projection neurons
(electrical in the fly) cuts the PNs driven by one ORN type from 73% to 4.5%, and the
responding Kenyon cells from 25% to 0.2%; the verdict counts that as within because the lock
had only upper bounds. The odor overlap is an antennal-lobe artefact of modelling an electrical
coupling as a chemical one. Report: `results/kc-sparseness/v2/`.

**2026-10-13: Kenyon cell sparseness v1, not_recurrence.** `flymsg kc-sparseness --run`,
seeds 60–62. Making KC → KC synapses metabotropic (no fast effect) lowers the share of
responding Kenyon cells from 25% to 17.4% (bound 17%), but the two odors still share 95%; APL
removal recruits all of them. The odor overlap originates upstream of the Kenyon cells.
Report: `results/kc-sparseness/v1/`.

**2026-10-13: KC → MBON11 depression v1, inconsistent.** `flymsg mb-plasticity --run`,
seeds 50–52, locked before the run. The measured rule (×0.10 on eligible Kenyon cell
synapses) silences MBON11 for both odors (272–286 → 0 spikes): ORN_VA1d and ORN_DL3 each
recruit about 1,000 Kenyon cells and share 95% of them, against 30–33% in the fly. The model's
Kenyon cell code is neither sparse nor odor-specific. Report: `results/mb-plasticity/v1/`.

**2026-10-11: T4, AVLP717m drops pIP10 after P1.** 1,000 matched-responder nulls, seeds
0–2, `w_syn` 0.192, threshold p ≤ 0.05. Silencing AVLP717m (2 neurons) drops pIP10 by
43% (104 → 60 Hz), p = 0.001. dPR1 after P1 drops 28% (97 → 70 Hz), p = 0.001; that
row does not decide. After the pIP10 stimulus, dPR1 is unchanged and the matched null
is not defined (no other excitatory `cb_intrinsic` responder), so that case has no p.
Report: `runs/t4-loop.txt`.

**2026-10-11: null families, 20 draws, MaleCNS v1.0.** `flymsg nulls --full`, seeds 0–19,
`w_syn` 0.192, `th_jump` 0. Score: signed one-hop stim → target weight. Headline = sum of
`max` over the seven specific pathways (real 4077). Smallest _p_ is 1/21. Every pathway
is reported.

| Family                 | headline real | null mean | null s.d. |  _p_ |   _z_ |
| ---------------------- | ------------: | --------: | --------: | ---: | ----: |
| `degree_preserving`    |          4077 |     21.40 |     21.30 | 1/21 | 190.4 |
| `cell_type_preserving` |          4077 |    3196.3 |     256.3 | 1/21 |  3.44 |
| `weight_within_type`   |          4077 |    679.75 |    107.64 | 1/21 |  31.6 |
| `sign`                 |          4077 |    1314.3 |     419.0 | 1/21 |  6.59 |

Real one-hop weights: LC4*R → DNp01 2580/2580 (sum/max), DNp01 → TTMn 90/70, P1 → pIP10
1537/812, pIP10 → dPR1 1112/615. LC4_R → TTMn, P1 → dPR1, sugar → MN9 and bitter → MN9
are 0. Bitter `sum` is not below the nulls (\_p* = 18/21 under degree-preserving; 1 under
the others). Under `cell_type_preserving`, every **sum** is invariant (_p_ = 1). **max**
for LC4*R → DNp01 is 2580 vs null mean 1447.45 (\_p* = 1/21, _z_ = 8.69); DNp01 → TTMn
max 70 is below the null mean 82.00 (_z_ = −1.19); pIP10 → dPR1 max 615 is below 811.70
(_z_ = −1.24). The one-hop score cannot test the four zero-weight pathways; N1 remains
the battery comparison. `w_syn` stayed 0.192.

**2026-10-11: T3 supports dPR1 → dMS9 → vMS12 → IN03B024 → dPR1.** 1,000 matched-responder
nulls, seeds 0–2, `w_syn` 0.192, threshold p ≤ 0.0167. IN03B024 (2 neurons): dPR1 +101%
after pIP10 (88 → 177 Hz) and +100% after P1 (97 → 193 Hz), p = 0.001 both. vMS12_a+b+c
(12): +67% (88 → 147 Hz) and +78% (97 → 172 Hz), p = 0.001 both. dMS9 together with
IN03B024 (4): +100% and +99%. The 95% intervals of the per-seed rise overlap (pIP10
[0.893, 1.167], P1 [0.966, 1.036]). Tests 1 and 2 pass in both cases and the epistasis
holds, so the chain is supported. Report: `runs/t3-loop.txt`.

**2026-09-21: first battery run** (`w_syn` 0.275, `th_jump` 4): 15/18 checks passed.
Failures: GF → DLMn 4.4 Hz (led to the exclusion above); P1 stability, 1,977 self-sustained
neurons on average; P1 control drives dPR1 to 36.7 Hz.

**The runaway is the mushroom body.** After P1 stimulation the self-sustained neurons are
mostly Kenyon cells (KCg-m, KCab-m, KCab-c, KCab-s), with antennal-lobe local neurons and
some sensory neurons. Neither P1 nor pCd stay active, so this is not the persistent courtship
state reported for P1/pCd in the literature. The P1 control most likely failed for the same
reason: a matching random draw of 86 `cb_intrinsic` neurons contained 13 Kenyon cells and
triggered the same runaway (10,222 neurons fired). That diagnostic draw was not the exact
control of the battery run, which shares one random generator across cases.

**The runaway depends on the seed.** Seed 0 alone left 5,931 neurons self-sustained against a
3-seed mean of 1,977, so other seeds stayed much quieter. Single-seed results near this
regime are unreliable.

**Rejected: KC → KC synapses as the cause.** Kenyon cells receive 1,153,845 synapses from other
Kenyon cells, 55% of their input, all treated as excitatory (acetylcholine). Removing them
changed nothing (5,941 vs 5,931 self-sustained neurons, same seed). The loop runs through a
wider circuit.

**The stimulated neurons must not adapt** (fixed in `30329b7`). Early versions let the adaptive
threshold act on stimulated neurons too, which weakened the drive (75 Hz instead of ~200 Hz)
and hid runaway activity. After the fix, `th_jump` 2 left 7,744 neurons self-sustained after
an LC4_R pulse, and the default had to be recalibrated.

**2026-09-21: calibrate-v1 exposed a flaw in criterion v1.** No parameter set passed all
16 checks; the best three (w_syn/th_jump 0.275/12, 0.2/4, 0.2/6) failed only GF → TTMn
(11, 9, 8 Hz against 20 Hz). Stimulating DNp01 directly, the GF fires 103–120 Hz whatever
`th_jump`, yet TTMn_R drops from 20 Hz (th_jump 4) to 10 Hz (th_jump 12): the cap comes from
TTMn's own adaptation, as the rate-cap estimate predicts ((19 − 7) / 1.2 ≈ 10 Hz). The 20 Hz
threshold therefore rewarded weak adaptation on positives while stability rewarded strong
adaptation. Criterion v2 (spikes + ratio) replaces it; `runs/calibrate-v1.csv` is kept for
reference.

**GF → TTMn: evaluated, kept as a documented limit** (2026-09-21, replaces an earlier note
that blamed the uniform synapse weight and quoted ~4.8 mV per GF spike; the correct peak is
3.0 mV: 70 synapses × 0.275 mV through τ_syn 5 ms and τ_m 20 ms, at 9 ms).

- Measured in the fly (Allen & Murphey 2007, Table 1, brain stimulation, TTM recording):
  latency 0.85 ms and 1:1 following at 100 and 250 Hz in controls; 1.62 ms and only 17.5 %
  (100 Hz) and 10.5 % (250 Hz) following in `shak-B²` flies, where only the cholinergic
  component is left.
- Latency cannot be compared: the model's synaptic delay alone (1.8 ms, from Shiu et al.)
  exceeds the whole wild-type latency and is close to the `shak-B²` one.
- Following can. With the fixed engine the stimulated GF fires at the stimulation rate, as in
  the experiment. TTMn_R follows 18.0 % of GF_R spikes at 100 Hz and 16.8 % at 250 Hz with the
  defaults (5 seeds × 500 ms), and 27.7 % / 25.2 % without the adaptive threshold, against
  17.5 % / 10.5 % in `shak-B²`. The connectome's 70 chemical synapses are therefore at least
  as effective as the real chemical component; the earlier hypothesis that the uniform weight
  underweights this synapse is not supported. The left side has only 20 GF → TTMn synapses
  and follows 1–10 %. (With the first engine, 14 % and 13 % at ~90 and ~200 Hz.)
- What the model lacks is the ShakB gap junction that makes the real synapse 1:1 and fast.
  It is not added: no measured coupling transferable to this LIF exists (the only numbers are
  conductances fitted inside a compartmental model), so it would have to be tuned on the very
  behaviour it should explain, and the connectome contains none of the other gap junctions.
  The model's giant fiber behaves like a `shak-B²` fly; behaviours that need the electrical
  synapses (1:1 following, sub-millisecond latency, GF → DLMn) are outside its scope. The
  agreement of the default following ratio with `shak-B²` depends on the adaptive threshold,
  so it is reported here, not used as a check.

**2026-09-21: the "Sugar SEL" neurons do not identify labellar sugar GRNs.** Six central
neurons carry the synonym "Yao & Scott 2022: Sugar SEL PN/LN" (GNG540, GNG550, GNG056). They
receive 1,233 of their 13,327 input synapses from gustatory neurons, almost all pharyngeal
(PhG9 754) or taste-peg (dorsal_tpGRN 356), and none from LB3. They were planned as the
second line of evidence for the sugar set and replaced by the cross-sex fingerprint.

**2026-09-21: criterion v3 with the first engine: 27/28.** All order and dose checks passed
(TTMn after DNp01 and dPR1 after pIP10 in every seed; every curve rises with the input rate).
Sugar → MN9 passed positive, dose and stability (MN9_L, contralateral as in Shiu et al.: 9 / 22
/ 32 / 39 Hz at 25 / 50 / 100 / 200 Hz, 83 % of peak at 100 Hz against their ~80 %) but failed
specificity: the superclass-matched control (17 random `cb_sensory` neurons) drove MN9 to
17.8 Hz. It drew labellar and head mechanosensory neurons (TPMN1, BM_Taste, BM_InOm, entering
through MxLbN) that reach MN9 through GNG015. In this model MN9 responds to sugar only 1.8×
more than to any labial sensory drive of the same size. The criterion is not changed after the
fact. This run used the engine before the fidelity fix below.

**2026-09-21: the engine deviated from the published model.** Reading the Shiu et al. brian2
code showed four differences: Poisson input went into the conductance g instead of the
membrane potential v; a spike reset only v, not g; g kept decaying during the refractory
period instead of being frozen; stimulated neurons kept the 2.2 ms refractory period instead
of none. Together they made stimulated neurons fire about twice the requested rate (noted in
the README as a feature). After fixing them, running both engines on FAFB still left
downstream neurons 3–18 % more active in flymsg, growing with the input rate. A two-neuron
network isolated the cause in the refractory period (both engines agreed with `t_ref` 0), and
a direct brian2 test showed that synaptic input reaching a refractory neuron is lost there,
while flymsg kept it; flymsg's refractory period was also one step too long. With those two
fixed the two-neuron network matches brian2 (45.1 vs 44.4 Hz, 19.4 vs 19.0 Hz). The engine now follows the brian2 schedule (see [model](model.md)); the
defaults are re-derived with calibrate-v3 below.

**2026-09-21: criterion v3 with the fixed engine and the calibrate-v3 defaults: 27/28**
(`runs/validate-v3-final.txt`). Every positive, order, dose and stability check passes;
latencies DNp01 4.4 ms, TTMn 13.2 ms after LC4_R; pIP10 6.7 ms, dPR1 8.8 ms after P1; MN9
29.8 ms after sugar. Shares of peak at 100 Hz: 49–87 % (MN9 73 %, against Shiu et al.'s ~80 %
in FAFB). The one failure is again sugar → MN9 specificity (MN9 38.9 Hz, control 25.6 Hz).

**2026-09-21, exploratory: with `w_syn` scaled for synapse density, the adaptive threshold
may not be needed.** MaleCNS neurons carry 1.81× the synapses of their FAFB counterparts
(docs/comparison.md), so Shiu's `w_syn` 0.275, tuned on FAFB, corresponds to 0.152 here.
The battery with `w_syn` 0.152 and **no adaptive threshold** (`runs/validate-density-w0152-th0.txt`)
passes 26/28: zero self-sustained neurons in every case, all positives, orders and doses,
except sugar → MN9, where MN9 stays almost silent (1.1 Hz) while the control drives it to
31.1 Hz. The runaway that motivated the compensation therefore comes from the synapse scale
of this dataset rather than from the VNC. This was not pre-registered, so it does not replace
the calibrate-v3 defaults; a pre-registered comparison of the two models is the next step
(done: model selection and replication below).

**2026-09-21: MN9 depends on LB3d in the density-scaled model** (descriptive,
`runs/stimulus-equivalence.txt`, 3 seeds, right side):

| Stimulus                                             | MN9, A (`w_syn` 0.275, `th_jump` 2) | MN9, B (`w_syn` 0.152, `th_jump` 0) |
| ---------------------------------------------------- | ----------------------------------- | ----------------------------------- |
| LB3b + LB3c (the sugar set, 17)                      | 38.9 Hz                             | 0.0 Hz                              |
| LB3b + LB3c + LB3d (like FAFB's single LB3 type, 32) | 48.9 Hz                             | 42.2 Hz                             |
| LB3d alone (15)                                      | 45.6 Hz                             | 14.4 Hz                             |

At the data's own synapse scale, the proboscis motor neuron responds to the combined LB3
population but not to the subtypes matched to Gr64f. LB3d was matched to high-salt,
avoidance-related receptor lines by one study, while its connectivity resembles Shiu's FAFB
"sugar" set, which FAFB types as a single LB3. Part of the published sugar → MN9 response may
therefore come from LB3d-like neurons. Which of these is right needs the receptor identity of
LB3d confirmed; the model cannot decide it.

**2026-09-21: model selection (criterion v4, 10 seeds, `flymsg select-model`): A wins.**
Reports: `runs/validate-v4-10seeds-{A,B,B-,B+}.csv`, summary `runs/select-model.txt`.

| Model                       | `w_syn`        | `th_jump` | Checks passed | Failures                                                                   |
| --------------------------- | -------------- | --------- | ------------- | -------------------------------------------------------------------------- |
| **A** (default at the time) | 0.275          | 2         | **28/29**     | looming stability: 196 self-sustained neurons on average (55 with 3 seeds) |
| B                           | 0.152 (ρ 1.81) | 0         | 26/29         | GF → TTMn reliable in 6/10 seeds; sugar → MN9 positive and specificity     |
| B− (not eligible)           | 0.192 (ρ 1.43) | 0         | **29/29**     | none                                                                       |
| B+ (not eligible)           | 0.113 (ρ 2.43) | 0         | 24/29         | GF → TTMn, all sugar checks, bitter negative (no sugar reference)          |

- The class-matched control resolves the sugar specificity failure: random gustatory
  neurons leave MN9 at 0 Hz in every model, while sugar drives it to 30–37 Hz (bootstrap
  interval) in A. Bitter GRNs leave MN9 at 0 Hz (negative check passed).
- By the pre-registered rule A stays the default. With 10 seeds its looming stability check
  fails, a reminder that the self-sustained regime depends on the seed.
- **B−, the published model with no compensation and `w_syn` at the lower bound of the
  measured density ratio, passes every check.** It was declared not eligible before the run,
  so it is not adopted; a confirmatory, pre-registered replication on fresh seeds is the way
  to decide whether it should replace A.

**2026-09-22: replication of B− — B− becomes the default.** On fresh simulation seeds
10–19 and fresh control draws (`runs/replication-Bminus.txt`,
`runs/validate-v4-replication-10seeds-{A,B-}.csv`) both A and B− pass 29/29; by the
pre-registered rule the tie goes to B−. The default is now `w_syn` = 0.275 / 1.43 = 0.192 and
**no adaptive threshold**: the published model at a density-scaled synapse weight, with no
compensation. A's looming stability failure at seeds 0–9 did not recur at seeds 10–19,
another sign that it was seed-dependent. The caveat stays: B− was one of four variants
tried, and 1.43 is the lower quartile of the density ratio, not its median (1.81, model B,
which fails sugar → MN9).

**2026-09-22: reconstruction audit (`flymsg audit`, docs/data.md).** Of the neurons behind
the validation, MN9 is flagged (MN9_L 6,012 input synapses, MN9_R 556; symmetric in FAFB):
the sugar case reads MN9_L through the contralateral right GRNs, so its checks are not
affected, but v0.5.0's "lateralised MN9" in the sex comparison was most likely an artefact
and is corrected there. LB3c is also flagged (right GRNs 2.5× the input of the left), which
may make the right-side sugar stimulus stronger than a left one. GF → TTMn's left/right
difference (20 vs 70 synapses) is a single-connection asymmetry the totals-based audit
cannot attribute; DNp01, pIP10, dPR1, dMS9, the P1 (pC1) neurons and LC4 are symmetric.

**2026-09-23: pre-registered silencing tests (T1, T2; docs/dimorphism.md), 1,000 null draws
each, threshold p ≤ 0.00625 over 8 confirmatory tests.** Reports:
`runs/silencing-1000.txt`, `runs/loop-silencing.txt`.

- **T1**: silencing the 948 sexually dimorphic neurons raises dPR1 by 61 % (after pIP10) and
  64 % (after P1), p = 0.001 both, more than any of 1,000 superclass-matched random
  silencings: confirmed. The fru/dsx+ category is not confirmed: the rise is larger
  (+79 … +100 %) but after P1 eleven random silencings of ~4,900 neurons matched it
  (p 0.011). Silencing a fifth of the CNS moves dPR1 by +21 % on average, so the effect is
  not specific to the category.
- **T2**: silencing dMS9 (2 neurons) raises dPR1 by 67 % and 74 % (p 0.001), against a null
  of silencing 2 matched responders. Silencing vPR9_a + IN00A038 does not: −6 % after pIP10
  (p 0.63) and +32 % after P1, inside the null (p 0.036). **The v0.5 prediction of the loop
  dPR1 → dMS9 → vPR9_a / IN00A038 → dPR1 is therefore half wrong**, and the docs are
  corrected: dMS9 restrains dPR1, by a route this test does not identify.
- Post-hoc, kept as a lead and pre-registered as T3: the inhibition of dPR1 that disappears
  with dMS9 silenced is IN03B024 (1,533 synapses onto dPR1), driven by vMS12_a/b/c.
- Cost and method: 1,000 draws × 3 seeds × 15 jobs. Runs stop at the end of the stimulus
  (identical rates in the scored window, 2–2.7× cheaper) and are resumable, since the whole
  battery takes many CPU hours on this machine.

**2026-10-11: T3** (pre-registered 2026-09-23; `runs/t3-loop.txt`; the checkpoint was
resumed). Silencing IN03B024 (2) raises dPR1 by 101% after pIP10 and 100% after P1.
Silencing vMS12_a+b+c (12) raises it by 67% and 78%. All four rises have p = 0.001.
Silencing dMS9 together with IN03B024 raises it by 100% and 99%, and the 95% bootstrap
intervals of the per-seed rise overlap in both cases. The chain is supported. `w_syn`
stayed 0.192. The full record is in [dimorphism](dimorphism.md).

**2026-10-11: T4** (pre-registered 2026-10-11, before the run; `runs/t4-loop.txt`).
Silencing AVLP717m (2) drops pIP10 after P1 by 43% (104 → 60 Hz), p = 0.001, so the
confirmatory test passes. The same silencing drops dPR1 after P1 by 28%; that row does
not decide. After the pIP10 stimulus the matched null is not defined and dPR1 is
unchanged. `w_syn` stayed 0.192. The full record is in [dimorphism](dimorphism.md).

## Limits of this validation

- Six cases in the calibration battery: five short feedforward chains and the bitter
  negative. They say little about long-range or recurrent processing. The held-out
  olfactory case is a separate protocol and it fails ([benchmarks](benchmarks.md)).
- Thresholds (3 spikes, 3× + 2 Hz, 100 neurons, ≥ 5 synapses for control exclusion, one spike
  of dose tolerance) are judgement calls, not derived from data.
- Order and dose are quantitative but coarse: no absolute latencies (the model's delay and
  time constants set a floor above some real latencies) and no fitted rate curves.
- The control matches superclass, or class for sensory stimuli (v4); it does not match
  transmitter, size of the population's output or distance from the target.
- One stimulus duration (300 ms).

## References

Every entry was checked against PubMed or bioRxiv (title, authors, venue, volume, pages, year)
on 2026-09-22.

- Ache, J. M. et al. Neural basis for looming size and velocity encoding in the _Drosophila_
  giant fiber escape pathway. _Current Biology_ 29, 1073–1081 (2019).
  doi:10.1016/j.cub.2019.01.079
- Allen, M. J. & Murphey, R. K. The chemical component of the mixed GF-TTMn synapse in
  _Drosophila melanogaster_ uses acetylcholine as its neurotransmitter. _European Journal of
  Neuroscience_ 26, 439–445 (2007). doi:10.1111/j.1460-9568.2007.05686.x
- Blagburn, J. M. et al. Null mutation in `shaking-B` eliminates electrical, but not chemical,
  synapses in the _Drosophila_ giant fiber system: a structural study. _Journal of Comparative
  Neurology_ 404, 449–458 (1999). PMID 9987990
- Cachero, S. et al. Sexual dimorphism in the fly brain. _Current Biology_ 20, 1589–1601
  (2010). doi:10.1016/j.cub.2010.07.045
- Gordon, M. D. & Scott, K. Motor control in a _Drosophila_ taste circuit. _Neuron_ 61,
  373–384 (2009). doi:10.1016/j.neuron.2008.12.033
- King, D. G. & Wyman, R. J. Anatomy of the giant fibre pathway in _Drosophila_. I. Three
  thoracic components of the pathway. _Journal of Neurocytology_ 9, 753–770 (1980).
  doi:10.1007/BF01205017
- Shiu, P. K. et al. A _Drosophila_ computational brain model reveals sensorimotor processing.
  _Nature_ 634, 210–219 (2024). doi:10.1038/s41586-024-07763-9
- Tastekin, I. et al. From sensory detection to motor action: the comprehensive _Drosophila_
  taste-feeding connectome. _bioRxiv_ (2025, v2). doi:10.1101/2025.08.25.671814 (v1 title:
  "Connectomics reveals a feed-forward swallowing circuit driving protein appetite")
- von Philipsborn, A. C. et al. Neuronal control of _Drosophila_ courtship song. _Neuron_ 69,
  509–522 (2011). doi:10.1016/j.neuron.2011.01.011
- von Reyn, C. R. et al. A spike-timing mechanism for action selection. _Nature Neuroscience_
  17, 962–970 (2014). doi:10.1038/nn.3741
- Yu, J. Y. et al. Cellular organization of the neural circuit that drives _Drosophila_
  courtship behavior. _Current Biology_ 20, 1602–1614 (2010). doi:10.1016/j.cub.2010.08.025
