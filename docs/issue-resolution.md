# Open-issue resolution ledger — 2026-10-16

Execution of the owner's accepted issue-resolution plan. Baseline: clean `main`
`b5c6d3b`, 20 open issues, no open PRs, tests/native/pages CI successful.
PRs #205 and #215 are merged; their prior draft descriptions are historical.
Merge, local tests, physical qualification and biological evidence are separate gates.

## Engineering work and exit criteria

| Issues    | Delivered or already present                                                                                                                                            | Remaining acceptance                                                                                                                                       |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #39       | GPU v2 implementation #215; both native and console collectors now require the explicit full matrix, not just a passing count; downloaded GPU output hashes are checked | Physical 12 v1 + 60 v2 parity, adversarial numeric cases, exact worker/shader identity; preserve 12 explicit clamp refusals                                |
| #40       | Existing v1 lifecycle; selectable `--extension none/graded/gap/spikelets/both/gap-all-free` for separate v2 lifecycle trials                                            | Physical long-run/cancel/suspend/restart per selected mode, gamepad B, hard termination/device fault, memory/thermal trials and old/new-worker negotiation |
| #177      | Experimental observer and immutable uploads #205, independent software geometry/image checks                                                                            | Complete surfaces and skeletons separately on Quest; stereo, head motion, immersive recovery, repeated entry/exit, memory and thermal evidence             |
| #24       | Desktop baseline already archived                                                                                                                                       | Physical phone cold/warm timing and memory; no new mobile default before measurement                                                                       |
| #179      | Independent Sobol ray and six rendered-camera cases; pure frame/unit and geometric boundary tests                                                                       | Real eye→body registration with provenance and uncertainty; synthetic identity cannot close this gate                                                      |
| #180      | Five arms, causal pose→later optics, exact replay, body-fault interruption/resume and immutable CLI outputs tested                                                      | Real-renderer on/off comparison, representative full-connectome resource/timing measurement and qualified physiological chain                              |
| #31, #176 | Existing M0/G1 contracts and single runtime/body/clock/runstore reused                                                                                                  | Keep engineering E0, evidenced sensory/motor E1 and held-out behavior E2 distinct; only close umbrellas after their children                               |
| #151      | Replication index fixed for GF/song locks; source-bound protocol/output audit and machine-readable exceptions                                                           | Independent operator/machine reproduces positive, negative and stopped-before-holdout results; input eligibility/licences and independent sign-off         |

## Scientific evidence requests

No new scored run or tuning is authorized by an incomplete evidence table. Each new
protocol must identify primary source/accession, file hash/licence, sex/preparation,
units, cell mapping, uncertainty and measured/inferred/compensatory/unknown status.
The [existing literature audit](leads.md) distinguishes inaccessible/not-found inputs
from a demonstrated absence of measurements; it is not a substitute for data.

| Issues         | Bounded next deliverable                                                                                                                                                                    | No-go                                                                                                           |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| #84, #97, #140 | Audit v4 traces by cell type, polarity, direction and timing; table of retinal registration, LMC/medulla release and type-specific filters; prospective v5 hypotheses and matched ablations | Missing release curves remain unknown; do not fit to Gruntman holdout or change v4 `robust: neither`            |
| #85            | Separate electrical, modulatory and APL/KC claims; prevalidate a readout with dynamic range in both APL-on and APL-off arms; quantify soma/claw distinction and odor overlap                | No gap conductance inferred from EM counts, calcium→Hz conversion or global gain retune; v1 stays uninformative |
| #34            | Source LC4/LPLC2 kinetics and an observation model; assess whether recordings discriminate circuit timing from onset/stimulus-following baselines                                           | No v3 without eligible source/holdout separation; preserve v1/v2 no-go/uninformative                            |
| #19, #35, #150 | One TTMn→muscle→real joint→actuator chain, with force/time course and sex/model uncertainty; resolve type-level versus neuron-level MANC discrepancies before per-neuron use                | Missing actuator/joint or force remains unmapped; female-body/male-connectome uncertainty stays explicit        |
| #36, #149      | One eligible independent physiological comparison; auditory tuning and stable model discrimination before song holdout, or another prospectively locked eligible circuit                    | Song v1 stays stopped; physiology cannot close behavioral M4; do not open held-out data to choose a mechanism   |
| #148           | Separate prospective weak-pathway latency/recruitment convergence, parameter sensitivity, identifiability and uncertainty protocols                                                         | Do not extend the existing rate/verdict convergence claim to latency or manufacture uncertainty ranges          |

