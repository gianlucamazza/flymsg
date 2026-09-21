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

| Case | Responders | fru/dsx+ | male-specific | dimorphic |
|---|---:|---|---|---|
| P1 courtship drive | 1,824 | **4.3×** (512) | **10.9×** (361) | **6.1×** (148) |
| pIP10 song pathway | 242 | **13.3×** (84) | **18.6×** (32) | **4.9×** (7) |
| looming escape | 1,087 | 0.40× (22) | 0.46× (7) | 1.3× (16), p 0.19 |
| sugar feeding | 360 | 0.44× (11) | 0 (0) | 0.51× (4) |
| giant fiber output | 2 | 0 | 0 | 0 |

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

| Case → target | fru/dsx+ (~4,900 silenced) | male-specific (~1,330) | dimorphic (948) | null, mean |
|---|---|---|---|---|
| P1 → pIP10 | −12 % (p 0.010) | +9 % | −3 % (p 0.04) | +5 … +12 % |
| P1 → dPR1 | **+79 %** | +2 % | **+64 %** | +11 … +22 % |
| pIP10 → dPR1 | **+100 %** | −13 % (p 0.03) | **+61 %** | −1 … −6 % |
| LC4_R → DNp01, TTMn | within the null | within the null | within the null | |

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

| Type silenced (neurons) | dPR1 after pIP10 | dPR1 after P1 | pIP10 after P1 |
|---|---|---|---|
| dMS9 (2) | **+67 %** | **+74 %** | +14 % |
| vPR9_a (4) / vPR9_c (3) | −9 % / — | +29 % / +38 % | +14 % / +21 % |
| vMS12_a (6) | +14 % | +39 % | +6 % |
| TN1a subtypes (1–4 each) | −1 … −15 % | +18 … +20 % | +3 … +4 % |
| AVLP717m (2) | — | −28 % | **−43 %** |

dMS9 (fru_high, sexually dimorphic, cholinergic; "Lillvis 2024: dMS9") receives 822 synapses
from dPR1 and gives it only 5. It drives two inhibitory neurons that project back onto dPR1:
vPR9_a (670 synapses from dMS9, 128 onto dPR1) and IN00A038 (161, 132). The model therefore
predicts a disynaptic negative feedback loop, **dPR1 → dMS9 → vPR9_a / IN00A038 → dPR1**,
that holds the song pathway back. AVLP717m (fru+) relays part of P1's drive to pIP10.
These are model predictions from wiring and predicted transmitters, open to experimental
test.

## Limits

- Annotations, not measurements: `fruDsx` and `dimorphism` are the release's best calls; the
  "potentially" levels are included.
- Enrichment says where the simulated activity goes; silencing tests necessity, with 100 null
  draws per category test and none for the per-type scan.
- The null matches superclass only, not transmitter or proximity to the stimulus.
