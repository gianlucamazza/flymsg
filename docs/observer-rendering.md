# Observer rendering qualification

The owner accepted the [rendering ADR](adr-observer-rendering.md) on 2026-10-15.
Quest 2 remains unqualified. The initial immersive timing result failed; the
adaptive-controller fixes did not establish that the original workload fits.

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
  The shared vertex buffer and single line draw remain; this is not yet a GPU
  page-residency/eviction implementation. Every frame evaluates the union of
  eye frusta in geometry coordinates, including a conservative raster margin.
  Without the flag, the full reference submission remains available.
- Decoded mesh cache eviction uses an explicit 128 MiB byte limit. Managed CPU
  backing stores are deduplicated in reports. Driver GPU totals remain unknown;
  JavaScript heap, managed bytes and process RSS are distinct measurements.
- Worker concurrency bounds skeleton preparation. Reports retain full-session
  frame stalls and sample expensive memory inventories only at report intervals.

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
was collected, but GPU render-stage attribution has not yet been established.

## Remaining gates

The raster fixture passing does not qualify the real scene. Required next:
compare the frozen real-scene images with the candidate; measure warmed,
interleaved full-content trials on Quest, including all-visible and motion;
attribute the remaining GPU cost before changing shaders; implement bounded
GPU page residency/uploads if those measurements require it; verify memory
plateau, thermal behaviour, context recovery and repeated XR enter/exit.

A mode that cannot preserve selected content within its resource and refresh
budgets must remain unsupported. Do not use a fast empty/partial scene, mixed
fallback, software GPU, hidden page or missing counters as qualification proof.
