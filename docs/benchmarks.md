# Held-out benchmarks

Issue #7 asks for circuits that were not used to choose the model, and for a
sensitivity check that is not a retune. This note freezes that partition on
2026-10-11, before any held-out simulation. The lock is
[`validation/benchmarks.yaml`](../validation/benchmarks.yaml) (version 1). Changing a
held-out case, a check, or a sensitivity corner requires a new version. Criterion v4
stays the baseline: `flymsg validate` is unchanged, and N1 is not redrawn.

`flymsg benchmarks` prints the frozen confirmatory case. It does not simulate.

## Inventory

Counts are bodies with that cell type in MaleCNS v1.0 (165,122 traced neurons,
CC-BY 4.0). No new recording dataset is downloaded. A **recording** claim is about
spikes or synaptic drive. A **behavioral proxy** is about what the fly does, and is
not turned into a firing rate.

| Candidate            | Primary source                             | Observable                                      | Kind              | Role                    |
| -------------------- | ------------------------------------------ | ----------------------------------------------- | ----------------- | ----------------------- |
| ORN_DM1 → DM1_lPN    | Couto et al. 2005; Kazama & Wilson 2008    | this glomerulus's ORNs recruit its PN (74 → 2)  | recording         | held-out, confirmatory  |
| ORN_V → V PNs        | Suh et al. 2004; Jones et al. 2007         | V ORNs recruit V_ilPN and V_l2PN (55 → 2 and 2) | recording         | held-out, reported      |
| v4 battery           | [validation](validation.md)                | the six cases that chose `w_syn`                | mixed             | calibration             |
| LPLC2 → DNp01        | von Reyn et al. 2014; Ache et al. 2019     | LPLC2 also drives the giant fiber               | recording         | exploratory             |
| LB3a → MN9           | Tastekin et al. 2025                       | water GRNs and proboscis extension              | behavior          | exploratory             |
| LB3d → MN9           | Tastekin et al. 2025                       | high salt, sign depends on concentration        | behavior          | exploratory, not scored |
| LC4 via DNp02, DNp11 | `path --alt` already lists these routes    | other chemical routes from LC4 to TTMn          | graph             | exploratory             |
| GF → DLMn            | Blagburn et al. 1999; Allen & Murphey 2007 | DLM spike; the chemical path reached 4.4 Hz     | recording         | exploratory, excluded   |
| vPR6, vMS11          | [validation](validation.md)                | stay silent under pIP10                         | model observation | exploratory             |
| pCd persistence      | findings log, after P1                     | P1/pCd activity that outlasts the stimulus      | literature state  | exploratory             |
| MDN                  | Bidaye et al. 2014                         | backward walking; MDN is 4 neurons              | behavioral proxy  | not scored              |
| T4 / T5              | Maisak et al. 2013                         | direction selectivity to a moving bar           | recording         | not scored              |
| DN1pA                | type is present (8 neurons)                | circadian phase                                 | hours             | not scored              |

The v4 cases, the silencing tests T1–T4, N1 and the null families are calibration or
already-reported results. They are not held-out. LPLC2 is named in the looming case's
own evidence sentence. LB3a and LB3d were compared by connectivity when the sugar set
was chosen, and MN9 is the calibration readout. The alternate LC4 routes were
enumerated by `path`. GF → DLMn, vPR6, vMS11 and pCd were already inspected. MDN has
no single recorded motor target in the manifest. T4/T5 need a moving bar, and this
simulator's stimulus is a Poisson rate on a whole type. DN1pA acts over hours, outside
a 600 ms run.

## Confirmatory test

One case: stimulate **ORN_DM1** and score **DM1_lPN**. Couto, Alenius and Dickson
(2005) place Or42b ORNs in DM1. Kazama and Wilson (2008) show that ORNs of a
glomerulus drive that glomerulus's PN through an identified excitatory synapse. The
claim is that recruitment, not an odor preference and not a published firing rate.
Kazama and Wilson used odor puffs. This stimulus is 100 Hz Poisson for 300 ms, so a
rate in hertz is reported and is not matched to those papers.

