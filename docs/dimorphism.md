# Dimorphism in the male model

`flymsg dimorphism` asks, for each validation case, whether the simulated response runs
through sexually dimorphic neurons more than expected. Code: `src/flymsg/dimorphism.py`.
Output: `runs/dimorphism.txt`.

## Method

- **Responders**: neurons other than the stimulated ones that fire during the 300 ms stimulus
  in ≥ 2 of 3 seeds (validation protocol, defaults: `w_syn` 0.192, no adaptive threshold;
  with the v0.3 defaults the pattern was the same, P1 3.4–8.1×, pIP10 5.8–16.3×).
- **Categories** (MaleCNS annotations; "potentially …" included): `fru/dsx+` (any `fruDsx`
  value), male-specific, dimorphic (sexually or potentially dimorphic).
- **Null**: 1,000 random neuron sets of the same size and superclass mix as the responders,
  drawn from all non-stimulated neurons. Matching superclass matters: responders of a visual
  stimulus are mostly visual neurons, and dimorphic neurons are not spread evenly.
- **Statistic**: share among responders / mean null share, with an empirical one-sided p
  (+1 smoothing, so the smallest possible p is 0.001). 15 tests (5 cases × 3 categories):
  with Bonferroni, p ≤ 0.0033 is significant.

## Results

| Case               | Responders | fru/dsx+       | male-specific   | dimorphic         |
| ------------------ | ---------: | -------------- | --------------- | ----------------- |
| P1 courtship drive |      1,824 | **4.3×** (512) | **10.9×** (361) | **6.1×** (148)    |
| pIP10 song pathway |        242 | **13.3×** (84) | **18.6×** (32)  | **4.9×** (7)      |
| looming escape     |      1,087 | 0.40× (22)     | 0.46× (7)       | 1.3× (16), p 0.19 |
| sugar feeding      |        360 | 0.44× (11)     | 0 (0)           | 0.51× (4)         |
| giant fiber output |          2 | 0              | 0               | 0                 |

Bold: p = 0.001. Counts of responders in the category in brackets.

- **Courtship circuits run through the dimorphic network.** P1 and pIP10 responses are 3–16×
  enriched in fru/dsx+, male-specific and dimorphic neurons, within their superclasses. This is
  the model's side of the known picture: P1 and pIP10 sit in the fruitless circuit that
  builds courtship song.
- **Escape and feeding avoid it.** Looming and sugar responses contain about half the
  expected share of fru/dsx+ and male-specific neurons.
- **The giant fiber's reach depends on the model.** With the v0.3 defaults its 29
  responders included 5 fru+ wing motor neurons (hg1, hg3, ps1); with the density-scaled
  weight only 2 neurons respond besides TTMn, so the escape output stays narrow.

## Silencing (`flymsg dimorphism --silencing`, `runs/silencing.txt`)

Every neuron of a category is silenced (it never fires, so it transmits nothing: for the rest
of the network this equals zeroing its outgoing synapses, as Shiu et al. silence neurons),
except the stimulus and the targets. The drop of each target's rate is compared with 100
silencings of as many neurons outside the category, with the same superclass mix (defaults,
3 seeds). The smallest possible p is 0.0099; with 15 tests nothing survives a Bonferroni
correction, so these are indications.

| Case → target       | fru/dsx+ (~4,900 silenced) | male-specific (~1,330) | dimorphic (948) | null, mean  |
| ------------------- | -------------------------- | ---------------------- | --------------- | ----------- |
| P1 → pIP10          | −12 % (p 0.010)            | +9 %                   | −3 % (p 0.04)   | +5 … +12 %  |
| P1 → dPR1           | **+79 %**                  | +2 %                   | **+64 %**       | +11 … +22 % |
| pIP10 → dPR1        | **+100 %**                 | −13 % (p 0.03)         | **+61 %**       | −1 … −6 %   |
| LC4_R → DNp01, TTMn | within the null            | within the null        | within the null |             |

Changes are relative to the unsilenced response; + is a rise. The p values test drops only.

- **Enrichment is not necessity.** Courtship responses survive the loss of thousands of
  dimorphic neurons, because they run mostly through the direct P1 → pIP10 → dPR1 links,
  which stay intact (stimulus and targets are never silenced).
- **The dimorphic network restrains the song pathway.** Silencing all fru/dsx+ or all
  dimorphic neurons doubles dPR1, far beyond the changes random silencings cause.
- With the v0.3 defaults (20 null draws) silencing the male-specific neurons lowered dPR1 by
  ~20 %; with the density-scaled model that effect is gone (P1: +2 %), so it is not robust.
- Looming escape does not depend on any of the three categories.

### Which cell types (`--by-type`, `runs/silencing-by-type-*.txt`)

Silencing the fru/dsx+ responders one cell type at a time (3 seeds, no null) points to one
loop:

