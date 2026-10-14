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

Kenyon cell sparseness v6–v8 restrict the eLN set to lLN2T (lLN1_bc as a variant) instead of
the whole cholinergic ALLN class. Next: a pair list for engine checks beyond the antennal lobe (GF →
TTMn/PSI with rectification, MN1–5 with Hürkey's coefficients).

## Graded transmission and visual kinetics ([#84](https://github.com/gianlucamazza/flymsg/issues/84), [#97](https://github.com/gianlucamazza/flymsg/issues/97))

No static Drosophila voltage-to-release curve exists: Zheng et al. (2006, 2009) report a
synaptic gain that adapts over seconds rather than a fixed curve, so scanning the curve
remains the honest treatment.

| Source                                                                                                                         | What it gives                                                                                                                                                                                                                                        | Data, licence                                                                 | Checked                            |
| ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------- |
| Groschner et al. 2022, _Nature_, doi:10.1038/s41586-022-04428-3                                                                | In vivo patch clamp of T4 and its inputs Mi1, Tm3, Mi4, Mi9, C3 to the same edges at 30°/s; T4 rests at −60.4 ± 7.4 mV (SD, 192 entries, control genotype), input resistance about 5.3 GΩ; a threshold-linear voltage-to-conductance model per input | Edmond doi:10.17617/3.8G; CC BY 4.0                                           | data (used by T4/T5 v3)            |
| Behnia et al. 2014, _Nature_, doi:10.1038/nature13427                                                                          | Linear-filter peak times: Mi1 71 ms (SEM 3.8) vs Tm3 53 ms (SEM 5.2), Tm1 56 ms (SEM 3.8) vs Tm2 43 ms (SEM 2.7); delays 18 and 13 ms (Fig. 3B, 3E; N = 7, 11, 15, 14 cells); all four respond with graded potentials                                | none deposited                                                                | full text, PMC4243710 (2026-10-14) |
| Gruntman et al. 2018 (_Nat Neurosci_, doi:10.1038/s41593-017-0046-4), 2019 (_eLife_, doi:10.7554/eLife.50706)                  | Whole-cell T4 and T5 responses to bars and moving bars in eight directions; graded, rare small transients                                                                                                                                            | Janelia figshare 10.25378/janelia.5576101 (T4), …c.4771805 (T5); CC BY-NC 4.0 | text (agent)                       |
| Arenz et al. 2017 (_Curr Biol_, doi:10.1016/j.cub.2017.01.051); Drews et al. 2020 (_Curr Biol_, doi:10.1016/j.cub.2019.10.035) | Calcium kernels of 13 types (L1–L5, Mi1, Tm3, Mi4, Mi9, Tm1, Tm2, Tm4, Tm9, CT1)                                                                                                                                                                     | kernels in a GitHub repository with no licence file                           | abstract                           |
| Borst 2025, _J Comput Neurosci_, doi:10.1007/s10827-025-00914-5                                                                | One passive time constant for every neuron reproduces the 13 kernels only with an H-current in L1 and L2 (a prediction)                                                                                                                              | CC BY 4.0; code without licence                                               | text (agent)                       |
| Zheng et al. 2006 (_J Gen Physiol_, doi:10.1085/jgp.200509470); 2009 (_PLoS ONE_, doi:10.1371/journal.pone.0004306, …0004307)  | Photoreceptor and LMC resting ranges in vivo; adaptive R → LMC gain, LMC adaptation τ 1.4–5.4 s                                                                                                                                                      | not deposited                                                                 | text (agent)                       |
| Lappalainen et al. 2024, _Nature_, doi:10.1038/s41586-024-07939-3                                                              | Per-type time constants and resting potentials, fitted on a task (not measured), arbitrary voltage units                                                                                                                                             | flyvis, MIT                                                                   | text (agent)                       |

T4/T5 v3 (locked and run, robust: neither) used Groschner's voltages and left per-type timing
unset. T4/T5 v4 (locked 2026-10-14, not yet run) sets Behnia's two delays (18 ms, 13 ms) through
the slower cell's τ_syn and holds out the Gruntman recordings as the direction benchmark; flyvis
values stay a fitted comparison only.

## Motor map and body ([#19](https://github.com/gianlucamazza/flymsg/issues/19), [#34](https://github.com/gianlucamazza/flymsg/issues/34), [#35](https://github.com/gianlucamazza/flymsg/issues/35))

In MaleCNS 406 of the 708 `vnc_motor` neurons already carry a muscle-named type (`Ti flexor
MN`, `Ti extensor MN`, `TTMn`, `DLMn a, b`, …); 293 carry generic codes (214 abdominal
`MNad`), 9 none (data). These names come from MANC, so what blocks a motor map is the link
from muscle to body actuator, not from neuron to muscle.

| Source                                                                                                        | What it gives                                                                                                                                                                                                                                                                       | Data, licence               | Checked                |
| ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ---------------------- |
| Cheong et al. 2024, _eLife_, doi:10.7554/eLife.96084                                                          | MANC motor neurons by type with light-microscopy muscle matches and match confidence (Supplementary file 3); TTMn matched to SS02623                                                                                                                                                | CC BY                       | text (agent)           |
| Azevedo et al. 2024, _Nature_, doi:10.1038/s41586-024-07389-x                                                 | FANC leg and wing motor neurons to muscles (female), linked to MANC by NBLAST                                                                                                                                                                                                       | GPL-3.0 code                | abstract               |
| Card & Dickinson 2008, _J Exp Biol_, doi:10.1242/jeb.012682                                                   | Escape take-off: centre-of-mass speed over the first 2 ms of flight 0.48 ± 0.01 m/s (s.e.m.; voluntary 0.28 ± 0.02), Fig. 8A; mated females, 3 days old; looming disc; 27 escapes filmed (n of the speed not stated); middle-leg extension 3.3 ms, peak acceleration about 112 m/s² | © The Company of Biologists | full text (2026-10-14) |
| Zumstein et al. 2004, _J Exp Biol_, doi:10.1242/jeb.01181                                                     | TTM twitch (already used); their model predicts 274 µN peak and about 5 ms to take-off                                                                                                                                                                                              | —                           | abstract               |
| Eldred et al. 2010, _Biophys J_, doi:10.1016/j.bpj.2009.11.051                                                | Jump-muscle isometric tension 37 mN/mm², Vmax 5.1 lengths/s: a Hill-type force–velocity curve                                                                                                                                                                                       | —                           | text (agent)           |
| von Reyn et al. 2017, _Neuron_ (ModelDB 230400); Ache et al. 2019, _Curr Biol_, doi:10.1016/j.cub.2019.01.079 | LC4 and LPLC2 contributions to the giant fiber potential as functions of angular velocity and size, with delays; LC4 spike-rate tuning itself is not measured                                                                                                                       | ModelDB; no licence stated  | text (agent)           |

Next: join MANC's supplementary table to MaleCNS types for a cited neuron → muscle column;
judge jump3d by take-off velocity (0.48 m/s, verified in the full text on 2026-10-14) before
distance, once the body has the leg push it lacks (jump3d v1 left at 0.06–0.07 m/s, TTM only); an M2 transducer that predicts
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

## Sensorimotor gates: registration, transduction, motor map (search of 2026-10-14)

What blocks a biological closed loop under the [body-wiring ADR](adr-body-wiring.md): the
eye-map registration (G2, [#179](https://github.com/gianlucamazza/flymsg/issues/179)), a measured
looming transducer (G3, [#34](https://github.com/gianlucamazza/flymsg/issues/34)) and a muscle →
actuator assignment (G4, [#19](https://github.com/gianlucamazza/flymsg/issues/19),
[#35](https://github.com/gianlucamazza/flymsg/issues/35)). Searched by three agents; the decisive
claims were re-read on the source.

### Eye map → body registration (G2)

Zhao et al. 2025 build the eye-map frame from the eye alone: "we used the lens positions from
both eyes to define the visual field's frontal midline (sagittal plane)", with the equator from
the inversion in photoreceptor chirality and z = 0 "defined by lens positions" (Methods). No
neck, thorax or resting posture enters it, although the scanned heads kept "the thorax and
abdomen intact and glued to the head". No published resting head pitch of _D. melanogaster_
relative to the thorax, with spread and n, was found.

| Source                                                                                                              | What it gives                                                                                                                                                                       | Data, licence                                                                    | Checked      |
| ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------ |
| Zhao et al. 2025, _Nature_, doi:10.1038/s41586-025-09276-5                                                          | Eye-intrinsic frame (above); field of view "from directly above to −70° in elevation"; flies "can coordinately redirect all ommatidia by up to about 15°" (citing Fenk et al. 2022) | CC BY 4.0; µCT on Janelia figshare 10.25378/janelia.29111339, 0.6–0.7 GB per fly | text         |
| Lobato-Rios et al. 2022, _Nat Methods_, doi:10.1038/s41592-022-01466-7                                              | NeuroMechFly head posed by hand ("rotated 20°" in the zero pose; head capsule pitch 10° in Table 4 of the preprint): authors' choices, not measurements                             | preprint CC BY-NC                                                                | text (agent) |
| Wang-Chen et al. 2024, _Nat Methods_, doi:10.1038/s41592-024-02497-y                                                | FlyGym's 721-ommatidium eye is an idealised hexagonal grid; the eye cameras were placed by hand against coloured pillars (Supplementary Note 5); no µCT direction map               | FlyGym Apache-2.0                                                                | text (agent) |
| Kim et al. 2017 (_Cell_, doi:10.1016/j.cell.2016.12.005); Klapoetke et al. 2017 (_Nature_, doi:10.1038/nature24626) | Head pitch relative to the rig in glued preparations (eye rows 65.6 ± 5.4° to the horizontal, n = 11; equator 55 ± 5° below it): preparation angles, not body ones                  | —                                                                                | text (agent) |
| Ispizua et al. 2026, bioRxiv doi:10.64898/2026.05.03.722293 (preprint)                                              | Free-walking 3D keypoints including antenna base, eye tips and scutellum: the only data found from which a head-to-thorax pitch could be measured; no head pitch reported           | CC BY-NC 4.0; dataset licence not checked                                        | abstract     |

Next: still blocked. A registration would be a new measurement, e.g. landmarks located in
Zhao's µCT volume (whether the glued thorax is in the field of view is unchecked) joined to a
head-to-thorax pitch from free-walking keypoints; yaw and roll, individual variation (n = 3 eye
maps) and the female eye under a male CNS stay open.

### Looming transduction (G3)

No deposited recording gives LC4 or LPLC2 firing rates for looming; the only LC4/LPLC2 looming
data are calcium ΔF/F, with no stated conversion to spikes. What is deposited is the giant
fiber's membrane potential to looming at four r/v values.

| Source                                                                                                          | What it gives                                                                                                                                                                                                                                                                              | Data, licence                                                          | Checked                      |
| --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- | ---------------------------- |
| Dombrovski et al. 2025, _Nature_, doi:10.1038/s41586-025-09037-4                                                | Giant fiber (DNp01) whole-cell current clamp to looming at r/v 10, 20, 40, 80 ms (Extended Data Fig. 8), controls and mutants, 20 kHz traces; a second set of 5 flies × 3 elevations × 5 trials, discs 0 → 30° at 500°/s. Disc sizes of the r/v runs and the sex are to be read before use | Zenodo 10.5281/zenodo.14983850, CC BY 4.0, 46 files, 33 MB             | data (record) ; text (agent) |
| Ache et al. 2019, _Curr Biol_, doi:10.1016/j.cub.2019.01.079                                                    | Giant fiber model: an LC4 term linear in angular velocity and an LPLC2 term Gaussian in ln θ, both with a 19 ms delay, and their weights (STAR Methods)                                                                                                                                    | on request only; ModelDB 230400 holds code                             | text (agent)                 |
| Jang et al. 2023, _J Exp Biol_, doi:10.1242/jeb.244790                                                          | Giant fiber whole-cell at r/v 10–80 ms, discs 10 → 63°, n = 10 females: the protocol the 2025 runs cite                                                                                                                                                                                    | on request                                                             | text (agent)                 |
| Klapoetke et al. 2017, 2022 (_Neuron_, doi:10.1016/j.neuron.2022.02.013); Turner et al. 2022, _eLife_ 11:e82587 | LPLC2 and LC4 calcium imaging to looming (ΔF/F only). Turner's set covers both glomeruli                                                                                                                                                                                                   | Klapoetke on request; Turner Dryad 10.5061/dryad.h44j0zpp8, CC0, 53 GB | text (agent)                 |

Next: an M2 transducer can now be scored without a data request on the stage that ends at the
giant fiber: an input shaped as Ache et al. 2019 drives the model's DNp01, judged against the
deposited r/v series with a held-out set fixed in the lock. That calibrates gains against the
giant fiber; it is not a measured LC4 or LPLC2 rate and must be named so.

### Muscle → body actuator (G4)

No source names a MaleCNS/MANC motor neuron or muscle together with a FlyBody actuator, so under
`validation/motor_map.yaml`'s rule every row stays unmapped. Muscle → joint actions are
published, and FlyGym 2.1.0 now ships a muscle model.

| Source                                                                                                           | What it gives                                                                                                                                                                                                                                                                                                                                                                                                     | Data, licence                          | Checked                             |
| ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | ----------------------------------- |
| Azevedo et al. 2024, _Nature_, doi:10.1038/s41586-024-07389-x                                                    | Per-muscle joint actions for the female T1 leg (Supplementary Appendix Table A1: tibia extensor/flexors on the femur–tibia joint, trochanter extensors/flexors on the coxa–trochanter joint, tarsus depressor/levator on tibia–tarsus); the tergotrochanter's "role in T2 trochanter–femur extension during jumping"; "It was previously assumed that the Drosophila trochanter and femur are functionally fused" | supplementary PDF; licence not checked | text (main); data (agent, Table A1) |
| Özdil et al., arXiv 2509.06426 (ICLR 2026), FlyMimic; shipped in FlyGym 2.1.0 as `assets/model/musculoskeletal/` | 15 Hill-type muscles of the left front leg named with their tendons and the joints they cross (coxa yaw/pitch/roll, trochanter yaw/pitch/roll, tibia pitch), grouped after Azevedo 2024 and Soler 2004; on a NeuroMechFly leg, not FlyBody; mid and hind legs not released                                                                                                                                        | CC BY 4.0 (paper), Apache-2.0 (model)  | data (local MJCF)                   |
| Vaxenburg et al. 2025, _Nature_, doi:10.1038/s41586-025-09029-4                                                  | FlyBody has joint actuators only, no muscles and no muscle → actuator table; legs body–coxa, coxa–femur, femur–tibia, tibia–tarsus; no trochanter                                                                                                                                                                                                                                                                 | licence not checked                    | text (agent)                        |
| Lesser et al. 2024, _Nature_, doi:10.1038/s41586-024-07600-z                                                     | Motor-neuron modules by joint; the tergotrochanter described as biarticular (Extended Data Fig. 6d)                                                                                                                                                                                                                                                                                                               | —                                      | text (agent, to re-read)            |

Next: still blocked as a published co-naming. Candidate rows (tibia T1 from Table A1; TTMn on
the T2 coxa–femur actuator) would need a documented two-source join, an antagonist rule and a
decision on whether FlyBody's coxa–femur joint stands for the coxa–trochanter one, which
Azevedo et al. 2024 put in doubt; each is an authored choice for a new lock, not a citation.

## Synapse strength and per-type parameters

| Source                                                      | What it gives                                                                                                                                                                                                                                                                                    | Data, licence                                                                                           | Checked      |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | ------------ |
| Liu et al. 2022, _Curr Biol_, doi:10.1016/j.cub.2021.11.056 | 29 measured PN → LHN unitary EPSPs (0.4–6.6 mV) matched to hemibrain: amplitude increases linearly with synapse density (count over whole-neuron area, r² 0.77 over 135 pairs, 0.84 dendritic); no count-only statistic is reported (corrected 2026-10-13). Pair means in Table S3 (Document S1) | Elsevier open archive (supplements); Zenodo 5716323/5716321/5711439 CC BY 4.0, code and morphology only | text         |
| Liu & Wilson 2013, _PNAS_, doi:10.1073/pnas.1220560110      | Glutamate inhibits antennal-lobe neurons through GluClα (the basis of the sign rule, measured there only)                                                                                                                                                                                        | —                                                                                                       | abstract     |
| Shiu et al. 2024, _Nature_, doi:10.1038/s41586-024-07763-9  | The model's source; names circuits that need tonic inhibition as its failure mode (zero baseline)                                                                                                                                                                                                | MIT                                                                                                     | text (agent) |
| flycns 0.7.0 (PyPI)                                         | MaleCNS v1.0 compiled into Shiu's LIF plus a flyvis optic lobe: the closest peer to compare against                                                                                                                                                                                              | MIT code, CC BY 4.0 data                                                                                | text (agent) |

Used by `validation/weight_rule.yaml` v1 (#139): on 57 PN → LHN pairs density ranks the
amplitudes barely better than count (Δρ +0.015, interval −0.011 to +0.054), undecided; count
stays the rule.
