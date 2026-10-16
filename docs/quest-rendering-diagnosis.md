# Quest rendering diagnosis

Status, 2026-10-15: **dense-scene/XR performance unresolved; Quest 2 not qualified**.
The [resident scheduler follow-up](observer-rendering.md#resident-catalog-and-compact-cache-result)
corrects the measured culling/index-streaming component and the CPU HUD's omitted
preparation time. It does not establish smooth immersive rendering.
Passing software checks or loading every neuron does not close this issue.

## Findings

The authorized physical Quest 2 is reachable through an isolated libusb ADB
server. USB rules and developer authorization are not the current rendering
failure. No persistent USB rules, device clocks, refresh, resolution, foveation,
proximity or safety settings were changed for these trials.

The earlier real immersive session failed its frame-time gate. Component trials
on the old mixed representation implicated both surfaces and skeletons; hiding
response neurons made the page faster but changed the observation. That is not
an admissible resolution. Conservative page culling removed only about 4.2% of
line indices in the recorded anatomical view and cannot alone establish a fix.

The new [evidence summary](https://github.com/gianlucamazza/flymsg/blob/feat/vee-quest-qualification/docs/evidence/quest2-rendering-diagnosis-2026-10-15.json)
and [raw archive](https://github.com/gianlucamazza/flymsg/blob/feat/vee-quest-qualification/docs/evidence/quest2-rendering-diagnosis-2026-10-15.zip) distinguish
the old mixed scene from the complete, unsimplified skeleton representation:

- Frozen source `8a76f6a40ef5cb7527d66e54039216335657ce01`, clean at site build.
- All 1,128 selected neurons loaded, none unavailable; 8,258,589 original segments,
  level zero for every skeleton. No surfaces were substituted into this mode.
- Managed CPU geometry: 303,051,944 bytes after index preparation. This is not
  total browser memory or GPU allocation.
- Direct rendering, one view, zero MSAA and no desktop composer. Every measured
  iteration reads the entire RGBA8 framebuffer. Rendered images are nonuniform;
  discarded draws produce the expected uniform clear image.

| Size        | Clear/readback | Full render | Raster discarded | Full repeat |
| ----------- | -------------: | ----------: | ---------------: | ----------: |
| 256 square  |         1.1 ms |     32.0 ms |          23.3 ms |     23.1 ms |
| 512 square  |         1.9 ms |     51.0 ms |          17.7 ms |     51.0 ms |
| 1024 square |         3.8 ms |     66.0 ms |          18.8 ms |     65.9 ms |

Values are medians of five **serialized wall-time** samples, after two warm-up
iterations. They include submission, browser/driver IPC and full readback;
they are neither GPU stage times nor XR frame intervals. The 256-square drift
and across-variant clock/thermal uncertainty prevent a precise additive stage
model. The size dependence supports investigating rasterization/overdraw as
well as geometry processing. It does not identify a single exclusive bottleneck.
These offscreen results do not prove a hardware limit or certify a stereo mode.

## Rejected optimizations

Three bounded experiments used the real loaded geometry. None became production
code:

1. Removing activity and colour work from the line vertex shader did not yield a
   stable improvement. It also changes rendering and is diagnostic only.
2. Computing colour/activity appearance once per neuron into an RGBA32F texture
   preserved every output byte in the tested mixed view. Interleaved A/B/B/A
   median times were 46.7 / 47.25 / 47.05 / 46.3 ms. It added a pass without a
   measured benefit.
3. Replacing the Bayer array lookup with equivalent integer arithmetic preserved
   every output byte in the tested full-skeleton view. At 512 square, A/B/B/A
   medians were 50.8 / 50.7 / 50.35 / 50.9 ms; at 1024 square they were
   66.85 / 67.45 / 67.5 / 67.7 ms. No useful improvement was established.

The latter experiments used eight samples after five warm-up iterations. They
are exploratory, fixed-camera/time diagnostics, not preregistered confirmation
or general shader-equivalence proofs. The original shaders, raster state and
render target were restored. The complete before/after 32-square reference
objects, including colour, neuron ID, packed depth, geometry hashes, camera and
activity, are identical in the archive.

## Resolution boundary

The [accepted rendering ADR](adr-observer-rendering.md) remains authoritative:
preserve all selected anatomy, explicit representation, original geometry as
reference, no resource-driven substitutions or hidden quality reductions.
Its implementation has corrected that fidelity failure and prevents normal XR
entry with incomplete anatomy. It has **not** demonstrated acceptable performance.

Do not merge or release this work as a complete Quest performance resolution. Outstanding
work remains bounded initial/cache uploads, remaining dense-scene cost and full-content XR
qualification, including dense views, motion, memory plateau, thermal behaviour,
context recovery and repeated entry/exit. No production shader change is justified
by the experiments above. Page scheduling alone is not an adequate resolution.

Under ADR decision 7, the current configuration must remain unsupported for a
qualified Quest offering until it passes those gates. A native renderer or
remote rendering is not an automatic next step: neither has measured benefit
here, and either requires a separate accepted ADR and end-to-end proof. This
diagnosis does not authorize a rewrite, a new host purchase, or weakened fidelity.

## Browser follow-up, 2026-10-16

The [machine-readable summary](https://github.com/gianlucamazza/flymsg/blob/feat/vee-quest-qualification/docs/evidence/quest2-browser-2026-10-16.json) and
[raw archive with independent verifier](https://github.com/gianlucamazza/flymsg/blob/feat/vee-quest-qualification/docs/evidence/quest2-browser-2026-10-16.zip)
record clean application `635c20a` and the later headless-only oracle option
`0d4c854`. Loaded application modules were read with CDP `Debugger.getScriptSource`
and matched the served source hashes. The archive verifier also checks the
captured main module against the retained source. The production renderer,
shaders, representation and resolution are unchanged.

### Plan and disposition

| Task               | Work completed                                                                                                                                                                                 | Remaining boundary                                                                                                         |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Replay UI          | Skip raster redraw when its bin, selection/run, width and DPR are unchanged; avoid rewriting identical clock labels. Selection/run changes, resize and Canvas2D recovery invalidate the frame. | Hardware timings use a synthetic maximum-selection fixture, not overall replay FPS.                                        |
| Initial/cache work | Account individual GL upload bytes and submission wall time separately from the steady loop and reference setup.                                                                               | Initial/cache allocation and upload scheduling is still unbounded; no fix is claimed.                                      |
| Dense GPU cost     | Add a bounded native realtime/CPU-profile collector and compare direct rendering with the actual desktop composer.                                                                             | Per-pass tile/render-stage attribution and a faster equivalent dense pipeline remain unresolved.                           |
| Browser            | Verify real Qualcomm Adreno 650 acceleration, loaded/served source identity, context settings and supported extensions. Keep bounded target-scoped CPU profiles.                               | No evidence supports forcing another ANGLE backend or browser flag. Browser/runtime lifecycle still needs an active panel. |
| Stereo multiview   | Check hardware extension availability and the pinned Three r170 path against Meta's documented model.                                                                                          | Extension presence does not implement stereo submission; no vendor patch or multiview implementation is shipped.           |

### Measured results

The raster retains only the current complete frame; it allocates **no additional
bitmap cache**. Ninety-six complete RGBA comparisons against the independent
frozen `drawRaster` from `63c63d6` pass on the Quest: sixteen layout/DPR/row-count
cases, repeated bins, forward changes and backward scrubbing. The canvas oracle
reads through separate sinks to avoid migrating only the repeatedly redrawn
source canvas from GPU to CPU rasterization through Chromium's readback heuristic.

The timing fixture contains forty synthetic rows and sixty bins, matching the
real looming replay's shape. At simulated 90 Hz callback timestamps and the
existing 40 ms/s replay speed, A/B/B/A median serialized canvas wall times are
**18.1 / 6.6 / 7.4 / 19.3 ms** (original / retained-frame / retained-frame /
original). With a different bin every update they are **18.2 / 19.0 / 17.9 /
18.5 ms**. Every sample includes complete sink readback; these exploratory
measurements are not JS-only durations, actual callback cadence, or an XR pass.
The raster is absent when no neuron is selected, so this cannot explain or fix
the original dense paused-view cost.

The direct workload still measures **50.2 ms** median over 146 iterations. Cold
reference preparation, outside that loop, made five `bufferData` calls totaling
**203,647,016 bytes** and approximately **463.1 ms** of submission wall time.
They include the position/owner/index buffers and contextual point attributes.
This was first offscreen GPU initialization while rAF was suspended, not a
measurement of the first visible browser frame. No geometry-buffer upload occurs
inside the steady direct loop.

The actual desktop composer with its existing 4x MSAA measures **137.35 ms** over
56 iterations at the same 512-square diagnostic size and square camera projection.
The two quality configurations are diagnostics; disabling MSAA/bloom is not the
production resolution. The desktop reference transition reuploads 66,068,712
index bytes before its timed loop; its only two steady-loop uploads total sixty
bytes of fullscreen-quad attributes. This distinguishes transfer spikes from the
remaining rendering cost without assuming that stage costs add linearly.

During the respective loop windows, system GPU counters have median vertex /
fragment shading shares of approximately **88.95% / 11.03%** for direct rendering
and **65.47% / 34.54%** for the composer. GPU frequency is 587 MHz in these
samples, without a forced clock. These counters are system-wide and sampled
once per second; shading shares do not partition the complete frame. CPU-profile
samples in `readPixels` include blocked driver/GPU wait, not equivalent CPU work.
Neither the earlier size dependence nor these counters establishes a single
exclusive bottleneck. They justify investigating vertex processing as well as
the desktop resolve/postprocessing path, rather than attributing everything to
fragment overdraw or browser JavaScript.

### Browser and tooling limits

Meta documents native [realtime GPU counters and render-stage tracing](https://developers.meta.com/vr/documentation/web/webxr-perf-tools/).
The existing on-device `ovrgpuprofiler` supplied the counters above. A subsequent
bounded detailed-mode attempt could not obtain a trace: after restarting Browser,
the CDP endpoint was unavailable in both detailed and restored normal modes.
The driver was verified **disabled**, as initially found, and the original local
URL was requested again. Visible-page restoration could not be verified. No
proximity override or synthetic user activation was used. The failed attempt is
retained separately from successful measurements.

The [Meta tool support table](https://developers.meta.com/vr/essentials/metavr-environment/)
lists macOS arm64 and Windows for its RenderDoc fork; no installed RenderDoc Meta
Fork was available on this Arch host. This does not assert that upstream RenderDoc
cannot run on Linux. Native realtime counters already provide useful evidence
without substituting an unverified capture tool.

[Multiview](https://developers.meta.com/vr/documentation/web/web-multiview/)
reduces duplicated stereo application/driver overhead, while GPU work may remain
duplicated. Both multiview extensions are exposed on this Quest, but the bundled
Three r170 renderer has no multiview integration. It cannot be enabled by a
quality setting. Replacing or forking the renderer would need the separate
accepted decision required by the rendering ADR. There is no measured evidence
that multiview would resolve the already slow single-view dense workload.

### Verification and next implementation gates

- 100 Node tests pass; one optional network test is skipped. Targeted Python
  pages/viz checks: fifteen pass, one deselected; four collector checks pass.
- Six independent software WebGL camera cases still match original full-source
  colour, neuron ID and depth for resident and cached paths. Software WebGL is
  correctness evidence only.
- The headless raster oracle also passes all 96 comparisons on explicitly selected
  CPU Canvas2D. That option belongs only to the diagnostic oracle; production and
  the Quest raster comparison keep the browser's default canvas backend.
- One bounded callback check saw a visible document but **zero rAF callbacks**.
  No new refresh, immersive, memory-plateau or thermal qualification is claimed.

Next work under the accepted ADR is generation-safe CPU preparation and bounded
GPU allocation/upload ownership for initial geometry and the compact-view cache,
with explicit preparation state before XR admission. It must retain full source
geometry, cancel stale view preparation without publishing partial indices,
rebuild resources after context loss, and compare colour/ID/depth against the
independent original renderer. Allocation stalls must be measured separately
from chunk transfers; splitting CPU copies alone does not establish bounded GPU
uploads. Dense single-view and warmed stereo timing remain mandatory gates.
This follow-up completes the browser investigations above and the verified UI
optimization; it does not complete those remaining renderer implementations or
make Quest 2 qualified.

### Subsequent immutable-page candidate

The [paged pipeline implementation](quest-paged-pipeline.md) now implements the
CPU worker preparation, explicit readiness and owned bounded upload scheduling
identified above. Its [software evidence](https://github.com/gianlucamazza/flymsg/blob/feat/vee-quest-qualification/docs/evidence/quest2-paged-2026-10-16.json)
retains exact original/candidate primitive and pixel comparisons, including the
unchanged desktop MSAA/bloom path. The preceding measurements remain historical;
they do not qualify this candidate. Both complete original representations still
require independent full-scene physical Quest acceptance before PR #205 is ready.
