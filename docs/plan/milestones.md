# Evidence-gated delivery milestones

Status: **native milestones provisioned and open issues routed**, 2026-10-27. This is the delivery plan for the [roadmap](../roadmap.md#completion-plan), not a new scientific protocol, calibrated model or source of experimental verdicts. Historical locks, scored results, `w_syn=0.192` and `th_jump=0` are unchanged. Do not infer biological fidelity from GPU parity, anatomical rendering, geometry, wiring shuffles or a synthetic closed loop.

## Baseline and conventions

- `main` at this consolidation: `f5e3709` (merged [#230](https://github.com/gianlucamazza/flymsg/pull/230)). [#227](https://github.com/gianlucamazza/flymsg/pull/227) and [#230](https://github.com/gianlucamazza/flymsg/pull/230) land the diagnostic bounded skeleton renderer. The 16 MiB motion campaign is a veto, not a headset cadence admission, and does not meet the exit of [#177](https://github.com/gianlucamazza/flymsg/issues/177) or [#24](https://github.com/gianlucamazza/flymsg/issues/24). The planning baseline was `fd0ab7a` (merged [#221](https://github.com/gianlucamazza/flymsg/pull/221)). [#40](https://github.com/gianlucamazza/flymsg/issues/40) is closed after its worker baseline; unfinished adversarial Series S hardware cases are tracked separately in [#224](https://github.com/gianlucamazza/flymsg/issues/224). [#226](https://github.com/gianlucamazza/flymsg/pull/226) and [#228](https://github.com/gianlucamazza/flymsg/pull/228) add the dimensional unit check and do not meet the exit of [#148](https://github.com/gianlucamazza/flymsg/issues/148).
- **Native GitHub milestones are live:** S0–S4 and H1–H2 were created on 2026-10-27, without due dates. The earlier baseline below remains historical evidence. Planning is not scientific acceptance.
- Current implementation baseline: `021e4be7a7d94f86df3ea54af9cc7e51cbb75be5`, merged #300/#301; see the [optic audit and O01–O15 evidence matrix](../report/optic-system-audit-2026-10-27.md).
- Each existing open issue has **one primary milestone** (index below). It may block other milestones as a dependency without being duplicated or closed early. Closed issues and merged PRs are historical evidence, not outstanding work.
- **Entry** means prerequisites that must exist before a confirmatory run. **Exit** requires an immutable artifact, an independently specified checker, explicit pass/fail/indeterminate/blocked verdict, and an issue-specific acceptance decision. `blocked` is honest progress, **not completion**.
- A no-go or failed model result is publishable and does not authorize changing a frozen lock, repurposing a held-out dataset for tuning or asserting validated animal behavior. Propose a new preregistered version only with new evidence.
- **Dates are intentionally unset.** External biological evidence and physical device access are not predictable deadlines. Review status when evidence is acquired and at each merged milestone-related PR.

## Critical path (science)

`S0 numerical reliability → S1 sourced sensory physiology → S2 evidenced sensorimotor interfaces → S3 independent held-out prediction → S4 external replication and claims audit`.

S1 and S2 can conduct independent source audits in parallel. Their **scientific acceptance** cannot bypass S0's model-specific numerical gates. S3 requires a locked, testable prediction and eligible untouched data; S4 may reproduce historical outcomes earlier, but its final claims sign-off depends on S3.

### S0 — Numerical reliability and identifiability (P0)

**Owner issues:** [#148](https://github.com/gianlucamazza/flymsg/issues/148). Related native semantics: [#39](https://github.com/gianlucamazza/flymsg/issues/39).

**Evidence already available:** convergence v1 passes its preregistered battery criterion; weak-pathway sugar → MN9 first-spike latency _does not converge_ (35.3 ms at 0.1 ms versus 77.4 ms at 0.025 ms). Sensitivity-grid identifiability remains post-hoc, with no biological parameter distributions or credible intervals. Seven positive battery cases exceed 199 degree-preserving rewires, a topology-specific result only.

**Work:** `flymsg.units` parses every evidence-registry unit and reads the live `sim._constants` and `sim.graded_arrays` values (decays, `gv`, kick, graded count). That check does not satisfy the exit below. Path-metrics v1 already froze latency, jitter, recruitment and rate and archived the 0.1 ms verdicts. Uncertainty propagation stays refused until a measured distribution exists. Shuffle baselines v1 are archived. Numerical-mode coverage stays with #39, and convergence v1 stays as archived.

**Exit:** reproduce and independently audit the archived verdicts, record all nonconvergent or unidentifiable outputs and provide a defensible numerical eligibility decision _per prospective biological observable_. An unqualified observable stays excluded from S1/S3 scoring. **No invented intervals**.

### S1 — Sourced sensory and circuit physiology (P0)

**Owner issues:** [#34](https://github.com/gianlucamazza/flymsg/issues/34), [#84](https://github.com/gianlucamazza/flymsg/issues/84), [#85](https://github.com/gianlucamazza/flymsg/issues/85), [#97](https://github.com/gianlucamazza/flymsg/issues/97), [#140](https://github.com/gianlucamazza/flymsg/issues/140).

**Evidence already available:** T4/T5 v4 remains `robust: neither`, giant-fiber looming v1/v2 and APL-claw v1 are uninformative, song v1 stopped before held-out data. Optional gap/graded kernels are implementations, not measured in-vivo conductances or release curves.

**Work:** build sourced observation/transfer contracts for at least one eligible modality (e.g. visual motion, looming, odor/APL), including cell identity, sex, stimulus geometry, units, gain/kinetics, measurement type, trial variability, and calibration-versus-holdout separation. Validate alternatives against simpler stimulus-following models and negative controls. Audit what cannot be mapped; do not convert calcium signals into Hz by fiat.

**Exit:** at least one independently defensible sensory/neural input/output comparison is _eligible for prospective scoring_ with a frozen protocol. If source/registration/observation semantics remain absent, mark S1 blocked; an engineered Poisson encoder does not pass.

**JO progress (2026-10-17):** protocol 6 now has a [source/identity/input design](../jo-measured-input-design.md)
and [accepted ADR](../adr-measured-jo-input.md). The 146 selected MaleCNS bodies
are an anatomical population, not 146 measured transfer functions. Absolute
source calibration and sex transfer remain blocked; runtime implementation is
blocked on a measured source. This advances S1 design, not its scientific exit.

### S2 — Evidenced body coupling and causal geometry (P0)

**Owner issues:** [#19](https://github.com/gianlucamazza/flymsg/issues/19), [#31](https://github.com/gianlucamazza/flymsg/issues/31), [#35](https://github.com/gianlucamazza/flymsg/issues/35), [#176](https://github.com/gianlucamazza/flymsg/issues/176), [#179](https://github.com/gianlucamazza/flymsg/issues/179), [#180](https://github.com/gianlucamazza/flymsg/issues/180).

**Evidence already available:** versioned 6-DoF frames, column optics, FlyGym/NeuroMechFly adapter, five-arm _synthetic_ causal loop and deterministic checkpoint/replay. The MaleCNS eye-to-body registration and the neuron → muscle → joint/actuator/force/timing chain remain unqualified. Every unsupported `validation/motor_map.yaml` path stays `unmapped`.

**Work:** independently qualify optical projection and its error bounds under fixed/moving poses, then obtain sourced coordinate registration and motor mapping/actuator evidence. Verify later sensor observations depend causally on preceding body motion against intact, open-loop, disconnected, shuffled and replayed controls. Archive real units, provenance, restart/failure traces and positive _or null_ outcomes.

**Exit:** qualified world → eye → sensory → neuron → muscle → actuator → body → later world/eye path for the **specifically mapped** channel, with no engineered link mislabeled as physiological. Without both sourced sensory and motor links, retain the synthetic loop and mark biological S2 blocked.

### S3 — Prospective independent physiological and behavioral tests (P0)

**Owner issues:** [#36](https://github.com/gianlucamazza/flymsg/issues/36), [#149](https://github.com/gianlucamazza/flymsg/issues/149), [#150](https://github.com/gianlucamazza/flymsg/issues/150).

**Entry:** an S0-eligible observable, S1/S2 interfaces needed by the selected task, independent accessible measurements, blinded or frozen calibration/ holdout partition, exact negative-control and simpler-model baselines.

**Work:** preregister one falsifiable neural/behavioral target before data inspection. Record exact provenance, trial variation, eligibility tests, statistical thresholds, effect sizes and adverse/null outcomes. Compare model variants only by separate prospective protocols; do not rewrite or reuse held-out files from earlier no-go experiments.

**Exit:** publish an independently scored preregistered test with a reproducible pass/fail/indeterminate/no-go and all controls. **Only a pass against untouched animal observations** satisfies the project's stated behavioral-completion claim. A properly documented failed or blocked run is valuable research but does not close that claim.

**Dated progress (2026-10-17):** the [Baker audit](../baker-crossmatch.md) completes
anatomical routes for 12 of 28 classes, including the still-excluded dimorphic
AVLP_pr36; 14 remain partial and two absent. The [M4 v2 proposal](m4-v2-proposal.md)
records a scoped basis for noncommercial local analysis and publication review.
This advances candidate identification, not S3 qualification: sex compatibility,
[qualified measured JO input](../jo-measured-input-design.md), observable qualification and the prospective partition/lock
remain required. No response data were opened or benchmark scored.

### S4 — External reproduction and claim audit (P1; mandatory for research release)

**Owner issue:** [#151](https://github.com/gianlucamazza/flymsg/issues/151).

**Work:** package exact lock/code/data/acquisition/license and hashes, parameter evidence, independent checker, golden positive, negative and no-go examples, artifact-integrity verifier and documented environment. Arrange a clean-clone execution by an operator/machine distinct from the authoring workspace. Classify each public statement as software, anatomical, physiological, causal or independent-animal evidence.

**Exit:** independently signed results and a machine-readable exception ledger, with failures/unavailable licensed inputs explicitly recorded. Local CI or clean re-reads on the authoring machine do **not** close S4. External reproduction of a failed biological result is still valid replication; it does not turn that result into a successful animal prediction.

## Parallel engineering milestones (not scientific prerequisites)

### H1 — Qualified native execution and physical console recovery

**Owner issues:** [#39](https://github.com/gianlucamazza/flymsg/issues/39) and [#224](https://github.com/gianlucamazza/flymsg/issues/224). Closed [#40](https://github.com/gianlucamazza/flymsg/issues/40) retains the worker baseline.

**Available:** full-connectome GPU/CPU bit parity in measured runs; 12 version-1 plus 60 supported version-2 fixture cases bit-identical on physical Series S, with 12 declared dynamic-clamp refusals. The 2,048-neuron ordinary `both` lifecycle qualifies cancel, suspend and resume; a [noncooperative process kill](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-hardstop-2026-10-18.json) recovers bit for bit with and without a checkpoint. An [API-induced device removal](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-gpufault-2026-10-18.json) is handled and recovered bit for bit; a hardware GPU fault is not qualified. A native publish whose temporary file does not grow is recorded as `failed` and is not replaced. The graded million-step publish that stayed in `checkpointing` with an empty temporary file was not rerun and does not meet the exit of [#224](https://github.com/gianlucamazza/flymsg/issues/224). The [sustained v1 full-connectome workload](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-sustained-2026-10-16.json) passes cold/warm setup and four back-to-back 500,000-step jobs per stimulus bit for bit, at median advance rates of 2,649 steps/s looming and 3,693 steps/s bitter without throughput decline.

**Exit:** adversarial numeric and resource boundaries; independently verified noncooperative termination and GPU/device-fault recovery; sustained representative load, transfer/OS/GPU memory and physical input evidence. If device fault cannot safely be injected, document a separate unqualified gate. No conflation of synthetic throughput with full-CNS real-time or neuromechanical parity.

### H2 — Full-fidelity 3D viewer and physical WebXR qualification

**Owner issues:** [#24](https://github.com/gianlucamazza/flymsg/issues/24) and [#177](https://github.com/gianlucamazza/flymsg/issues/177).

**Available:** the merged [#221](https://github.com/gianlucamazza/flymsg/pull/221) records source-attested Wi-Fi Quest A/B/B/A trials, rejects the 4 MiB paged approach on three valid dense blocks, and includes an **exploratory** bounded-error original-skeleton-path prototype (not production enabled). Merged [#227](https://github.com/gianlucamazza/flymsg/pull/227) and [#230](https://github.com/gianlucamazza/flymsg/pull/230) keep that renderer diagnostic. The recorded 16 MiB anatomical-motion campaign vetoes the candidate (median p95 ratio 1.409) and does not meet the exit of [#177](https://github.com/gianlucamazza/flymsg/issues/177) or [#24](https://github.com/gianlucamazza/flymsg/issues/24). The earlier complete-content partial 90 Hz session failed timing.

**Exit:** original-quality correctness plus strict visual/error budgets on real selected anatomy, physical phone cold/warm/memory baseline, repeatable eligible headset cadence and stereo/session/context-loss/ sustained thermal tests. Separately qualify any alternative renderer or bounded-error representation under its own ADR. A fast empty/incomplete scene, background tab or changed quality is not a pass.

## Native milestone assignment (2026-10-27)

The 27 open delivery issues have one native milestone each. [#265](https://github.com/gianlucamazza/flymsg/issues/265) remains a coordination board without a delivery milestone. Closed milestone `Next` is preserved.

| Native milestone | Primary open issues | Execution index |
| --- | --- | --- |
| [S0 — Numerical reliability](https://github.com/gianlucamazza/flymsg/milestone/2) | #148 | #148 |
| [S1 — Sensory/circuit physiology](https://github.com/gianlucamazza/flymsg/milestone/3) | #34, #84, #85, #97, #140, #302, #303, #304 | #97; eye work in #84 |
| [S2 — Body coupling/geometry](https://github.com/gianlucamazza/flymsg/milestone/4) | #19, #31, #35, #176, #179, #180, #263, #305, #306 | #176 |
| [S3 — Independent validation](https://github.com/gianlucamazza/flymsg/milestone/5) | #36, #149, #150 | #149 neural; #150 behavioral |
| [S4 — External replication](https://github.com/gianlucamazza/flymsg/milestone/6) | #151 | #151 |
| [H1 — Native/console](https://github.com/gianlucamazza/flymsg/milestone/7) | #39, #224 | #39 software; #224 physical |
| [H2 — Viewer/WebXR](https://github.com/gianlucamazza/flymsg/milestone/8) | #24, #177, #307 | #24 software; #177 physical |

Each issue retains its present open/closed state, historical result and evidence blockers. The set must be refreshed when issues change, rather than pretending this snapshot is a live GitHub query.

## Optic completion work packages

Only six new issues were needed; existing issues retain circuit, body, validation and hardware ownership. Each new issue contains a verifiable requirement, scope, dependencies, acceptance checks and evidence limits.

| New issue | Work and priority | Dependencies / admission |
| --- | --- | --- |
| [#302](https://github.com/gianlucamazza/flymsg/issues/302) | P0: recover and verify physiological sources from a clean clone | Authoritative licensed sources; hashes, provenance and calibration/holdout partition. Unavailable inputs remain unavailable. |
| [#303](https://github.com/gianlucamazza/flymsg/issues/303) | P0: assignment ambiguity and anatomical uncertainty | #84/#179 registration; #148 uncertainty semantics. Candidate vote support is not a measured probability. |
| [#304](https://github.com/gianlucamazza/flymsg/issues/304) | P0: luminance, adaptation, recovery and noise | #302 source eligibility, #97 release contract, #148 identifiability/convergence. No data means physiological no-go, not invented parameters. |
| [#305](https://github.com/gianlucamazza/flymsg/issues/305) | P1: multi-object optics and independent 6-DoF error bounds | Synthetic geometry can proceed now; real-anatomy claims require #303 and #84/#179 measured registration. |
| [#306](https://github.com/gianlucamazza/flymsg/issues/306) | P1: synchronized retinal, voltage, release and circuit traces | Existing #180 scheduler and #97 graded semantics; bounded observer with renderer-on/off identity. |
| [#307](https://github.com/gianlucamazza/flymsg/issues/307) | P1: bilateral visual field and stimulus-response replay | #306 recording contract; #24 performance and #177 physical XR acceptance. Synthetic fixtures permit UI work now. |

### Requirement ownership and completion gates

This routes the audit requirements; it does not upgrade any audit verdict.

| Audit requirements | Canonical issues | Outstanding acceptance |
| --- | --- | --- |
| O01–O03: anatomy, missingness, sources | #84, #303, #302 | Quantified ambiguity, explicit missing masks, reproducible eligible sources |
| O04–O05: frames and optics | #84, #179, #303, #305 | Independent measured registration or UNKNOWN; qualified geometric error bounds |
| O06–O09: luminance, graded release, cell transfers and adaptation | #84, #97, #302, #304 | Evidence ledger for R1–R8, L1–L5, Mi1/Mi4/Mi9, Tm1/Tm2/Tm3/Tm9; identifiable kinetics, histamine sign and observation contract |
| O10: T4/T5 and directional subtypes | #140, #97, #148, #149 | Prospective ON/OFF, direction, contrast, speed, latency and seed robustness; independent held-out comparison; preserve failed v4 |
| O11: LC4/LPLC2, central and descending paths | #34, #97, #149, #263 | Eligible retinal-to-target transfer and independently specified readouts, including nulls; no forced spikes |
| O12–O13: runtime causality and body feedback | #180, #176, #19, #31, #35, #36, #306 | Single scheduler, reproducible interventions and later retinal change; sourced motor coupling for biological claims |
| O14: synchronized observer and XR | #306, #307, #24, #177 | Actual recorded voltage/release, eye-specific missingness, replay identity; physical device evidence |
| O15: numerical and scientific qualification | #148, #149, #150, #151 | Per-observable convergence, ablations, identifiability, justified uncertainty, held-out data and independent replication |

### Execution order and blocked work

1. Start #302 source recovery, #303 ambiguity audit and #148 observable qualification. In parallel, #305 synthetic geometry and #306 trace engineering need no physiological tuning.
2. Implement #307 against the versioned #306 contract. Continue #24/#177 and #39/#224 qualification only with eligible hardware evidence.
3. Admit source-supported #304 and #97 models only after source and identification gates. Lock new #140/#149 experiments before scoring; historical locks remain immutable.
4. Qualify full-network #180 causal propagation and body feedback with positive and negative controls. Synthetic engineering acceptance remains separate from #19/#35 biological motor admission. Reconcile #263 historical tracking with merged evidence and #297 before any new experiment.
5. Run eligible independent neural/behavioral comparisons under #149/#150/#36, then external clean-clone replication and claims sign-off under #151.

The earlier S1 exit of “at least one modality” is an initial gate, **not total optic completion**. The full optic goal requires a scoped disposition for every O01–O15 requirement and acceptance of every claimed function. Record results as **MEASURED / VALIDATED / INFERRED / SYNTHETIC / UNKNOWN / FAILED**, specifying whether VALIDATED refers to software or independent physiology. A documented no-go completes an investigation deliverable but does not satisfy a biological claim or close its unresolved parent gate. No percentage or deadline substitutes for missing evidence.

## Execution and change-control protocol

1. For each milestone, nominate one issue as the execution index; keep implementation work and evidence requests on their existing issues.
2. Audit exact external data eligibility and model/source identity before drafting a new experimental lock. Publish the lock and independent gates on `main` **before** starting the scored run from a clean commit.
3. Separate each PR by one coherent boundary: protocols versus runs versus implementation; native/Quest qualification versus scientific outputs.
4. Require Ruff/pytest, relevant JS/native tests, documentation formatting, and reproducible checks appropriate to modified files. A passing GitHub status is not evidence of physical hardware that CI cannot exercise.
5. Attach raw checksummed evidence, negative results, observed units/variance, and a source-specific limits statement; leave failed/blocked items open.
6. Report at review: **delivered / verified / failed / blocked / next evidence request**. No percentage-complete estimates for unsolved biological inference.
