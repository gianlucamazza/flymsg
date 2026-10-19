# ADR: certified bounded skeletons in the existing observer runtime

Status: accepted by the owner through approval of the implementation plan on
2026-10-16. Extends the accepted bounded-path experiment; does not rewrite it.

## Context

The fixed-view experiment preserves 1,128 neurons with a half-pixel path bound
and reduces serialized desktop work by about 66% dense / 48% close. Preparing
it on the main thread takes 21–24 seconds. This is not interactive or XR proof.
Existing immutable page ownership and chunked upload infrastructure remain the
runtime boundary. Original data, materials, activity and clocks remain unchanged.

## Decision

Add explicit `representation=skeleton-bounded`, initially requiring `check`.
It uses the existing paged renderer automatically; an explicit `uploads=0` is
invalid. Original representations and the original default stay unchanged.

Prepare canonical full pages, immutable source provenance, anchored graph paths
and dyadic spatial levels in the existing page worker. Original degree != 2
vertices are anchors even across page boundaries; cycles retain all edges.
Retain the full index and only independently certified levels. Original source
arrays remain immutable on the main thread. Per-page coarser CPU indices consume
at most one additional full-index byte budget; consider coarsest levels first.
The full resident GPU index, current selection and one pending selection bound
index ownership. Reuse native buffer ownership, 256 KiB transfers and 1 MiB/2 ms
submission budgets; report synchronous driver overruns rather than hiding them.

A worker composes selected page indices; the main thread selects levels using
per-neuron certificates, never traversing every edge per frame. Replies are
identified by content/context generation and selection request. Publish complete
selections atomically; cancel/discard obsolete generations and release ownership.

For clip rows a_x, a_y and c=w and a source box with strictly positive w_min,
bound each projection gradient by |a|/w_min + max|numerator| |c|/w_min^2.
Combine viewport-scaled x/y bounds with the Euclidean norm. Multiply by the
independently verified spatial path error. Include conservative float32 transform
roundoff from the actual uploaded model-view and projection matrices. Apply the
stricter eye, actual viewport and data transform immediately before every draw.
Use full geometry when the box intersects a clip plane, the numeric bound is
unproved, or the sum exceeds 0.5 physical framebuffer pixels. Prepare preferred
selections at 0.4 pixels, retaining valid current selections up to 0.5. Missing
or changing XR poses never reuse a previous pose certificate blindly.

Use full source indices for picking and diagnostic neuron-ID/depth passes.
Certify direct colour raster differences within independently constructed source
path footprints expanded by the half-pixel bound and existing conservative raster
margin. Desktop comparison propagates that footprint through the pinned bloom
kernel support; it does not demand false post-bloom pixel identity. Materials,
activity and original-mode colour/depth/ID remain exact. Inspect depth collision,
clipping, thin branch and stereo cases; no image score replaces topology or the
path bound. Human visual acceptance is required before normal use.

Record bounded state, generation, current projected upper bound, submitted lines,
full-geometry fallback frames, transfers and owned CPU/GPU bytes. Incomplete data
or allocation failure cannot be reported as complete. Context loss invalidates
all GPU ownership; rebuild from retained original sources before admission.

## Qualification and consequences

Keep the mode diagnostic until unit, independent raster/error, complete device
cadence, sustained memory/thermal and human visual/XR gates pass. Test 4/16/64 MiB
pages with the existing four-view three-repeat ABBA protocol. Require >=10%
median p95 improvement in a moving view, favorable in every repeat, and no view
with >10% median regression. Select the admitted winner by measured gain, using
owned memory to break ties within one percentage point. Count fallback frames
and upload work in the measured windows. A failure is not permission to increase
the error, omit content or lower display quality. No admitted configuration means
no normal bounded-mode release. One final assisted session groups the existing
physical visual, head-motion, lifecycle and sustained XR checks.

## Alternatives

Per-pose projected simplification on the main thread is rejected because it
blocks interaction and cannot track head motion. Native/remote renderers,
multiview forks and relaxed surfaces remain separate decisions. The original
full renderer remains the independent reference and supported fallback mode.
