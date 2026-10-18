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

| Issues         | Bounded next deliverable                                                                                                                                                                                  | No-go                                                                                                           |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| #84, #97, #140 | Audit v4 traces by cell type, polarity, direction and timing; table of retinal registration, LMC/medulla release and type-specific filters; prospective v5 hypotheses and matched ablations               | Missing release curves remain unknown; do not fit to Gruntman holdout or change v4 `robust: neither`            |
| #85            | Separate electrical, modulatory and APL/KC claims; prevalidate a readout with dynamic range in both APL-on and APL-off arms; quantify soma/claw distinction and odor overlap                              | No gap conductance inferred from EM counts, calcium→Hz conversion or global gain retune; v1 stays uninformative |
| #34            | Source LC4/LPLC2 kinetics and an observation model; assess whether recordings discriminate circuit timing from onset/stimulus-following baselines                                                         | No v3 without eligible source/holdout separation; preserve v1/v2 no-go/uninformative                            |
| #19, #35, #150 | One TTMn→muscle→real joint→actuator chain, with force/time course and sex/model uncertainty; resolve type-level versus neuron-level MANC discrepancies before per-neuron use                              | Missing actuator/joint or force remains unmapped; female-body/male-connectome uncertainty stays explicit        |
| #36, #149      | One eligible independent physiological comparison; auditory tuning and stable model discrimination before song holdout, or another prospectively locked eligible circuit                                  | Song v1 stays stopped; physiology cannot close behavioral M4; do not open held-out data to choose a mechanism   |
| #148           | Path-metrics v1 ran (seeds 5000–5004): latency not converged for sugar → MN9. Identifiability is a post-hoc re-read; all five parameters stay blocked. Uncertainty propagation still needs a distribution | Do not extend convergence v1 to latency, and do not manufacture an uncertainty range                            |

