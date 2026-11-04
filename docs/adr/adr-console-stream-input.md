# ADR: bounded console input and continuous drive

Status: proposed, 2026-10-28. Implementation and engineering qualification are separate gates. This decision requires owner acceptance before scientific console use.

## Context

The accepted graded-eye ADR, decision 5, keeps `kick_equivalent` on the host until an explicit native input contract and requalification exist. The existing console batch interface accepts integer counts and cannot supply new sensory input after a feedback step. A dense whole-horizon drive also consumes unnecessary console memory.

The current DN arena v3 campaign retains its original source, CPU backend, lock, seeds and execution identity. This implementation does not migrate or replay that campaign.

## Proposed contract

Native fixture v5 retains the common forty-word header and all ordered state arithmetic. Its five-word descriptor at header slot 39 contains sparse mode, event count, membrane offset, flags and input-window length. Flag 0 distinguishes nonnegative finite float32 drive, widened exactly to float64, from nonnegative integer counts at most 2^53. Flag 1 enables a bounded dense window. Unknown flags, fractional counts and nonrepresentable float32 drive are refused. Fixtures v1 through v4 keep their bytes and validation rules; version-1 batches remain counts only.

A streaming fixture has an empty initial schedule and a fixed window. FMI1 input blocks carry version, encoding, absolute start, rows, columns and payload word count, followed by widened float64 values. The next block starts at the current cursor, fits the window and horizon, and is validated completely before mutation. Advancing beyond supplied input is refused. The GPU receives the same absolute start offset; integration and delivery arithmetic do not change.

The host owns input generation, body integration and the scheduler. The console owns neural advancement. Device Portal transfers a graph once per job and then ordered blocks and compact traced spikes. This is an explicit experimental deployment boundary: round-trip latency and the current DX12 buffer/pipeline reconstruction on each advance must be measured. There is no real-time or speedup claim and no automatic CPU fallback. A native body loop or persistent DX12 resources may be needed after measurement.

`flymsg.neural_stream/v1` jobs pin worker source, shader and adapter. Commands pin job identity, sequence, expected cursor, previous receipt hash and payload hash. Receipts bind the exact command, source, cursor and result SHA256. Only the next sequence executes; a lost response poisons the host session, which must not retry advancement. Worker interruption requires checkpoint restoration in a fresh job, never replay of commands from the interrupted job. Cancellation and suspension stop at an execution boundary. Idle commands have a ten-minute deadline.

Native streaming checkpoints use checkpoint v2, binding the static fixture prefix, cursor, current input window and full neural state. The host NPZ envelope additionally binds fixture/source/package/shader/adapter, encoding, scheduled future inputs and trace history with SHA256. These are integrity and lineage checks, not authentication of arbitrary untrusted files. Existing native checkpoints retain version 1. Console checkpoints have their own schema and are not interchangeable with CPU checkpoints.

## Acceptance and qualification

Local C++ tests compare state bytes, counts, ring contents and traces with the Python oracle across fractional dense/sparse input, bounded windows, feedback and checkpoint resume. Invalid modes, payloads and receipts must fail before a host cursor is committed. CI must build the strict shader and UWP worker on Windows and run native regression tests on both platforms.

On a physical Series S, run the existing 120-case matrix with its twelve expected refractory-clamp refusals, then `scripts/console_stream_parity.py` against the exact new source and packaged shader. The separate streaming matrix has 36 cases: two seeds, counts/drive and nine neural extensions, including directly driven graded inputs with and without heterogeneous membranes; each compares feedback boundaries and checkpoint restoration bit for bit. Retain immutable device/package/source/shader evidence, memory and elapsed time. Passing synthetic parity does not qualify whole-connectome throughput, biological claims, full-system body checkpointing or hard GPU-fault recovery of the new protocol.

Scientific console use remains gated on owner acceptance and physical evidence. Future scored experiments need a new approved lock naming this backend; existing locks are unchanged.

## Engineering evidence, 2026-10-28

The physical Series S passes all 120 legacy fixtures and all 36 streaming cases, including 216 state comparisons across feedback and checkpoint boundaries. Sixteen additional preloaded-drive cases cover dense/sparse storage, two seeds and four membrane/graded-input combinations, with non-binary float32 values and zeros. The twelve existing refractory-clamp refusals remain exporter refusals before submission. Suspension at step 40 writes the same checkpoint as the host request; restart requires a fresh job, restoration preserves the future input schedule and state bytes, and a cancelled job refuses advancement. The worker is stopped after qualification. The in-place package update preserves the app-data marker and performs no uninstall.

The [evidence report](../evidence/series-s-stream-2026-10-28.json) pins worker source `3cfa17f5c2d2247bef7ab7d5ae9dc212c2801817`, host collector `58136dc4baa1392e664baad2c74abc5cac679087`, supplemental host `a0591596f07de7efd3a00e72fe1d6594ed01a973`, package `0.1.0.1`, shader, executable and package hashes. The worker and streaming collector native source trees are identical. The [raw archive](../evidence/series-s-stream-2026-10-28.zip) retains 3,393 files with SHA256 inventory, commands, receipt chains, outputs and lifecycle/preloaded-drive reproduction recipes.

Observed worker memory ranges from 20.2 to 36.9 MB on these small fixtures. Each 100-step qualification case takes 8.46–12.07 seconds including setup, Device Portal transfers, comparisons and checkpoint restoration. This is not a throughput benchmark. Full-connectome continuous-drive throughput and real-time body control remain unmeasured; this evidence does not justify moving the active DN campaign to the console. Owner acceptance and independent review remain pending.
