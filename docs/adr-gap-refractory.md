# ADR: electrical coupling with refractory voltage clamps

Status: accepted, 2026-10-13. Accepted by the user before implementation.
Scope: the optional electrical path of B2; supplements the accepted
[architecture](architecture.md) and [runtime](runtime.md) decisions.

## Context

At `9a52fe2`, `gap_arrays` exponentiates the full connected component assuming all
membranes are free. `_advance` zeroes the refractory cell's synaptic forcing and discards
its updated voltage, but the exponential still includes its virtual voltage excursion
inside the step. This does not integrate the stated condition that a refractory cell
stays at rest throughout that step. Kernel/reference parity shares this assumption and
cannot establish correctness of the clamp.

Independent two-cell diagnostic: coupling/leak = 5, default parameters, cell 0 initially
5 mV above rest, cell 1 refractory at rest, no chemical weights or input. The free cell
must satisfy `v(dt) = v_rest + 5 exp(-(1 + 5) dt / tau_m)`. Current runtime gives
−47.14625549316406 mV; the analytic value is −47.14777233225746 mV. The error is
0.001516839093397948 mV in one step, larger than float32 rounding at this voltage.
This demonstrates the numerical defect, not its effect size in a connectome run.

Concurrent update: #121 (`7ccedb2`) keeps this algorithm and explicitly documents a
different convention: refractory voltages may move virtually within a step and are
reset at its boundaries. The diagnostic therefore now distinguishes two model
semantics, rather than disproving that newly documented boundary-only convention.
The proposal below selects the continuous clamp; accepting it is a numerical-model
decision, not a claim that #121 fails to implement its own new docstring. Do not present
the two conventions as mathematically equivalent or silently change historical runs.

## Decision

Keep the existing model contract: refractory membranes are clamped at rest, their
chemical conductance stays frozen, their threshold adaptation continues, and they accept
electrical current only after leaving refractory. They remain an electrical sink for
their free partners. Silencing suppresses spike output; it does not remove electrical
contacts or clamp the membrane. A graded cell never enters refractory through a spike.

For a fixed refractory mask over a neural step, integrate only the free cells. Write
`x = v - v_rest`, let `F` denote free cells, and define
`A = (K - diag(1 + row_sum(K))) / tau_m`. Use `A_FF`, retaining the diagonal contribution
of contacts to clamped cells. Integrate `dx_F/dt = A_FF x_F + g_F/tau_m` together with
`dg_F/dt = -g_F/tau_syn`. Clamped `x` is zero throughout the step. Obtain the step map
from a matrix exponential of this reduced block system. Do not remove clamped contacts
from the diagonal. Refractory deadlines are integer step boundaries, so the mask is
constant during each step under the existing spike timing contract.

Use the existing all-free map when the component has no refractory cells. Precompute or
cache reduced maps only on demand, with a bounded memory policy. Before choosing cache
capacity or a more elaborate solver, measure component sizes, distinct masks, hit rate,
setup time, per-step time and memory on the existing KC topology. Failure to meet the
resource budget must be explicit; do not silently substitute Euler integration or move
the clamp to the end of the step. If exact dense maps are impractical, bring a separate
solver decision for review with those measurements.

Version the optional electrical semantics and bind them into neural-checkpoint identity;
reject restoration of old electrical checkpoints under the new algorithm. Preserve
compatibility for uncoupled checkpoints when their execution semantics have not changed.
The native path continues to refuse electrical fixtures until explicitly qualified.

## Consequences

- Add analytic one-free/one-clamped tests, a case with decaying chemical input, clamp
  entry/exit, multiple coupled cells and all-clamped components. Use float32-aware state
  tolerances registered before comparing; counts and spikes must match across paths.
- Reference integration derives the reduced system independently; it must not call the
  production step-map builder. Kernel and runtime must agree after chunking and restore.
- No-gap and zero-coupling execution must preserve existing operation order and results.
- Measure numerical impact against both `b1116af` (explicit coupling) and `17173c2`
  (full-component exponential). Keep archived KC v4 immutable. A new scored run requires
  a prospective protocol/version and output identity, never replacing v4.
- Spikelets, rectification, dendrites and biological coupling calibration remain outside
  this correction. This decision supplies no missing biological measurement.

## Alternatives

- Keep the full exponential and clamp afterwards: rejected, contradicts the clamp
  during the step; the diagnostic already distinguishes the two systems.
- Retain #121's boundary-only convention: a possible explicit alternative, but not
  selected here because it differs from a continuous refractory clamp. If chosen,
  record acceptance and qualify the approximation against the clamped model instead
  of claiming the two dynamics are identical.
- Delete contacts to refractory cells: rejected, removes their sink contribution.
- Return to explicit Euler or introduce substeps: not the selected solution; would
  require a separately specified error bound and convergence/performance evidence.
- Precompute every refractory mask: rejected, exponential storage in component size.
