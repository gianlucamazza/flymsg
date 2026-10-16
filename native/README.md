# Native execution lane

This implements the R1 fixture executor and the initial R2 worker source. It builds on the CPU architecture in [runtime.md](../docs/runtime.md). Its GPU lane is qualified on a Series S for the version-1 fixtures; its cancel, suspension with checkpoint and resume pass there on a synthetic fixture.

| Component               | Current evidence                                                                                       |
| ----------------------- | ------------------------------------------------------------------------------------------------------ |
| Python fixture exporter | Contract tests; incoming edge order preserves CPU source traversal                                     |
| C++ CPU executor        | Exact synthetic state/spike parity, chunk/resume and corruption rejection on Linux                     |
| DX12 host and HLSL      | Windows compile gate; bit-for-bit parity on the 12 version-1 fixtures on a Series S GPU (2026-10-15)   |
| UWP worker              | On a Series S: cancel, suspension with checkpoint and bit-for-bit resume; 44k steps/s at 2,048 neurons |

## Build and acceptance

```bash
cmake -S native -B build/native
cmake --build build/native --config Release
uv run python scripts/native_acceptance.py --exe build/native/flymsg_native --out build/native/acceptance.json
```

On Windows the executable is `build/native/Release/flymsg_native.exe`. Compile `native/lif.hlsl` with the Windows SDK DXC using `-T cs_6_0 -E CSMain -Gis -Ges`. Run the same acceptance script with `--shader path/to/lif.cso` on an actual hardware adapter. It rejects software adapters and requires double-precision shader support for the existing kick arithmetic. Failure of that capability is a **no-go for this numerical mode**, not permission to silently change precision.

Each of the 12 fixtures is checked after step 217 and after checkpoint/resume to step 1000. All potentials, conductances, thresholds, refractory deadlines, counts, first spikes, spike raster and delayed spike membership must match exactly. This is qualification of those synthetic fixtures; full-connectome and biological claims require separate evidence. The report records executable, shader and fixture hashes.

## Binary contract

All formats are little endian, versioned and reject incompatible dimensions/offsets. The 40-word fixture header is specified by the exporter and validated by the C++ reader. It carries precomputed float32 constants, stable incoming edges, masks, trace/stimulus columns and explicit double-valued integer kick counts. Count range is limited to exactly representable doubles (up to 2^53). Payload and state together are capped at 512 MiB for this qualification lane. The native representation uses delayed spike membership masks; it does not invent new event timestamps.

