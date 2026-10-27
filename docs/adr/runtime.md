# ADR: scientific semantics and replaceable execution backends

Status: accepted by the user, 2026-10-14. CPU foundation (R0) and a native CPU fixture executor (R1, CPU) implemented; the HLSL shader, DX12 host and UWP worker build in CI; on a Series S the worker runs and the DX12 lane matches the CPU oracle bit for bit on the 12 version-1 fixtures (2026-10-15); the worker's cancel, stop-to-suspension with checkpoint and resume pass on the console with bit-for-bit output, at about 44,000 steps/s on a 2,048-neuron synthetic fixture; the default full connectome is bit for bit at about 2,320 steps/s with exact float32; the [sustained v1 workload](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-sustained-2026-10-16.json) is bit for bit at about 2,650 steps/s looming and 3,690 steps/s bitter, with no throughput decline over four back-to-back 500,000-step jobs per stimulus. Version-2 fixtures are implemented on the GPU lane (#215); the [2026-10-16 qualification](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-gpu-v2-2026-10-16.json) passes 12 v1 and 60 v2 cases on Series S, retaining 12 expected clamp refusals. The graded+gap v2 lifecycle also passes one million steps, cancel and suspension/resume. A [noncooperative process kill](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-hardstop-2026-10-18.json) (2026-10-18) recovers bit for bit from step 0 and from the last complete checkpoint. An [API-induced GPU device removal](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-gpufault-2026-10-18.json) (`RemoveDevice`, 2026-10-18) fails the job with `DXGI_ERROR_DEVICE_REMOVED`, exits the worker and recovers bit for bit on restart; a hardware fault is unmeasured ([#39](https://github.com/gianlucamazza/flymsg/issues/39), [#40](https://github.com/gianlucamazza/flymsg/issues/40)). Related: architecture #30, workbench #27, embodiment #31 and sensory feedback #34.

Independent v2 GPU evidence from #216 is also retained in `docs/evidence/series-s-gpu-parity-v2-2026-10-16.json`.

## Context

`sim.run()` owns input preparation and a Numba kernel that previously initialized and executed a complete run. Its scientific semantics include integration, thresholding, ordered float32 synaptic delivery, Poisson kicks and reset. Delayed spikes, adaptive thresholds and refractory deadlines must survive every execution boundary. The viewer is a replay consumer; it does not own the simulator clock.

The Xbox trainer already contains a DX12 GPU-resident runtime, UWP lifecycle management and evidence-driven acceptance, but its transformer operators are not a neuron simulator. Reuse execution infrastructure while keeping scientific semantics in FlyMSG. A CPU/GPU port cannot assume identical arithmetic or random sequences.

## Decision and module boundaries

| Boundary                    | Existing authority                                              | Contract and verification                                                                                                                                          |
| --------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Data ingestion and topology | `data.py`, `graph.py`, `wiring.py`                              | Dataset bodyIds resolve to stable run-local rows; preserve CSC edge order; existing data/wiring tests                                                              |
| Scientific semantics        | `sim.py`, `validation/`                                         | `flymsg.lif/ordered-f32-v1`; original four update phases; core oracle regression tests                                                                             |
| Incremental execution       | `runtime.py`                                                    | `NeuralRuntime`: absolute exclusive step boundaries, detached snapshots, explicit inputs (`counts` or `kick_equivalent`), checkpoint/restore; runtime parity tests |
| Experiment orchestration    | `cli/`, `manifest.py`, `prereg.py`                              | Existing `flymsg.run_manifest/v1`; artifact hashes and backend identity belong in config/extra; existing manifest/preregistration tests                            |
| Embodiment                  | `embodiment.py`, `motor_map.py`                                 | Versioned SI units, bodyIds, integer clock and verified mapping gates; M0/motor-map tests                                                                          |
| Analysis                    | `validate.py`, `silence_scan.py`, `compare.py`, `dimorphism.py` | Consume immutable results; retain preregistration boundaries; existing analysis tests                                                                              |
| Presentation                | `viz.py`, `pages.py`, `viz_static/`                             | Existing replay formats remain unchanged; viewer/JS/link regression tests                                                                                          |

