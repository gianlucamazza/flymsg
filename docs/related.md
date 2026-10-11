# Related work

flymsg asks whether the measured MaleCNS wiring, under the fixed LIF model of Shiu et al.
(_Nature_ 2024; parameters in [model](model.md#parameters)), recruits circuits whose function
is known from experiments. The checks are criterion v4 in [validation](validation.md#protocol).
Integration stays at `dt` = 0.1 ms.

## MaleCNS counts

Berg et al. (_Cell_ 2026, doi:10.1016/j.cell.2026.08.015) released MaleCNS v1.0. The
annotation table holds **211,577** bodies. `flymsg build` keeps the **165,122** with
`status == "Traced"` and the edges between them: 25,563,197 connections and 124,025,046
synapses. The dropped bodies are orphans, glia, fragments and unassigned segments. Both
rows are the compaction table in [data](data.md#compaction-flymsg-build).

## BANC

Bates et al. (_Nature_ 2026, doi:10.1038/s41586-026-10735-w) map one female central nervous
system, brain and ventral nerve cord together (BANC). The paper reports **150,841** neurons
brought to backbone-proofread status. That count was read from the article's methods.

flymsg has no BANC loader. Sex comparisons stay on MaleCNS against FlyWire FAFB, as in
[comparison](comparison.md).

## A body on the same wiring

Vaxenburg et al. (_Nature_ 2025, doi:10.1038/s41586-025-09029-4) publish a whole-body
_Drosophila_ in MuJoCo. FlyBody (TuragaLab) is the open-source model:

<https://github.com/TuragaLab/flybody>

## N1 — specific checks need the measured partners

Fixed 2026-10-10, before the confirmatory comparison. The census below is that one
permutation. The comparison was run on 2026-10-11. The same seed was run again the same
day so the five passing rows could be named; the census and the pass counts matched.

The question is whether criterion v4's `specific` checks still pass when each neuron keeps
its degree and its outgoing weights but loses its measured partners. One shuffle, on the
traced MaleCNS graph (`data/edges.parquet` after `build`), same default model (`w_syn`
0.192 mV per synapse, `th_jump` 0), criterion v4, seeds 0, 1 and 2.

**Shuffle.** Permute the `post` column (`wiring.shuffle_targets`, numpy `Generator.permutation`,
seed **0**). Weights stay on the presynaptic side, so each neuron keeps its out-degree and
the multiset of its outgoing weights. The multiset of `post` ids is unchanged, so the
multiset of in-degrees is unchanged. The sign of an edge is the presynaptic transmitter, so
it stays with `pre`. Self-loops and duplicate `(pre, post)` pairs are counted and kept. The
simulator sums the weights of a duplicate pair into one matrix entry. One shuffle. No second
seed is drawn after the first is seen. No p-value. There is no flag for another seed, another
`w_syn`, or another `th_jump`.

`flymsg wiring-null --stats` prints that census and does not simulate. On the traced
MaleCNS graph, seed 0 gives **423** self-loops and **84,560** duplicate pairs (87,365 extra
edges) among 25,563,197 edges. `flymsg wiring-null` runs this comparison on one core.

**Confirmatory rule.** Every `specific` check that passes on the real graph fails on the
shuffle. A `specific` check that still passes is a finding: under this null that case does
not depend on who connects to whom. `w_syn` is not retuned. On the shuffle, `positive`,
`order`, `dose` and `stability` are reported and not scored.

**Result** (2026-10-11, `flymsg wiring-null`, one core). The real graph passes **29/29**.
The shuffle passes **5/29**, and those five are the `stability` check of every case:
self-sustained activity still dies out. All **7/7** `specific` checks fail on the shuffle,
so the confirmatory rule holds. `positive`, `order`, `dose` and `negative` fail on the
shuffle as well. `w_syn` stays 0.192. The permutation was not replaced.

Multi-draw families (degree-preserving, cell-type-preserving, weight-within-type, sign)
are a separate protocol. They do not replace this one-draw comparison. See
[nulls](nulls.md).

## Already open

T3 was run on 2026-10-11. The chain is supported; the counts and p-values are in
[dimorphism](dimorphism.md). T4 was run the same day: silencing AVLP717m drops pIP10
after P1 (p = 0.001). This note does not restate the rules.
