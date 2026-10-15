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