For SF2, the next protocol proposal must fix reference dt, seed partition, response
windows, latency/recruitment/rate metrics and failure/indeterminate rules before a run.
Sensitivity ranges must come from evidence records; unsupported ranges are labelled
engineering envelopes. Identifiability compares distinct parameter sets/mechanisms
against the same outputs and simple follower/null models. Uncertainty propagation
retains correlations and mapping uncertainty; absent distributions block a biological
interval rather than becoming invented point estimates. Thresholds need a prospective
lock; this ledger is not that lock and changes no existing score.

## Physical trial procedure

Use exact source, package, shader and input hashes and a new output directory for each
trial. Keep all partial and failed attempts. Ordinary suspension is not a GPU fault;
hard-termination recovery must prove that a completed checkpoint is valid, partial
output is quarantined and the resumed result equals an uninterrupted independent
oracle. Never inject a fault into another owner's job or globally reset shared devices.

Console v2 parity uses `scripts/console_gpu_parity.py --v2 --package PFN --shader
LIF_CSO --out NEW_DIRECTORY`. Lifecycle uses `scripts/console_lifecycle.py --extension
EXTENSION --package PFN --aumid AUMID --shader LIF_CSO --lineage LINEAGE_JSON --out
NEW_DIRECTORY`. A selectable mode is instrumentation, not a passed hardware trial.
Retain CPU-vs-console end-to-end latency including preparation/upload/download; the
existing battery does not establish a console throughput advantage.

Quest trials follow [the accepted profile](vee-qualification.md) and
[candidate procedure](quest-paged-pipeline.md): complete content first, actual measured
refresh, p95 ≤ 1.1 frame budgets, p99 ≤ 2 budgets, estimated missed slots ≤ 1%.
Keep estimates distinct from compositor drops and UI diagnostics from stereo timing.
USB or Wi-Fi ADB connectivity is not evidence that Browser is visible or the headset
awake. No frames, incomplete uploads, changed representation or absent refresh cannot
pass. A rejected surface selection is unsupported, not permission to reduce anatomy.

Wireless ADB can be enabled over the authorized USB transport with `adb -P 5038 -s
USB_SERIAL tcpip 5555`, then `adb -P 5038 connect QUEST_IP:5555`; select the resulting
`QUEST_IP:5555` explicitly. New trials retain their transport identity. Reverse/forward
mappings are owned per trial; do not restart the shared TV ADB server. Restoring USB-only
debugging uses `adb -P 5038 -s QUEST_IP:5555 usb` when wireless testing is finished.

## Verification and closure

### Recorded hardware outcomes

- [Series S v2 parity](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-gpu-v2-2026-10-16.json):
  12 v1 + 60 v2 cases passed, with 12 expected clamp refusals. Raw artifacts,
  source/shader identities and an independent float-bit/oracle verifier are archived.
- [Series S v2 lifecycle](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-lifecycle-v2-2026-10-16.json):
  `both`, 2,048 neurons, 1,000,000 steps, about 36,897 steps/s; cancellation at
  39,168, suspension checkpoint at 36,032 and byte-identical resumed completion.
  This is a synthetic fixture, not full-connectome throughput.
- [Quest hardware attempt](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/quest2-qualification-2026-10-16.json):
  all 1,128 skeletons/8,258,589 source segments loaded. The partial 90 Hz session
  failed: 198 active intervals, p50 100.201 ms, p95 723.923 ms, p99 773.669 ms,
  estimated missed slots 94.58%. Content checks passed. The later aggregate mixes
  72/90 Hz and is indeterminate. Neither is a completed qualification matrix.
  Zero-callback diagnostics and failed/sleeping attempts remain unscored.
- [Forced-stop attempt](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-force-stop-attempt-2026-10-16.json):
  interrupted before a verified recovery state; status/recovery file access failed.
  Another console artifact was signed during the attempt, so deployment interference
  is not excluded. This does not establish a worker defect or qualify hard termination.
  The collector now persists stage progress, rejects source drift, and refuses to upload
  resume without a verified parked state. A new exclusively owned trial is required.

