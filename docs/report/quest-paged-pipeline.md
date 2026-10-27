# Immutable GPU page candidate

Status: experimental implementation merged in #205 on 2026-10-16,
**not a Quest 2 qualification**. Both complete original surfaces and complete
original skeletons must pass separately before hardware support is claimed in #177.
This implements resource scheduling within the accepted
[observer rendering ADR](../adr/adr-observer-rendering.md); it does not amend that ADR.

## Runtime contract

`?representation=surface|skeleton&uploads=1` enables the candidate. The existing
renderer remains the default and independent reference. `mixed` is rejected with
paged uploads. `gpuPageMiB=4|16|64` selects the allocation trial; 4 MiB is the
initial default, not a hardware-qualified optimum. `pages=1` additionally enables
conservative page culling. There is one renderer, animation loop and replay clock.
Resolution, MSAA, bloom and original anatomy are retained.

The worker packs source primitives in submission order, remapping vertices only
to copy their original float32 values. Original normals are copied after full
fragment finishing, never recomputed at a boundary. Cross-page line endpoints
are duplicated without changing any edge. Page provenance identifies source
fragment/neuron, first primitive and count. Colour and activity remain separate
per-neuron textures. Surface shaders omit identity batch transforms and indirect
instance lookups; equivalent output must pass the original renderer oracle.

Packing streams one completed page at a time, with GPU backpressure. Copying to
the worker yields after a 2 ms slice, with 256 KiB copy operations. Native upload
submission permits at most 1 MiB or 2 ms per existing animation tick, in chunks
of at most 256 KiB. Synchronous driver calls cannot be preempted: allocation,
submission, maximum tick/call duration and budget overruns are reported rather
than hidden. When animation callbacks stop, upload completion waits for a signal
instead of polling the main thread.

Native buffers use public `GLBufferAttribute` and WebGL2 APIs. Index buffers are
first classified on a private VAO; COPY targets preserve the renderer's VAO and
array bindings. Each buffer has one owner. Native attributes are detached before
geometry/VAO disposal; the owner deletes buffers exactly once. Context loss
abandons invalid handles and rebuilds a new generation from CPU originals.

Pages become drawable only after the generation is complete. GPU readiness also
waits for a full-quality colour draw and its nonblocking GPU fence, including
initial shader/texture work. VR admission is disabled until ready; the click
still calls `requestSession` before its first await. Source changes cancel stale
work and publish no incomplete generation. Camera movement only changes page
eligibility, without rebuilding or uploading indices. Bounds include both
endpoints and conservative float32 roundoff; either eye can retain a page.
Transparent pages retain their original object's sort centre and source order.
Opaque anatomical pages share a conservative sort centre, preserving the single
reference object's primitive order and neuron-ID ownership at equal depth. Bounds
remain valid public geometry bounds; page-box culling remains independent.

Catalog discovery, soma preparation and selected neuropil preparation participate
in one context-readiness policy used by both VR admission and the GPU candidate.
An optional absent local soma export is distinct from an explicitly requested
missing layer. Context coordinate/colour conversion and full mesh concatenation
and normals run in the existing geometry workers. Raw skeleton parsing and levels
also run there, transferring the input instead of cloning it on the main thread.
Worker-owned legacy fragments
use zero-copy input views; canonical source outputs remain retained on the CPU.
Worker failures reject their pending jobs, and pending input bytes are reported
separately from geometry/GPU totals. A changed selection can recover from a failed
GPU allocation after the previous generation's resources have been released.

The original global surface/skeleton arenas are constructed lazily for an
explicit diagnostic capture, not during candidate startup. Source slot reuse is
checked against the pinned Three.js public instance allocator, including holes
and submission order. An oracle capture intentionally allocates reference GPU
resources: use a fresh page/process for subsequent cold-memory/performance trials.

## Diagnostics and reproducible checks

`flymsg.fidelity()` retains CPU anatomical status and adds `gpu_ready` (null for
the untracked original path). `flymsg.resources().gpu_resources` exposes state,
generation, prepared/uploaded/staging bytes, owned native GPU bytes, allocation
and submission durations, cancellations and overruns. Worker input bytes are
known transferred data, not a claim about total worker/browser memory.
`gpu_total_bytes` remains unavailable. XR records content readiness every frame,
separately from its slower resource samples and its timing verdict.

Under `?check`, `flymsg.reference({pipeline:"original"|"paged", ...})` captures
colour, neuron ID and packed depth; the default is always the original oracle.
`flymsg.gpuInventory()` reads actual native buffer contents outside timing runs,
including checksums and primitive provenance. CPU originals are not replaced by
candidate-generated expected arrays.
`flymsg.desktopReference()` captures the actual desktop framebuffer at unchanged
resolution, MSAA and bloom settings while the diagnostic owns the renderer.

Direct/compositor probes use `flymsg.renderScene()`/`renderDesktop()` to select
the same pipeline as the application loop, and record that pipeline explicitly.
Serialized probes suspend ordinary animation-loop scene/control updates and
restore the complete diagnostic state on success and failure. This prevents
OrbitControls roundoff or idle renders from changing a supposedly frozen trial;
it cannot suspend an immersive session and is never an FPS qualification path.
The legacy resident-index probe rejects immutable pages instead of accidentally
timing the hidden reference. Context recovery also waits for the active pipeline.