Maintain a Python-first single-process baseline. The native runtime is an optional backend. A console worker adds a deployment boundary, not network participation in each neural tick. A dedicated FlyMSG worker owns the local neural/body loop. Python submits immutable jobs and collects artifacts. Rendering reads snapshots independently.

State tracing #26 extends selective recordings; workbench #27 owns experiment configuration; causal explorer #25 schedules controlled interventions at explicit boundaries; sensitivity #28 runs separate parameterized jobs. These features do not write UI state back into historical scientific artifacts.

## CPU execution contract

`CpuRuntime` shares the compiled `_advance` kernel with `sim.run()`. Chunking does not introduce a second neuron implementation. Initialization copies topology, parameters, inputs and mappings. `advance_to(k)` executes `[current_step, k)`; backward/out-of-horizon targets fail and equal targets are a no-op. `snapshot()` returns detached copies. `result()` requires a complete horizon and preserves the existing `sim.Result` shape and semantics.

The runtime accepts a known horizon and explicit Poisson-count inputs, generated by the existing `sim.poisson_kicks` for baseline parity. `schedule_inputs(counts)` replaces the next input block starting at the current exclusive boundary; it cannot rewrite past inputs. Counts enter at the existing kick phase **after** threshold detection. The encoding is a required constructor argument: `counts` keeps nonnegative integer counts, and `kick_equivalent` takes the real-valued graded drive of `sim.run` as a nonnegative finite float32 array, stored and applied as its float64 widening, so the result equals `sim.run` with the same kicks bit for bit ([graded eye ADR](adr-vee1-graded-eye.md), vee1-2). `schedule_inputs` refuses the other encoding's dtype. A `sim.Membrane` passes through to the same kernel; the native fixture refuses it, since its header carries one set of membrane constants. This API does not force output spikes, bypass refractory rules or implement a biological sensory encoder.

State is private: potentials, conductances, threshold offsets, refractory deadlines, delayed spike ring/lengths, accumulated counts, first-spike times, selective spike recording and the input schedule. Scratch buffers are reused and have no persistent mathematical state at a successful step boundary.

The CPU checkpoint `flymsg.neural_checkpoint/v1` is a non-pickle NPZ archive. It includes the cursor, input horizon and all persistent arrays. Identity binds ordered topology, parameters, the input encoding, initial explicit input schedule, silencing, trace selection, horizon, binning and semantics version. Checksum binds state and temporal metadata. Restore validates compatibility, array shapes/dtypes, queue ranges and checksum before replacing live state. Checkpoints are atomically replaced on one filesystem; concurrent writers to the same path are unsupported. They are neural checkpoints, not yet complete body/decoder/environment checkpoints.

The reference `sim.run()` still generates its original inputs, accepts its existing arguments and returns its existing result. Model defaults, seeds, preregistered protocols and historical manifests are unchanged.

## Executable usage

```python
from pathlib import Path

import numpy as np
from scipy import sparse

from flymsg import sim
from flymsg.runtime import CpuRuntime

p = sim.Params()
W = sparse.csc_matrix(np.array([[0, 0], [50, 0]], dtype=np.float32))
kicks = sim.poisson_kicks(7, 150, p.dt, 1000, 1)
kwargs = dict(steps=1000, kicks=kicks, p=p, per_bin=100, trace=np.array([0, 1]))
runtime = CpuRuntime(W, np.array([0]), **kwargs)
runtime.advance_to(217)
runtime.checkpoint(Path("neural.npz"))
resumed = CpuRuntime(W, np.array([0]), **kwargs)
resumed.restore(Path("neural.npz"))
resumed.advance_to(1000)
result = resumed.result()
```

## Xbox architecture

Create a workload-specific native neural runtime with the same boundary semantics, initially exposing a fixture CLI before UWP deployment. FlyMSG owns equations, constants, oracle inputs, scientific tests and model version. `xbox-gpu-training` owns its existing trainer and can supply reusable buffer pools, command submission, bounded waits, lifecycle patterns and build tooling. Do not make FlyMSG depend on transformer autograd or modify accepted training campaigns to run neuron jobs.

