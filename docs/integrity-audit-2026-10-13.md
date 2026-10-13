# FlyMSG integrity audit and resolution ledger

Snapshot: 2026-10-13, source `9a52fe2`, refreshed against `7ccedb2` (#121). This is an engineering audit, not a new scientific
protocol or an accepted architectural decision. Live process and CI states below are
observations at inspection time. No existing run, protocol or archived result was changed.

## Baseline and concurrent work

- Main advanced during inspection from `b1116af` through #119 (`17173c2`) to #120
  (`9a52fe2`). The initial `exact-gap-progress` branch was clean; #119 and #120 are merged.
- This audit uses a separate `integrity-audit` branch/worktree initially based on
  `9a52fe2`, fast-forwarded to `7ccedb2` without changing the other worktrees.
- Concurrent #121 fixes float round-trip parsing, checks float32 graded parameters and
  guards component size/nonfinite matrices. These are implemented fixes, not outstanding
  tasks to duplicate. It documents boundary-only refractory handling without changing
  that algorithm; the continuous-clamp choice remains proposed in this audit.
- KC v4 completed in a clean detached worktree at `b1116af`, using the explicit coupling
  integrator. Its archived manifest says `none`, seeds 83–85, 165,122 neurons and 25,563,197
  edges. This is a record of that implementation, not a test of #119's exponential map.
- T4/T5 v2 is running in a detached worktree at `17173c2`. At 09:14 Europe/Rome it had
  reported 2/136 simulations after 4.9 minutes, ETA 329.7 minutes. It was launched with a
  five-hour timeout. This estimate can change; it is not evidence of completion. Steps
  persist per whole configuration (eight simulations), so interruption can lose work
  within the current configuration. Do not stop or upgrade this process as part of audit.
- The viewer harness requires load <= 1.0. Observed load was 2.22 and a scientific job
  was active, so no idle-host performance baseline was attempted.
- PR #119's tests/Linux/native Windows builds passed. #120's PR native workflow passed;
  main workflows at `9a52fe2` were still running at inspection. Pages build/deploy status
  alone is not a browser or scientific validation.

## Reproduced defects

Run `python scripts/audit_integrity.py` using the project environment. It creates only
temporary scratch files, needs no dataset and prints JSON. Reproduction on unchanged
simulation/progress code produced:

| ID  | Priority | Evidence                                                                                                                                                                       | Required correction and independent acceptance                                                                                                                  |
| --- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | High     | One free cell coupled to one refractory cell: actual −47.14625549316406 mV, analytic clamp −47.14777233225746 mV; error 0.001516839093397948 mV in one step                    | Accept [electrical ADR](adr-gap-refractory.md); implement the clamped reduced system; analytic state tests before parity, then chunk/checkpoint tests           |
| F2  | High     | Same protocol hash with a different computation returns cached value 1 instead of new value 2                                                                                  | Accept [run-integrity ADR](adr-run-integrity.md); identity includes code, semantics, all inputs and execution dependencies; mismatches refuse before mutation   |
| F3  | High     | Changing a completed cached CSV to value 999 is silently accepted                                                                                                              | Validate step inventory, schema and checksums; tampering and missing/extra files must fail closed                                                               |
| F4  | High     | `cmd_kc_sparseness` and `cmd_t4t5` use `mkdir(exist_ok=True)` then overwrite tables/report/manifest; the same pattern occurs in sister writers                                 | Shared finalization policy; immutable completed runs; atomic publication and real process-level writer exclusion; second invocation preserves all output hashes |
| F5  | Medium   | After 50 resumed units and one fresh unit taking 60 s, ETA reports 1 minute; fresh-work estimate is 49 minutes                                                                 | Separate resumed units from timed work; unknown ETA before fresh work; deterministic-clock test                                                                 |
| F6  | High     | Dataset provenance hashes only compact neurons/edges, while KC consumes DoOR and T4/T5 consumes raw annotations/eye-map assets; versions/hashes may be collected at finish     | Snapshot all consumed inputs/dependencies before computation, verify before finalization; change each auxiliary asset in a refusal test                         |
| F7  | Medium   | Roadmap says the eye registration/graded mode is absent although #84/#97 comments and engine show it implemented; KC text generalizes beyond a finite explicit-integrator scan | Reconcile status from artifacts and commits; state finite-grid scope and identify untested mechanisms as hypotheses                                             |

F1's effect on biological or whole-connectome outputs has not been measured. At #121,
F1 is an explicit semantic decision: the new docstring declares boundary-only reset,
which the current algorithm implements; the discrepancy is with the continuous clamp,
not with that revised docstring. The proposed ADR makes this choice reviewable. F2's
different callable is a minimal demonstration of absent computation identity, not a
claim that an existing scientific run actually mixed implementations. F3 demonstrates
missing corruption detection, not evidence that historical data were corrupted. F4
is confirmed by writer control flow; no historical result was overwritten to test it.

Validation before any engine correction: 44 gap/progress/KC/T4/T5 tests passed on
`17173c2` during the preceding inspection; the subsequent #120 change archives results
and updates documentation. Existing tests do not cover F1's analytic clamp or F2–F6.
The three progress tests were also rerun during this audit. Passing parity tests do not
invalidate the independently reproduced defects.

## Open issue reconciliation

GitHub currently lists 12 open issues. Every row below requires an explicit evidence
gate; no issue is closed merely because a tool exists.

| Issue                                                                          | Verified implementation/status                                                                              | Next task and exit criterion                                                                                                                                                                                        |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#24](https://github.com/gianlucamazza/flymsg/issues/24) viewer performance    | Harness and scene instrumentation exist; idle baseline missing                                              | Extend/verify cold and warm cache coverage, hardware backend, mobile device and heavy comparison scenes; record reproducible baseline before setting regression thresholds or optimizing                            |
| [#31](https://github.com/gianlucamazza/flymsg/issues/31) embodiment umbrella   | M0/R0, engineered M1/M2, FlyGym TTM and jump3d tooling exist; several comments describe older states        | Reconcile milestone matrix with child issues and outputs; keep physical plausibility, numerical prediction and animal validation distinct                                                                           |
| [#34](https://github.com/gianlucamazza/flymsg/issues/34) sensory feedback      | Engineering loop exists; calibrated LC4 tuning absent                                                       | Require measured response/gain/latency variability and independently mapped inputs; then prospectively lock animal comparison and feedback controls                                                                 |
| [#35](https://github.com/gianlucamazza/flymsg/issues/35) FlyBody feasibility   | FlyBody evidence gate remains; FlyGym is a separate implemented backend                                     | Preserve FlyBody-specific no-go; evaluate runtime/mapping requirements against the selected body without claiming FlyGym closes FlyBody acceptance                                                                  |
| [#36](https://github.com/gianlucamazza/flymsg/issues/36) biological validation | No eligible independent held-out behavioral benchmark established                                           | Identify accessible independent data, freeze partition and causal tests, review transducer/decoder confounds before a scored run                                                                                    |
| [#19](https://github.com/gianlucamazza/flymsg/issues/19) motor map             | General map remains fail-closed; a targeted TTM/FlyGym actuator exists separately                           | Document exactly what the targeted actuator establishes; bilateral TTM/TLM/general motor mapping still requires independent evidence, not names or fitted policies                                                  |
| [#39](https://github.com/gianlucamazza/flymsg/issues/39) native GPU            | CPU fixture parity and strict HLSL builds exist; no hardware GPU acceptance                                 | Run held-out phase/state/spike fixtures on physical D3D12 adapter, log capabilities and operation differences; benchmark matched workloads only after parity                                                        |
| [#40](https://github.com/gianlucamazza/flymsg/issues/40) Series S              | UWP build and lifecycle code exist; physical-console proof absent                                           | Qualify install/package/shader identity, real suspension/cancellation/recovery, watchdog and memory outside debugger; report matched performance with feedback costs                                                |
| [#84](https://github.com/gianlucamazza/flymsg/issues/84) eye                   | Registered column geometry and drive exist; T4/T5 v1 `neither`; v2 running                                  | Validate all 17 configurations and eight stimuli each, actual source/asset identity and final completeness; then archive exact run. Gain/transfer and animal comparison remain evidence gates                       |
| [#85](https://github.com/gianlucamazza/flymsg/issues/85) electrical/modulatory | Optional Gap and measured-depression tooling exist; KC v4 uses old integrator                               | Resolve F1, compare numerical modes under a prospective execution/protocol plan, and state coupling/spikelet hypotheses with their missing measurements. No invented gains or new fast modulatory signs             |
| [#95](https://github.com/gianlucamazza/flymsg/issues/95) KC sparsity           | v1–v4 archived; v4 `none` on a finite grid with explicit first-order coupling                               | Preserve v4; prospectively distinguish algorithmic replication from new mechanism tests. Source decisions must not be chosen after viewing the new runs                                                             |
| [#97](https://github.com/gianlucamazza/flymsg/issues/97) graded neurons        | `sim.Graded` exists; default remains unchanged; native refuses; real-valued input unsupported by CpuRuntime | Clarify which paths are qualified and which inputs they accept; complete T4/T5 envelope evidence. Claim only the documented source audit, not universal absence of measurements without refreshed literature search |

The closed-issue inventory contains 36 items. Notable closure classes: #18 records an
empty eligible held-out partition; #20/#76 record model-side causal results; #90/#94/#96
record backend/actuator/input tooling; #43 records incremental execution. None substitutes
for #36's animal validation or #39/#40's physical hardware acceptance. Audit closure bodies
and artifacts before proposing any reopening; title/state alone is insufficient. The
remaining closed issues require that same acceptance-to-artifact cross-check during the
implementation phase; this snapshot does not claim that all 36 closures are validated.

## Execution order and ownership

1. Review and accept the two proposed ADRs. They do not supersede or rewrite historical
   locks/accepted ADRs and do not authorize new biological assumptions.
2. F1: `sim.py`, independent reference, `runtime.py`, electrical checkpoint semantics and
   focused analytic/regression tests. Measure topology/cache cost before cache design.
3. F2–F6: progress and experiment lifecycle helpers, manifests, affected CLI writers,
   archive selection and run index. First KC/T4/T5, then the enumerated sister commands.
   Test subprocess crash/recovery and immutable completion before long simulations.
4. Measure numerical differences and prepare any new KC lock/classification before a
   scored rerun; validate and archive existing T4/T5 under its original implementation.
5. Reconcile docs and prepare issue updates against exact code/artifacts, then publish
   changes under the repository's review/release gates. Do not silently promote previous
   engineering outcomes to scientific validation.
6. Run viewer baseline when host/device conditions qualify. Physical GPU/console tasks
   wait for actual access; evidence tasks wait for independently sourced measurements.

Run source changes in isolated worktrees. Long CPU-heavy jobs must use the host's
`bg` wrapper (`/home/gianluca/.local/bin/bg` when Bash's builtin shadows it). Preserve the
other worktrees and their processes. A commit/PR with green CI proves neither a full
connectome result nor GPU/console/animal acceptance. Final delivery must list implemented,
locally validated, CI validated, published and externally blocked work separately.

## Accepted implementation phase

The user accepted both ADRs on 2026-10-13. Implementation is isolated on
`integrity-audit`; it does not alter the other worktrees or their runs. The original
audit tables above remain the baseline evidence, not claims about the corrected code.

- Continuous clamping now gives −47.14777374267578 mV for F1's fixture, the nearest
  float32 to its analytic solution. The reduced-system oracle is independent of the
  production map builder. Cache state is derived, not a new persistent neural state.
- Persistent steps require full execution identity and verify typed table inventory,
  schema and checksums. The original lock-only/corruption probes now refuse reuse.
- A shared lifecycle owns all identified scientific writers, including file-output
  commands and dimorphism; it freezes all consumed assets/dependencies, separates
  execution identities, records attempts and atomically finalizes immutable output.
- Draw records also receive checksums and fsync; explicit checkpoint paths retain
  their meaning under identity sidecars and file ownership. Legacy caches are not
  automatically imported or described as verified.
- Resume-aware ETA, explicit archive selection, deep archive comparison and completion
  verification in the run index close the corresponding policy gaps.
- The viewer harness captures cold/warm passes and hardware/load identity. A real
  Chromium fixture observed warm-cache hits and the requested responsive viewport;
  this software-rendered smoke is not a performance result.

Validation at this stage includes focused analytical, process-crash, concurrent-writer,
typed-roundtrip, CLI, archive and site-link tests. Full-suite and native gates are run
against the committed implementation before delivery; a green focused test is not a
claim that those broader gates have passed.

Open evidence/hardware issues remain governed by the table above. KC v4 and T4/T5 v2
remain tied to their original implementations. No new scored electrical result has been
manufactured under v4's old first-order lock. A prospective numerical replication needs
an explicit new lock/classification and computational budget before execution.
