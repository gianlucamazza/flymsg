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
| `somaSide`            | `L`, `R` or missing                                                                                 |
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

## Citation

> Sexual dimorphism in the complete connectome of the _Drosophila_ male central nervous
> system. _Cell_ (2026). <https://www.cell.com/cell/fulltext/S0092-8674(26)00942-6>.
> Preprint: bioRxiv, doi:10.1101/2025.10.09.680999.

Take the author list from the _Cell_ article.
