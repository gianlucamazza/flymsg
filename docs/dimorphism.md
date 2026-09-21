# Dimorphism in the male model

`flymsg dimorphism` asks, for each validation case, whether the simulated response runs
through sexually dimorphic neurons more than expected. Code: `src/flymsg/dimorphism.py`.
Output: `runs/dimorphism.txt`.

## Method

- **Responders**: neurons other than the stimulated ones that fire during the 300 ms stimulus
  in ≥ 2 of 3 seeds (validation protocol, defaults `w_syn` 0.275, `th_jump` 2).
- **Categories** (MaleCNS annotations; "potentially …" included): `fru/dsx+` (any `fruDsx`
  value), male-specific, dimorphic (sexually or potentially dimorphic).
- **Null**: 1,000 random neuron sets of the same size and superclass mix as the responders,
  drawn from all non-stimulated neurons. Matching superclass matters: responders of a visual
  stimulus are mostly visual neurons, and dimorphic neurons are not spread evenly.
- **Statistic**: share among responders / mean null share, with an empirical one-sided p
  (+1 smoothing, so the smallest possible p is 0.001). 15 tests (5 cases × 3 categories):
  with Bonferroni, p ≤ 0.0033 is significant.

## Results

| Case               | Responders | fru/dsx+       | male-specific  | dimorphic         |
| ------------------ | ---------: | -------------- | -------------- | ----------------- |
| P1 courtship drive |      3,275 | **3.4×** (717) | **8.1×** (485) | **4.8×** (209)    |
| pIP10 song pathway |        285 | **11.3×** (88) | **16.3×** (35) | **5.8×** (10)     |
| giant fiber output |         29 | **7.5×** (5)   | 0 (0)          | 9.8× (2), p 0.017 |
| looming escape     |      2,206 | 0.44× (57)     | 0.48× (18)     | 1.2× (35), p 0.11 |
| sugar feeding      |        912 | 0.50× (25)     | 0.39× (5)      | 0.49× (7)         |

Bold: p = 0.001. Counts of responders in the category in brackets.

- **Courtship circuits run through the dimorphic network.** P1 and pIP10 responses are 3–16×
  enriched in fru/dsx+, male-specific and dimorphic neurons, within their superclasses. This is
  the model's side of the known picture: P1 and pIP10 sit in the fruitless circuit that
  builds courtship song.
- **Escape and feeding avoid it.** Looming and sugar responses contain about half the
  expected share of fru/dsx+ and male-specific neurons.
- **The giant fiber recruits fru+ wing motor neurons.** Its 5 fru/dsx+ responders are wing
  motor neurons (hg1 left and right, hg3, ps1 left and right, all `fru_high`; hg1 also
  dimorphic): the escape pathway reaches the wing motor system, which in males also produces
  song. With 29 responders this rests on few neurons.

## Limits

- Annotations, not measurements: `fruDsx` and `dimorphism` are the release's best calls; the
  "potentially" levels are included.
- Enrichment says where the simulated activity goes, not that dimorphic neurons are needed:
  that would take silencing experiments in the model.
- The null matches superclass only, not transmitter or proximity to the stimulus.
