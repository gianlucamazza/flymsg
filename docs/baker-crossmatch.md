# Baker auditory neuron correspondence

Anatomical identity audit, 2026-10-17. No physiological response files were
opened, no benchmark was scored, and no manifest or model default changed.
The [M4 v2 proposal](m4-v2-proposal.md) remains a proposal.

## Result

The cited route is now complete for **12 of 28 Baker classes**, up from 2:
11 with unresolved sex compatibility, plus AVLP_pr36, which remains excluded
because its MaleCNS matches include dimorphic annotations. Fourteen classes
remain partial and two are absent from Table S3. No class is yet eligible for
physiological benchmarking.

Here, complete means that **every Table S3 reconstruction of the class** has an
anchored FlyWire v783 root, a published cell-type label and at least one named
MaleCNS type linked by an exact `flywireType` token. It does not mean that an
original Baker class is equivalent to one modern type. All one-to-many mappings
and individual body IDs remain in the evidence. In particular, B2 splits into
CB0090/CB0758, and AVLP_pr23 into AVLP598/WED193; do not pool their responses as
though they were single modern types.

| Baker class    | Reconstructions with a named MaleCNS route / listed | Identity coverage             | Named MaleCNS types                                                                |
| -------------- | --------------------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------------- |
| A2             | 2/2                                                 | complete                      | SAD097                                                                             |
| B1             | 110/117                                             | partial                       | 29 named types; see evidence                                                       |
| B2             | 6/6                                                 | complete                      | CB0090, CB0758                                                                     |
| WED-VLP        | 24/28                                               | partial                       | CB1206, CB2108, WED063_a, WED063_b, WED065, WED066                                 |
| AVLP_pr01      | 16/19                                               | partial                       | AVLP005, LHAV4d1, WED001                                                           |
| AVLP_pr02      | 0/6                                                 | partial                       | —                                                                                  |
| AVLP_pr04      | 4/4                                                 | complete                      | AVLP535, AVLP537, AVLP538                                                          |
| AVLP_pr05      | 25/25                                               | complete                      | AVLP481, AVLP483, AVLP484, AVLP485, AVLP486, AVLP560, CB1447, CL252, CL253, PLP160 |
| AVLP_pr11      | 14/15                                               | partial                       | AVLP166, AVLP168, AVLP175, AVLP179, AVLP188, CB2281, CB2458, CB2659, CB2660        |
| AVLP_pr12      | 13/13                                               | complete                      | CL062_a1, CL062_a2, CL062_b1, CL062_b2, CL062_b3                                   |
| AVLP_pr18      | 0/0                                                 | absent                        | —                                                                                  |
| AVLP_pr22      | 18/26                                               | partial                       | AVLP225_b1, AVLP225_b2, AVLP231, AVLP235, CB1187, CB2006, CB2041, CB2433, CB2623   |
| AVLP_pr23      | 2/2                                                 | complete                      | AVLP598, WED193                                                                    |
| AVLP_pr24      | 0/0                                                 | absent                        | —                                                                                  |
| AVLP_pr31      | 0/14                                                | partial                       | —                                                                                  |
| AVLP_pr32      | 0/3                                                 | partial                       | —                                                                                  |
| AVLP_pr35      | 2/2                                                 | complete                      | AVLP091                                                                            |
| AVLP_pr36      | 16/16                                               | complete; excluded: dimorphic | CB3269, aSP10A_a, aSP10A_b                                                         |
| AVLP/PVLP_pr01 | 8/9                                                 | partial                       | AVLP451, AVLP452, AVLP457, AVLP459, CB1498, CB2624                                 |
| GNG_pr01       | 8/9                                                 | partial                       | PVLP046                                                                            |
| IPS_pr01       | 8/9                                                 | partial                       | WED025, WEDPN1A                                                                    |
| IPS_pr02       | 2/2                                                 | complete                      | WED208                                                                             |
| IPS/WED_pr01   | 13/13                                               | complete                      | WED057                                                                             |
| PVLP_pr03      | 10/18                                               | partial                       | AVLP204, CB2676, PVLP034, PVLP047                                                  |
| SAD_pr01       | 2/2                                                 | complete                      | SAD107                                                                             |
| SAD_pr02       | 7/14                                                | partial                       | CB1065, CB1942, CB3024, SAD104                                                     |
| WED_pr01       | 11/11                                               | complete                      | CB1533, CB1818, WED089, WED091, WED093, WEDPN12                                    |
| WED_pr02       | 11/19                                               | partial                       | CB1948, CB2228, CB3245, SAD021_a, SAD021_b, SAD021_c, WED055_b                     |

The nine newly complete classes other than the dimorphic AVLP_pr36 are A2, B2,
AVLP_pr04, AVLP_pr05, AVLP_pr12, AVLP_pr23, IPS/WED_pr01, SAD_pr01 and WED_pr01.
AVLP_pr35 and IPS_pr02 retain their original complete routes.

Across 404 source reconstructions, 332 have named MaleCNS routes. Of the remaining
72, two have no FlyWire `cell_type` label, 63 have a label absent from MaleCNS
`flywireType` tokens, and seven link only to MaleCNS bodies without a `type` name.
These categories are mutually exclusive. AVLP_pr02, AVLP_pr31 and AVLP_pr32 have
no named MaleCNS route in this audit. AVLP_pr18 and AVLP_pr24 are absent from S3;
CAVE cannot supply identities that the source never lists.

## Method and independent checks

Sources:

