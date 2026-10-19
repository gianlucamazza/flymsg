# ADR: immutable run identity, resumable steps and finalization

Status: accepted, 2026-10-13. Accepted by the user before implementation.
Scope: B3/B4 experiment outputs; supplements the accepted
[architecture](architecture.md) and [runtime](runtime.md) decisions without editing them.

## Context

`progress.Steps` binds cached CSVs only to a protocol hash. Changing code, input data or
the numerical mode under the same lock reuses old values. A `done` file certifies no file
inventory or checksum: modifying a cached value from 1 to 999 is silently accepted.
It has no writer exclusion or atomic step publication. KC/T4/T5 commands write to the
same version directory and rewrite reports/manifests even when already complete.
Several sister commands use the same overwrite pattern. The archive helper protects
`results/`, but not the source run directories.

Manifests hash the compact connectome, but KC additionally consumes DoOR tables and
T4/T5 consumes raw annotations and eye-map files. These inputs are not fully identified
by the current compact-dataset hashes. `mark_start` captures git at startup, but package
versions and file hashes collected at finalization can describe a different environment
if dependencies or files change during a long run.

## Decision

Use one local run lifecycle shared by the affected commands. No service or database.
Separate scientific protocol identity, execution identity and execution-attempt metadata.

Execution identity is a canonical versioned payload containing:

- protocol schema/version/hash and fully resolved configuration, seeds and selection;
- clean source commit, numerical-semantics identifiers and relevant package/Python
  versions, recorded before computation;
- hashes and sizes of every consumed data asset, including auxiliary DoOR/eye-map/raw
  annotations; ordered row/bodyId identity where it is not already fixed by those assets;
- command and recording/precision options that affect computed outputs.

Hash this payload into the run identity. Require clean source for newly resumable scored
runs, using the existing clean-worktree workflow. Resolve/fetch required assets before
capturing identity; verify inputs remain unchanged before finalization. Resume requires
exact identity. Host/kernel and attempt timestamps are provenance, not interchangeable
with the scientific identity; restrict cross-platform resume until parity is qualified.

Store different execution identities in distinct directories under the protocol version.
Existing `runs/<experiment>/vN/` and `results/` remain historical and read-only. Update
indexing, CLI output and archive selection to accept explicit new run directories, so
multiple runs of one protocol are never chosen by an implicit “latest” convention.
Existing locks, seeds and scored tables are not edited.

Use OS advisory writer exclusion for the whole run, acquired before any output mutation.
The lock is released when its owning process exits; a filesystem marker alone is not
writer ownership. The initial deployment target is local Linux with `fcntl.flock`;
unsupported write platforms fail explicitly until their locking implementation is
qualified. Native worker lifecycle and neural checkpoints are separate existing
contracts; do not silently replace them with this experiment-level lock.

For each step, publish a temporary sibling directory containing the complete expected
table inventory plus schema, dtypes, row counts, checksums and producing-attempt identity.
Flush contents, then atomically rename on the same filesystem, under writer ownership.
Restore validates inventory and hashes before reading, with round-trip-safe float parsing
and explicit dtype restoration. Missing or invalid completed artifacts fail closed with
an actionable diagnostic; an explicitly unfinished staging directory is recomputable.
Never infer completion from an empty marker. Unsupported old step caches are not upgraded
or reused automatically.

Stage final output tables, report and manifest, verify identity and artifacts, and publish
an atomic completion record last. An existing completed run is immutable: rerunning it
returns its verified result/status or refuses before writes. A different execution
identity gets a different directory. A crash during finalization must recover under the
same identity without presenting partial files as a completed result. Keep the existing
`flymsg.run_manifest/v1` reader contract and add explicit run-identity, attempt and artifact
metadata; version any incompatible schema change separately.

Record original start time and all resume attempts, their source identity, resumed step
IDs and newly computed IDs. Manifest provenance must describe the actual producers of
the results. Compute ETA from newly computed work and its measured elapsed time; report
resumed work separately. Before any fresh unit completes, ETA is unknown.

## Consequences

- Migrate KC and T4/T5 first, then all locked/scored writers: behavior, silence-scan,
  partner-followup, MB plasticity, jump3d, sensitivity, validation/benchmarks, nulls and
  model-selection outputs. Audit exploratory output writers separately for explicit
  overwrite policy. Commands already refusing overwrite must preserve that policy.
- Test changed code/data/auxiliary assets/semantics, corruption, missing and extra tables,
  dtype/float round trips, process death, concurrent writers, repeated finalization and
  attempts to reopen historical directories. Verify immutable file hashes on second run.
- Run crash/recovery tests with real subprocesses and filesystem writes, not only mocks.
  Prove resumed and uninterrupted artifacts match except attempt/timing provenance.
- Historical artifacts remain valid records of their recorded implementation. They do
  not acquire the new integrity guarantee retroactively. Never rewrite their manifests.
- T4/T5 already running at `17173c2` continues in its existing worktree; do not inject new
  code, checkpoint formats or dependencies into it. Archive it under its actual semantics
  after validating completeness. No automatic restart under this decision.
- No new experiment is preregistered by this infrastructure decision.

## Alternatives

- Lock hash only: rejected, identifies a protocol but not its execution.
- Commit only: rejected, does not identify input assets or execution dependencies.
- Add checksums but retain mutable output directories: rejected, permits overwrite and
  competing writers while claiming immutable results.
- Trust a PID marker as ownership: rejected, stale processes and PID reuse are ambiguous.
- Rewrite existing manifests or convert old caches in place: rejected, fabricates a
  guarantee their producing code did not enforce.
- Require a new scientific protocol for every rerun: rejected as a storage policy; a
  numerical replication can keep the protocol but needs distinct execution identity and
  prospective classification. Actual changes to hypotheses or scoring need new locks.