Use separate GPU arrays for `v`, `g`, threshold, refractory deadlines and delayed spike state. Upload topology once. Preserve state on-device across bounded batches. Read back only requested recordings, control summaries and checkpoint boundaries. Use explicit barriers between dependent dispatches and verify device capabilities before selecting optional features. Desktop success is not console qualification.

First GPU path: one owner per postsynaptic target, ordered source accumulation, no concurrent floating-point scatter sum. Build an incoming-edge index ordered to reproduce the CPU's ascending source-column traversal. Reordering duplicate edges or reducing a different tree changes arithmetic and requires a fresh qualification. This path can scan many inactive edges and may be slower than the CPU. Later sparse event-driven propagation is a separately versioned optimization, benchmarked against activity density and memory budget.

Neuron arithmetic must also be qualified: the CPU mixes explicit float32 operations and float64 Poisson-kick addition. Shader precision, contraction, transcendental constants and threshold crossings require operation-level fixtures. Fixed reduction order alone does not establish bit identity. Share precomputed constants and explicit kick fixtures for initial tests; a device RNG is a later versioned change.

Use baseline DX12 functionality already demonstrated on the target. Enhanced barriers, indirect dispatch or newer shader features are optional capability-gated paths. Reject software adapters and wrong hardware identity for console claims.

### Worker job and lifecycle requirements

