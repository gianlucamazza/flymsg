# Validation

`flymsg validate` checks the simulator against circuits whose function is known from
experiments. `flymsg calibrate` runs the same battery over a parameter grid. Code:
`src/flymsg/validate.py`; the full battery also runs as a slow test
(`uv run pytest -m slow`).

## Protocol

Every case stimulates a population with Poisson input at 100 Hz for 300 ms, runs 600 ms in
total and uses 3 seeds (0, 1, 2). For each target type the **best neuron** (highest mean
stimulus-window rate over seeds) is scored; many targets are bilateral pairs and a unilateral
stimulus drives one side (LC4_R → DNp01_R and TTMn_R). Three kinds of check:

| Kind | Passes when | Why |
|---|---|---|
| positive | the best neuron fires ≥ 3 spikes in the 300 ms window in ≥ 2 of 3 seeds | the known pathway carries the signal, even as a weak or labile response |
| specific | its rate ≥ 3 × the control rate + 2 Hz | the response needs the specific wiring, not just any drive of that size |
| stability | ≤ 100 neurons still fire from 400 ms (stim end + 100 ms) to 600 ms | no self-sustained runaway |

The control stimulates the same number of random neurons, matching the stimulus' superclass
mix (e.g. 55 `visual_projection` neurons for LC4_R), and excludes the stimulated neurons, the
targets and every neuron with a direct connection of ≥ 5 synapses onto a target. Draws use a
fixed seed, so a run is reproducible. The report also gives each target's median first-spike
latency (descriptive, not checked).

**Criterion v3** (fixed 2026-09-21 before running it; the defaults `w_syn` 0.275 and
`th_jump` 6 are not retuned for it, and a failure is recorded as a finding; the engine fix
found afterwards required a separate, also pre-registered, calibrate-v3) adds two
quantitative checks to v2:

| Kind | Passes when | Why |
|---|---|---|
| order | for targets that are successive stages of one pathway (LC4 → DNp01 → TTMn, P1 → pIP10 → dPR1), the earlier stage fires first in ≥ 2/3 of the seeds where both fire | signals must travel along the chain, not reach the later stage by another route first |
| dose | the best target neuron's rate, at input rates 25 / 50 / 100 / 200 Hz, never drops by more than one spike per window (3.3 Hz) from one rate to the next, and is higher at 200 Hz than at 25 Hz | a feed-forward sensorimotor pathway should respond more to stronger input |

For each target the report also gives the share of its peak reached at 100 Hz, next to
Shiu et al.'s calibration (100 Hz sugar input gives ~80 % of maximal MN9 firing); this is
descriptive, not a check.

**Why spikes and a ratio, not a rate threshold** (criterion v2, fixed 2026-09-21 before
`calibrate-v2`): the adaptive threshold caps steady rates at about
`(drive − 7 mV) / (th_jump · τ_th)`, so the first criterion (target ≥ 20 Hz, control < 20 Hz)
penalised adaptation itself: raising `th_jump` lowered every target's rate regardless of wiring.
See the findings log.

## Cases

| Case               | Stimulus           | Targets                   | Evidence                                                                                                   |
| ------------------ | ------------------ | ------------------------- | ---------------------------------------------------------------------------------------------------------- |
| looming escape     | LC4_R (55 neurons) | DNp01 (Giant Fiber), TTMn | LC4/LPLC2 drive the GF, which drives the jump muscle motor neuron (von Reyn et al. 2014; Ache et al. 2019) |
| giant fiber output | DNp01 (2)          | TTMn                      | GF → TTMn (King & Wyman 1980); the cholinergic component alone still drives TTM, with long latency, in *shak-B²* flies lacking the gap junctions (Allen et al. 2007) |
| P1 courtship drive | P1 (86)            | pIP10, dPR1               | P1 activation elicits courtship song through pIP10 (von Philipsborn et al. 2011)                           |
| pIP10 song pathway | pIP10 (2)          | dPR1                      | pIP10 and dPR1 are courtship song neurons (von Philipsborn et al. 2011); 337 synapses pIP10 → dPR1 here    |
| sugar feeding      | sugar GRNs, right (LB3b_R + LB3c_R, 17) | MN9       | sugar GRNs drive proboscis extension; MN9 moves the proboscis (Gordon & Scott 2009); the headline case of Shiu et al. 2024 |

**P1** is not a cell type in MaleCNS. It is selected as the `pC1*` types whose literature
synonyms include pMP4/pMP-e (Yu et al. 2010; Cachero et al. 2010): 86 neurons, all male-specific
or potentially male-specific.

### Excluded on purpose

- **GF → DLMn** (flight muscle motor neurons): GF → PSI → DLMn depends on gap junctions. In
  *shak-B²* mutants, which lack them, GF stimulation elicits no DLM response at all, while the
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

| male type | sugar | water | bitter | receptor line |
|---|---|---|---|---|
| LB3a | 0.58 | **0.90** | 0.03 | water |
| LB3b | **0.77** | 0.65 | 0.04 | sugar |
| LB3c | **0.96** | 0.77 | 0.01 | sugar |
| LB3d | **0.90** | 0.72 | 0.02 | high salt |
| LB1a / LB1c / LB1e | ≤ 0.05 | ≤ 0.06 | **0.64 / 0.82 / 0.57** | bitter |

The lines agree on LB3a, LB3b and LB3c, so the sugar set is LB3b + LB3c. LB3d disagrees and
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

