# Evidence-gated delivery milestones

Status: **proposed for review**, 2026-10-16. This is the delivery plan for the [roadmap](roadmap.md#completion-plan), not a new scientific protocol, calibrated model or source of experimental verdicts. Historical locks, scored results, `w_syn=0.192` and `th_jump=0` are unchanged. Do not infer biological fidelity from GPU parity, anatomical rendering, geometry, wiring shuffles or a synthetic closed loop.

## Baseline and conventions

- `main` at this consolidation: `1123a63` (merged [#228](https://github.com/gianlucamazza/flymsg/pull/228)). The planning baseline was `fd0ab7a` (merged [#221](https://github.com/gianlucamazza/flymsg/pull/221)). [#40](https://github.com/gianlucamazza/flymsg/issues/40) is closed after its worker baseline; unfinished adversarial Series S hardware cases are tracked separately in [#224](https://github.com/gianlucamazza/flymsg/issues/224). Draft [#227](https://github.com/gianlucamazza/flymsg/pull/227) is open and is not an accepted result. [#226](https://github.com/gianlucamazza/flymsg/pull/226) and [#228](https://github.com/gianlucamazza/flymsg/pull/228) add the dimensional unit check and do not meet the exit of [#148](https://github.com/gianlucamazza/flymsg/issues/148).
- **Milestone IDs below are planning identifiers**, not claims that GitHub's native Milestone objects have been created or that target dates have been committed. Issue descriptions and this index provide traceability until native objects are explicitly provisioned.
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

### S4 — External reproduction and claim audit (P1; mandatory for research release)

**Owner issue:** [#151](https://github.com/gianlucamazza/flymsg/issues/151).

**Work:** package exact lock/code/data/acquisition/license and hashes, parameter evidence, independent checker, golden positive, negative and no-go examples, artifact-integrity verifier and documented environment. Arrange a clean-clone execution by an operator/machine distinct from the authoring workspace. Classify each public statement as software, anatomical, physiological, causal or independent-animal evidence.

**Exit:** independently signed results and a machine-readable exception ledger, with failures/unavailable licensed inputs explicitly recorded. Local CI or clean re-reads on the authoring machine do **not** close S4. External reproduction of a failed biological result is still valid replication; it does not turn that result into a successful animal prediction.

## Parallel engineering milestones (not scientific prerequisites)

### H1 — Qualified native execution and physical console recovery

**Owner issues:** [#39](https://github.com/gianlucamazza/flymsg/issues/39) and [#224](https://github.com/gianlucamazza/flymsg/issues/224). Closed [#40](https://github.com/gianlucamazza/flymsg/issues/40) retains the worker baseline.

**Available:** full-connectome GPU/CPU bit parity in measured runs; 12 version-1 plus 60 supported version-2 fixture cases bit-identical on physical Series S, with 12 declared dynamic-clamp refusals. The 2,048-neuron ordinary `both` lifecycle qualifies cancel, suspend and resume, not hard death or GPU fault.

**Exit:** adversarial numeric and resource boundaries; independently verified noncooperative termination and GPU/device-fault recovery; sustained representative load, transfer/OS/GPU memory and physical input evidence. If device fault cannot safely be injected, document a separate unqualified gate. No conflation of synthetic throughput with full-CNS real-time or neuromechanical parity.

### H2 — Full-fidelity 3D viewer and physical WebXR qualification

**Owner issues:** [#24](https://github.com/gianlucamazza/flymsg/issues/24) and [#177](https://github.com/gianlucamazza/flymsg/issues/177).

**Available:** the merged [#221](https://github.com/gianlucamazza/flymsg/pull/221) records source-attested Wi-Fi Quest A/B/B/A trials, rejects the 4 MiB paged approach on three valid dense blocks, and includes an **exploratory** bounded-error original-skeleton-path prototype (not production enabled). The earlier complete-content partial 90 Hz session failed timing.

**Exit:** original-quality correctness plus strict visual/error budgets on real selected anatomy, physical phone cold/warm/memory baseline, repeatable eligible headset cadence and stereo/session/context-loss/ sustained thermal tests. Separately qualify any alternative renderer or bounded-error representation under its own ADR. A fast empty/incomplete scene, background tab or changed quality is not a pass.

## Open-issue primary assignment (2026-10-16)

The following 20 issues are assigned **only in this plan**:

- **S0:** #148.
- **S1:** #34, #84, #85, #97, #140.
- **S2:** #19, #31, #35, #176, #179, #180.
- **S3:** #36, #149, #150.
- **S4:** #151.
- **H1:** #39, #224.
- **H2:** #24, #177.

Each issue retains its present open/closed state, historical result and evidence blockers. The set must be refreshed when issues change, rather than pretending this snapshot is a live GitHub query.

## Execution and change-control protocol

1. For each milestone, nominate one issue as the execution index; keep implementation work and evidence requests on their existing issues.
2. Audit exact external data eligibility and model/source identity before drafting a new experimental lock. Publish the lock and independent gates on `main` **before** starting the scored run from a clean commit.
3. Separate each PR by one coherent boundary: protocols versus runs versus implementation; native/Quest qualification versus scientific outputs.
4. Require Ruff/pytest, relevant JS/native tests, documentation formatting, and reproducible checks appropriate to modified files. A passing GitHub status is not evidence of physical hardware that CI cannot exercise.
5. Attach raw checksummed evidence, negative results, observed units/variance, and a source-specific limits statement; leave failed/blocked items open.
6. Report at review: **delivered / verified / failed / blocked / next evidence request**. No percentage-complete estimates for unsolved biological inference.