- Baker et al. (2022), [paper](https://doi.org/10.1016/j.cub.2022.06.019),
  [Table S3, publisher workbook](https://ars.els-cdn.com/content/image/1-s2.0-S0960982222009782-mmc2.xlsx).
  Only the identity/coordinate table is used. Its two root-ID columns refer to
  synapse tables v11 and v274; those numbers are not the target annotation release.
- [FlyWire annotation tag v3.2.0](https://github.com/flyconnectome/flywire_annotations/tree/v3.2.0),
  `supplemental_files/Supplemental_file1_neuron_annotations.tsv`, associated with
  materialization 783. Cite [Schlegel et al. (2024)](https://doi.org/10.1038/s41586-024-07686-5)
  and [Berg et al. (2026)](https://doi.org/10.1016/j.cell.2026.08.015).
- MaleCNS v1.0 `data/neurons.parquet`, with `type`, `flywireType`, `dimorphism`
  and `fruDsx` independently checked against the original downloaded body
  annotation Feather: zero field differences. Input hashes are in the evidence.

The target is explicitly `flywire_fafb_public`, version **783**, timestamp
**2023-09-30T05:10:01.441140 UTC**. No query selects the latest release.

1. Read Table S3 identity cells directly from the workbook XML. Root IDs remain
   exact integer strings; they never pass through floating-point spreadsheet
   conversion. Select the 28 classes already in the proposal. B1-1 through B1-5
   and B1-u belong to the original B1 class; WED-VLP-1/2 belong to WED-VLP.
2. Sample each published FlyWire coordinate at its `[4, 4, 40]` nm voxel resolution
   from the static watershed segmentation, with agglomeration disabled. The
   downloaded volume advertises `[16, 16, 40]` nm resolution, so CloudVolume
   performs the coordinate conversion explicitly. Keep the resulting supervoxel.
3. Map each supervoxel to its root at the exact version-783 timestamp. Separately,
   query CAVE lineage for all **556 distinct historical root IDs** in the two
   source columns. Remove nodes after the target timestamp and require the
   anchor's root to be reachable from **both** source IDs. All 404 anchors agree.
   No split is resolved by selecting the first or largest descendant. Lineage
   without a coordinate anchor can include unrelated branches after old merges.
4. Join each anchored root to its v3.2.0 `cell_type`, then to exact, case-sensitive
   MaleCNS `flywireType` tokens, split only on comma or semicolon. Retain all male
   body IDs, types and dimorphism annotations. No synonym or fuzzy-name fallback.
5. Independently ask CAVE whether every anchored root is valid at the target
   timestamp: **404/404**. Map the **404 annotation-table supervoxels**, obtained
   independently of S3 coordinates, to roots at that timestamp: **zero mismatches**.
   The two previously complete classes reproduce their original mappings.

The transformation changes 243 v11 IDs and 156 v274 IDs. For **156/404** source
reconstructions, the v783 root equals neither original root ID. These counts
verify that the audit actually updated identities, rather than merely joining
unchanged source IDs.

The first raw binary root request returned an empty body because its content
type was unsuitable. A response-length assertion rejected it. The successful
request specifies `application/octet-stream`; the retained successful response
contains exactly 404 uint64 roots (3,232 bytes).

## Evidence and reproduction

- [Summary and input SHA-256 hashes](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/baker-crossmatch-2026-10-17.json).
- [Captured API responses, row-level identity results and offline replay](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/baker-crossmatch-2026-10-17.zip).

The archive contains identity metadata and analysis code, no response traces,
credentials, source workbooks, full annotation tables or segmentation volumes.
Download the original S3 and v3.2.0 annotations separately, and use the hashed
MaleCNS parquet. `replay.py` verifies input hashes, reconstructs the source rows
and both historical lineages, recomputes the joins, checks the independent CAVE
oracles and reconciles the counts. See the archive README for the exact command.

## Sex annotation audit (2026-10-18)

For the 11 complete classes other than AVLP*pr36, every one of the 126 matched
MaleCNS bodies has an empty `dimorphism`, and every one of the 82 anchored
materialization-783 roots is `isomorphic` in flywire_annotations v3.2.0. That
column was added in v3.0.0 from the MaleCNS comparison (Berg et al.,
[bioRxiv 2025](https://doi.org/10.1101/2025.10.09.680999), now
[Cell 2026](https://doi.org/10.1016/j.cell.2026.08.015)), whose isomorphic
category means no consistent \_morphological* sex difference. Neither paper's
retrieved text names these types. [`audit.py`](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/baker-sex-audit-2026-10-18/audit.py)
reproduces the counts from hashed inputs into
[`results.json`](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/baker-sex-audit-2026-10-18/results.json).

The female label does not clear the sex gate. It is the residual value of the
column, not a per-type comparison result: v3.2.0 has no empty `dimorphism`, and
1,528 `isomorphic` neurons have no `cell_type` at all, so they cannot have been
compared at type level (5,012 more typed ones match no MaleCNS `flywireType`
token). MaleCNS has no `isomorphic` value; its empty field means unflagged. Both
sides therefore say only "not flagged dimorphic", and morphology does not
establish physiological equivalence of female recordings and male neurons. The
11 classes keep **unresolved** sex compatibility. An explicit per-type statement
from the MaleCNS authors, or male recordings of the same types, would resolve it.

## Remaining limits

Empty sex annotations do not establish isomorphism. The completed routes other
than AVLP_pr36 have unannotated MaleCNS sex compatibility, so the female-recording
versus male-connectome gate stays open. AVLP_pr36 remains excluded.

Complete identity coverage also does not establish calcium-to-model readout
compatibility, the measured protocol-6 JO input, independence from model tuning,
or a prospective held-out partition. Those gates must be met and the manifest
locked before opening responses. Partial classes need their missing published
annotations or cross-connectome identities resolved; no arbitrary renaming is
introduced here.