| w_syn \ th_jump | 2 | 4 | 6 | 8 | 12 |
|---|---|---|---|---|---|
| 0.2 | 16 | 16 | 16 | 15 ¹ | 15 ¹ |
| 0.275 | 13 ² | 15 ³ | **16** | 16 | 16 |
| 0.35 | 12 ² | 12 ² | 13 ² | 14 ² | 14 ² |

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

**Result (calibrate-v3): `w_syn` 0.275, `th_jump` 2 mV**, 27/28 — the default since then.

| w_syn \ th_jump | 2 | 4 | 6 | 8 | 12 |
|---|---|---|---|---|---|
| 0.2 | 27 | 26 ¹ | 26 ¹ | 26 ¹ | 24 ² |
| 0.275 | **27** | 27 | 26 ³ | 27 | 27 |
| 0.35 | 25 ⁴ | 25 ⁴ | 25 ⁴ | 27 | 26 ⁴ |

Checks passed out of 28. Every set fails sugar → MN9 specificity (control 3–26 Hz): no
parameter separates sugar from the labial mechanosensory drive of the control, so this is not
a calibration issue. ¹ MN9 below 3 spikes as well. ² TTMn and MN9 below 3 spikes. ³ 385
neurons self-sustained after LC4_R. ⁴ Self-sustained activity after P1, GF, LC4_R or sugar.

With the engine fixed, much less adaptation is needed (2 mV instead of 6). Stability is not
monotonic in `th_jump` (6 fails where 2, 4, 8 and 12 pass at `w_syn` 0.275), a sign that the
runaway regime depends on the seed near its edge, as already seen with P1.

## Findings log

Negative and surprising results, kept so they are not rediscovered.

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
  (100 Hz) and 10.5 % (250 Hz) following in *shak-B²* flies, where only the cholinergic
  component is left.
- Latency cannot be compared: the model's synaptic delay alone (1.8 ms, from Shiu et al.)
  exceeds the whole wild-type latency and is close to the *shak-B²* one.
- Following can. With the fixed engine the stimulated GF fires at the stimulation rate, as in
  the experiment. TTMn_R follows 18.0 % of GF_R spikes at 100 Hz and 16.8 % at 250 Hz with the
  defaults (5 seeds × 500 ms), and 27.7 % / 25.2 % without the adaptive threshold, against
  17.5 % / 10.5 % in *shak-B²*. The connectome's 70 chemical synapses are therefore at least
  as effective as the real chemical component; the earlier hypothesis that the uniform weight
  underweights this synapse is not supported. The left side has only 20 GF → TTMn synapses
  and follows 1–10 %. (With the first engine, 14 % and 13 % at ~90 and ~200 Hz.)
- What the model lacks is the ShakB gap junction that makes the real synapse 1:1 and fast.
  It is not added: no measured coupling transferable to this LIF exists (the only numbers are
  conductances fitted inside a compartmental model), so it would have to be tuned on the very
  behaviour it should explain, and the connectome contains none of the other gap junctions.
  The model's giant fiber behaves like a *shak-B²* fly; behaviours that need the electrical
  synapses (1:1 following, sub-millisecond latency, GF → DLMn) are outside its scope. The
  agreement of the default following ratio with *shak-B²* depends on the adaptive threshold,
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
the calibrate-v3 defaults; a pre-registered comparison of the two models is the next step.

## Limits of this validation

- Five cases, all short feedforward chains (1–2 hops) close to the stimulus. They say little
  about long-range or recurrent processing.
- Thresholds (3 spikes, 3× + 2 Hz, 100 neurons, ≥ 5 synapses for control exclusion, one spike
  of dose tolerance) are judgement calls, not derived from data.
- Order and dose are quantitative but coarse: no absolute latencies (the model's delay and
  time constants set a floor above some real latencies) and no fitted rate curves.
- The control matches superclass only; for sensory stimuli that mixes modalities.
- One stimulus duration (300 ms).

## References

Entries marked as checked had title, venue and year verified online (not authors); the others are
compiled from memory: verify titles and venues before citing.

- Allen, M. J. et al. The chemical component of the mixed GF-TTMn synapse in
  *Drosophila melanogaster* uses acetylcholine as its neurotransmitter. *European Journal of
  Neuroscience* (2007). <https://pubmed.ncbi.nlm.nih.gov/17650116/> (title, venue and year checked)
- Blagburn, J. M. et al. Null mutation in *shaking-B* eliminates electrical, but not chemical,
  synapses in the *Drosophila* giant fiber system: a structural study. *Journal of Comparative
  Neurology* (1999). (title, venue and year checked)
- Ache, J. M. et al. Neural basis for looming size and velocity encoding in the _Drosophila_
  giant fiber escape pathway. _Current Biology_ (2019).
- Cachero, S. et al. Sexual dimorphism in the fly brain. _Current Biology_ (2010).
- King, D. G. & Wyman, R. J. Anatomy of the giant fibre pathway in _Drosophila_. _Journal of
  Neurocytology_ (1980).
- von Philipsborn, A. C. et al. Neuronal control of _Drosophila_ courtship song. _Neuron_ (2011).
- von Reyn, C. R. et al. A spike-timing mechanism for action selection. _Nature Neuroscience_
  (2014).
- Yu, J. Y. et al. Cellular organization of the neural circuit that drives _Drosophila_
  courtship behavior. _Current Biology_ (2010).