Path-metrics v1 fixed the reference dt, the seed partition, the windows and the
failure and indeterminate rules before the run from `e6a041e`. The verdict is in
[validation](validation.md#weak-pathway-timestep-metrics-sf2-a-check-not-a-score). It
does not rewrite convergence v1. The identifiability re-read
([validation](validation.md#identifiability-re-read-sf2-post-hoc-not-a-score)) is
post-hoc and scored false. Sensitivity ranges still have to come from evidence records;
the ±20% `w_syn` factors stay an engineering envelope. Uncertainty propagation still
retains correlations and mapping uncertainty; absent distributions block a biological
interval. This ledger is not a lock and changes no existing score.

### Entry protocols — 2026-10-16

Each front names its stimulus, its readout, the only admissible input and its control.
Until that input exists no new version is written and no recorded result is rerun or retuned.

1. **Eye (#84, #97, #140).** Stimulus: Gruntman et al.'s bars and directions, already held
   out from T4/T5 v4. Readout: T4 and T5 direction selectivity, not medulla amplitude.
   Admissible input: a Drosophila voltage → release curve or a measured lamina → medulla
   gain. Control: gain 16 with LMCs at 200 Hz, where the medulla swings reach the order of the
   measured ones (about ±5–10 mV around the settled dark potential, where the recordings depolarize
   12.8–23.9 mV and hyperpolarize 1.6–7.2 mV; Mi4 at most 0.6 mV) and T4 stays unselective. v4 stays robust neither; no v5 is
   written until the curve exists.
2. **Junctions and modulation (#85).** Three separate protocols. Electrical: conductance in
   nS and input resistance on the same cells, mapped to MaleCNS bodyIds; an EM synapse count
   is not a conductance. Modulatory: an effect per type, not a global factor on `w_syn`.
   APL/KC: a readout with dynamic range in both the APL-on and the APL-off arm. v1 stays
   uninformative and is not retuned.
3. **Looming (#34, G3).** Stimulus: approaching discs at the r/v values already deposited
   for the giant fiber. Transducer readout: LC4 or LPLC2 spike rate with trial-to-trial
   variability, mapped to MaleCNS bodyIds. The DNp01 peak time is a downstream readout,
   already used and not sufficient. Control: an input that follows only the stimulus onset.
   v1 and v2 stay uninformative; no v3 without that source and a holdout partition written
   beforehand.
4. **Head (#179, G2).** Measurement: the resting head-to-thorax angle in _D. melanogaster_,
   with dispersion and n, to register Zhao et al.'s micro-CT frame onto the NeuroMechFly
   body. Hengstenberg 1991's flight pitch, Whitehead et al. 2015's in-flight pitch correction
   and the 20° chosen by the NeuroMechFly authors do not count. Until then G2 is unqualified
   geometry on the real eye.
5. **Muscles (#19, #35, G4).** Chain: `TTMn_L` and `TTMn_R` → muscle → real joint →
   actuator, with force and time course. The body is female and the connectome male. The
   MANC type/neuron disagreement (140 of 623) is resolved before any per-neuron use. Without
   a published muscle → actuator pairing `motor_map.command` keeps refusing; NeuroMechFly's
   short jump does not become the missing force.
6. **Completion (#36, M4).** First, a Johnston's organ input with a measured band-pass, or
   tuned to the carrier, on exactly MaleCNS JO-A, JO-B and JO-D. Then a case still eligible
   in the frozen partition, other than song v1. Checked on 2026-10-16: the v1 manifest has
   none left. Its only scored held-out case, ORN_DM1 → DM1_lPN, ran and failed; ORN_V is
   reported and does not decide; no exploratory row is promoted
   ([benchmarks](benchmarks.md)). A case therefore needs a new manifest version written
   before its data, from a source that did not select the model. The Pacheco data are not
   opened to choose the mechanism; a fitted filter and mosquito tuning do not enter. Only a positive outcome
   against unused animal observations closes the project; a documented no-go does not.

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

The [follow-up evidence](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/device-trials-followup-2026-10-16.json)
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
- As of `f201060`, a native checkpoint publish whose temporary file does not
  grow is recorded as `failed` and is not replaced. A temporary file that grows
  is replaced and recorded as `completed`. The graded million-step job on worker
  `90249e45` was not rerun. The cause of its empty temporary file remains
  undetermined. This does not meet the exit of #224.
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

### Wi-Fi performance and bounded-path experiment — 2026-10-16

The [Wi-Fi investigation](https://github.com/gianlucamazza/flymsg/blob/main/docs/quest-performance-2026-10-16.md)
retains full-scene 4/16/64 MiB geometric/raster oracles, eligible raw cadence,
excluded attempts and the corrected Device Portal canaries. Three complete dense
blocks reject 4 MiB (median paired p95 ratio 2.0498). Remaining 16/64 cadence and
surface/physical-phone/immersive gates remain open. Serial direct/composer probes
supply useful stage diagnostics, not a replacement for those missing matrices.

The owner accepted a separate half-pixel path experiment. Independent original
edge/topology/projected-error checks and actual draw counts preserve all 1,128
selected neurons. Three fixed-camera A/B/B/A repeats show approximately 66% and
48% less serialized desktop wall time in dense and close views. Preparation
still takes 21–24 seconds. This clears an exploratory gate only: moving-eye
bounds, worker/upload scheduling, raster/depth/picking acceptance and physical XR
remain required. The production entrypoint does not import the experiment.

At the owner's request, unattended diagnostics temporarily simulate proximity,
record this distinct power profile and verify return to physical sensor control.
Static readback readiness cannot qualify cadence or XR receipts; their callback
checks remain unchanged. The final archive includes independent checksum/raw
statistics verification and explicit limits. Keep #24 and #177 open; neither a
hardware qualification nor a complete performance resolution is claimed.

### Sustained full-connectome workload — 2026-10-16

The [Series S sustained workload](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-sustained-2026-10-16.json)
records the three cases declared in `scripts/console_sustained.py`, protocol
revision 2: MaleCNS v1.0 default model, version-1 fixtures, looming escape and
bitter feeding at 100 Hz. All ten jobs pass: each case's first job matches the
CPU oracle bit for bit and every repeated output is identical. Looming drives
DNp01 and TTMn; the bitter negative stays silent at MN9.

| Case                                | Jobs × steps | Advance steps/s, median (min–max) | 60 s windows steps/s, median (min–max; n) | Upload s  | Download s | Submit-to-running s | Peak app memory, bytes | GPU engine-0 %, median / max |
| ----------------------------------- | ------------ | --------------------------------- | ----------------------------------------- | --------- | ---------- | ------------------- | ---------------------- | ---------------------------- |
| setup-looming (cold/warm, seed 600) | 2 × 20,000   | 2,366 (2,318–2,415)               | none                                      | 9.5–10.5  | 8.0–8.2    | 11.7–12.8           | 1,708,285,952          | 66.7 / 73.0                  |
| sustained-looming (seed 601)        | 4 × 500,000  | 2,649 (2,646–2,653)               | 2,660 (2,644–2,675; 12)                   | 16.5–20.1 | 2.9–4.9    | 19.8–23.4           | 1,946,570,752          | 98.2 / 99.1                  |
| sustained-bitter (seed 602)         | 4 × 500,000  | 3,693 (3,689–3,694)               | 3,709 (3,701–3,724; 8)                    | 10.8–13.2 | 2.7–3.2    | 14.0–16.5           | 1,512,374,272          | 97.9 / 98.6                  |

Neither sustained case shows throughput decline over four back-to-back jobs:
last/first advance ratios are 1.001 (looming) and 1.000 (bitter); 60 s window
ratios are 1.000 and 1.002. Revision 2 records zero Device Portal errors.
Attempt 1 (`1d1fde5`) passed setup but failed uploading sustained-looming job 3
with HTTP 500, with about 1 GB of fixture, checkpoint and output files left on
the console; the script stopped without a record. Revision 2 (`01bdb0f`) deletes
each job's large files after downloading and hashing its output, and records a
Device Portal error as the job's final state.

This is one console and about 23 minutes of sustained load. Host load averages
of 2–25 affect upload, export and oracle times, not console advance timing.
[#224](https://github.com/gianlucamazza/flymsg/issues/224) stays open:
noncooperative termination, GPU/device fault and gamepad input remain unmeasured.
Full-connectome v2 is not measurable through this exporter because
`flymsg.native` refuses per-neuron membranes; synthetic v2 lifecycle evidence
remains separate. There is no full-CNS real-time claim beyond the measured
steps/s. GPU temperature is unobserved (Device Portal does not expose it);
throttling is inferred from throughput only.

### Noncooperative termination — protocol 2026-10-18

Prospective protocol for #224, written before measurement. No physical result is
claimed. Run `scripts/console_hardstop.py --package PFN --aumid AUMID
--worker-image IMAGE.exe --shader LIF_CSO --lineage LINEAGE_JSON --out NEW_DIRECTORY`.
Use the imported lifecycle synthetic fixture: 2,048 neurons, two inputs, seed 40,
1,000,000 steps, version 1 (`extension=none`). Retain every attempt; refuse an
existing output directory. The declared installed worker source must match every
observed status. No address or credential belongs in the report.

Method: resolve exactly one PID by exact worker image basename from WDP
`GET /api/resourcemanager/processes` (`Processes`, `ImageName`, `ProcessId`).
Record matching image/PID observations before and after
`DELETE /api/taskmanager/process?pid=PID` (TerminateProcess). Never substitute
`DELETE /api/taskmanager/app`, even with `forcestop=yes`, for this kill. The PID
must disappear, no replacement worker may remain, and status must not report
suspension after the kill. Missing/ambiguous PID or refused DELETE is **blocked**;
a surviving process, suspension or uncertain observation is **indeterminate**,
never pass. Observe running strictly between start and end immediately before
DELETE. Record any observed `checkpointing` race without engineering one; it
invalidates the mid-advance case and requires a fresh attempt.

- **A — no checkpoint:** kill mid-advance before any checkpoint exists. Restart
  the app, require `awaiting_recovery`, then upload explicit resume. Worker.cpp
  reports parked step 0; without a checkpoint execution restarts from step 0.
  Require completed output bit for bit against the independent CPU oracle and
  `result.advance_steps == 1,000,000`.
- **B — last complete checkpoint:** suspend the running app once using the app
  DELETE, require `suspended` at an interior step, download `checkpoint.json` and
  `checkpoint.bin`, and verify the declared SHA256. Record the suspended step
  and checksum. Restart and resume once; after progress beyond that step, kill
  mid-advance using process DELETE. Require the last complete checkpoint to be
  unchanged, restart into `awaiting_recovery`, then explicitly resume. Require
  bit-for-bit CPU parity and `result.advance_steps == 1,000,000 - saved_step`.
  This verifies the restoration step independently of parked status (which is 0).

For each case retain the remote TrialEpoch identity and checks across stop/kill/
restart, timestamped status.json history, remote folder listings immediately
before and after kill (including all temporary/incomplete filenames), downloaded
status.json, checkpoint.json and checkpoint.bin snapshots where present, process
observations, effective restoration step and pass/fail/indeterminate/blocked
verdict. Preserve partial artifacts; never delete corrupt or incomplete evidence.
Missing recovery or wrong output/restoration is fail; missing evidence is
indeterminate. A partial-checkpoint observation cannot qualify a complete-checkpoint
case. Always stop the app at the end, leaving the console idle on Home; failure
of that cleanup prevents an overall pass. This synthetic gate does not qualify
GPU/device faults, full-connectome throughput or biological behavior.

### Noncooperative termination — result 2026-10-18

Run under the protocol above (committed in `6ccde6c` before measurement), worker
source `22bef37`, shader SHA256 `957a1202…`. [Evidence](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-hardstop-2026-10-18.json): report, trial
epochs, status histories, folder listings and checkpoint snapshots; the zip
holds SHA256SUMS of every file including the binaries left out of it.

| Case | Kill (WDP process DELETE) | After kill                                 | Recovery                                                                 | Verdict  |
| ---- | ------------------------- | ------------------------------------------ | ------------------------------------------------------------------------ | -------- |
| A    | step 12,288, PID gone     | status stale `running`, no checkpoint      | `awaiting_recovery` at restart; resume from step 0; bit for bit          | **pass** |
| B    | step 145,792, PID gone    | checkpoint (step 14,144) unchanged, SHA ok | `awaiting_recovery`; restored at step 14,144; 985,856 steps; bit for bit | **pass** |

Neither case reported `suspended` after the kill, and no worker process remained
after the final app stop (console on Home). No `.tmp` or incomplete file was
present before or after either kill. The kill landed during advance, not during
`checkpointing`, so a kill mid-publish stays unobserved, as declared. This
closes the noncooperative-termination gate of #224 for the synthetic 2,048-neuron
v1 fixture; GPU/device fault and gamepad input remain open.

### GPU device removal — protocol 2026-10-18

Prospective #224 protocol, written before measurement. **Unmeasured**: this
change supplies instrumentation and a harness, not a hardware result. Test
hardware only. Use the documented
[ID3D12Device5::RemoveDevice](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device5-removedevice)
(Windows build 20348 or later; the console reports 26100), which tells the runtime
the device can no longer be used and signals every fence to `UINT64_MAX`. This is
an API-induced removal exercising the worker's removal path, not a hardware,
driver or TDR fault; Microsoft does not describe it as a test method. Query the optional interface once at device creation; a requested
injection without that interface fails before any dispatch with
`fault injection unavailable`. Do not substitute a driver reset, TDR registry
change or persistent device setting. Removal is process-local; restoration is a
process restart. Record that no persistent device setting changed.

Build a new worker and record CI run, exact commit, MSIX and shader SHA256.
Download the CI artifacts independently, verify their hashes, and retain the
installed package identity and actual hardware/driver identity with the trial.
Before injecting any fault, requalify **that new binary** using
`scripts/console_gpu_parity.py --v2` (with its usual package, shader and output
arguments): the unchanged full matrix must pass, 12 v1 cases, 60 v2 cases and
12 declared refusals. Retain the report and artifact hashes with the lineage.
Lifecycle is not repeated in this protocol. Prior parity or lifecycle evidence
does not qualify the new binary.

Run `scripts/console_gpufault.py --package PFN --aumid AUMID --worker-image
IMAGE.exe --shader LIF_CSO --lineage LINEAGE_JSON --out NEW_DIRECTORY` only after
that prerequisite passes. Lineage must declare `worker_source_commit`; every
observed job status must match it. Use the unchanged lifecycle fixture: synthetic
version 1, 2,048 neurons, two inputs, seed 40, 1,000,000 steps. Retain every attempt
and its files; refuse an existing output directory. No address or credentials
belong in the output. The report schema is `flymsg.console_gpufault/v1`.

- **F1 — mid-advance without checkpoint.** Upload `fault.json` with schema
  `flymsg.worker_fault/v1`, the exact job folder ID and step 200,000 before
  publishing `job.json`. At the first submission cursor at or above that step,
  immediately after ExecuteCommandLists and Signal, remove the device once.
  Require status `failed` containing a failing device-removed HRESULT (hex), the
  original worker PID gone with no replacement worker, no `output.bin` or
  completed result, no checkpoint, and a retained folder listing and fault
  control. Allow at most 60 s from terminal-status observation to PID exit.
- **F2 — after a published checkpoint.** Start an identical job without a fault;
  suspend once with app DELETE and require an interior `suspended` boundary and
  complete checkpoint. Download both checkpoint files and hash their exact bytes.
  While stopped, upload `fault.json` at checkpoint step + 200,000 (strictly below
  the horizon), restart, require the job still parked `suspended` at the
  checkpoint step, and explicitly resume.
  Require the same failed/device-removed/exit evidence as F1 and SHA256 of both
  `checkpoint.bin` and `checkpoint.json` unchanged after the fault. Never consume
  or delete `fault.json` or any partial artifact.

For each fault record the failing GetDeviceRemovedReason HRESULT (not an assumed
`0x887A0005`), selected status history, source/package/shader identity, TrialEpoch
checks across transitions, PID observations and all job folder filenames. Record
fault-to-PID-exit time as an interval: the injection is between submission/resume
and terminal observation; the submit/resume-to-exit elapsed time is a conservative
upper bound, with lower bound zero. Also record terminal-observation-to-exit
elapsed time. These polling observations do not establish an exact device clock
timestamp or an exact RemoveDevice-to-exit latency.

After each fault, restart the app and publish a **fresh**, identical job ID
without `fault.json`. Require its first identity-checked worker status within
**60 s**, including the app-start request and submission. Require completion
at 1,000,000 steps within 900 s and output bit for bit against the independent CPU
oracle. A failed job is terminal and is never resumed for this recovery check.

Verdicts: **pass** only with all case evidence and fresh-job parity; **blocked**
when injection is unavailable and status is failed; **fail** for failed status
without a failing device-removed HRESULT, any other terminal state (including
completed despite the request), changed checkpoint, output/result after the fault,
PID-exit deadline, recovery deadline or parity failure; **indeterminate** for
missing/inaccessible evidence, identity loss, an unqualified suspension boundary
or interrupted observation. Missing evidence never passes. Both cases and cleanup
must pass for an overall pass. Always stop the app in `finally`, verify no worker
process remains, and leave the console on Home. This gate does not qualify
biological behavior, full-connectome v2 or gamepad input.

**Revision 2 (2026-10-18, before the second attempt).** Attempt 1 (`98fe27f`
worker, archived with the evidence) passed F1 and stopped F2 on a protocol error:
after a suspension the worker correctly keeps the job parked `suspended` until
`resume.json` (`Worker.cpp` reserves `awaiting_recovery` for jobs interrupted while
`running` or `checkpointing`), while revision 1 required `awaiting_recovery`; the
harness timed out waiting for it. Revision 2 requires `suspended` at the
checkpoint step. Nothing else changes; both cases are rerun from scratch on the
same requalified binary, and attempt 1 is reported, not replaced.

### GPU device removal — result 2026-10-18

Worker `98fe27f` (PR #244 merge build, CI run 39110356086, signed MSIX
`be417752…`, shader `957a1202…`), requalified before any fault: 72 of 72
parity cases bit for bit (12 v1, 60 v2) and 12 declared refusals. Attempt 2
under revision 2; attempt 1 (F1 pass, F2 stopped by the revision-1 error) is
archived in the same [evidence](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-gpufault-2026-10-18.json) zip with the requalification report.

| Case | Fault                              | Device result                          | Worker                                                        | Recovery (fresh job)             | Verdict  |
| ---- | ---------------------------------- | -------------------------------------- | ------------------------------------------------------------- | -------------------------------- | -------- |
| F1   | step 200,000, no checkpoint        | `0x887A0005` DXGI_ERROR_DEVICE_REMOVED | `failed`, no output/result; exit 0.36 s after terminal status | first status 1.85 s; bit for bit | **pass** |
| F2   | step 214,336, checkpoint at 14,336 | `0x887A0005`                           | `failed`; checkpoint.bin/json SHA256 unchanged; exit 3.05 s   | first status 1.59 s; bit for bit | **pass** |

Fault-to-exit upper bounds are 6.47 s and 8.48 s (submission/resume to exit);
no device clock timestamps the removal itself. No worker process remained after
the final stop (console on Home); no persistent device setting was changed. This
qualifies the worker's handling of an API-induced device removal on the
synthetic 2,048-neuron v1 fixture, not a hardware, driver or TDR fault, which has
no supported injection on the console. Gamepad input remains the last open gate
of #224.