`flymsg.neural_job/v1` (parsed by `native/uwp/Worker.cpp`) carries job ID, dataset release/hash, ordered topology hash, row/bodyId map hash, semantics version, parameter/config hash, horizon, tick duration, input/recording asset hashes and backend requirements. Artifact formats and compatibility are explicit; the protocol is unqualified on a console ([#40](https://github.com/gianlucamazza/flymsg/issues/40)).

States: queued, validating, running, checkpointing, completed, failed, cancelled, suspended. A checkpoint publish whose temporary file does not grow is recorded as `failed` and is not replaced; one that grows is replaced into the checkpoint. One active job per console worker. Commands carry sequence IDs and expected job identity; submissions and recovery must be idempotent. On suspension or cancellation, checkpoint at a completed scientific boundary. Incomplete artifacts are not successful outputs. Recovery onto a different shader/package requires a compatibility decision and new evidence.

Record source commit, shader hash, package version, adapter, precision mode, memory budget, clock, dataset/config hashes and acceptance report. Measure without the debugger masking memory constraints. Do not extrapolate transformer tokens/second to neuronal steps/second.

## Closed-loop timing

Integer scientific ticks govern causality. An adapter maps tick index to physical time exactly; the current CPU supports configurable `Params.dt`, while embodiment must reject incompatible/nonrepresentable periods. Decoder, body and encoder periods are explicit and initially integer multiples of the neural period.

At a body/control boundary, complete only the neural interval whose inputs are known, extract mapped motor output, advance the body, sample sensors and schedule the resulting input for the next permitted neural boundary. Document command latency and the kick application phase. Never batch past an unresolved feedback boundary. Network and rendering cadence never advance the scientific clock.

The synthetic runtime test couples a toy neural circuit to `MockBody` and verifies feedback changes neural output and body position versus feedback disabled. It is an engineering causality fixture, not M1 physics, independent behavioral validation or a verified MaleCNS motor mapping. Real motor rows remain gated by `motor_map.py`.

## Alternatives and consequences

- Directly replace Python with Xbox code: rejected; would lose an independent oracle and bind scientific work to one device.
- Reuse the transformer graph as the neuron engine: rejected; sparse delayed propagation and update semantics differ.
- Network RPC per neural step: rejected; latency enters the experimental loop and complicates causality.
- GPU scatter accumulation as the initial backend: deferred; reduction order and races complicate parity.
- A general multi-backend framework immediately: deferred; implement one native backend before adding an abstraction for unmeasured APIs.

The incremental CPU API makes causality, state inspection and pause/resume testable. Costs include checkpoint size and validation hashing. It currently allocates recordings and input schedules for the known horizon, like the existing simulator; it is not an unbounded streaming engine. Large runs must explicitly budget those arrays. Cross-platform CPU/GPU bit identity, full connectome real-time throughput and console power are unmeasured.

## Migration and acceptance gates

| Gate | Deliverable                         | Acceptance                                                                                                      |
| ---- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| R0   | Shared CPU advance and checkpoint   | Exact counts, spikes, first-spike times and state after chunking/resume; invalid restore leaves state unchanged |
| R1   | Native CPU and GPU fixture executor | Four phases and precision verified against held-out Python fixtures; no changed defaults                        |
| R2   | Series S worker                     | Real deployment, memory, lifecycle, resume and throughput evidence with immutable hardware identity             |
| R3   | Sparse propagation optimization     | Separate backend version; declared precision/threshold gates and density-scaled benchmarks                      |
| R4   | Full neuromechanical worker         | Whole-system checkpoint, validated timing, open/closed-loop controls and mapping gate                           |

R0 is implemented here. Native implementation is tracked in [#39](https://github.com/gianlucamazza/flymsg/issues/39), and physical-console qualification in [#40](https://github.com/gianlucamazza/flymsg/issues/40). R1's CPU fixture executor exists, and on 2026-10-15 the DX12 lane matched the CPU oracle bit for bit on all 12 version-1 fixtures on a Series S GPU (adapter `SraKmd_arden`; `scripts/console_gpu_parity.py`, evidence `docs/evidence/series-s-gpu-parity-2026-10-15.json`); the [version-2 qualification](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-gpu-v2-2026-10-16.json) now also passes all 60 supported v2 cases, with exact floating-point state bytes independently rechecked. R2 has its worker launching and completing GPU jobs on the console. On a 2,048-neuron synthetic version-1 fixture of 1,000,000 steps (`scripts/console_lifecycle.py`, evidence `docs/evidence/series-s-lifecycle-2026-10-15.json`):

Independent v2 GPU evidence from #216 is also retained in `docs/evidence/series-s-gpu-parity-v2-2026-10-16.json`.

- the advance runs at about 44,000 steps/s, timed by the worker, at about 133 MB of app memory against a 5 GiB limit;
- a cancel ends the job in `cancelled`;
- a Device Portal stop suspends the app with a checkpoint, and after a restart and a resume the job completes bit for bit with the CPU oracle.

The full MaleCNS default model (165,122 neurons, 24.5 million synapses; looming stimulus, 2,000 steps; `scripts/console_bench.py`, evidence `docs/evidence/series-s-full-connectome-2026-10-15.json`) runs on the console bit for bit with the CPU oracle.

- **Pull delivery.** With the original kernel, which pulls every incoming synapse every tick from an upload heap, the console ran at 28 steps/s.
- **Event-driven delivery** (#202) runs at about 1,630 steps/s. Inputs are copied once to a default heap. A spiking neuron sets the bit of each outgoing synapse, and a target sums its set bits in ascending order, the pull loop's float sequence, so the result is unchanged.
- **The host's Python oracle** ran at 850–1,130 steps/s, measured while the host was busy.
- **The 2,048-neuron lifecycle fixture** rises from about 44,000 to about 70,000 steps/s.
- **Longer runs and subnormals.** A 20,000-step run then differed in `g` alone, in 4,329 neurons whose conductance had decayed into the float32 subnormal range: the console flushes those to zero, even with a shader built `-denorm preserve`. The shader now computes every float32 operation on state in double and rounds once to float32, which gives the correctly rounded float32 result, and it reads and writes subnormals as bits.
  - With that, the 20,000-step run is bit for bit at about 2,320 steps/s, and the 12 fixtures, cancel, suspension and resume pass again.
  - Exactness costs about a quarter of the throughput.

**The console as a backend.**

- `flymsg.console` holds the Device Portal client. It turns `sim.run` calls on one network into one batch job: the network is uploaded once, then every run follows.
- The decoded results are `sim.run`'s, bit for bit.
- `flymsg baselines --run --backend console` runs each graph's battery that way. `--backend hybrid` serves one queue of graphs from the CPU workers and the console together (`parallel.imap_shared`), and each side takes its next graph when it is free.
- The manifest records the worker package and shader hash, never an address.
- Each batch deletes its network copy and outputs from the console once they are read.
- `scripts/console_battery.py` checks a whole battery on the console against `sim.run` on the host, run by run. On 2026-10-15 one graph's battery (6 cases × 5 seeds, 600 ms each, the whole connectome) matched in all 30 runs (`docs/evidence/series-s-battery-2026-10-15.json`).
- **Cost.**
  - The console advanced the 30 runs in 70 s, about 2.3 s per run. One host core ran the same 30 `sim.run` calls in 46–62 s, so for this model with exact float32 the Series S GPU is worth about one host core.
  - End to end the batch took 243 s (330 s before local fixtures shrank to their header), because each run returned its whole state, about 45 MB.
  - Since #211 a batch asks for `"output": "counts"` and each run returns only its nonzero counts and first spikes. On 2026-10-16 the same battery matched in all 30 runs and took 180 s end to end, with 69 s of advance (`docs/evidence/series-s-battery-sparse-2026-10-16.json`). One host core ran the 30 runs in 29 s that day, so the console is still one slow lane.
  - Since #213 the battery reports where the time goes (`docs/evidence/series-s-battery-phases-2026-10-16.json`, 164 s): 28 s building the 30 runtimes and 33 s exporting the batch on the host, 10 s hashing and uploading, 77 s waiting for the console (69.6 s advance, 5.4 s rebuilding runs, 0.3 s writing outputs), 12 s downloading. The host's own preparation, 61 s, is now the largest cost outside the advance. Since #214 the runtimes are built one at a time as the export asks and each fixture stays in memory: preparing the battery went from 97.6 s to 25.2 s, and its memory peak from 11.3 GB to 2.6 GB, with the same bytes (`docs/evidence/batch-prep-2026-10-16.json`). What remains is per run: each runtime copies and hashes the network, and the export rebuilds every run's whole fixture to check its patch word for word.

An API `RemoveDevice` and a noncooperative process kill passed on 2026-10-18 and recovered bit for bit (`docs/evidence/series-s-gpufault-2026-10-18.json`, `docs/evidence/series-s-hardstop-2026-10-18.json`). A hardware GPU fault and gamepad input stay open. R3–R4 need implementation beyond this batching. The existing M1–M4 embodiment roadmap remains authoritative for physics and biology; this execution lane does not mark those issues complete.

Run `uv run pytest tests/test_runtime.py tests/test_core.py tests/test_embodiment.py`. Existing CI also checks all synthetic regressions, documentation links, formatting and browser modules.

## Native fixture extension implementation (2026-10-18)

This implementation update supersedes the earlier native `Membrane` limitation
without changing the accepted scientific update phases. `export_fixture` accepts
explicit `input_encoding="sparse"` (default remains dense): fixture v3 stores
strictly ordered nonzero `(step, column, float64 count)` events with semantics
`flymsg.lif/ordered-f32-v2`. GPU inputs stream in whole-step blocks within the
512 MiB input-buffer budget, without a dense GPU allocation or a reset of the
neural cursor. Sparse fixture size scales with event count; host input generation
and output/state allocations retain their own limits.

Non-uniform `sim.Membrane` uses fixture v4 and semantics
`flymsg.lif/ordered-f32-v3`, carrying per-neuron float32 decay/gain, rest/reset and
threshold arrays from the same `sim.kernel_constants` used by Numba. The native
CPU and shader retain the kernel's arithmetic order. Uniform membranes retain
the scalar format; global refractory timing and refusals on Gap nodes stay the
same. Sparse input and membranes compose with supported graded/gap fixtures.
Worker jobs bind the exact semantics returned by the exporter.

See [the binary contract and limits](https://github.com/gianlucamazza/flymsg/blob/main/native/README.md#sparse-inputs-and-per-neuron-membranes-2026-10-18).
Acceptance adds 48 cases to the original 72, preserving the original fixture
bytes and 12 clamp refusals. CPU parity and block planning are checked locally.
The Series S matrix is 120 of 120 with the 12 clamp refusals
(`docs/evidence/series-s-final-parity-2026-10-18.json`). A sparse
1,500,000-step full-connectome looming job completed bit for bit
(`docs/evidence/series-s-sparse-long-2026-10-18.json`). A hardware GPU fault
and gamepad input stay open. Historical console results above are unchanged.
