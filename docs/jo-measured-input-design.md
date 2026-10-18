# Qualify measured JO input before scoring

Status: **complete design for review, not an implemented or qualified input**,
2026-10-17. Applies to [entry protocol 6](issue-resolution.md) and
[M4 v2](m4-v2-proposal.md). The [ADR](adr-measured-jo-input.md), accepted
2026-10-18, defers runtime implementation until a measured source establishes the mode. No source response archive,
Baker/Pacheco outcome, simulation, seed search or new validation lock was opened
or executed for this design.

**Measured JO input remains blocked.** The audited sources establish useful
mechanical and calcium constraints, but none establishes an accessible,
licensed, identity-resolved absolute JO-A/B/D spike or calibrated membrane input
covering the admitted stimulus domain. This is a bounded source audit, not proof
that no suitable recordings exist. A normalized band-pass can support a labelled
engineered diagnostic; it cannot satisfy protocol 6 by receiving an arbitrary Hz
gain. The next executable step is source acquisition and qualification, not
fitting Baker responses. Historical song v1, its stopped outcome and the failed
v1 benchmark remain unchanged.

## Source observations constrain different links

The required chain is **sound particle velocity → arista displacement/rotation →
JO native neural observable → declared simulation input**. Direct arista
actuation bypasses the first link. Air velocity and arista velocity are different
observables: `v = 2πfx` applies to velocity and displacement of the same object,
not across this biological transfer. Pressure-to-particle-velocity conversion
requires a justified acoustic model and geometry; do not assume a plane wave in
this near-field preparation. Every transfer needs its own units, uncertainty and
domain. Preserve peak, peak-to-peak and RMS conventions explicitly; their familiar
sinusoidal conversions do not apply blindly to pulse trains or noise.

