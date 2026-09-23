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

## Silencing (`flymsg dimorphism --silencing --null 1000`, `runs/silencing-1000.txt`)

Every neuron of a category is silenced (it never fires, so it transmits nothing: for the rest
of the network this equals zeroing its outgoing synapses, as Shiu et al. silence neurons),
except the stimulus and the targets. The change of each target's rate is compared with 1,000
silencings of as many neurons outside the category, with the same superclass mix (defaults,
3 seeds). These are the pre-registered T1 runs (below); the smallest possible p is 0.001 and
the threshold is 0.00625.

**Confirmatory: does the dimorphic network hold dPR1 back?** (one-sided for a rise)

| Silenced (n)     | Case  | dPR1, base → silenced | Change     | Null change, mean (range) | p         |
| ---------------- | ----- | --------------------- | ---------- | ------------------------- | --------- |
| fru/dsx+ (5,008) | pIP10 | 87.8 → 175.6 Hz       | **+100 %** | −4.0 % (−21.5 … +53.2 %)  | **0.001** |
| fru/dsx+ (4,922) | P1    | 96.7 → 173.3 Hz       | +79 %      | +21.3 % (−10.3 … +89.7 %) | 0.011     |
| dimorphic (948)  | pIP10 | 87.8 → 141.1 Hz       | **+61 %**  | −4.3 % (−17.7 … +48.1 %)  | **0.001** |
| dimorphic (948)  | P1    | 96.7 → 158.9 Hz       | **+64 %**  | +9.9 % (−32.2 … +51.7 %)  | **0.001** |

**Verdict, by the pre-registered rule (both cases must pass):**

- **dimorphic: confirmed.** Silencing the 948 sexually dimorphic neurons raises dPR1 by
  61–64 % after either stimulus, more than any of 1,000 matched random silencings.
- **fru/dsx+: not confirmed.** The rise is as large (+79 … +100 %), but after P1 eleven of
  1,000 random silencings of ~4,900 superclass-matched neurons raised dPR1 as much or more
  (p 0.011, above the 0.00625 threshold). Silencing a fifth of the CNS moves dPR1 a lot by
  itself: the null mean is +21 % there. The effect is real but not specific to fru/dsx+.

Descriptive (not part of the 8 confirmatory tests): male-specific neurons (1,332/1,418)
change dPR1 by −2 % after P1 and −13 % after pIP10 (p 0.99, 0.015 for a drop); fru/dsx+
silencing lowers pIP10 after P1 by 12 % (p 0.001 for a drop), the one clear fall.
**Looming escape depends on none of the three categories**: silencing any of them moves
DNp01 by under 1 % and TTMn by −10 … +18 %, inside the null in every case (p 0.11 … 0.93).
The 1,000 draws confirm what the v0.5 run with 100 draws showed.

- **Enrichment is not necessity.** Courtship responses survive the loss of thousands of
  dimorphic neurons, because they run mostly through the direct P1 → pIP10 → dPR1 links,
  which stay intact (stimulus and targets are never silenced).
- The v0.5 run with 100 draws reported the same direction and sizes; what 1,000 draws add is
  the threshold, and they show that the fru/dsx+ effect does not clear it.
- With the v0.3 defaults (20 null draws) silencing the male-specific neurons lowered dPR1 by
  ~20 %; with the density-scaled model that effect is gone, so it is not robust.

## The predicted loop (`flymsg dimorphism --loop --null 1000`, `runs/loop-silencing.txt`)

Pre-registered test T2. Two sets are silenced: **dMS9** (2 neurons) and **the inhibitory
feedback** it drives (4 vPR9_a + 4 IN00A038). The null silences as many of the case's own
responders, matched on superclass and transmitter sign — a stricter comparison than random
neurons, since those are active neurons of the same kind.

| Silenced (n)          | Case  | dPR1, base → silenced | Change    | Null change, mean (range) | p         |
| --------------------- | ----- | --------------------- | --------- | ------------------------- | --------- |
| dMS9 (2)              | pIP10 | 87.8 → 146.7 Hz       | **+67 %** | −6.5 % (−16.5 … +5.1 %)   | **0.001** |
| dMS9 (2)              | P1    | 96.7 → 167.8 Hz       | **+74 %** | −8.7 % (−5.7 … +26.4 %)   | **0.001** |
| vPR9_a + IN00A038 (8) | pIP10 | 87.8 → 82.2 Hz        | −6 %      | +6.6 % (−27.8 … +110 %)   | 0.626     |
| vPR9_a + IN00A038 (8) | P1    | 96.7 → 127.8 Hz       | +32 %     | +12.1 % (−3.4 … +98.9 %)  | 0.036     |

