# Scientific input follow-up — 2026-11-04

## Source recovery (#302)

The authoritative Edmond download into an initially empty directory succeeded for
all five historical Groschner files. Every SHA-256 matches the registered digest.
The source inventory and rederived voltage ranges are recorded in
[the acquisition ledger](../evidence/medulla-acquisition-2026-11-04.json).
This resolves the earlier HTTP 503 acquisition blocker, not the physiological
transfer or independent-validation gates. Sex/genotype eligibility remains UNKNOWN;
no reserved held-out response was opened. Calibration uses the historical source
only. No model parameter or archived result was changed.

`uv run python scripts/audit_science_inputs.py --data data --out NEW_DIRECTORY`
exports source verification, candidate support and missing-column diagnostics.
The output directory must not exist. Per-column derivatives remain local, alongside
the GPL eyemap-derived assets; the public report includes aggregates only.

## Assignment diagnostics (#303)

The local diagnostic covers 4,107 simulated receptors: 171 have no candidate, and
seven have tied top support. There are 4,840 candidate rows including the unmapped
sentinels. Top support, candidate count and winner/runner-up margin are descriptive,
not probabilities. A single candidate has no runner-up margin. Historical selection
and all missing-direction masks are unchanged.

The two historical assignments absent from the L1-defined table both refer to
left column (2,13), with support 1 and 5 synapses. Original annotations contain an
L1_R at (2,13), but no L1_L; left medulla cells at this hex key exist. This explains
the lookup failure without inventing a missing L1 or a viewing direction. Fragment
coverage and reconstruction asymmetry remain distinct from biological asymmetry.
Registration, measured angular covariance and independent landmark evidence remain
UNKNOWN. No uncertainty propagation is performed from synapse vote margins.

## Viewer documentation (#312)

The viewer reference now documents ordinary URL controls, three existing scenes,
and scripted screenshots. Chromium/SwiftShader smoke captures confirmed paused
60 ms replay, the requested neuron and comparison selection. Geometry was still
loading or refused by the full-resolution capacity gate. These captures verify
URL/control behavior only; they do not qualify surfaces, performance or hardware.
The favicon returned 404, without preventing the replay controls from opening.

## Numerical next gate (#148/#149)

[The observable qualification proposal](../plan/optic-observable-qualification.md)
defines voltage, release, latency and selectivity entry gates. It is not a lock,
scored run or approval. Source-specific transfer, numerical tolerances and an
untouched independent holdout must be established before scoring. Historical
nonconvergence and failed T4/T5 results retain their original verdicts.

## Coordination (#265/#263)

Module-boundary steps are complete and motor/proprioception ADR #288 was accepted
on 2026-10-27. PRs #309 and #319 remain separate work. The inspected local DN arena
v3 log stops after job 159/166 and ends with a resource-tracker warning. This is
incomplete execution evidence, not a final verdict or a diagnosis of its cause.
No new counted run or automatic resume was started.

The four workflows for f45375d (tests, native-runtime, CodeQL and Pages) completed
successfully. New implementation tests cover cache preservation, staged publication,
failed transfers, tied assignments, unmapped receptors and input ordering.
