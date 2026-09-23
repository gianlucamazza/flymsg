# Data

## Source

flymsg uses the **MaleCNS v1.0** connectome of an adult male _Drosophila melanogaster_, the
first complete central nervous system (central brain, optic lobes and ventral nerve cord),
produced by the Janelia FlyEM project team with Google Research, the MRC Laboratory of
Molecular Biology and the University of Cambridge.

- Project page: <https://janelia-flyem.github.io/male-cns/>
- Imaging: focused ion beam scanning electron microscopy (FIB-SEM), 8 nm isotropic voxels
- Segmentation: Google flood-filling networks, then proofread at Janelia and Cambridge
- Release: v1.0, June 2026 (v0.9: October 2025)
- License: [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/). Any published use must
  cite the dataset (see [Citation](#citation)).

## Files

`flymsg fetch` downloads three Apache Arrow Feather tables from
`gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/` (served over HTTPS) into
`data/raw/`. No neuPrint account or token is needed.

| File                                                   |    Size | Content                                                                             |
| ------------------------------------------------------ | ------: | ----------------------------------------------------------------------------------- |
| `body-annotations-male-cns-v1.0-minconf-0.5.feather`   |   14 MB | 211,577 bodies: type, instance, class, side, status, dimorphism, fru/dsx, synonyms… |
| `body-neurotransmitters-male-cns-v1.0.feather`         |   43 MB | predicted transmitter per body (`consensus_nt` is used)                             |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 1.05 GB | 151.9M segment-to-segment edges with synapse counts                                 |

`minconf-0.5` means synapses detected with confidence ≥ 0.5, the threshold used by the
release. Other tables on the download page (synapse points, 12.7 GB; skeletons; EM volumes)
are not used.

## Compaction (`flymsg build`)

`build` keeps bodies with `status == "Traced"` and edges whose two ends are both traced.

|                  |         Raw |        Kept |
| ---------------- | ----------: | ----------: |
| Bodies / neurons |     211,577 |     165,122 |
| Edges            | 151,856,684 |  25,563,197 |
| Synapses         | 311,833,243 | 124,025,046 |

The dropped bodies are orphans, glia, fragments and unassigned segments. Most of the raw
synapse total sits between those fragments: traced neurons receive 130.4M input synapses,
and **95.1%** of them come from other traced neurons. The compacted graph therefore keeps
almost all of the input to the neurons it models.

Reproduce: `flymsg build` prints the kept counts; the 95.1% comes from summing
`connectome-weights` rows whose `body_post` is traced, split by whether `body_pre` is traced.

## Schema

Row position is the neuron index used everywhere (`edges.pre`/`edges.post`, `sim` arrays).
Neurons are sorted by `bodyId`.

`data/neurons.parquet`

| Column                | Meaning                                                                                             |
| --------------------- | --------------------------------------------------------------------------------------------------- |
| `bodyId`              | FlyEM body ID (use it in neuPrint and Neuroglancer)                                                 |
| `type`, `instance`    | cell type (`LC4`) and side-specific instance (`LC4_R`); may be missing                              |
| `superclass`, `class` | coarse grouping (`descending_neuron`, `vnc_motor`, `Kenyon_Cell`…)                                  |
| `subclass`            | finer grouping (`labellar bristle`, `pharyngeal sensillum`…)                                        |
| `somaSide`            | `L`, `R` or missing (sensory neurons have no soma in the CNS: use `instance`)                       |
| `entryNerve`          | nerve through which a sensory neuron enters (`MxLbN`, `PhN`…)                                       |
| `receptorType`        | putative receptor (752 leg/wing gustatory neurons only; no Gr labels)                               |
| `flywireType`         | matching FlyWire FAFB cell type, the key for male ↔ female comparisons                              |
| `dimorphism`          | `male-specific`, `sexually dimorphic`, `potentially …`, or missing                                  |
| `fruDsx`              | fruitless/doublesex expression class                                                                |
| `synonyms`            | names used in earlier literature (used to select P1 neurons, see validation)                        |
| `nt`                  | `consensus_nt`: acetylcholine, glutamate, gaba, histamine, dopamine, octopamine, serotonin, unclear |
| `sign`                | +1 excitatory, −1 inhibitory, 0 no fast effect (see [model](model.md#synapse-sign))                 |

`data/edges.parquet`: `pre`, `post` (neuron indices, int32), `weight` (synapse count, int32).

## Known data limits

- **One animal**: no measure of variability between individuals.
- **Chemical synapses only**: gap junctions are invisible to EM at this resolution, so
  electrical pathways (e.g. Giant Fiber → PSI) are missing or underweighted.
- **Predicted transmitters**: `consensus_nt` is a machine prediction. 502 traced neurons have
  none and 3,100 are `unclear`.
- **Missing names**: 2,605 traced neurons have no type and 7,040 no instance.
- **Incomplete neurons**: 3.2 % of bilateral types have one side far below the other (see
  [Reconstruction completeness](#reconstruction-completeness-flymsg-audit-runsaudittxt)).

## Reconstruction completeness (`flymsg audit`, `runs/audit.txt`)

Proofreading can leave a neuron incomplete, and a bilateral pair makes it visible: the two
sides should carry similar synapse counts. `flymsg audit` compares, for each of the 11,095
cell types with neurons on both sides (side from the instance suffix), the median input
synapses of the right and left neurons, and scores log2(R/L) against all types with a robust
z-score (median/MAD). Across types the 5–95 % range of log2(R/L) is −0.47 … 0.53; 355 types
(3.2 %) are flagged at |z| > 3. For the neurons behind flymsg's results it also reports the
share of each neuron's input that comes from traced partners, and the same pair's asymmetry
in FAFB where the type is matched.

| Neurons behind results                              | log2(R/L)   | z        | Verdict                                                                                                                                                              |
| --------------------------------------------------- | ----------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **MN9** (6,012 vs 556 input synapses)               | −3.43       | −12.8    | **flagged**: 13th most asymmetric type in the CNS; symmetric in FAFB (CB0701, −0.08). MN9_R is most likely incompletely reconstructed                                |
| **LB3c** (99.5 vs 254)                              | 1.34        | 4.9      | **flagged**: right sugar GRNs carry 2.5× the input and 1.4× the output of the left ones; in FAFB the LB3 imbalance goes the other way (−0.97)                        |
| LB1d (1 vs 4 neurons)                               | −0.80       | −3.1     | flagged, on a single left neuron                                                                                                                                     |
| LB3b, TTMn                                          | 0.62, 0.57  | 2.2, 2.0 | not flagged                                                                                                                                                          |
| DNp01, pIP10, dPR1, dMS9, all pC1 (P1), LC4, LB1a–c | −0.4 … 0.45 | < 1.6    | symmetric. Input from traced partners: pIP10, dPR1, dMS9, pC1, LC4 ≥ 95 %; DNp01 83–86 %; gustatory neurons 60–81 % (much of their input lies on untraced fragments) |

The audit sees totals, not single connections: GF → TTMn has 70 synapses on the right and 20
on the left while both GF and TTMn totals are symmetric, an asymmetry it cannot attribute.
**Rule:** a result that hinges on a flagged neuron must say so; where a bilateral pair is
flagged, flymsg reads the side that is not.

## Female brain: FlyWire FAFB v783 (`--dataset fafb`)

`flymsg --dataset fafb fetch` and `build` write the female brain to `data/fafb/` in the same
schema, for the comparisons in [comparison.md](comparison.md). Sources, pinned to commits:

| File                                        |   Size | Source                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------- | -----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Connectivity_783.parquet`                  | 101 MB | Shiu et al. model repository, commit `91bdd1e` (MIT): 15.1 M connections, synapse counts and the model's signs                                                                                                                                                                                                     |
| `Completeness_783.csv`                      | 3.3 MB | same: the 138,639 neurons of the model                                                                                                                                                                                                                                                                             |
| `Supplemental_file1_neuron_annotations.tsv` |  32 MB | flyconnectome/flywire_annotations, commit `8587524`: cell types, classes, side, nerve, `dimorphism`, `fru_dsx`, top transmitter. No licence file; the repository asks to cite Berg et al. 2025 (the MaleCNS paper, cited from its preprint), Schlegel et al. 2024, Matsliah et al. 2024 and Dorkenwald et al. 2024 |

Mapping: `type` = `cell_type` (also `flywireType`), `instance` = type + side, `superclass`
= `super_class`, `class` = `cell_class`, `subclass` = `cell_sub_class`, `entryNerve` = `nerve`,
`fruDsx` = `fru_dsx`, `nt` = `top_nt`. `sign` follows the same transmitter map as MaleCNS;
`shiu_sign` keeps the published model's own signs (it treats dopamine, serotonin and
octopamine as ±1 and used other transmitter predictions: the two differ for 14,515 neurons),
so that the model can be reproduced exactly.

FAFB is **brain only** (no VNC) and **one female**. Shiu et al. used FlyWire v630; of their 21
sugar GRN IDs, 20 still exist in v783. The published model's side labels are mirrored with
respect to the FlyWire `side` column: its "sugarR" GRNs are annotated `left` and its "MN9
left" is `CB0701_R`.

## Citation

> Berg, S. et al. Sexual dimorphism in the complete _Drosophila_ male central nervous system
> connectome. _Cell_ 189, 5504–5526 (2026). doi:10.1016/j.cell.2026.08.015.
> Preprint (different title: "Sexual dimorphism in the complete connectome of the _Drosophila_
> male central nervous system"): bioRxiv, doi:10.1101/2025.10.09.680999.

Take the full author list from the _Cell_ article.

For `--dataset fafb` (FlyWire), as the sources ask, also cite:

- Dorkenwald, S. et al. Neuronal wiring diagram of an adult brain. _Nature_ 634, 124–138
  (2024). doi:10.1038/s41586-024-07558-y
- Schlegel, P. et al. Whole-brain annotation and multi-connectome cell typing of
  _Drosophila_. _Nature_ 634, 139–152 (2024). doi:10.1038/s41586-024-07686-5
- Matsliah, A. et al. Neuronal parts list and wiring diagram for a visual system. _Nature_
  634, 166–180 (2024). doi:10.1038/s41586-024-07981-1
- Shiu, P. K. et al. (2024), for the model's connectivity and signs (see
  [validation](validation.md#references)).
- Berg et al., the MaleCNS paper above, for the `dimorphism` and `fru_dsx` annotations.
