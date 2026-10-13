# Evidence leads: sources that could lift an approximation

Literature and data search of 2026-10-13, ordered by the [approximation](approximations.md)
each source could lift. A lead is not a result and changes nothing in the model: using one
needs an issue and a lock committed before any run, as for every claim here.

"Checked" says how far each row was verified:

- **data**: checked against the local MaleCNS tables or a downloaded data file;
- **text**: numbers read in the full text;
- **abstract**: from the abstract or the publisher page only; numbers to be read before use.

Licences marked "not checked" must be confirmed before any file is fetched into the repository.

## Electrical synapses ([#85](https://github.com/gianlucamazza/flymsg/issues/85))

No connectome-scale gap-junction map exists for any fly dataset: MANC states gap junctions
were not annotated, and none was found for FlyWire, BANC or MaleCNS.

| Source                                                              | What it gives                                                                                                                                                                                                                                                                                                                                                                       | Data, licence                                              | Checked                    |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | -------------------------- |
| Eckstein et al. 2024, _Cell_, doi:10.1016/j.cell.2024.03.016        | lLN2T_abc (~13 neurons, predicted serotonergic in FAFB) have "a cell body placement and general morphology most similar to reported cholinergic local neurons" (STAR Methods; Fig. S5F legend). lLN1_bc is "positioned closely among them", not named a match. Morphology only, no staining. In MaleCNS: lLN2T_a 5, lLN2T_b 4, lLN2T_c 4, lLN1_bc 30, all class ALLN, acetylcholine | CC BY 4.0                                                  | data (types), text         |
| Hürkey et al. 2023, _Nature_, doi:10.1038/s41586-023-06099-0        | Flight motoneurons MN1–5: coupling coefficients 0.023 ± 0.003 (MN1–MN2, MN3–MN4) and 0.010 ± 0.003 (other pairs), non-rectifying, ShakB-dependent; a Brian2 model with 43.5 pS junctions and CC = g/(g + g_L)                                                                                                                                                                       | Zenodo 7737730 (data), 7740678 (code); licence not checked | text (agent)               |
| Phelan et al. 2008, _Curr Biol_, doi:10.1016/j.cub.2008.10.067      | Giant fiber → TTMn/PSI junctions are heterotypic ShakB and rectify, Gj min/max ≈ 0.21 (oocytes: shape transfers, magnitude does not)                                                                                                                                                                                                                                                | open access                                                | text (agent)               |
| Pokusaeva et al. 2024, _Nat Commun_, doi:10.1038/s41467-024-53173-w | Dye-coupled partners of HS cells (HS–HS, HS–CH, HS–bIPS, HSE–H2, HS–VCNM/CNM-like); qualitative strength only. HSE, HSN, HSS are typed in MaleCNS                                                                                                                                                                                                                                   | ISTA 10.15479/AT:ISTA:17488                                | data (types), text (agent) |
| Ammer et al. 2022, _Curr Biol_, doi:10.1016/j.cub.2022.03.040       | Innexin antibody atlas by neuropil; ShakB is the most widespread neuronal innexin. Not pair-resolved                                                                                                                                                                                                                                                                                | —                                                          | abstract                   |
| Lillvis et al. 2022, _eLife_, doi:10.7554/eLife.81248               | Expansion light-sheet detection of Inx6 clusters; proof of concept, no map                                                                                                                                                                                                                                                                                                          | CC BY                                                      | text (agent)               |