The case passes only when all three hold, at seeds 0–2, control seed 0, `w_syn`
0.192, `th_jump` 0. The numbers are criterion v4:

1. **positive.** The best DM1_lPN fires at least 3 spikes in the 300 ms window in at
   least 2 of 3 seeds.
2. **specific.** Its rate is at least 3 times the class-matched control plus 2 Hz.
3. **stability.** At most 100 neurons still fire from 400 ms to 600 ms.

Order and dose are not endpoints. There is one confirmatory case, so the three checks
are simply all required. Adding a case later is a new version.

**ORN_V → V_ilPN and V_l2PN** is the same kind of claim for the CO2 receptor
population (Suh et al. 2004; Jones et al. 2007). Both targets are reported. The case
does not decide, and it does not score CO2 avoidance.

## Sensitivity

Parameter uncertainty and stimulus-seed variation are separate. The seeds above are
the stimulus variation. The parameter corners are three published points, not a
search:

| Corner       | `w_syn` | `th_jump` | Role                            |
| ------------ | ------: | --------: | ------------------------------- |
| default      |   0.192 |         0 | the scored case                 |
| Shiu weight  |   0.275 |         0 | FAFB weight, adaptation off     |
| adaptation A |   0.192 |         2 | the weight chosen in 2026-09-22 |

The scored claim uses only the default. Another corner that flips a pass into a
failure, or a failure into a pass, is reported. No corner replaces the default.

Edge confidence is not varied: the build uses one table, synapses at confidence
≥ 0.5. The sign shuffle is the null-family protocol, not this one. Transmitter labels
stay the release's `consensus_nt`.

## What a result may say

A pass says that, under this stimulus and these three checks, DM1_lPN is recruited by
ORN_DM1 beyond a class-matched control, and the network does not run away. It does not
say that the model smells, that the rate matches an odor recording, or that `w_syn`
should move. A failure is a finding. The v4 battery remains the baseline comparison.

## References

- Ache, J. M. et al. _Current Biology_ 29, 1073–1081 (2019). doi:10.1016/j.cub.2019.01.079
- Allen, M. J. & Murphey, R. K. _European Journal of Neuroscience_ 26, 439–445 (2007).
  doi:10.1111/j.1460-9568.2007.05686.x
- Bidaye, S. S. et al. Neuronal control of _Drosophila_ walking direction. _Science_ 344,
  97–101 (2014). doi:10.1126/science.1249964
- Blagburn, J. M. et al. _Journal of Comparative Neurology_ 404, 449–458 (1999). PMID 9987990
- Couto, A., Alenius, M. & Dickson, B. J. Molecular, anatomical, and functional organization
  of the _Drosophila_ olfactory system. _Current Biology_ 15, 1535–1547 (2005).
  doi:10.1016/j.cub.2005.07.034
- Jones, W. D. et al. Two chemosensory receptors together mediate carbon dioxide detection
  in _Drosophila_. _Nature_ 445, 86–90 (2007). doi:10.1038/nature05466
- Kazama, H. & Wilson, R. I. Homeostatic matching and nonlinear amplification at identified
  central synapses. _Neuron_ 58, 401–413 (2008). doi:10.1016/j.neuron.2008.02.030
- Maisak, M. S. et al. A directional tuning map of _Drosophila_ elementary motion detectors.
  _Nature_ 500, 212–216 (2013). doi:10.1038/nature12320
- Suh, G. S. B. et al. A single population of olfactory sensory neurons mediates an innate
  avoidance behaviour in _Drosophila_. _Nature_ 431, 854–859 (2004). doi:10.1038/nature02980
- Tastekin, I. et al. _bioRxiv_ (2025). doi:10.1101/2025.08.25.671814
- von Reyn, C. R. et al. _Nature Neuroscience_ 17, 962–970 (2014). doi:10.1038/nn.3741
