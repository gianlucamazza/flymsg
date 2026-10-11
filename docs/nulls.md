# Null families

`flymsg nulls` asks which pre-registered pathway weights depend on the measured
partners, the type-to-type counts, the weight assignment, or the transmitter
signs. It is a separate protocol from N1 (`flymsg wiring-null`): N1 is one
degree-preserving shuffle and the full criterion v4 battery. This command does
not redraw that shuffle and does not retune `w_syn`.

The hypotheses, metrics, thresholds, families, tails and draw counts are locked
in [`validation/preregistration.yaml`](../validation/preregistration.yaml)
before a confirmatory run. A run whose config differs from that file fails
unless the file version is bumped. Code: `src/flymsg/nulls.py`.

## Why

A connectome-constrained model can match a known circuit for reasons that do not
need the measured wiring: degree sequences, cell-type totals, weight
distributions, or the balance of excitation and inhibition can be enough.
Brunton et al. (2026) show that behavioural agreement can occur without
biological fidelity. Bargmann (2012) sets the broader limit: a wiring diagram
does not by itself determine function. The families below destroy one of those
structures at a time and keep the rest.

## Families

Each family is a seeded draw. Seeds are `0 .. n-1`. Draw 0 of
`degree_preserving` is the same permutation as N1 (`wiring.shuffle_targets`,
numpy `Generator.permutation`). That one-draw battery result is not replaced.

| Family                 | What is destroyed                         | What is kept                                                            | Method                                                     |
| ---------------------- | ----------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------- |
| `degree_preserving`    | who connects to whom                      | each neuron's out-weights; the multiset of in-degrees                   | permute `post` (configuration model)                       |
| `cell_type_preserving` | which neuron of a type receives each edge | type-to-type synapse counts; individual in-degrees; out-weights         | permute `post` inside each postsynaptic cell type          |
| `weight_within_type`   | which edge of a type carries which weight | every `(pre, post)` pair; each presynaptic type's weight multiset       | permute `weight` among outgoing edges of the same pre type |
| `sign`                 | which fast-transmitter neuron is + or −   | topology; weights; neurons with sign 0 (modulators / unknown) stay at 0 | permute the non-zero `sign` column                         |

`degree_preserving` is the configuration-model permutation already used for N1,
after Maslov and Sneppen (2002) and Newman (2003). `cell_type_preserving` is
that model applied inside each postsynaptic cell type, so the type-to-type
block structure stays (Newman 2003). `weight_within_type` and `sign` follow the
weight-preserving and signed-network randomizations described by Rubinov and
Sporns (2010), restricted to a cell type or to neurons that already have a fast
sign.

## Score

For each locked pathway (the seven `specific` checks and the bitter negative
case) the score is the signed synaptic weight from the stimulated neurons onto
that target type: `sum_e weight_e * sign[pre_e]` for edges with `pre` in the
stimulus and `post` of the target type. Two summaries are always reported:

- **sum** — total onto the type. Invariant under `cell_type_preserving`.
- **max** — the largest onto a single neuron of the type. Changes when partners
  inside the type are swapped.

The family headline, fixed before the run, is the sum of **max** over the seven
specific pathways (upper tail: the real wiring is stronger than the null) and,
separately, bitter **sum** (lower tail: the real wiring is weaker). Every
pathway is printed. None is dropped after the draws are seen.

Empirical _p_ uses the same +1 smoothing as the silencing tests
([dimorphism](dimorphism.md)): _p_ = (1 + number of nulls as or more extreme) /
(1 + _n_). With _n_ draws the smallest _p_ is 1/(1+_n_). _z_ is (real − null
mean) / null s.d. (*n*−1); if the nulls have no spread, _z_ is 0 when the real
value matches them and omitted otherwise.

This is a graph score, not a rerun of the 29 criterion v4 checks. N1 remains
the one-draw battery comparison.

## Draw counts

| Mode          | Draws per family | How                   |
| ------------- | ---------------: | --------------------- |
| CI / default  |                2 | `flymsg nulls`        |
| Full protocol |               20 | `flymsg nulls --full` |

`--draws` must be one of those two values unless `--exploratory` is set. The
default keeps CI and a local `pytest` run fast. The full command is the
confirmatory one.