Kenyon cell sparseness v6 restricts the eLN set to lLN2T (lLN1_bc as a variant) instead of
the whole cholinergic ALLN class. Next: a pair list for engine checks beyond the antennal lobe (GF →
TTMn/PSI with rectification, MN1–5 with Hürkey's coefficients).

## Graded transmission and visual kinetics ([#84](https://github.com/gianlucamazza/flymsg/issues/84), [#97](https://github.com/gianlucamazza/flymsg/issues/97))

No static Drosophila voltage-to-release curve exists: Zheng et al. (2006, 2009) report a
synaptic gain that adapts over seconds rather than a fixed curve, so scanning the curve
remains the honest treatment.

| Source                                                                                                                         | What it gives                                                                                                                                                                                                                                        | Data, licence                                                                 | Checked                   |
| ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------- |
| Groschner et al. 2022, _Nature_, doi:10.1038/s41586-022-04428-3                                                                | In vivo patch clamp of T4 and its inputs Mi1, Tm3, Mi4, Mi9, C3 to the same edges at 30°/s; T4 rests at −60.4 ± 7.4 mV (SD, 192 entries, control genotype), input resistance about 5.3 GΩ; a threshold-linear voltage-to-conductance model per input | Edmond doi:10.17617/3.8G; licence not checked                                 | data (rest), text (agent) |
| Behnia et al. 2014, _Nature_, doi:10.1038/nature13427                                                                          | Linear-filter peak times: Mi1 71 ms (SEM 3.8) vs Tm3 53 ms (SEM 5.2), Tm1 56 ms (SEM 3.8) vs Tm2 43 ms (SEM 2.7); all four respond with graded potentials                                                                                            | none deposited                                                                | text                      |
| Gruntman et al. 2018 (_Nat Neurosci_, doi:10.1038/s41593-017-0046-4), 2019 (_eLife_, doi:10.7554/eLife.50706)                  | Whole-cell T4 and T5 responses to bars and moving bars in eight directions; graded, rare small transients                                                                                                                                            | Janelia figshare 10.25378/janelia.5576101 (T4), …c.4771805 (T5); CC BY-NC 4.0 | text (agent)              |
| Arenz et al. 2017 (_Curr Biol_, doi:10.1016/j.cub.2017.01.051); Drews et al. 2020 (_Curr Biol_, doi:10.1016/j.cub.2019.10.035) | Calcium kernels of 13 types (L1–L5, Mi1, Tm3, Mi4, Mi9, Tm1, Tm2, Tm4, Tm9, CT1)                                                                                                                                                                     | kernels in a GitHub repository with no licence file                           | abstract                  |
| Borst 2025, _J Comput Neurosci_, doi:10.1007/s10827-025-00914-5                                                                | One passive time constant for every neuron reproduces the 13 kernels only with an H-current in L1 and L2 (a prediction)                                                                                                                              | CC BY 4.0; code without licence                                               | text (agent)              |
| Zheng et al. 2006 (_J Gen Physiol_, doi:10.1085/jgp.200509470); 2009 (_PLoS ONE_, doi:10.1371/journal.pone.0004306, …0004307)  | Photoreceptor and LMC resting ranges in vivo; adaptive R → LMC gain, LMC adaptation τ 1.4–5.4 s                                                                                                                                                      | not deposited                                                                 | text (agent)              |
| Lappalainen et al. 2024, _Nature_, doi:10.1038/s41586-024-07939-3                                                              | Per-type time constants and resting potentials, fitted on a task (not measured), arbitrary voltage units                                                                                                                                             | flyvis, MIT                                                                   | text (agent)              |

Next, for a T4/T5 v3 lock: hold out the Gruntman recordings as the direction benchmark; gate
any per-type timing on Behnia's two measured delays (18 ms, 13 ms); report flyvis values only
as a fitted comparison.

## Motor map and body ([#19](https://github.com/gianlucamazza/flymsg/issues/19), [#34](https://github.com/gianlucamazza/flymsg/issues/34), [#35](https://github.com/gianlucamazza/flymsg/issues/35))

In MaleCNS 406 of the 708 `vnc_motor` neurons already carry a muscle-named type (`Ti flexor
MN`, `Ti extensor MN`, `TTMn`, `DLMn a, b`, …); 293 carry generic codes (214 abdominal
`MNad`), 9 none (data). These names come from MANC, so what blocks a motor map is the link
from muscle to body actuator, not from neuron to muscle.

| Source                                                                                                        | What it gives                                                                                                                                                 | Data, licence              | Checked      |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- | ------------ |
| Cheong et al. 2024, _eLife_, doi:10.7554/eLife.96084                                                          | MANC motor neurons by type with light-microscopy muscle matches and match confidence (Supplementary file 3); TTMn matched to SS02623                          | CC BY                      | text (agent) |
| Azevedo et al. 2024, _Nature_, doi:10.1038/s41586-024-07389-x                                                 | FANC leg and wing motor neurons to muscles (female), linked to MANC by NBLAST                                                                                 | GPL-3.0 code               | abstract     |
| Card & Dickinson 2008, _J Exp Biol_, doi:10.1242/jeb.012682                                                   | Escape take-off: velocity 0.48 m/s, middle-leg extension 3.3 ms, peak acceleration about 112 m/s²                                                             | —                          | text (agent) |
| Zumstein et al. 2004, _J Exp Biol_, doi:10.1242/jeb.01181                                                     | TTM twitch (already used); their model predicts 274 µN peak and about 5 ms to take-off                                                                        | —                          | abstract     |
| Eldred et al. 2010, _Biophys J_, doi:10.1016/j.bpj.2009.11.051                                                | Jump-muscle isometric tension 37 mN/mm², Vmax 5.1 lengths/s: a Hill-type force–velocity curve                                                                 | —                          | text (agent) |
| von Reyn et al. 2017, _Neuron_ (ModelDB 230400); Ache et al. 2019, _Curr Biol_, doi:10.1016/j.cub.2019.01.079 | LC4 and LPLC2 contributions to the giant fiber potential as functions of angular velocity and size, with delays; LC4 spike-rate tuning itself is not measured | ModelDB; no licence stated | text (agent) |

Next: join MANC's supplementary table to MaleCNS types for a cited neuron → muscle column;
judge jump3d by take-off velocity (0.48 m/s) before distance; an M2 transducer that predicts
the giant fiber potential, validated on the giant fiber.

## Held-out validation ([#36](https://github.com/gianlucamazza/flymsg/issues/36))

Berg et al. 2026 report that the sensory and motor periphery is largely isomorphic between
the sexes, so female recordings can test non-dimorphic circuits, not fru/dsx ones.

| Source                                                                                                                      | What it gives                                                                                                        | Data, licence                                  | Checked      |
| --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ------------ |
| Pacheco et al. 2021, _Nat Neurosci_, doi:10.1038/s41593-020-00743-y                                                         | Brain-wide responses to pulse and sine song by neuropil, with iav mutants as a null                                  | Princeton DataSpace 10.34770/gv6w-5351, "none" | text (agent) |
| Cande et al. 2018, _eLife_, doi:10.7554/eLife.34275                                                                         | Behaviour of single descending-neuron activations                                                                    | Dryad 10.5061/dryad.fr89c0c                    | text (agent) |
| Currier & Clandinin 2025, bioRxiv doi:10.1101/2025.03.06.641774 (preprint)                                                  | Visual responses of 91 cell types against connectome predictions                                                     | CC BY-NC-ND; no data repository found          | abstract     |
| Lin et al. 2014 (_Nat Neurosci_, doi:10.1038/nn.3660); Amin et al. 2020 (_eLife_ 56954); Prisco et al. 2021 (_eLife_ 74172) | APL: blocking it makes Kenyon cell responses denser; inhibition is local and scales with input — relational KC tests | open access (eLife)                            | abstract     |

Next: lock Pacheco 2021 as the first held-out benchmark (song → neuropil responses, iav null),
with the scoring rule fixed before any run.

## Synapse strength and per-type parameters

| Source                                                      | What it gives                                                                                                                                                                                                                                                                                    | Data, licence                                                                                           | Checked      |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | ------------ |
| Liu et al. 2022, _Curr Biol_, doi:10.1016/j.cub.2021.11.056 | 29 measured PN → LHN unitary EPSPs (0.4–6.6 mV) matched to hemibrain: amplitude increases linearly with synapse density (count over whole-neuron area, r² 0.77 over 135 pairs, 0.84 dendritic); no count-only statistic is reported (corrected 2026-10-13). Pair means in Table S3 (Document S1) | Elsevier open archive (supplements); Zenodo 5716323/5716321/5711439 CC BY 4.0, code and morphology only | text         |
| Liu & Wilson 2013, _PNAS_, doi:10.1073/pnas.1220560110      | Glutamate inhibits antennal-lobe neurons through GluClα (the basis of the sign rule, measured there only)                                                                                                                                                                                        | —                                                                                                       | abstract     |
| Shiu et al. 2024, _Nature_, doi:10.1038/s41586-024-07763-9  | The model's source; names circuits that need tonic inhibition as its failure mode (zero baseline)                                                                                                                                                                                                | MIT                                                                                                     | text (agent) |
| flycns 0.7.0 (PyPI)                                         | MaleCNS v1.0 compiled into Shiu's LIF plus a flyvis optic lobe: the closest peer to compare against                                                                                                                                                                                              | MIT code, CC BY 4.0 data                                                                                | text (agent) |

Next: compare weight = count with weight = density against Liu 2022's 29 pairs before any
change to `w_syn`.