| Type silenced (neurons)  | dPR1 after pIP10 | dPR1 after P1 | pIP10 after P1 |
| ------------------------ | ---------------- | ------------- | -------------- |
| dMS9 (2)                 | **+67 %**        | **+74 %**     | +14 %          |
| vPR9_a (4) / vPR9_c (3)  | −9 % / —         | +29 % / +38 % | +14 % / +21 %  |
| vMS12_a (6)              | +14 %            | +39 %         | +6 %           |
| TN1a subtypes (1–4 each) | −1 … −15 %       | +18 … +20 %   | +3 … +4 %      |
| AVLP717m (2)             | —                | −28 %         | **−43 %**      |

dMS9 (fru_high, sexually dimorphic, cholinergic; "Lillvis 2024: dMS9") receives 822 synapses
from dPR1 and gives it only 5. It drives two inhibitory neurons that project back onto dPR1:
vPR9_a (670 synapses from dMS9, 128 onto dPR1) and IN00A038 (161, 132). The model therefore
predicts a disynaptic negative feedback loop, **dPR1 → dMS9 → vPR9_a / IN00A038 → dPR1**,
that holds the song pathway back. AVLP717m (fru+) relays part of P1's drive to pIP10.
These are model predictions from wiring and predicted transmitters, open to experimental
test.

## Pre-registered tests (v0.6, fixed 2026-09-22 before running)

The silencing results above are indications: 100 null draws cannot reach a Bonferroni
threshold, the p values tested drops while the claims are rises, and the loop comes from a
scan without a null. Two confirmatory tests, with the defaults and the validation protocol
(3 seeds, 100 Hz, 300 ms; target rate = best neuron's mean rate), follow. The rules below
are fixed before any of these runs; a failure is reported as a finding.

**T1. The dimorphic network restrains dPR1** (`flymsg dimorphism --silencing --null 1000`).
Same design as above (silence every neuron of the category except stimulus and targets; null
= as many neurons outside the category with the same superclass mix), with 1,000 null
draws and a one-sided test for a **rise**: p = (1 + number of null draws whose rise is ≥ the
observed rise) / 1,001. Four confirmatory tests: fru/dsx+ and dimorphic, each after P1 and
after pIP10, on dPR1. Male-specific, the other targets and looming escape are reported as
descriptive.

**T2. The predicted loop dPR1 → dMS9 → vPR9_a / IN00A038 → dPR1** (`flymsg dimorphism
--loop --null 1000`). Two silenced sets: **dMS9** (both neurons, cholinergic, ascending)
and **the inhibitory feedback** (all 4 vPR9_a and all 4 IN00A038, GABAergic, VNC
intrinsic). The null silences as many neurons drawn from **the case's own responders**
(firing in ≥ 2 of 3 seeds), matched on superclass and transmitter sign, never the stimulus,
the targets or the tested neurons. This is stricter than a random draw: it asks whether
these neurons matter more than other active neurons of the same kind, not whether silencing
active neurons does anything. Four confirmatory tests: each set after pIP10 and after P1,
one-sided for a rise of dPR1, as in T1. Silencing both sets together is reported as
descriptive.

**Decision rules.** The 8 confirmatory tests (T1 and T2) share one Bonferroni threshold,
p ≤ 0.05 / 8 = 0.00625. T1 is confirmed for a category if both cases pass. The loop (T2)
is **supported** if both sets pass after pIP10, the most direct test; **partly supported**
if only dMS9 passes (dMS9 restrains dPR1 through some route, not necessarily the named
inhibitors); **not supported** otherwise. The P1 results qualify the verdict but do not
change it. Known beforehand: in the v0.5 per-type scan, silencing vPR9_a alone after pIP10
lowered dPR1 by 9 %, and IN00A038 was never tested (it is not fru+).

### Execution notes (added 2026-09-22, before any confirmatory result)

- **Runs stop at the end of the stimulus.** The tests use only the target rate in the
  0–300 ms window. The Poisson input is drawn for the stimulus only and the dynamics are
  causal, so stopping each run at 300 ms instead of 600 ms gives bit-identical rates. This
  was checked on the real data for pIP10, P1 and looming, through `sim.run` and
  `validate.respond`, and it is locked by a unit test. It costs 2–2.7× less.
- **Confirmatory jobs run first**, so that an interrupted run has the 8 decisions before the
  descriptive tests.
- **Interruptions.** A first run, which stored nothing until the end, was stopped after
  5 hours because the CPU was thermally capped at 900 MHz and would have needed about 20
  hours; its output was lost. The runs now save every null draw (`--checkpoint`). A resumed
  run replays the saved picks, each checked against its hash, and simulates only the
  missing draws.
- **Disclosed peeks.** End-to-end checks of the code on the real data used 2 and 4 null
  draws. They showed silencing dMS9 after pIP10 raising dPR1 by about 67 %, and silencing
  the inhibitory feedback lowering it by about 6 %. No rule was changed after them.

## Limits

- Annotations, not measurements: `fruDsx` and `dimorphism` are the release's best calls; the
  "potentially" levels are included.
- Enrichment says where the simulated activity goes; silencing tests necessity, with 100 null
  draws per category test and none for the per-type scan.
- The null matches superclass only, not transmitter or proximity to the stimulus.
