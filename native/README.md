# Native execution lane

This implements the R1 fixture executor and the initial R2 worker source. It builds on the CPU architecture in [runtime.md](../docs/runtime.md). Its GPU lane is qualified on a Series S for the version-1 fixtures; lifecycle and throughput are not yet.

| Component               | Current evidence                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------- |
| Python fixture exporter | Contract tests; incoming edge order preserves CPU source traversal                                   |
| C++ CPU executor        | Exact synthetic state/spike parity, chunk/resume and corruption rejection on Linux                   |
| DX12 host and HLSL      | Windows compile gate; bit-for-bit parity on the 12 version-1 fixtures on a Series S GPU (2026-10-15) |
| UWP worker              | Launches on a Series S in Dev Mode and completes GPU jobs; real suspension and throughput remain     |

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

Version 2 fixtures add graded neurons and electrically coupled groups (`sim.Graded`, `sim.Gap`). Header word 37 points to an extension block (graded and coupled counts, matrix size, spike-term length and amplitude, the per-neuron graded column and coupled position, release parameters, group offsets and the float64 step matrices [P | Q | S]); word 38 points to its state (release ring, this step's release, per-bin potential sums in float64, the coupled-group buffer, the steps left of each spike term). The C++ executor validates every extension field and reproduces the CPU runtime bit for bit, including checkpoint and resume; the acceptance runs each synthetic case without extension, with graded neurons, with coupling, with asymmetric coupling and spikelets, and with graded neurons and spikelets together (60 cases). The DX12 lane refuses version 2 fixtures: its float64 group step and graded release need hardware qualification first (#39).

Native checkpoints bind the complete fixture and cursor with a noncryptographic integrity/compatibility token. They do not authenticate an untrusted artifact. The UWP worker wraps them with SHA-256 asset checks and binds backend, shader, source commit and package identity. A job does not resume across a different package or backend implicitly. The Python CPU checkpoint and native checkpoint are distinct formats; conversion is not implemented.

The initial GPU host retains state across batches of up to 64 ticks within one `advance_gpu` call, uses barriers between each of the four phases and reads state at the requested endpoint or a requested lifecycle stop. A new call currently rebuilds/uploads the device state. Persistent device ownership across body/control calls, event-driven sparse dispatch, streaming recordings and complete body/environment checkpoints are subsequent optimizations, not claimed here.

## UWP packaging and console runbook

Run `scripts/build-native-uwp.ps1` from a Windows Visual Studio environment. It produces an **unsigned** x64 package with identity `GianlucaMazza.FlymsgWorker`, separate from the trainer. Use an appropriate development certificate/signing configuration before deploying through Xbox Device Portal. Keep the worker in the foreground. The app is a minimal XAML application (`app.idl` declares `Flymsg.App`; its `Flymsg.winmd` resolves the manifest's EntryPoint at activation, without which the console refuses to launch the app with 0x80070002) with a one-line window and file-based status; a dashboard is not implemented.

Prepare a GPU qualification job against the exact packaged shader:

```bash
uv run python scripts/prepare_native_job.py --out jobs --shader native/uwp/Assets/lif.cso --adapter SraKmd_arden
```

Copy the generated job directory into the worker's `LocalState/inbox/`. Transfer `fixture.bin` first and `job.json` last. The job ID must equal the directory name. The worker validates fixture/shader hashes and adapter identity, estimates memory against the actual app limit, runs one job at a time and publishes `status.json`, `checkpoint.bin`, `checkpoint.json`, `output.bin` and `result.json`.

Retrieve artifacts and validate `output.bin` against the original Python oracle. Record installed package/source/shader, hardware adapter, memory usage outside the debugger, latency, throughput and outcome. The expected adapter is explicit and must match the actual console; an alternate adapter requires an intentional new job. `scripts/console_gpu_parity.py` runs the 12 version-1 fixtures as GPU jobs against an installed, running worker and checks each output against the oracle; Device Portal settings come from `XBOX_IP`, `XBOX_USER`, `XBOX_PASS` and optionally `FLYMSG_DEVICE_PIN`, never from files in the repository. The 2026-10-15 run is `docs/evidence/series-s-gpu-parity-2026-10-15.json`.

To cancel, publish `cancel.json` containing `{"schema":"flymsg.worker_cancel/v1","job_id":"<id>"}`. It is checked at completed scientific boundaries. To recover a suspended or interrupted job, publish `resume.json` containing `{"schema":"flymsg.worker_resume/v1","job_id":"<id>"}` and restart/resume the worker. Interrupted jobs wait for explicit recovery. Completed jobs are not rerun. Failed/cancelled jobs are terminal; create a new job ID for a new attempt.

Suspension requests a deferral and stops at a completed boundary, then writes checkpoint metadata. The OS may terminate a stalled process before checkpointing completes; only a matching completed checkpoint can be recovered. An in-flight GPU fault quarantines resources, writes failure status where possible and exits the worker. Physical suspension timing and GPU-fault lifecycle remain acceptance requirements for #40.

## Reuse and license

UWP build/project/package patterns and placeholder package icons are adapted from `gianlucamazza/xbox-gpu-training` at `d067b325b0232e0f766512e4b6e2c3ed902d478e`, MIT, copyright 2026 Gianluca Mazza. The original trainer and its accepted campaigns are unchanged. These assets are packaging placeholders, not a FlyMSG visual identity. The runtime and HLSL implement FlyMSG semantics directly and do not depend on transformer operators.

Continuous refractory clamps use a new Python electrical semantics. The native fixed-map
path retains the explicit historical boundary-reset mode. For the new continuous mode
it is equivalent only for coupled cells that cannot become refractory (graded, silenced,
stimulated, or a model without a refractory hold). The fixture exporter proves that
condition before admitting an electrical fixture; otherwise it raises
`NativeCapabilityError`. The acceptance report preserves original fixtures in their named boundary mode, lists
continuous refractory fixtures as unsupported, and separately qualifies all-free fixtures. This is not native
qualification of dynamic continuous clamps or GPU hardware.
