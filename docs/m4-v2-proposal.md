# M4 version-2 held-out benchmark proposal

Status: proposal, 2026-10-17. Not a lock; nothing here is scored.

Scope: M4 ([#36](https://github.com/gianlucamazza/flymsg/issues/36)),
[S3](milestones.md#s3-prospective-independent-physiological-and-behavioral-tests-p0).
This proposes eligibility for a later manifest, not a new experimental result.

## Why a v2 is needed

The [v1 manifest](../validation/benchmarks.yaml) has no unused scored case left.
Its only scored held-out case, ORN_DM1 → DM1_lPN, ran and failed specificity and
stability. ORN_V is reported only and does not decide. No exploratory row in the
[benchmark inventory](benchmarks.md#inventory) is promoted. A new source must not
have selected the model. The [completion plan](roadmap.md#completion-plan) requires
a pass against untouched animal observations; a no-go does not close M4.

## Eligibility rules

All must hold, with the rules written before any candidate response data are opened:

- Independent animal observations, unused to build or tune flymsg.
- Cells identified in MaleCNS through a cited cross-match. Name similarity,
  resemblance and an authored mapping do not establish identity.
- Sex compatible with the male connectome, or an explicit non-dimorphic annotation
  for the matched type. An empty annotation is not evidence of non-dimorphism.
- An admissible measured model input under the entry protocols. An auditory case
  requires protocol 6's measured band-pass or carrier-tuned input on exactly
  MaleCNS JO-A, JO-B and JO-D. That input does not yet exist.
- Prediction, observable, metric, null, simpler-model baseline and pass/fail rule
  fixed and hashed before opening responses. S0 must qualify the observable;
  required S1/S2 interfaces must be evidenced. Freeze trial handling, thresholds,
  seeds and no-go/indeterminate rules too.
- A licence permitting the intended analysis.

## Candidates assessed

These are feasibility findings from the supplied entry-protocol search and type
match analysis, without opening response files. No candidate is eligible now.

| Source | Evidence and limits | Verdict |
| --- | --- | --- |
| [Baker et al. 2022](https://doi.org/10.1016/j.cub.2022.06.019) | 24 new WED/VLP types plus A2, B1, B2 and WED-VLP: 28 consistently responding classes. Princeton deposit 10.34770/7zem-x425: CC BY-NC-ND 4.0, 3 files, about 2.3 MB; not opened. FlyWire route detailed below. Virgin females; most matched types have no dimorphism annotation. | Eligible after protocol 6 input, identity completion where needed, sex evidence and licence clearance; AVLP_pr36 excluded. |
| [Deutsch et al. 2019](https://doi.org/10.1016/j.cub.2019.08.008) | Dsx types pC1, pC2l, pC2m, pMN1 and pMN2; mostly dimorphic. Female auditory pC1 has no corresponding male response; pMN2 is female-specific. No resolved cited class-to-MaleCNS mapping; raw data on request. | Not eligible now. |
| Matsuo 2014; Ishikawa 2017; Patella & Wilson 2018 | JO calcium/driver-line measurements; female or unresolved type correspondence; figures only, no deposit or on request. Not protocol 6's input. | Not eligible. |
| Yang 2016; Pang 2025 | No measured paired lamina → medulla gain; Pang has no medulla readout. | Not eligible. |
| Kazama & Wilson 2009; Augustin 2019; Kohn 2021; Strother 2018; Apostolopoulou & Lin 2020 | Missing conductance/input resistance, fitted conductance, unavailable per-type traces, calcium without gain, or unresolved APL baseline/dynamic range. | Not eligible. |
| Dombrovski 2023/2025; Klapoetke 2017; Jang 2023; Zhao 2025; DANDI 001869 | No identified LC4/LPLC2 spike input. | Not eligible. |
| Hengstenberg 1992; Ispizua 2026; Lobato-Rios 2022 | Tethered/undefined angle reference, unavailable keypoints/licence, or one fixed female; no qualified resting registration. | Not eligible. |
| FlyGym 2.1.0; Fenwick 2026; Azevedo 2020 | Joint naming, chemically activated myofibrils, or tibia rather than TTM; no required muscle → actuator chain. | Not eligible. |

Baker's route is Table S3 root IDs → `flywire_annotations` v3.2.0,
materialization 783 → exact MaleCNS `flywireType` tokens. Annotation sources:
[Schlegel et al. 2024](https://doi.org/10.1038/s41586-024-07686-5) and
[Berg et al. 2026](https://doi.org/10.1016/j.cell.2026.08.015).
Two of 28 classes have complete cited routes: AVLP_pr35 → AVLP091 and
IPS_pr02 → FlyWire CB0033 → WED208. Twenty-four are partial: Table S3 uses
synapse-table v11/v274 root IDs, requiring a CAVE root-ID update and resolution of
remaining unmatched tokens. Two, AVLP_pr18 and AVLP_pr24, are absent from Table S3.
The older name/synonym search does not override this route. AVLP_pr36 includes
sexually dimorphic matches and is excluded; unannotated matches remain unresolved.

## Blockers and owner decisions

- Obtain protocol 6's JO input. No auditory case can be scored until then.
- Supply a CAVE token for root-ID updates; audit unresolved identities afterward.
- Decide whether intended NC-ND analysis without redistribution is permitted;
  record the licence basis or obtain permission before use.
- Resolve female recordings versus the male connectome with cited sex evidence.
  Acceptance alone cannot replace a non-dimorphic annotation.

## Next, if unblocked

Write the calibration/exploratory/held-out partition first. Lock
`validation/benchmarks.yaml` version 2 with a new content hash and the complete
prospective rules before opening responses. Preserve v1's failure and reported roles.
Then open the eligible data once under that lock; archive provenance, controls and
all outcomes. Baker, Deutsch and Pacheco response data remain unopened here.