Version 2 fixtures add graded neurons and electrically coupled groups (`sim.Graded`, `sim.Gap`). Header word 37 points to an extension block (graded and coupled counts, matrix size, spike-term length and amplitude, the per-neuron graded column and coupled position, release parameters, group offsets and the float64 step matrices [P | Q | S]); word 38 points to its state (release ring, this step's release, per-bin potential sums in float64, the coupled-group buffer, the steps left of each spike term). The C++ executor validates every extension field and reproduces the CPU runtime bit for bit, including checkpoint and resume; the acceptance runs each synthetic case without extension, with graded neurons, with coupling, with asymmetric coupling and spikelets, and with graded neurons and spikelets together (60 cases). The DX12 lane runs version 2 fixtures too (#39). A fifth phase, before the four of each tick, steps each coupled group in float64 from the state before the update, one thread per coupled row, in the CPU's order and with no fused operation. A graded neuron's release divides by its span as a correctly rounded float32, from a float32 reciprocal refined in double and then corrected by exact tests against the neighbouring midpoints; the host refuses a span whose reciprocal would leave the normal float32 range. Each neuron's synapses from graded sources are listed on the host, so the release sum reads only those, in ascending order. On 2026-10-16 the 60 version-2 acceptance cases and the 12 version-1 ones matched the CPU oracle bit for bit on a Series S (`docs/evidence/series-s-gpu-parity-v2-2026-10-16.json`).

The acceptance contract requires 12 version-1 cases, 60 supported version-2 cases and exactly 12 expected continuous-refractory-clamp refusals. Missing or duplicate cases and unexpected refusals fail qualification. Per-neuron `Membrane` and continuous refractory clamps remain refused.

**Batches** (`flymsg.native.export_batch`, `batch_fixture` in `lif.h`) carry several runs of one network: a base fixture, then for each run the words before the kicks that differ from the base, as (offset, word) pairs, and its own kicks.

- **Exactness.** A version-1 fixture ends with its kicks, so the network goes up once. The exporter checks that every run rebuilds its own fixture word for word, and the rebuilt words go through the same validation as any fixture.
- **Executor.** `flymsg_native --fixture BASE --batch FILE --run K` runs one of them.
- **Worker.** It runs a batch job (`"batch": {"sha256": ..., "runs": N}` in `job.json`, files `fixture.bin` and `batch.bin`) in order. It writes `output_<k>.bin` and `result_<k>.json` per run, and after an interruption resumes at the first run without a result.
- **Sparse counts.** With `"output": "counts"` in the batch the worker writes `counts_<k>.bin` instead of the whole state (`flymsg_native --counts FILE`, `Runtime::counts`). The format is `FMS1` (`0x31534D46`), all uint32 words: magic, step, n, bins and nnz, then nnz pairs (bin·n + neuron, count); then m and m pairs (neuron, first step as int32). `flymsg.native.read_counts` decodes it into the arrays `read_output` gives. It checks n, bins and step against the run's fixture and refuses out-of-range or repeated indices. The worker refuses any other `output` value, records the kind in each `result_<k>.json`, and lists the kinds it writes in `status.json` (`batch_outputs`). The console backend stops a job at the worker's first report when the worker does not list the kind it asked for, as a worker built before sparse counts does. Each `result_<k>.json` also records the run's time outside the advance: `prepare_ms` (rebuilding its fixture and runtime) and `write_ms` (writing and hashing its output); `result.json` sums them, like `advance_ms`, over the runs of this execution only.

Native checkpoints bind the complete fixture and cursor with a noncryptographic integrity/compatibility token. They do not authenticate an untrusted artifact. The UWP worker wraps them with SHA-256 asset checks and binds backend, shader, source commit and package identity. A job does not resume across a different package or backend implicitly. The Python CPU checkpoint and native checkpoint are distinct formats; conversion is not implemented.

The GPU host retains state across batches of up to 64 ticks within one `advance_gpu` call, uses barriers between each of the four phases and reads state at the requested endpoint or a requested lifecycle stop.

- **Inputs in a default heap.** The fixture's inputs are copied once into a default heap; an upload heap is read uncached on every tick.
- **Event-driven delivery, exact.** The host builds each neuron's outgoing synapses, as positions in the targets' incoming CSR, and a delivery bitset with one slot per delay-ring slot, seeded from the ring of the fixture or checkpoint.
  - Phase 3 ORs the bits of a spiking neuron's synapses into its slot.
  - Phase 2 sums a target's set bits in ascending order and clears only its own bits.

  The float sequence is the pull loop's, so parity is unchanged; the full connectome runs about 58 times faster on the Series S.

A new call currently rebuilds and uploads the device state. Persistent device ownership across body/control calls, fewer dispatches per tick, streaming recordings and complete body/environment checkpoints are subsequent optimizations, not claimed here.

## UWP packaging and console runbook

Run `scripts/build-native-uwp.ps1` from a Windows Visual Studio environment. It produces an **unsigned** x64 package with identity `GianlucaMazza.FlymsgWorker`, separate from the trainer. Use an appropriate development certificate/signing configuration before deploying through Xbox Device Portal. Keep the worker in the foreground. The app is a minimal XAML application (`app.idl` declares `Flymsg.App`; its `Flymsg.winmd` resolves the manifest's EntryPoint at activation, without which the console refuses to launch the app with 0x80070002) with file-based status and a dashboard for the TV.

- **What it shows:** the build commit and GPU adapter; the current job's state, progress, steps per second, ETA and app memory; the last error; the jobs since the app started (kept in memory, so a restart clears them); and the last completed job's spikes per count bin with its most active rows.
- **How it reads.** The job thread publishes a telemetry copy under a lock, and a UI timer reads it four times a second, so the dashboard never touches a job's state.
- **Controls.** The gamepad's B cancels the running job by writing the same `flymsg.worker_cancel/v1` file a host would upload. Y opens the 3D viewer in the system browser, at the address in `LocalState/viewer.json` (`flymsg.worker_viewer/v1`), and an uploaded `LocalState/open_viewer.json` does the same from the host. Edge on an Xbox has no WebGL, so there the page loads but draws no scene (see [viz.md](../docs/viz.md)). The app asks for no pointer, so the console shows no mouse-mode cursor.

Prepare a GPU qualification job against the exact packaged shader:

```bash
uv run python scripts/prepare_native_job.py --out jobs --shader native/uwp/Assets/lif.cso --adapter SraKmd_arden
```

Copy the generated job directory into the worker's `LocalState/inbox/`. Transfer `fixture.bin` first and `job.json` last. The job ID must equal the directory name. The worker validates fixture/shader hashes and adapter identity, estimates memory against the actual app limit, runs one job at a time and publishes `status.json`, `checkpoint.bin`, `checkpoint.json`, `output.bin` and `result.json`.

Retrieve artifacts and validate `output.bin` against the original Python oracle. Record installed package/source/shader, hardware adapter, memory usage outside the debugger, latency, throughput and outcome. The expected adapter is explicit and must match the actual console; an alternate adapter requires an intentional new job. `scripts/console_gpu_parity.py` runs the 12 version-1 fixtures as GPU jobs against an installed, running worker and checks each output against the oracle; Device Portal settings come from `XBOX_IP`, `XBOX_USER`, `XBOX_PASS` and optionally `FLYMSG_DEVICE_PIN` (a `--pinnedpubkey` pin that curl checks on every connection), never from files in the repository. The 2026-10-15 v1 run is `docs/evidence/series-s-gpu-parity-2026-10-15.json`. With `--v2`, the 2026-10-16 run passes all 72 supported cases and 12 expected refusals (`docs/evidence/series-s-gpu-v2-2026-10-16.json`); its raw archive rechecks output checksums and float32 state bytes against the CPU oracle. The `both` v2 lifecycle passes throughput, cancel and suspension/resume over 1,000,000 steps (`docs/evidence/series-s-lifecycle-v2-2026-10-16.json`). These are bounded synthetic qualifications, not full-connectome v2 performance or animal validation.

The independent #216 parity record is `docs/evidence/series-s-gpu-parity-v2-2026-10-16.json`.

To cancel, publish `cancel.json` containing `{"schema":"flymsg.worker_cancel/v1","job_id":"<id>"}`. It is checked at completed scientific boundaries. To recover a suspended or interrupted job, publish `resume.json` containing `{"schema":"flymsg.worker_resume/v1","job_id":"<id>"}` and restart/resume the worker. Interrupted jobs wait for explicit recovery. Completed jobs are not rerun. Failed/cancelled jobs are terminal; create a new job ID for a new attempt.

Suspension requests a deferral and stops at a completed boundary, then writes checkpoint metadata. A checkpoint publish whose temporary file does not grow is recorded as `failed` and is not replaced; only a replaced checkpoint can be recovered. The OS may still terminate a stalled process before that publish returns. An in-flight GPU fault quarantines resources, writes failure status where possible and exits the worker. On a Series S a Device Portal stop suspends the app at a boundary with a checkpoint, from which a resume completes bit for bit (`scripts/console_lifecycle.py`); GPU-fault lifecycle and a termination that bypasses suspension remain acceptance requirements for #40.

## Reuse and license

UWP build/project/package patterns and placeholder package icons are adapted from `gianlucamazza/xbox-gpu-training` at `d067b325b0232e0f766512e4b6e2c3ed902d478e`, MIT, copyright 2026 Gianluca Mazza. The original trainer and its accepted campaigns are unchanged. These assets are packaging placeholders, not a FlyMSG visual identity. The runtime and HLSL implement FlyMSG semantics directly and do not depend on transformer operators.

Continuous refractory clamps use a new Python electrical semantics. The native fixed-map
path retains the explicit historical boundary-reset mode. For the new continuous mode
it is equivalent only for coupled cells that cannot become refractory (graded, silenced,
stimulated, or a model without a refractory hold). The fixture exporter proves that
condition before admitting an electrical fixture; otherwise it raises
`NativeCapabilityError`. The acceptance report preserves original fixtures in their named boundary mode and lists
dynamic continuous refractory fixtures as unsupported. The 12 gap-all-free fixtures are qualified on the Series S
GPU (2026-10-16). This is not qualification of dynamic continuous clamps.
