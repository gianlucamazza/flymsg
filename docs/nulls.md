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

Numbers come only from a run on the named dataset. They are not copied from
elsewhere. The confirmatory MaleCNS v1.0 table lives in `runs/nulls/report.txt`
next to that run's manifest. A short copy is recorded in the
[findings log](validation.md#findings-log) after the run.

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
