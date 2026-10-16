# Quest performance investigation and bounded-path experiment

The accepted bounded-error experiment is complete. It demonstrates a useful
fixed-view reduction, **not a completed interactive or XR performance fix**.
The default renderer and scientific outputs are unchanged. See the accepted
[experiment ADR](adr-observer-screen-error.md) for the different fidelity contract.

## Completed work

- Full original looming skeletons: 1,128 selected neurons, 8,258,589 segments.
- Clean frozen device source, explicit ADB Wi-Fi transport, unchanged DPR 1,
  four-sample scene MSAA and enabled bloom in desktop comparisons.
- Full-scene original/paged primitive coverage, stereo color/depth/neuron-ID
  references and full-quality desktop references. 4, 16 and 64 MiB correctness
  checks pass; none establishes sufficient performance by itself.
- Three valid physical-presence dense A/B/B/A blocks reject 4 MiB: median p95
  ratio 2.0498. Two valid 16 MiB blocks remain incomplete, with later excluded
  windows explained by the owner removing the headset. No formal 16/64 cadence
  verdict is inferred from partial matrices or serialized diagnostics.
- Reversible unattended automation, independently attempted cleanup and verified
  return to physical sensor control. These samples remain separate from worn XR.

## Exact-geometry stage isolation

These are single-order, eight-second artificial 512-square completed-image
probes, including readback and CPU/driver wait. They are not GPU timers, paired
optimization confirmation or immersive frame cadence.

| Pipeline     | Direct, no desktop composer | Existing desktop composer |
| ------------ | --------------------------: | ------------------------: |
| Original     |                     62.6 ms |                  165.1 ms |
| Pages 16 MiB |                     68.5 ms |                 196.25 ms |
| Pages 64 MiB |                     65.3 ms |                  175.8 ms |

Native realtime counters were collected over Wi-Fi. System GPU utilization is
about 85–88%; vertex shading accounts for about 68–76% of shading time in the
direct probes, while fragment shading accounts for about 54–68% in the composer
probes. These system-wide counters do not partition complete frame time and do
not establish an exclusive bottleneck. No device clock or driver mode changed.
They support reducing proven geometry work and examining the compositor;
paging alone has not supplied a demonstrated win here.

## Accepted bounded-path experiment

The candidate reconstructs unbranched source paths and simplifies in projected
space. A separate verifier imports none of its path walker, projection or error
estimator: it checks every original edge once, branch/end points, cycles,
clipping fallback and projected error using the pinned vector implementation.
Closed and unproved clipped paths retain their original edges. The experiment
checks three synthetic views (left, center, right), each at the actual desktop
framebuffer dimensions. These are not tracked physical headset eye projections.

For an unclipped path with positive homogeneous depth, projection maps each
source edge continuously to a screen segment. All source vertices of a replaced
path must lie in the half-pixel capsule around its chord; convexity bounds the
complete intervening segments as well. Continuity between the retained endpoints
also bounds the reverse chord-to-path distance. This is a projected path bound,
not a depth-order or transparency equivalence proof.

The reproducible CLI was exercised on clean `6d9bef1`, on the Quest over Wi-Fi.
Both fixed-camera views run three A/B/B/A blocks, five warmups and eight raw
completed-image samples per arm. Every arm checks the actual submitted line
count. Resolution, MSAA, materials, activity and bloom agree; the deliberate
path simplification is the only changed content dimension.

| Fixed view | Original segments | Bounded segments | Maximum verified error | Original paired medians | Bounded paired medians |
| ---------- | ----------------: | ---------------: | ---------------------: | ----------------------: | ---------------------: |
| Dense      |         8,258,589 |        2,090,860 |           0.4999991 px |        182.13–183.58 ms |         61.93–62.50 ms |
| Close      |         8,258,589 |        4,392,101 |           0.4999994 px |        120.38–121.10 ms |         62.25–62.47 ms |

Every repeat exceeds the preregistered 10% exploratory gain gate: about 66%
less serialized wall time in dense view and 48% less in close view. Preparation
still costs 20.9 and 23.0 seconds, outside measurement. Original color/depth/ID
reference state is identical after restoration. A prior corrected collector run
replicates the gain; the initial null-source collector failure is retained and
excluded rather than counted as a timing result.

The pixel images change, as expected for this approximation. A geometric
half-pixel bound does not establish identical Bayer transparency, depth ordering,
picking or visual comfort. The offline archive verifier checks hashes, raw
statistics and recorded reports; the actual geometric check runs independently
in-browser against the retained source arrays. Offline verification does not
reconstruct those source paths from summary fields.

```bash
ANDROID_ADB_SERVER_PORT=5038 uv run python scripts/quest_bounded.py \
  --serial 192.168.1.146:5555 --out /new/immutable/evidence/directory \
  --unattended
```

## Reviewable artifacts

The [machine-readable report](evidence/device-trials-wifi-2026-10-16.json) links
its checksummed raw archive and independent verifier. Full-size captured pixels
are available for visual review:

- Dense: [original](evidence/quest-bounded-dense-original-2026-10-16.png),
  [bounded](evidence/quest-bounded-dense-bounded-2026-10-16.png).
- Close: [original](evidence/quest-bounded-close-original-2026-10-16.png),
  [bounded](evidence/quest-bounded-close-bounded-2026-10-16.png).

The retained visual-artifact run `c2205a1` repeats the gain (dense approximately
182–184 to 62 ms; close approximately 123 to 63 ms). Tiny frozen-pose differences
can change the threshold decision for one segment; each run retains its own
camera, projection, geometry hashes and per-neuron bound rather than treating
these captures as one identical-pose matrix. The static readback preflight is
explicitly ineligible for cadence or XR receipt qualification.

## Remaining implementation plan

1. Move the demonstrated preparation into generation-safe workers and retain
   auditable path/error certificates. Bound allocations and uploads using the
   existing scheduler; obsolete generations must never replace the complete view.
2. Establish a conservative bound for actual changing eye projections and
   viewport dimensions. Revalidate before publishing a frame; retain full paths
   for unproved near-plane/depth cases. A fixed-camera certificate cannot simply
   be reused after camera motion. Cancellation and context recovery are required.
3. Preregister raster/depth/picking acceptance, including transparency and tie
   cases; verify independent source topology and error for moving/stereo views.
   Record the human visual acceptance required by the ADR before production use.
4. Run the complete four-view, three-repeat cadence matrix and sustained memory/
   thermal trials. The present serialized 62 ms value is not a headset FPS
   prediction, a refresh-budget pass or grounds to admit the mode.
5. Only then qualify physical stereo, head motion, context recovery and repeated
   enter/exit. Surfaces and physical-phone baselines remain separate gates.

The candidate is intentionally not imported by the production entrypoint. The
experiment clears a research gate; normal XR and production admission remain
false. Issues #24 and #177 remain open. Implementation and raw evidence are in
[PR #221](https://github.com/gianlucamazza/flymsg/pull/221).
