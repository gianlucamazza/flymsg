# Observer rendering qualification

The owner accepted the [rendering ADR](adr-observer-rendering.md) on 2026-10-15.
Quest 2 remains unqualified. The initial immersive timing result failed; the
adaptive-controller fixes did not establish that the original workload fits.
The [current diagnosis](quest-rendering-diagnosis.md) includes a real-device
trial with every original skeleton loaded and rejected shader experiments.
Performance remains unresolved; this work must not be described as a lag fix.

## Implemented contracts

- `representation=surface` (default) requests original full-resolution surfaces.
  Admission is all-or-none, using the existing compressed-size estimate followed
  by actual buffer capacity checks. Estimates are not GPU memory measurements.
  Missing data, incomplete loading and exhausted capacity are visible states.
  Unsupported content is never substituted with skeletons.
- `representation=skeleton` explicitly requests every selected neuron's original
  skeleton, without geometric simplification. It does not allocate surface
  geometry buffers or queue surface manifests. Neither strict representation
  activates adaptive pixel-ratio reductions.
- `representation=mixed` reproduces the old diagnostic selection policy. Its
  automatic substitutions are explicitly **unqualified**; it is not an accepted
  fidelity mode or a successful fallback.
- `pages=1` enables the candidate spatial scheduler. Workers assign original
  segments to immutable pages. Every endpoint remains unchanged, crossing edges
  belong to exactly one page, and compaction retains original draw order.
  Complete strict skeleton scenes use an immutable resident original-order index
  arena and one compact-view cache. Camera changes update at most eight public
  geometry groups, without rewriting or uploading the resident arena. Coalesced gaps contain only conservatively rejected
  pages; hidden neurons remain hard barriers. If those barriers exceed the draw
  limit, the existing compact path preserves their visibility policy. Reports
  distinguish eligible, submitted and bridged indices and identify the fallback.
  A stable view builds one exact compact index from contiguous original runs,
  then draws once. Its generation key tracks exact page masks and neuron
  visibility, including changes hidden inside coalesced ranges. A changed view
  can immediately reuse the resident catalog, or keep the compact cache when
  its eligibility set is unchanged. Vertex buffers are shared by both index
  owners; memory reports include both arenas and all planner scratch buffers.
  This is not per-page GPU eviction or bounded initial/cache allocation/upload.
  Selection uses the union of eye frusta in
  geometry coordinates, including a conservative raster margin. Identical view
  stamps reuse the selection until geometry or visibility policy changes.
  Without the flag, the full reference submission remains available.
- Decoded mesh cache eviction uses an explicit 128 MiB byte limit. Managed CPU
  backing stores are deduplicated in reports. Driver GPU totals remain unknown;
  JavaScript heap, managed bytes and process RSS are distinct measurements.
- A separate preparation queue bounds worker concurrency while the existing
  network queue continues to overlap downloads. Reports retain full-session
  frame stalls and sample expensive memory inventories only at report intervals.
- Normal VR entry requires complete selected anatomy. Mixed diagnostic sessions
  require the explicit `check` mode; an incomplete scene cannot obtain a normal
  VR session merely because an empty view would meet a timing budget.
- The CPU HUD now includes frame preparation before render submission. Earlier
  small CPU readings excluded skeleton selection/index rebuilding and cannot
  establish that the workload was exclusively GPU-bound. GPU timers, when
  available, retain their render-query scope.

## Independent references and commands

