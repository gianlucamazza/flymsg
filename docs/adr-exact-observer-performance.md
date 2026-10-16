# ADR: exact observer performance qualification

Status: accepted by the owner through the implementation instruction, 2026-10-16.

## Context

The owner requires performance work without geometric simplification or quality
reductions. The bounded-path experiments establish neither exact fidelity nor
physical XR qualification. Their original decisions and evidence remain immutable.
This decision supersedes their use as the solution for the current Quest and
desktop performance work; it does not erase the historical experiments.

## Decision

Qualify only complete original skeletons and original surfaces, separately.
Preserve original Float32 geometry, primitive order, neuron identity, activity,
transparency, resolution and MSAA. Resource pressure cannot change representation,
hide selected content or lower quality. Conservative union-of-eye culling must
preserve the original output, including clipping and transparency boundaries.

Keep approximate implementations explicitly diagnostic and outside this
qualification. Attest requested representation and source-geometry identity in
preflight, raw frame identity and independent ABBA scoring. Missing fidelity
evidence fails closed; older evidence is not retroactively admitted or rescored.

Profile the exact original and existing exact paged pipeline before choosing an
optimization. Change only a measured cost, one intervention at a time. Independent
original colour/depth/ID and primitive-coverage checks precede timing. Retain the
existing four-view, three-repeat 4/16/64 MiB ABBA admission and physical XR gates.
Unavailable GPU counters remain unavailable; diagnostic shader substitutions never
qualify the final renderer. Keep one renderer, application loop and replay clock.

Testing uses explicit Wi-Fi ADB. Temporary power/proximity leases have verified
cleanup. Phone, Xbox and scientific validation remain separate requirements.

## Consequences

A measured hardware limit is an acceptable outcome, but not a completed fluidity
qualification. Keep the affected requirements open. Missing readiness, sleep,
focus loss and transport errors are exclusions rather than hardware-limit proof.
Any alternative architecture requires its own accepted decision and end-to-end
fidelity/latency evidence. No performance gain is claimed by this decision.

## Alternatives

- Bounded geometry, reduced anatomy, lower resolution/MSAA or implicit fallback:
  rejected for this solution because they change the requested observation.
- Immediate native, WebGPU or remote-rendering rewrite: deferred until measured
  exact-path costs justify a separate architectural decision.
- Delete historical approximate code and results: unnecessary; retain them as
  explicit diagnostics without using them as exact acceptance evidence.