**Verdict: partly supported.** dMS9 passes in both cases: silencing those two neurons raises
dPR1 by two thirds, far beyond silencing any 2 matched responders. The named inhibitors do
not: after pIP10 silencing them _lowers_ dPR1 (−6 %), and after P1 the rise stays inside the
null (p 0.036). **The second half of the v0.5 prediction is wrong**: dMS9 restrains dPR1, but
not through vPR9_a and IN00A038 as stated — or not only through them, since the null shows
that silencing 8 active VNC inhibitory neurons can raise dPR1 by up to 99 % on its own.

Descriptive: silencing both sets together gives +61 % (pIP10, p 0.012) and +75 % (P1,
p 0.001), close to dMS9 alone, which fits dMS9 being the part that matters. Silencing dMS9
also raises pIP10 itself after P1 (+14 %, p 0.001).

## Reading the two results carefully

- **The two categories overlap little.** Only 318 of the 948 sexually dimorphic neurons are
  also fru/dsx+, so the confirmed result is not a subset of the one that failed.
- **A category's size sets the power of its test.** Silencing ~4,900 superclass-matched
  random neurons raises dPR1 by +21 % on average, with draws up to +90 %: only a very large
  effect can clear that null, and fru/dsx+'s +79 % does not. The 948-neuron null moves dPR1
  by ±10 % at the median, which is why the same size of effect passes there. "Not confirmed"
  therefore means "not distinguishable from silencing that many neurons", not "no effect".
- **T2's inhibitory test is stringent by construction.** Its null silences 8 active VNC
  inhibitory responders, which on their own can raise dPR1 by up to 110 %. What sinks the
  prediction is not only the p value: after pIP10 silencing vPR9*a + IN00A038 \_lowers* dPR1,
  the opposite of what a feedback inhibitor should do.
- dPR1 is far from saturation (a 2.2 ms refractory period allows ~450 Hz), so the rises are
  not a ceiling artefact.

### Where the restraint comes from (post-hoc, found after T2, not yet tested)

Silencing dMS9 and looking at what changes gives a longer chain than the one v0.5 proposed.
The inhibitory input to dPR1 that collapses is **IN03B024** (2 GABAergic VNC neurons, 731 and
802 synapses onto dPR1): from 90 Hz to 29 Hz when dMS9 is silenced. Its drive comes from
**vMS12_a/b/c** (12 cholinergic fru+ neurons, a quarter of its excitatory input), which dMS9
drives with 4,054 / 1,028 / 1,480 synapses and which fall to 0 Hz without it:

**dPR1 →822→ dMS9 →6,562→ vMS12_a/b/c →1,458→ IN03B024 →1,533→ dPR1**

The v0.5 route (dMS9 →670→ vPR9_a →128→ dPR1) is thin next to this one, which fits T2's
rejection. This chain was found by looking at the result, so it is a hypothesis, not a
finding, and the numbers above are wiring and one descriptive comparison.

**T3, pre-registered for the next run** (fixed 2026-09-23, before running it; same protocol,
1,000 matched-responder null draws, threshold p ≤ 0.05/3 = 0.0167 for a rise of dPR1 after
pIP10 and after P1):

1. Silencing **IN03B024** (2 neurons) raises dPR1.
2. Silencing **vMS12_a + vMS12_b + vMS12_c** (12 neurons) raises dPR1.
3. Epistasis: silencing **dMS9 together with IN03B024** raises dPR1 no more than silencing
   IN03B024 alone (their 95 % bootstrap intervals overlap). If dMS9 acts through another
   route as well, this fails.

The chain is supported only if 1 and 2 pass in both cases and 3 holds; if 1 passes and 2
fails, the drive to IN03B024 comes from somewhere else; if 1 fails, IN03B024 is not the
route either.

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
vPR9_a (670 synapses from dMS9, 128 onto dPR1) and IN00A038 (161, 132). From that wiring
v0.5 predicted a disynaptic negative feedback loop, **dPR1 → dMS9 → vPR9_a / IN00A038 →
dPR1**. The pre-registered test T2 (above) keeps the first step and rejects the second:
silencing dMS9 raises dPR1 by two thirds, beyond any matched silencing, while silencing
vPR9_a and IN00A038 does not (it lowers dPR1 after pIP10). **What dMS9 restrains dPR1
through is an open question**; the two neurons named in v0.5 are not the answer, or not the
whole answer. AVLP717m (fru+) relays part of P1's drive to pIP10. These per-type numbers come
from a scan without a null and are indications, unlike T1 and T2.

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
