# ADR: fidelity-constrained geometry scheduling for the observer

Status: accepted by the owner, 2026-10-15. Implementation and hardware qualification pending.
Extends the accepted [observer ADR](adr-virtual-experimental-environment.md);
does not change its scientific or lifecycle boundaries.

## Context

Quest 2 is currently unqualified. The initial immersive session failed timing.
Correcting the adaptive controller's interval sampling fixes a real measurement
defect, but has not established acceptable headset performance.

The [component diagnostic](https://github.com/gianlucamazza/flymsg/blob/feat/vee-quest-qualification/docs/evidence/quest2-components-2026-10-15.json)
used the real Quest Browser, a visible page, fixed resolution and antialiasing,
and playing replay. Median callback intervals were approximately 234 ms with
7.2 million triangles and 3.4 million line segments; 100 ms with 0.8 million
triangles and 3.6 million segments; 11 ms after hiding the response group.
Restoring that group while leaving whole-CNS points hidden returned to 100 ms.
These are sequential desktop diagnostics, not GPU timings or an XR pass.
The evidence file retains raw intervals and methodological limitations.

The source explains a structural mismatch: a triangle budget can send neurons
to skeletons without accounting for their cost. Skeletons share one global
index buffer and disable object frustum culling. Their vertex shader fetches
activity and colour for each vertex; the fragment shader uses screen-door
transparency. Several million segments are submitted even though draw-call
count is low. Current measurements do not distinguish vertex processing,
memory bandwidth, rasterization, or synchronization as the dominant GPU stage.
Small JavaScript HUD times do not settle that question.

## Decision

Build one fidelity-constrained rendering scheduler shared by desktop and XR,
with representation correctness preceding resource scheduling. Preserve every
user-selected neuron, its identity, coordinates, topology, activity, timing,
selection and visibility policy. Resource pressure must not silently replace
surfaces with skeletons or omit neurons. Surface versus skeleton is an explicit
representation choice; loading state is reported separately.

1. Establish a frozen reference first: source/site hashes, scene and geometry
   hashes, replay timestamps, camera matrices, per-eye viewport and projection,
   resolution, shading and transparency settings. Capture colour, depth and
   neuron-ID reference outputs using the existing renderer before replacing it.
   Preserve original geometry as the independent geometric oracle.
2. Profile bounded trials on the device before choosing shader optimizations.
   Record browser renderer/main/GPU processes separately, GPU busy/clock and
   thermal state where readable, and native GPU stages where supported. Compare
   fixed replay timestamps and cameras; separately measure steady-state rendering,
   loading, buffer rebuilds and uploads. Unsupported counters stay unavailable.
   Diagnostic shader/pass substitutions are temporary and never qualification
   results. Do not change device clocks or disable safety features.
3. Partition original geometry into spatially bounded immutable pages with
   stable neuron IDs and explicit ownership. Skeleton partitioning preserves
   every original edge, including cross-page edges; surfaces preserve chunk
   boundaries. Separate immutable geometry from changing activity/colour data.
   Worker preparation and bounded uploads avoid main-thread allocation bursts.
   Resident memory, retained CPU copies and eviction have explicit byte accounting.
4. Select visible pages conservatively from the union of both eye frusta.
   A page visible to either eye must remain eligible. Account for line extent,
   near-plane intersection and scene transforms. Do not rely on occlusion culling
   for the initial solution: screen-door transparency makes opaque occlusion
   assumptions unsafe. A dense all-visible view is a mandatory benchmark;
   partitioning alone is not assumed sufficient.
5. Retain full geometry as the reference mode. Existing skeleton LOD's 0.5 device
   pixel tolerance is a candidate contract to verify against original paths,
   not permission to relax it. Surface chunk projected size is not a proven
   geometric error bound. Approximate surface levels require measured bounds
   before admission. Stereo checks use the stricter eye; clipping and camera
   motion must not create holes or unreported representation changes.
6. Schedule mesh, line, shading and transfer work together. Budgets constrain
   resource admission and report an unmet target; they never authorize dropping
   scientific content. Keep one renderer, animation loop and replay clock.
   Batch pages where profiling supports it; avoid replacing one giant submission
   with an uncontrolled number of draw calls. Choose shader/data-layout changes
   only from stage measurements and verify equivalent output.
7. If the declared fidelity cannot meet the observed refresh budget on standalone
   Quest 2, report that configuration as unsupported. Any alternative renderer,
   transport or host architecture requires a separate decision and measured
   end-to-end latency; it is not an implicit fallback.

## Acceptance and implementation sequence

Acceptance of this ADR authorizes the following staged work, with evidence at
each boundary rather than a promise that Quest 2 can sustain the workload:

1. Reproducible profiling harness and frozen visual/geometric references.
2. Immutable page preparation, memory ownership and conservative stereo culling.
3. Measured shader/upload/batching changes and explicit representation selection.
4. Full-scene qualification on the physical headset and desktop regression checks.

Correctness tests must use independent original geometry and fixed reference
captures, not the new scheduler's own selection as expected output. Verify
identity/activity at fixed timestamps, all source edges in reference mode,
no missing visible pages, clipping, stereo boundaries, loading transitions and
context loss/re-entry. Exact rendering changes use reference image/depth/ID
comparisons; permitted raster differences must be specified before examining
candidate results. Any approximation needs its own geometric bound and visual
acceptance criterion; image similarity alone cannot establish topology fidelity.

Performance trials cover default looming replay, dense all-visible geometry,
close inspection, motion and repeated enter/exit. Measure actual XR refresh,
complete eligible frame intervals, CPU/GPU availability, memory plateau and
thermal state. Use the existing p95 <= 1.1 frame budgets, p99 <= 2 budgets and
estimated missed slots <= 1% gate. Keep compositor drops distinct from estimates.
Repeat trials with interleaved baseline/candidate order after warm-up; predeclare
durations and exclusions. Hidden pages and incomplete sessions cannot pass.
All selected content and declared fidelity must hold during the timing test.

## Consequences

This is a geometry/resource architecture change, not an adaptive-quality patch.
It adds preprocessing, page metadata, lifecycle tests and reference artifacts.
Conservative culling may save little in dense views; profiling may show that the
remaining workload exceeds Quest 2. That is a valid outcome, not a reason to
weaken fidelity or reclassify a failed test. Existing scientific outputs and
the accepted headless experiment architecture remain independent.

## Alternatives

- Hide response neurons, substitute points, relax LOD error, lower resolution or
  skip replay frames: changes the requested observation; rejected as a resolution.
- Tune only the triangle budget: measured fallback increases unaccounted line
  work; rejected as the architecture.
- Rewrite immediately in WebGPU/native or add remote rendering: no measured
  proof of benefit yet and changes support/lifecycle/latency; deferred.
- Keep one unbounded line batch: low draw-call count does not bound geometry
  cost or permit conservative spatial selection; rejected.