```sh
node --test tests/js/*.test.mjs
.venv/bin/pytest -q tests
.venv/bin/python scripts/check_geometry_pages.py --oracle paged --out NEW_DIRECTORY
.venv/bin/python scripts/check_geometry_pages.py --oracle viewer-surface --timeout-seconds 240 --out NEW_DIRECTORY
.venv/bin/python scripts/check_geometry_pages.py --oracle viewer-skeleton --out NEW_DIRECTORY
```

The paged oracle compares exact source/GPU primitive streams and colour/ID/depth,
including depth ties, clipping, translucent context, cancellation, five release
cycles and context restoration. It also exercises actual context-worker messages,
input ownership transfer and point primitives. The viewer oracles use **two explicitly declared
real source neurons**, three replay timestamps and two camera positions, with
the actual application materials and page culling. They retain both raw RGBA
images and view matrices. Direct colour/ID/depth comparisons are supplemented by
three full desktop frame comparisons per representation with 4x MSAA and bloom.
They require source network
access. These reduced fixtures test correctness only; neither they nor
SwiftShader establish full-scene, physical stereo or performance qualification.
`--timeout-seconds` bounds the complete software test, including readbacks and
raw-image transport. It does not alter any physical frame-time acceptance gate.

The pinned Three.js baseline emits stale-context deletion warnings when ordinary
geometry/materials are disposed after context restoration. A control with only
Three.js, without the candidate, reproduces this. The page oracle checks restored
images and valid current GPU state before final cleanup; it does not reinterpret
these baseline cleanup warnings as proof of candidate speed or total GPU memory.

Hardware collection explicitly selects the candidate:

```sh
ADB_LIBUSB=1 ANDROID_ADB_SERVER_PORT=5038 .venv/bin/python scripts/quest_xr.py \
  --serial <quest-serial> --scene looming --representation skeleton \
  --uploads --gpu-page-mib 4 --pages --check --seconds 1800
```

Repeat separately for surfaces. The collector requires clean committed source;
it records upload/page settings and never substitutes content or forces headset
presence, clocks, refresh, resolution, foveation or a browser backend.

## Recorded software evidence

The [summary](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/quest2-paged-2026-10-16.json) and
[raw archive](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/quest2-paged-2026-10-16.zip) freeze source revision
`754c65e`, exact source hashes, both raw images in all 42 comparisons, camera
matrices, actual native buffer hashes, worker/lifecycle checks and the reproduced
depth-tie regression. Extract the archive and run `python verify.py .` to check
inventory, raw byte equality, nonempty neuron IDs and provenance independently.
An optional repository argument also verifies source blobs at the frozen commit.
The compressed archive was extracted afresh and verified before publication.

Node tests: 129 passed, one optional network test skipped. The clean complete
Python suite passed 711 tests with two deselected on `c32de77`; subsequent code
changes only make the software collector timeout configurable and align its CDP
limit. The final exact PR head must additionally pass CI. Both incomplete surface
collector attempts remain in the archive and are not counted as passing trials.
These correctness results do not establish a performance improvement on Quest.

## Outstanding acceptance

The [2026-10-16 physical attempt](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/quest2-qualification-2026-10-16.json)
now reaches complete 4 MiB paged skeletons on Quest. Its partial 90 Hz immersive
session fails timing (p95 723.923 ms, p99 773.669 ms; 94.58% estimated missed slots)
while content checks pass. A later 72/90 Hz aggregate is indeterminate, not a pass.
No complete surface or 4/16/64 MiB qualification is established by this attempt.

- Full original surfaces still obey the existing explicit admission capacity.
  A complete selection exceeding that capacity is unsupported, not rendered
  partially. This is **not** a measured Quest hardware limit. No automatic budget
  increase, skeleton substitution or geometry reduction is introduced.
- Obtain an active, visible Browser/CDP session before stage profiling or timing.
  A connected USB device, sleeping headset or zero callbacks cannot pass.
- On the physical device, compare 4/16/64 MiB allocations and select the largest
  passing correctness, latency and memory checks. Retain all overruns. Attribute
  dense GPU cost before accepting further shader changes.
- For each representation, run original/candidate/candidate/original, 30 seconds
  per arm, in dense, close, static and moving views. Preserve complete content and
  native quality; a source-admission failure invalidates the trial.
- Verify ten minutes of continuous operation and five physical VR entry/exit
  cycles per representation. Keep thermal state, all eligible intervals and
  compositor drops separate. At actual XR refresh require p95 <= 1.1 frame
  budgets, p99 <= 2 budgets and estimated missed slots <= 1%. Desktop targets
  60 Hz. Timing alone cannot override failed or unverified content readiness.
- Keep hardware qualification open until both representations pass on the exact
  candidate tree with CI and hardware evidence. Merge of #205 did not pass these gates.
  An alternative renderer, transport or host
  requires a separate accepted ADR; missing evidence never authorizes a fallback.
