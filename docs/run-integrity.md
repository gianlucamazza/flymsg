# Run integrity and electrical numerical semantics

Implementation of the accepted [electrical](adr-gap-refractory.md) and
[run-integrity](adr-run-integrity.md) ADRs. Historical protocols and archived results
retain their original source and numerical semantics.

## Scientific output lifecycle

The scientific CLI writers share `managed` and `runstore`. The execution identity includes
clean committed source, the complete protocol, parsed configuration, Python and installed
package versions, architecture, numerical thread settings and hashes of consumed inputs.
These include DoOR, eye-map/raw annotations, both connectomes for comparisons and FlyGym
body assets where used. Inputs, source and environment are checked again after loading and
before finalization. Changed inputs select a distinct execution; they never inherit cached
results from the old one.

`--out` selects an output base. New runs use `<base>.executions/<full execution hash>/`,
leaving historical directories unchanged. File outputs use their stem as the base. For
example, `sim ... --out runs/looming/rates.csv` publishes
`runs/looming/rates.executions/<hash>/output/rates.csv`. The CLI prints the final path.

A Linux advisory lock excludes concurrent writers. Output is staged, flushed and renamed
on one filesystem; a checksummed completion record is published last. A repeated command
verifies and returns the completed output without rewriting files or recomputing. Failed
scientific validation is also an immutable completed result and retains its nonzero exit
status when reopened. Missing/corrupt completion records do not become successful rows in
`flymsg runs` or eligible archives.

Rerun the same command from the same clean source to resume an interrupted execution.
KC/T4/T5 cache each complete arm/configuration as typed Parquet tables, preserving exact
floats, strings, missing values and indices. Each step records its execution, producing
attempt, inventory, schema and checksums. Only explicitly uncommitted staging files are
disposable; corruption in a committed step is an error. Attempts record computed/resumed
steps/jobs, original start time and interruption state. ETA uses newly computed work;
resumed work is counted separately and ETA stays unknown until fresh work completes.

Draw checkpoints use checksummed, fsynced JSON-line records under exclusive ownership.
An explicit `--checkpoint FILE` is honored and bound to the full execution identity by a
sidecar; otherwise the execution owns an automatic checkpoint. Old unbound/checksum-free
checkpoints are refused for scientific resume. They remain historical files and can still
be inspected by the read-only progress command. Existing long-running jobs continue with
their original worktree/code; this implementation does not upgrade them in place.

The shared policy covers simulation output, tracing, comparison/homology, engineered
jump/loop, validation, benchmarks, behavior, scans, partner follow-up, plasticity, KC,
T4/T5, jump3d, sensitivity, nulls, model selection, calibration, wiring nulls and dimorphism.
The exploratory workbench/causal commands already refuse overwrites; visualization and
geometry exports remain presentation artifacts with their existing explicit export paths.
They are not newly certified immutable scientific runs.

Archive a new run by its explicit `...executions/<hash>/output` path. The archive helper
verifies source completion before copying and compares archived bytes deeply. It never
selects the latest run implicitly and never overwrites a differing archived directory.

## Electrical clamp

Free cells retain the electrical sink from contacts to refractory cells. Each refractory
mask has an exact reduced linear operator with clamped voltages fixed at rest and clamped
chemical conductances frozen. The kernel and incremental runtime share the integration;
the NumPy oracle constructs its reduced operators independently. Analytic clamp/input and
boundary-release fixtures check the mathematics before parity.

The optional electrical path retains its all-free map and reuses the current map until a
mask changes. Additional maps have a process-wide 64 MiB LRU budget. No-gap and zero-gap
execution retain the original operations and neural checkpoint identity; nonzero-gap
checkpoints carry `flymsg.gap/continuous-clamp-v1` and refuse previous electrical semantics.

Measured on 2026-10-13: the KC candidate topology has one 823-cell component; a full map
occupies 10,837,264 bytes. A sampled reduced-map exponential took 1.81 s with one BLAS
thread on the loaded host. This is setup cost, not a whole-run benchmark. The number of
unique refractory masks determines actual cost; no real-time or full-connectome performance
claim follows. Do not replace exact integration with an unqualified approximation to make
an experiment finish sooner.

KC v4 explicitly locks first-order coupling. Its archived `none` result is preserved and
the scored runner refuses to reinterpret that lock under the new integrator. Any new
scored electrical run needs a prospectively registered protocol naming the new numerical
semantics. A paired numerical replication must be identified as such, not fresh biological
confirmation; grid, hypotheses and thresholds cannot be chosen after its outcomes.

## Viewer measurements

`GL=gl uv run python scripts/bench_viewer.py` measures cold and warm reloads in one fresh
browser profile per scene. Each pass records network/cache activity, actual WebGL renderer,
host load and benchmark data. Software rendering or unknown GPU identity cannot qualify
as a hardware baseline. The idle-load invariant is checked for each scene and pass.
`--viewport WIDTH HEIGHT --mobile-emulation` labels desktop browser emulation explicitly;
it does not qualify a physical mobile device. Hardware/mobile baselines still require
appropriate idle machines/devices. A software-rendered fixture validates capture only.