Run unit tests before integration, then the repository's lint/format/Python/JS/site-link
checks. Collector regression tests must reject missing/duplicate cases, unexpected
refusals, wrong refusal reasons, failed parity and output checksum mismatches. The
archive audit must detect source/lock mismatch, missing/extra output and corruption.

Issue bodies may be corrected to the verified merge/status record now. Hardware and
scientific boxes remain unchecked until their exact evidence exists. External replica
sign-off cannot be supplied by another local checkout or by this session.

### Follow-up instrumentation — 2026-10-16

The Quest desktop collector now checks actual loaded module hashes against its
checkout, the exact page URL, page visibility, full anatomy and GPU readiness
before measuring. The headset collector independently checks Android wakefulness,
retains each preflight, and excludes the configuration after three consecutive
invalid preflights. Its optional `--keep-awake` restores the original powered-display
setting; it does not override the presence sensor. A visible document on an asleep
headset is ineligible. Every collector remains unqualified until its timing and
physical-device gates pass.

Bounded CPU stage windows distinguish frame preparation, page synchronization and
upload, and draw submission. These wall times overlap (page work is part of
preparation), and submission can include driver blocking; none is a GPU timer.
Existing GPU timer queries and raw XR intervals remain separate. Serialized
readback probes verify that the active anatomy pages use the shared line material;
surface or inactive-material experiments are refused. The current skeleton pages
share that material, so an inactive shader was not established as the cause of lag.

Console requests retain HTTP and curl status without credentials or query strings.
Only a missing status file or a partial JSON replacement is treated as pending;
authentication and transport failures propagate. Lifecycle trials write a unique
remote epoch containing package, shader and declared lineage, then reread it before
stop, after stop, after restart and after recovery. A changed or missing marker
invalidates the attempt rather than establishing a worker defect. Source checks
and the requirement for `awaiting_recovery` after a hard stop remain in force.

These changes instrument the pending trials. They do not establish a performance
improvement, a completed XR matrix, hard-termination recovery or a GPU-fault pass.

### Follow-up trials — 2026-10-16

The [follow-up evidence](evidence/device-trials-followup-2026-10-16.json)
archives raw preflights, lifecycle jobs, epoch readbacks, software oracles and a
checksum verifier. No scientific result or historical lock changed.

- Quest: three invalid preflights (Browser diagnostics unavailable, then headset
  asleep); zero eligible timing samples. Keep-awake restored to `0`, presence
  sensor unchanged. The original/4/16/64 MiB comparison and physical XR matrix
  remain open; no performance improvement or unsupported-workload verdict follows
  from this attempt.
- Series S, `both`: the controlled ordinary lifecycle passes at about 37,173
  steps/s on the 2,048-neuron synthetic fixture. Cancel occurs at step 37,440;
  suspension at 49,152 resumes the remaining 950,848 steps with exact CPU parity.
  All remote epoch checks match.
- The separate `forcestop=yes` attempt parks as `suspended` at step 43,456 and
  completes the remaining 956,544 steps with exact parity. Its hard-termination
  gate correctly fails: graceful suspension cannot qualify noncooperative death.
  GPU-fault injection is still separate and unmeasured.
- An earlier attempt stalled at checkpoint publication. Activation timed out
  (`HTTP 0`, curl 28). A diagnostic forced stop preserved the epoch and produced
  `awaiting_recovery`; explicit resume completed with CPU-identical output. Its
  interventions keep it unscored, and its root cause remains undetermined.
- Independent software WebGL oracles pass for pages, real skeletons and real
  surfaces, including stereo color/depth/ID and full-quality desktop comparisons.
  Surface timeouts also reproduced on the old baseline under concurrent load;
  the frozen candidate passed with a larger outer timeout. These are correctness
  checks, with no hardware-performance claim.

The combined tree passed 764 ordinary Python tests plus both slow checks; the
callback/transport follow-up passes 141 JavaScript tests (optional network test
also covered by the slow run) and 40 targeted Python tests. Authentication and
transport failures propagate in all three status readers; a missing file or a
partial status JSON remains pending. Callback-free desktop or XR observations
are excluded even when the document reports itself visible.
