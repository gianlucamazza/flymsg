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

Resource reports add cumulative document counters `composed_pages`,
`reused_pages` and `installed_selections`, alongside discarded requests, fallback
frames, actual submitted indices, upload bytes and CPU/GPU ownership.

## Verification and decision rule

Unit regressions exercise the 0.4/0.5 interval with actual projection bounds,
pose changes during worker execution/upload, atomic multi-page publication,
shared-buffer cancellation and context reset. Existing stale-generation,
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