The frozen reference renderer is commit `18224c3`, before page integration.
The [Quest capture archive](https://github.com/gianlucamazza/flymsg/blob/feat/vee-quest-qualification/docs/evidence/render-reference-18224c3-t20.zip)
contains raw colour, neuron-ID and packed-depth images, geometry hashes, camera
matrices, fixed replay timestamp 20 ms, and the frozen site hash. It captures
the old mixed view of 1,128 selected neurons, not a full-surface qualification.
The depth/ID passes intentionally exclude context and use opaque geometry;
colour captures direct rendering without the desktop composer. Raw RGBA rows
start at the bottom; depth uses the pinned three.js packing shader.

```bash
uv run python scripts/check_geometry_pages.py --out runs/render-pages-oracle/new-trial
```

This launches an owned headless browser against local files. The reference draws
original source indices independently of page selection. Six camera scenarios
exercise dense all-visible geometry, close inspection, near-plane clipping,
stereo projections, off-axis projection, long edges and depth ties. Colour,
ID and packed-depth must match byte-for-byte. Software WebGL is a correctness
test, never a headset performance result. Hashes, browser log and screenshot
are retained; output cannot overwrite an existing trial.

For an explicitly selected local `?check` page with completed loading:

```bash
node scripts/render_reference.mjs http://127.0.0.1:40623 TARGET_ID runs/reference/new 20
REFERENCE=runs/reference/new/reference.json CULLING=1 \
  node scripts/render_reference.mjs http://127.0.0.1:40623 TARGET_ID runs/reference/candidate 20
```

The second capture reuses the reference camera/projection and timestamp. Capture
refuses incomplete strict anatomy, hidden pages and active immersive sessions.
It restores replay/material/render-target state and writes completion metadata
last. These offscreen captures do not establish XR stereo timing.

For a fixed-time desktop trial on that same fully loaded page:

```bash
PAGES=0 node scripts/observer_trial.mjs http://127.0.0.1:40623 TARGET_ID runs/trial/reference 15
PAGES=1 node scripts/observer_trial.mjs http://127.0.0.1:40623 TARGET_ID runs/trial/candidate 15
```

The collector restores observer state, records all intervals, visibility changes,
source hashes, geometry submission and resource totals. Repeat in interleaved
order; these are diagnostics, not immersive qualification. Hidden trials remain
ineligible and partial content cannot pass the full-anatomy gate.

Device sampling is read-only and explicitly selects the headset:

```bash
uv run python scripts/quest_profile.py --serial QUEST_SERIAL \
  --seconds 30 --out runs/quest-profile/new
uv run python scripts/quest_xr.py --serial QUEST_SERIAL --representation skeleton \
  --pages --check --port 8895 --seconds 1800 --out runs/quest-xr/new
```

If using an isolated ADB server, set `ANDROID_ADB_SERVER_PORT=5038` for the
commands. No rules, persistent unit, clocks or safety settings are changed.
The native sampler records all browser child processes and raw KGSL counters;
counter reset semantics are not inferred. A bounded Perfetto capability trace
was collected, but native GPU render-stage timestamps are unavailable.

```bash
node scripts/observer_gpu_probe.mjs http://127.0.0.1:40623 TARGET_ID runs/gpu-probe/new
```

For an actual-scheduler residency trial on a complete strict skeleton scene:

```bash
node scripts/observer_residency.mjs http://127.0.0.1:40623 TARGET_ID runs/residency/new
node scripts/observer_context.mjs http://127.0.0.1:40623 TARGET_ID runs/context/new
```

The residency protocol records served-source hashes before running compact /
resident / resident / compact trials. Dense, anatomical-motion, close-motion and
close-static views retain original geometry and shaders. Full-source colour/ID/
depth references and every measured moving colour image must match. Actual
WebGL index-buffer upload calls/bytes are counted; resident steady state requires
zero. Diagnostic state and the complete reference must restore identically.
The context command is an explicit synthetic, non-immersive loss/recovery test;
it does not simulate headset presence or certify immersive lifecycle behaviour.

This separate offscreen diagnostic remains usable when the headset suspends
animation callbacks. It reads the whole framebuffer, verifies rendered and
discarded image witnesses, records a clear/readback control, and restores the
original shader and raster state. Altered shaders and discarded rasterization
are experiments, never a faster fidelity mode. The metric includes CPU command
submission, driver synchronization and readback; it is not a pure GPU timer or
an XR frame rate. An earlier `gl.finish`-only attempt was rejected because it did
not independently establish completed rendering. Readback equality for colour,
ID and depth verified restoration on the physical Quest.

The [recorded evidence](https://github.com/gianlucamazza/flymsg/blob/feat/vee-quest-qualification/docs/evidence/observer-rendering-2026-10-15.json)
includes the six-case raster pass and real Quest image comparisons. Culling on
the same loaded scene preserves all three image buffers exactly and submits
about 4.2% fewer line indices in that view. This does not establish sufficient
performance. Four interleaved timing attempts produced no animation callbacks
and were rejected. With explicit readback, the direct 1024-square scene took
about 61–64 ms wall time; the no-raster diagnostic took about 30 ms. Removing
line vertex shading naively made that diagnostic slower, not faster. Those
results justify neither a shader shortcut nor a successful XR timing claim.

## Remaining gates

The raster fixture passing does not qualify the real scene. Required next:
compare the frozen real-scene images with the candidate; measure warmed,
interleaved full-content trials on Quest, including all-visible and motion;
refine attribution of the remaining rendering cost before changing production shaders;
qualify the resident scheduler across workloads, bound initial GPU allocation/uploads
and implement eviction if required by admission policy; verify memory
plateau, thermal behaviour, context recovery and repeated XR enter/exit.

A mode that cannot preserve selected content within its resource and refresh
budgets must remain unsupported. Do not use a fast empty/partial scene, mixed
fallback, software GPU, hidden page or missing counters as qualification proof.
