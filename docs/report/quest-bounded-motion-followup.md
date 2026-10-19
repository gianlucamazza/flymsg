# Bounded selection motion follow-up

This implements the accepted runtime ADR's 0.4-pixel preparation / 0.5-pixel
retention policy. The ADR and historical hardware artifacts remain unchanged.
No improvement on hardware is established for this follow-up yet.

## Measured trigger

Frozen `febbfc2` on Quest 2, 16 MiB pages, full looming source:

- Three valid dense ABBA repeats have ratios 0.507769, 0.727700 and 0.592648
  (candidate/original p95), median 0.592648. All 1,087 bounded frame certificates
  passed independent replay; this does not admit a moving view.
- The first anatomical-motion ABBA block has original p95 245.0 ms and candidate
  p95 345.2 ms, ratio 1.408980. Its first candidate arm discarded 99 requests,
  fell back on 72 of 166 measured frames, and composed a selection in 115.9 ms.
  All measured error bounds stayed below 0.5 pixels. A single repeat is not a
  formal three-repeat performance veto.

Source inspection and five failing unit regressions show two unnecessary costs:
changed preferences discarded still-certified work, and unchanged native page
indices were uploaded again. The first cost also prevented retention between
0.4 and 0.5 pixels. These findings do not prove that they explain all observed
latency or that correcting them meets the admission threshold.

## Correction and ownership

Evaluate asynchronous replies and pending uploads against the actual pose
certificate, not equality with the latest preferred selection. Revalidate before
publication and before every draw. Retain current per-owner levels up to 0.5
pixels when they use no more indices than the newly preferred level; a genuinely
coarser preferred level can still replace them. Missing, invalid or stricter eyes
continue to force full source indices on the same draw.

After a worker reply, reuse ready current native buffers only for an identical
per-page selection. Inspect current ownership at reply time rather than retaining
GPU references across asynchronous execution. Current and pending snapshots can
reference an unchanged record; releasing either snapshot excludes records still
owned by the other. Context reset releases their union once. Changed buffers
publish only after the complete pending selection is ready. The full source,
current and at most one pending selection retain the existing ownership bound.
The worker still composes complete CPU replies; this change only avoids redundant
native uploads. Do not claim reduced worker composition from buffer reuse.

A separate zero-error regression exposed `Infinity * 0` producing `NaN` when
projection certification fails. The certificate boundary now maps nonfinite or
negative projection bounds to explicit infinity even for zero spatial error.
The draw path accepts only a bound <=0.5, matching selection/publication policy;
unproved clip-plane poses force full source indices on the same draw.

Resource reports add cumulative document counters `composed_pages`,
`reused_pages` and `installed_selections`, alongside discarded requests, fallback
frames, actual submitted indices, upload bytes and CPU/GPU ownership.

## Verification and decision rule

Unit regressions exercise the 0.4/0.5 interval with actual projection bounds,
pose changes during worker execution/upload, atomic multi-page publication,
shared-buffer cancellation, context reset and zero-error unproved projections. Existing stale-generation,
allocation failure and strict stereo/missing-pose cases remain mandatory.

Run the complete JavaScript suite and the real viewer bounded software oracle
before hardware collection. Preserve the running frozen campaign. Any replacement
campaign must use clean committed source and the same Wi-Fi full-source ABBA
protocol: 4/16/64 MiB, all four views, three repeats; at least 10% median p95 gain
in a moving view, favorable in each repeat, no view over 10% median regression.
A confirmed three-repeat negative veto may stop that configuration. Explicit
operator exclusions remain exclusions, never invented vetoes or improvements.
Compare discard, reuse, fallback and upload counters as diagnostics only; they
cannot substitute for cadence, error bounds, source coverage or physical XR.
Keep normal bounded-mode release gated by the accepted ADR and #177.

## Shared eye preparation

The first old candidate motion arms cost 74.25–76.60 ms median measured CPU
per frame, compared with 1.40–1.50 ms for originals. A host-only decomposition
using captured 4/16 MiB metadata attributed about 14–15 ms per pass to projection
certification and 3–5 ms to level selection. These host times do not qualify
hardware cadence or isolate all device costs.

Prepare Float32 eye matrices, absolute rows, composite rows, norms, viewport and
subpixel precision once per actual eye, then certify each box with the same
arithmetic and guards. Preparations snapshot all eye inputs and remain local to
the existing actual-pose cache. Invalid boxes cannot modify another certificate.
Resource counters `projection_views` and `projection_boxes` expose the ratio of
eye preparations to certified boxes. No geometric bound or clip policy changes.

An independent frozen b4427da implementation and the shared preparation produced
bit-identical scale/rounding for 188,240 certificates across all captured 4/16 MiB
boxes, 40 translated poses and two offsets: 182,212 finite and 6,028 unproved.
A host exploratory rerun reduced median certification from 14–15 to 10–11 ms;
its level selection timing varied. Treat this as CPU diagnosis, not device speed
or admission. Repeat the software viewer/context oracle and clean-commit device
protocol before qualifying the complete corrected runtime.

## Canonical camera calibration

The b4427da diagnostic campaign passed static correctness at 4/16/64 MiB, but
ordinary 4/16 MiB preparation was excluded by native Guardian focus. The 64 MiB
configuration was additionally excluded because its default camera differed from
the first profile by about 1e-13. No timing arms completed and no configuration
was admitted; the old exclusion remains unchanged.

Freeze the first complete camera as an explicit input to subsequent direct
correctness captures, as already done for cadence arms. Save the observed default
separately. Do not use tolerance or round values to accept a changed output.
Both correctness and cadence validate the frozen viewport, pixel ratio and MSAA
against actual preflight identity; the Python raw-receipt checker independently
rejects even a common viewport drift across all four arms. Original source
coverage, error and performance thresholds remain unchanged. Desktop correctness
still records its actual per-document camera; it is independent of timed arms.
The geometry audit now uses the camera/projection returned by the original
capture, including its matrix reconstruction, rather than the undecomposed input.

## Final-source hardware status

Clean source `6b2865a3c9bbb91be59e36c22dc3ccf428362ad0` passed sampled
Quest 2 static correctness at 4, 16 and 64 MiB, each covering all 1,128
neurons and 8,258,589 source segments. These are readback-only checks,
not cadence or physical XR admission.

The first 4 MiB dense ABBA block was excluded before completion. Collection
subsequently terminated on a Wi-Fi ADB device-identity timeout while opening
the next configuration. No complete valid ABBA block or final-source performance
benefit was established. Initial cleanup also encountered the disconnected
transport; recovery is recorded separately rather than overwriting that failure.

The implementation can merge as an explicit diagnostic mode. Performance
admission and physical XR qualification remain open under #177 and #24;
merging this change does not satisfy either gate.
