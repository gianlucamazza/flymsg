# ADR proposal: an explicit bounded-error skeleton mode

Status: accepted by the owner on 2026-10-16 for the disposable experiment and
its validation gates. Production integration remains conditional on those gates.
The accepted exact-geometry observer ADR remains in force for the default mode.

## Context

The complete looming skeleton workload contains 1,128 selected neurons and
8,258,589 original segments. Controlled physical-presence trials rejected the
4 MiB page candidate in dense views: the median of three paired p95 ratios was
2.0498 relative to the original renderer. A subsequent unattended diagnostic
retains a full primitive/color/depth/ID oracle and one valid dense block, ratio
1.5293; its interrupted matrix cannot admit or formally reject another mode.

New isolated device diagnostics are being retained with source 7c140db. The
original direct 512-square zero-MSAA probe measures a 62.6 ms median serialized
render/readback time; the existing desktop composer measures 165.1 ms. These
are artificial completed-image diagnostics, not immersive frame times or a
proof of an absolute hardware limit. Device counters are system-wide.

Paging and upload scheduling preserve fidelity but do not reduce the dense
primitive workload. Shader substitutions previously tested on the device did
not show a stable useful improvement. Disabling bloom/MSAA or silently replacing
content would change the current acceptance contract.

## Decision

Develop a separate, explicit `skeleton-bounded` candidate while retaining exact
original skeletons as the default and independent reference. Preserve every
selected neuron, branch/end point, connected component, closed path, identity,
activity, timing and visibility policy. Permit simplification only along
unbranched source paths, with an independently verified maximum projected
path deviation of 0.5 physical framebuffer pixels in each eye. This changes
rendered geometry; it must never be described as exact original edges.

Use source originals and path provenance to check the error independently of
the candidate simplifier. Selection uses actual per-eye projection, viewport,
world transform and near-plane bounds. Near-plane crossings, unproved bounds,
context/projection changes and incomplete preparation require full geometry;
never publish an intermediate incomplete selection. No relaxed surface mode,
new renderer, remote transport, lower DPR or altered MSAA is included.

Before production implementation, preregister raster acceptance separately:
subpixel geometric bounds do not prove identical screen-door transparency,
depth ordering or neuron picking. The existing exact raster oracle continues
for exact mode. Candidate topology/provenance/error tests, depth/ID collision
cases, conservative stereo clipping and a human visual acceptance gate must
all be explicit. No image similarity score substitutes for a geometric bound.

First implement a disposable, bounded experiment and measure its actual segment
reduction and interleaved device cost. Stop if the reduction, correctness or

> =10% repeated gain gate fails; do not ship a dormant complexity increase.
> Only a passing experiment proceeds to production scheduling/context recovery,
> full four-view cadence, sustained memory/thermal measurements and assisted XR.
> An unattended run cannot certify physical head motion or visual comfort.

## Consequences

This creates a visibly declared approximation with a testable bound; performance
and XR success are not promised. Full geometry remains available and is required
when a bound is unproved. Source scientific files and simulation results stay
unchanged. The current exact-mode Quest qualification issue remains open.

## Alternatives

- Continue exact geometry only: finish measured stage/data-layout experiments,
  retain the unqualified Quest status if they fail. This preserves the current
  contract and does not promise a path to headset refresh budgets.
- Lower pixels, MSAA or hide anatomy: excluded from this proposal and from the
  existing exact-mode trial; these alter independent quality/content dimensions.
- Native/multiview or remote rendering: require a separate architecture ADR and
  measured end-to-end latency; no claim of benefit has been established here.