```bash
flymsg nulls --full --out runs/nulls
```

Each run writes `report.txt`, one CSV per family and metric, and
`manifest.json` (git commit, dataset hashes, config, seeds, package versions,
platform, timestamps).

## Results

Dataset: MaleCNS v1.0 after `flymsg build` (165,122 neurons, 25,563,197 edges).
Draws: **20** per family, seeds 0–19. `w_syn` 0.192, `th_jump` 0. Manifest
dataset hashes: `neurons.parquet`
`7ec0020f08495c35398deafa3183292dfb489ce6717d889b80cfcc11cb757c7c`,
`edges.parquet`
`2da9fe967204ad330d0576a25723e8c74fdc8b77e7806ccf7297a4f5189ee67a`.
Smallest possible _p_ is 1/21 ≈ 0.0476.

Real signed stim → target weights (one-hop):

| Pathway           |  sum |  max |
| ----------------- | ---: | ---: |
| LC4_R → DNp01     | 2580 | 2580 |
| LC4_R → TTMn      |    0 |    0 |
| DNp01 → TTMn      |   90 |   70 |
| P1 → pIP10        | 1537 |  812 |
| P1 → dPR1         |    0 |    0 |
| pIP10 → dPR1      | 1112 |  615 |
| sugar GRNs → MN9  |    0 |    0 |
| bitter GRNs → MN9 |    0 |    0 |

Headline (sum of the seven specific `max` values = 4077; bitter `sum` = 0):

| Family                 | real | null mean | null s.d. | _p_ (upper) |   _z_ |
| ---------------------- | ---: | --------: | --------: | ----------: | ----: |
| `degree_preserving`    | 4077 |     21.40 |     21.30 |        1/21 | 190.4 |
| `cell_type_preserving` | 4077 |    3196.3 |     256.3 |        1/21 |  3.44 |
| `weight_within_type`   | 4077 |    679.75 |    107.64 |        1/21 |  31.6 |
| `sign`                 | 4077 |    1314.3 |     419.0 |        1/21 |  6.59 |

Bitter `sum` is 0 on the real graph and is not below the nulls (_p_ = 0.86
under degree-preserving; 1.0 under the other three). Those rows have no
one-hop signed weight.

`cell_type_preserving` leaves every **sum** unchanged (_p_ = 1), as the
method requires. The headline still moves because **max** can move inside a
type: LC4*R → DNp01 max 2580 vs null mean 1447.45 (\_p* = 1/21, _z_ = 8.69).
DNp01 → TTMn max 70 is below the null mean 82.00 (_p_ = 1, _z_ = −1.19).
pIP10 → dPR1 max 615 is below the null mean 811.70 (_p_ = 1, _z_ = −1.24).
P1 → pIP10 max 812 vs 855.15 (_p_ = 14/21, _z_ = −0.62). All eight pathways
are in the command output; none were dropped.

Pathways with real weight 0 (LC4_R → TTMn, P1 → dPR1, sugar → MN9, bitter →
MN9) cannot stand out on this one-hop score. Their criterion v4 `specific`
checks, when they pass, run through more than one hop. N1 remains the
battery comparison for those.

The full per-pathway tables are in the findings log.

## References

- Bargmann, C. I. Beyond the connectome: how neuromodulators shape neural
  circuits. _BioEssays_ 34, 458–465 (2012). doi:10.1002/bies.201100185
- Brunton, B. W. et al. The digital sphinx: Can a worm brain control a fly
  body? _bioRxiv_ (2026). doi:10.64898/2026.03.20.713233
- Maslov, S. & Sneppen, K. Specificity and stability in topology of protein
  networks. _Science_ 296, 910–913 (2002). doi:10.1126/science.1065103
- Newman, M. E. J. The structure and function of complex networks. _SIAM
  Review_ 45, 167–256 (2003). doi:10.1137/S003614450342480
- Rubinov, M. & Sporns, O. Complex network measures of brain connectivity:
  uses and interpretations. _NeuroImage_ 52, 1059–1069 (2010).
  doi:10.1016/j.neuroimage.2009.10.003
- Shiu, P. K. et al. A _Drosophila_ computational brain model reveals
  sensorimotor processing. _Nature_ 634, 210–219 (2024).
  doi:10.1038/s41586-024-07763-9
