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
- **Sugar GRNs → MN9** (the headline validation of Shiu et al.): MN9 exists, but MaleCNS
  gustatory neurons are named by sensillum (`LB3`, `PhG…`) with no sugar annotation, so the
  sugar-sensing set cannot be selected yet.

## Calibration

Grid: `w_syn` ∈ {0.2, 0.275, 0.35} × `th_jump` ∈ {2, 4, 6, 8, 12}, 3 seeds, criterion v2, ranked
by checks passed; ties go to the set closest to the published model (`w_syn` nearest 0.275,
then the smallest `th_jump`). Rule fixed before the run (commit `fc5c332`). Reproduce:
`flymsg calibrate --out runs/calibrate-v2.csv` (~45 min with 5 workers).

**Result (calibrate-v2): `w_syn` 0.275, `th_jump` 6 mV** — the default since `b6dc609`.

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

**GF → TTMn is weak in the model itself.** It has 70 synapses on the right and 20 on the left.
With one weight per synapse, a single GF spike moves TTMn by ~4.8 mV, below the 7 mV gap to
threshold, so TTMn needs several summed GF spikes: first spike at 19 ms under every
parameter set. In the fly each GF spike drives a TTMn spike, and even the chemical-only path of
*shak-B²* mutants responds with a latency of a few ms. A uniform `w_syn` underweights this
giant synapse. This is a model limitation, not a calibration issue.

## Limits of this validation

- Four cases, all short feedforward chains (1–2 hops) close to the stimulus. They say little
  about long-range or recurrent processing.
- Thresholds (20 Hz, 100 neurons, ≥ 5 synapses for control exclusion) are judgement calls, not
  derived from data.
- Checks are qualitative (does it fire?), not quantitative (latency, rate ratios).
- One stimulus rate (100 Hz) and duration (300 ms).

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