| Primary source                                                                      | Native observation and stimulus                                                                                                                                                        | Identity/access limits and admissible use                                                                                                                                                                                                                                                         |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Matsuo 2014](https://doi.org/10.3389/fphys.2014.00179), Figs 2–4                   | GCaMP3 ΔF/F at 3 frames/s; 4-s electrostatic vibrations, 40/100/200/400/800 Hz; 35-ms-IPI pulses; approximately 10-µm vibration, amplitude convention/measurement point to recover     | JO29 labels D plus some B/E; output-zone ROI, not DA/DP single cells. D frequency n=7, pulse n=5. Female imaging; passive male receiver calibration is a different preparation. Article CC BY; no public raw deposit established. Constrains D responsiveness only.                               |
| [Ishikawa 2017](https://doi.org/10.3389/fncir.2017.00046), Fig 7                    | GCaMP3/6m; 4 fps frequency/10 fps pulse; 40–800-Hz tones, 167-Hz pulse carrier; measured arista 1.31 ± 0.52 µm peak-to-peak                                                            | Females, overlapping A driver subsets, at least five flies/experiment; no verified public raw deposit. Supports heterogeneity, not absolute spike gain or exact EM subtype assignments.                                                                                                           |
| [Patella & Wilson 2018](https://doi.org/10.1016/j.cub.2018.02.074), STAR Methods    | GCaMP6f, generally 11.63 fps; glued piezo/arista drive, mean-to-peak displacement; tones 4–325 Hz, AM carriers 8–600 Hz, FM 2–600 Hz                                                   | Female 1–2 days; functional pixel clusters are not connectome types. Data/software on request. Request original trials and actuator calibration, not only normalized cluster curves.                                                                                                              |
| [Azevedo & Wilson 2017](https://doi.org/10.1016/j.neuron.2017.09.004), STAR Methods | Intracellular postsynaptic A2/B1 voltage/current, 50-kHz acquisition, 10-kHz filtering; some B1 cells graded                                                                           | Central neurons, **not receptor JO-A2/JO-B1**. Data on request. Cannot infer JO input without independently measured synaptic transfer.                                                                                                                                                           |
| [Clemens 2018](https://doi.org/10.1038/s41467-017-02453-9)                          | Antennal-nerve compound action potential and mechanics; intensity changes each 100 ms                                                                                                  | Compound voltage conflates recruitment, synchrony and electrode geometry. Data/code on request; not identified single-cell spikes/s. Full sex/sample/physical calibration still requires acquisition audit.                                                                                       |
| [Yamakoshi 2025](https://doi.org/10.1016/j.isci.2025.113232), Figs 3–4              | Pooled JO-A/B axonal GCaMP6f, 10 fps/100-ms exposure; 2-s playback; 167-Hz carrier with IPI35/75 ms; 100-Hz tone. Acoustic velocity 11.1–13.1 mm/s peak-to-peak pulses, 15.5–18.4 tone | Female 5–7 days; mating state matters; A/B bundle ROIs. [Mendeley v1](https://data.mendeley.com/datasets/29hpr3nrrv/1) metadata states CC BY 4.0, original data/scripts. Metadata only inspected. Already used for songv1 A/B ratios: source-calibration-only, never fresh confirmatory evidence. |
| [Gregory 2025](https://doi.org/10.1523/ENEURO.0083-24.2024)                         | Sound-evoked antennal field potentials and LDV arista mechanics                                                                                                                        | Genotype/antenna-level measurements; not subtype-resolved absolute event input.                                                                                                                                                                                                                   |

A publication's open licence does not establish the reuse licence of recordings
available only from authors. Archive-level and file-level notices must be checked.
Replication units must distinguish animals, antennae, cells, ROIs, sessions and
trials. Do not pool female mating conditions or invent a total n from figure-specific
counts. Calcium exposure integrates away fast timing: neither band-pass shape nor
ΔF/F ratios determine baseline, saturation, latency, carrier phase, adaptation,
absolute rate or intercell correlations. Preserve calcium in native units for
source validation; conversion to Hz requires separate simultaneous electrical
calibration and independent validation.

## Identity is a separate gate from transfer calibration

The frozen MaleCNS selector `^JO-[ABD]` selects **146 bodies: A=50, B=88, D=8**
from `data/neurons.parquet`, SHA256
`7ec0020f08495c35398deafa3183292dfb489ce6717d889b80cfcc11cb757c7c`.
These are local anatomical counts, not measured transfer functions. Side comes
from `instance`, since `somaSide` is absent. There are 85 left/61 right bodies:
A 18/32, B 59/29, D 8/0. Left-only D is reconstruction coverage, not biological
unilaterality. Do not invent right D cells or mirror their spike trains.

| Exact MaleCNS label            |       Bodies | Left/right          |
| ------------------------------ | -----------: | ------------------- |
| JO-A-unclear                   |           24 | 0/24                |
| JO-A1, JO-A2, JO-A3, JO-A4     |  8, 13, 2, 3 | 4/4, 11/2, 2/0, 1/2 |
| JO-B-unclear                   |           13 | 2/11                |
| JO-B1_a, JO-B1_b, JO-B1_c      |   17, 12, 10 | 12/5, 7/5, 9/1      |
| JO-B2, JO-B3, JO-B4_a, JO-B4_b | 9, 12, 3, 12 | 7/2, 10/2, 3/0, 9/3 |
| JO-DA, JO-DP                   |         5, 3 | 5/0, 3/0            |

The **37 `-unclear` bodies remain subgroup-only**. Body `308087` lacks a
`flywireType`; `138093763` is MaleCNS `JO-B-unclear` with `flywireType`
`JO-B`, so neither names a subtype and neither is upgraded. All selected male
`dimorphism` fields are absent. Female raw annotations have 412 selected rows,
all annotated `isomorphic`; processed female parquet has 411, including no
root `720575940616042508`, and includes JO-A5 absent from the male selection.
The processing discrepancy needs provenance resolution before any female
coverage denominator. Female anatomical isomorphism does not establish male
physiological equivalence. [Dataset provenance](data.md) remains authoritative
for source versions.

A/B/D projection zones, overlapping genetic drivers, calcium clusters and modern
EM subtypes are distinct identities. Do not assign pulse-only A, sine-only B,
or a D centre frequency/gain from a qualitative preference. Group-level evidence
can admit an explicitly labelled population model at group resolution; it cannot
justify subtype-specific transfer functions. Freeze one mapping row per source
observation × target body, retaining source animal/ROI linkage. Fan-out is not
146 independent observations. Female-to-male physiology needs direct evidence or
a restricted female claim, which does not automatically qualify MaleCNS protocol 6.

## Choose the numerical boundary from the observed signal

The current [song generator](https://github.com/gianlucamazza/flymsg/blob/main/src/flymsg/song.py) supplies voltage-kick counts,
not measured JO emissions. Defaults give approximately 48.08 mV per event against
a 7-mV rest-to-threshold gap; the binary envelope has no measured carrier
transduction. Dead-time filtering uses 2.2 ms and thinning equalizes per-cell
counts across conditions, deliberately discarding integrated-count differences.
Stimulated cells bypass ordinary refractory deadlines but retain recurrent
conductance and thresholding. Thus **454.5 Hz is not their hard output ceiling**.
The [kernel](https://github.com/gianlucamazza/flymsg/blob/main/src/flymsg/sim.py) thresholds before delivering input, so ordinary
kicks also acquire next-step emission timing. Actual JO spikes and input kicks
are separately recorded and are not guaranteed equal.

The proposed primary boundary is **outgoing source-event replay**. Observed JO
spikes prescribe emissions directly; their source rows cannot also generate LIF
spikes. Preserve outgoing chemical weights, signs, fan-out and delays. Record
excluded feedback to clamped JO cells and limit the claim to the network driven
by observed source output. Audit incident gap junctions before admission: reject
unsupported electrical coupling rather than invent source voltage. The decision
is pending in the [ADR](adr-measured-jo-input.md).

Absolute measured rates require a separately justified rate-to-event model:
rate is not an observed train. Independent Poisson, shared latent drive and
empirical trial sampling make different correlation assumptions. A pooled ROI
cannot establish independent cells, and cloning one train fabricates perfect
correlation. Require source-only evidence for timing/correlation assumptions and
predeclared uncertainty/sensitivity treatment; otherwise refuse the claim.
Do not silently impose dead time or count matching on an absolute rate.
Calibrated JO current/conductance or membrane recordings offer a separate
membrane mode only with recording location, holding conditions, reversal
potentials and independently measured JO conversion parameters. Recurrent
feedback and the declared biological refractory treatment then remain active;
do not simultaneously force emissions. Neither a postsynaptic current nor an
arbitrary pA-to-kick gain qualifies this mode.

## Freeze typed assets and falsify their transformation

The following is an artifact contract, not a new implemented format. A manifest
references immutable native files, mapping and transforms by content hash; no
implicit `latest`. Use explicit `null` plus `missing_reason` for unknown metadata,
never zero, empty-string eligibility or guessed defaults. Required unknowns block
qualification. Distinguish absence of events from missing acquisition intervals;
missing intervals cannot become silence. Invalid units, timestamps, identities,
negative rates, nonfinite values and corrupt bytes are typed refusals.

| Artifact            | Required fields and semantics                                                                                                                                                                                                                                  |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source manifest     | DOI/accession/version, licence/file notices, raw SHA256, acquisition/animal/cell/ROI/trial IDs, observable enum, native units, sex/age/mating/genotype/temperature/preparation, exclusions and missing intervals                                               |
| Stimulus table      | Original waveform/hash/timebase; carrier, phase, envelope, pulse width/IPI/gap, amplitude and peak/peak-to-peak/RMS convention; pressure versus particle velocity; delivery location/geometry; arista axis/point; same-preparation calibration and uncertainty |
| Native signal table | Samples or spike timestamps, sample clock/rate, clock alignment/error, native baseline/gain/offset, instrument filtering/bandwidth, exposure, electrical corrections, extraction method and validated detection errors                                         |
| Identity map        | Source observation/group/subtype/side and driver-coverage evidence; target dataset/hash/bodyId/type/instance/side-field/FlyWire type; mapping resolution/cardinality; sex evidence; eligible/ambiguous/refused and reason; no inferred subtype overwrite       |
| Transfer record     | Observed/fitted/engineered labels per field, model/parameters/units, supported frequency/amplitude/state domain, source-only animal-level calibration/validation split, residuals and uncertainties; frozen admissibility tolerances                           |
| Replay artifact     | Mode/version, ordered bodyIds, source interval and clock conversion, quantization, prescribed events and hash; rate sampler/version/seed/key schedule if needed; excluded feedback policy; emitted-event and delayed-delivery audit hashes                     |

Stimulus preprocessing must resolve the **carrier** with documented acquisition
and anti-alias filtering; neural sampling must independently resolve the claimed
neural timing. A 0.1-ms simulator tick supplies neither lost carrier phase nor
missing calcium bandwidth. Align stimulus and neural clocks explicitly, retaining
latency rather than fitting it downstream. Use half-open intervals `[t0,t1)` and
bins `[k·dt,(k+1)·dt)` relative to frozen t0: an exact boundary enters the next
bookkeeping bin. These bins do not specify physical emission time. Preserve the
native timestamp t and dispatch at tick `q(t) = ceil((t−t0)/dt)`: an event exactly
on a tick stays on that tick, and dispatch never precedes the recorded event.
At dt=100 µs, source times 0, 99 and 100 µs dispatch at 0, 100 and 100 µs.
Thus the latter two collide at one **dispatch tick**, although they occupy
different acquisition bins. Preserve multiplicity at dispatch or refuse the
incompatible timestep/mode; never boolean-clip events. The deterministic
quantization error lies in `[0,dt)` relative to the declared source clock, with
clock-alignment uncertainty accounted separately. Do not fit away this shift
using downstream responses. Apply the exclusive source end t1 before quantization.
A valid source event that rounds to the run horizon must be retained in an
explicit continuation or cause horizon refusal, never silently dropped; without
a continuation, extend the declared run before admission or refuse that boundary.

For rate models integrate the declared intensity over bins rather than sample an
arbitrary endpoint. Materialize complete events offline and hash them, or use a
vetted deterministic key schedule containing asset hash, algorithm version,
master seed, condition, trial, source/bodyId and absolute bin. Chunk boundaries,
worker order and checkpoint restart must not change realizations. Source data,
ordered identities, transform, generated events and numerical semantics enter
[run identity](adr-run-integrity.md); no historical lock is rewritten.

Independent acceptance cases must prove the transformation, not just internally
consistent hashes. Hand-derived two-source events at zero, bin boundaries and
exclusive end test timing and multiplicity. Close spikes inside 2.2 ms remain
unchanged under event replay or receive an explicit refusal. Strong recurrent
feedback must not add source events under clamp; it must affect a calibrated
membrane-mode control. A one-source/two-target fixture checks exact signed,
weighted, delayed deliveries with no duplicate LIF spike. Constant, step and
analytically integrated sinusoidal rates test integral, latency and aliasing
against formulas independent of production conversion. Statistical tolerances
come prospectively from the chosen process variance and instrument uncertainty,
not invented empirical thresholds. Chunk/restart/reordered-worker tests require
identical per-body event bytes. Negative cases include ×1000 unit errors,
A/B swaps, missing sex/side, unsupported calcium-to-Hz conversion, leaked held-out
animals, altered hashes and out-of-domain stimuli; all refuse before run mutation.

## Logic and architecture make admission explicit

The selector defines candidate anatomy, not a claim that all 146 bodies share
one auditory transfer. D's static-deflection responses and coarse 100–200-Hz
vibration preference do not resolve DA/DP functions or a universal auditory
encoder. Observed train replay is conditional on its measured stimulus/trial;
it is not a reusable sound-to-spike transducer for novel stimuli. A reusable
transducer requires independently validated stimulus-domain transfer evidence.

The causal graph is `stimulus → measured JO output → chemical delivery → central
network`. Source clamping cuts `central feedback → JO output`; excluded recurrent
contacts remain in an audit ledger. Central efferent perturbations therefore
cannot establish effects on JO transduction in this intervention. Such claims
need a new closed-loop sensory-physiology model and protocol.

Admission follows `catalogued → acquired → identity_reviewed → calibrated →
source_validated → frozen → numerically_qualified → protocol_eligible`. Every
transition consumes immutable evidence and emits a decision/reason record.
Missing evidence yields `blocked` at that stage; incompatible units/licence,
identity contradiction, corruption or unsupported domain yields `refused`.
Changing a consumed asset creates a new identity starting at the affected gate;
there is no override from a downstream score. `protocol_eligible` still does not
mean independently validated downstream prediction.

The proposed integration separates `read_native_asset(manifest)` (units, licence,
missingness and checksums), `resolve_body_map(source, dataset)` (explicit identity
rows), `qualify_transfer(source, domain, split)` (scientific admission),
`materialize_source_events(asset, mapping, clock, sampler)` (immutable event
artifact), and `deliver_source_events(events, connectivity, tick)` (accepted
numerical boundary). These are prospective contracts, not existing APIs.
A run invokes the first four before mutating runtime state; the last consumes
only qualified events and preserves chemical edge semantics. A verifier compares
native-to-event transformations and emitted/delivered events using an independent
analytic oracle. Calibration provenance and held-out outcomes remain separate
inputs, with no target-response dependency in source admission.

The [preregistered mathematical controls](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/jo-input-design-2026-10-17/analytic-protocol.md),
[standalone script](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/jo-input-design-2026-10-17/analytic-controls.py) and
[results](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/jo-input-design-2026-10-17/analytic-results.json) supply **six
finite cases and 19 passing assertions**. They expose carrier/envelope ambiguity,
sampling aliasing, amplitude conventions, multiplicity/quantization loss,
underdetermined correlation and normalized-gain ambiguity. These counterexamples
support design refusals; they test no production adapter, biological recording,
calcium forward model or downstream prediction.

## Experimental decisions are fixed before observations

| Experiment                                   | Controlled comparison and recorded outcome                                                                                                                                       | Prospective decision                                                                                                                                                |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source feasibility/pilot                     | Verified JO group/cell identity; native electrical output versus simultaneous calcium where available; baseline/no-drive and actuator artifact controls                          | If spikes or calibrated graded output cannot be recovered at the claimed bandwidth, retain native calcium diagnostic status; do not infer missing events            |
| Physical transfer calibration                | Same-preparation near-fly particle velocity and arista mechanics, multiple amplitudes/carriers spanning the actual protocol domain; sham/no-drive and actuator polarity controls | Accept only calibrated units, geometry, synchronization and domain; unsupported points are refused rather than extrapolated                                         |
| Carrier/envelope separation                  | Factorial carrier changes at fixed envelope and envelope/IPI changes at fixed carrier; baseline, pulse/sine, adaptation/recovery, randomized order                               | Distinguish carrier tuning from envelope following; failure to separate them blocks the claimed carrier-responsive transducer                                       |
| Neural transfer calibration                  | Repeated identified-cell trials across amplitude/carrier matrix, onset/offset, saturation and recovery; preserve native single-cell and population levels                        | Estimate gain/baseline/timing/adaptation only at supported resolution. A population sum cannot become a per-neuron rate                                             |
| Covariance/sex transfer                      | Simultaneous cells where feasible; held-out animals; matched male/female and mating-state blocks if transfer is claimed                                                          | Admit only evidenced correlation and sex/state scope; unmeasured covariance remains an explicit model uncertainty, not empirical independence                       |
| External source validation                   | Animals/acquisition sessions excluded from every calibration choice, preferably another operator/laboratory; preregister error/coverage tests                                    | Pass only prespecified native-unit residual, timing and uncertainty-coverage rules; failure limits domain or blocks transfer without retuning on these observations |
| Numerical qualification after ADR acceptance | Exact event/silent/constant fixtures, recurrent-feedback perturbation, delayed fan-out, count/multiplicity and restart controls                                                  | Preserve prescribed events and expected deliveries exactly where discrete; derive continuous/statistical tolerances independently before execution                  |

Before the pilot, freeze acquisition/identity rules, instrument error accounting,
missing/exclusion policy, response definitions, experimental units, split method
and the algorithm that turns pilot variance into confirmatory sample size. Choose
the target precision or minimum relevant effect and power/error rates from the
scientific claim before confirmatory acquisition; record pilot-derived n before
those trials. No fixed empirical threshold or powered n is defensible from this
source audit alone. Calibration animals cannot reappear as validation animals;
retain failures and acquisition dropouts. If new choices follow an external
validation failure, the next validation needs fresh animals and a new version.

### Prelaunch decision record

Before confirmatory acquisition, freeze the unit of inference as an independent
animal, the calibration/validation animal allocation, the supported stimulus
matrix and endpoint families. Within each animal, estimate absolute firing-rate
residuals in fixed baseline/response windows, onset-latency residuals with a
fixed detection rule, and adaptation residuals as the prospectively defined
late-minus-early response contrast. Native membrane-mode endpoints use physical
voltage/current units instead of an invented rate. Pool repeated trials only
through the declared animal-level estimator; cells and ROIs within an animal
are nested observations, not independent n. Identify every primary
condition × endpoint comparison before observing validation trials.

For each endpoint j, define an equivalence margin δ_j from source/instrument
uncertainty and the scientifically acceptable prediction error, with units and
justification retained. A margin cannot be enlarged after seeing model error.
Compute the preregistered animal-level residual confidence interval with the
chosen coverage and multiplicity adjustment. An interval wholly inside
`[−δ_j, +δ_j]` passes equivalence; wholly outside that interval fails; any overlap
with a boundary is indeterminate. Requiring all primary endpoints to pass defines
the overall pass; any primary failure yields failed, otherwise an indeterminate
endpoint yields indeterminate. A nonsignificant difference never establishes
equivalence. Report each condition even when the overall decision is stopped.

A concrete planning rule is precision-based. For K prespecified primary
comparisons and familywise error α, use α*j = α/K (or another frozen justified
allocation). Given a source-only pilot estimate s_j of the standard deviation
of independent animal residuals and target confidence-interval half-width ε_j,
start with `n_j = ceil((z*(1−α_j/2) · s_j / ε_j)^2)` and take the maximum across
required endpoints. Before confirmation, recalculate upward with the t critical
value at n−1 degrees of freedom until the planned half-width criterion holds;
record the resulting n and pilot variance estimate. Choose ε_j prospectively
relative to δ_j and a justified planning residual, so the intended interval can
fit inside the equivalence region. This rule plans precision, **not guaranteed
equivalence power**. If a power claim is required, specify an assumed true
animal-level residual, target power and a prospective equivalence-power analysis;
the precision formula cannot replace it. Small/nonrepresentative pilots,
non-normal residuals, clustering, exclusions and uncertainty in s_j require a
prespecified conservative variance bound or simulation-based planning under the
chosen analysis model. Freeze attrition handling and maximum recruitment; do not
stop opportunistically when equivalence first appears.

Missing calibration, bandwidth, licensing, subgroup coverage or sex-transfer
evidence yields **blocked** before confirmatory comparison. Adequate measurements
showing a residual interval outside its margin yield **failed**. Adequate-domain
measurements with insufficient precision yield **indeterminate**. These states
cannot be exchanged by relabeling acquisition exclusions. A narrower A/B or
female-only source can support an explicitly restricted experiment but cannot
close the full MaleCNS A/B/D requirement. Reconstruction's missing right D bodies
remain absent; do not invent them or claim full biological bilateral coverage.
No Baker/Pacheco target response enters endpoint selection, tolerance, sample-size
planning, exclusions, source-transfer fitting or subsequent reconsideration.

Downstream experiments are later: compare the qualified input with constant-rate,
spike-silent, envelope-only and correlation-assumption controls under a fresh
prospective protocol, with simpler stimulus-following baselines and independent
negative controls. These controls identify which input features matter; they
cannot be selected by inspecting Baker/Pacheco responses. A successful input
qualification permits proposal of those experiments, not their automatic scoring.

## Acquisition and review precede a new experiment

| Step and owner                       | Reviewable artifact                                                               | Pass or refusal                                                                                                                |
| ------------------------------------ | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Project owner                        | Accepted or superseding ADR and explicit scientific scope                         | No runtime change before acceptance; a narrower subgroup scope must be explicit and cannot silently close all-A/B/D protocol 6 |
| Source curator                       | JO-only acquisition allowlist, licence/access audit and request draft             | Verify original trials/calibration; exclude downstream/Baker/Pacheco responses. No external request has been sent              |
| Physiology collaborator              | Electrical/spike availability assessment or new calibration protocol              | Native events/rates or calibrated membrane with exact stimulus domain and identity; calcium alone stays diagnostic             |
| Identity reviewer                    | BodyId map, driver coverage and sex-transfer ledger                               | Resolve or explicitly exclude ambiguity; no artificial subtype/side population                                                 |
| Source-analysis owner                | Frozen source-only transfer, animal-separated validation and uncertainty criteria | Validate absolute units, latency, adaptation and relevant covariance; unsupported transfer refuses                             |
| Runtime implementer after acceptance | Minimal versioned source boundary plus independent analytic tests                 | Exact prescribed/emitted events and downstream delivery; deterministic restart; no v1 regression                               |
| Scientific owner                     | New prospective protocol and later manifest-v2 proposal                           | S0/readout eligibility, fresh held-out partition and independent simpler/null controls before any target-response access       |

First pursue original JO trials from Wilson/Kamikouchi sources and the public
Yamakoshi JO-only file inventory, checking allowlists before archive inspection.
Request waveform, mechanics, clocks, electrical traces if available, unnormalized
fluorescence otherwise, anatomical verification, animal state and reuse terms.
If a new experiment is necessary, first establish whether identified JO output
is spiking or graded and whether it is technically recordable. Synchronize native
neural acquisition, near-fly acoustics and same-preparation arista mechanics;
include baseline, randomized carrier/amplitude/pulse conditions spanning the exact
protocol domain, recovery and adaptation blocks. Pilot variance determines a
later preregistered sample size; historical stimulus frequencies do not supply
one. An independently validated paired electrical/calcium calibration is needed
if only fluorescence is ultimately available.

This sequence completes the design while leaving source eligibility honestly
blocked. Input qualification alone does not make Baker eligible, resolve its
sex/readout gates, authorize a new lock, or turn physiological success into
behavioral M4 completion.
