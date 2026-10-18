# ADR: measured JO source boundary

Status: accepted by the owner, 2026-10-18 (proposed 2026-10-17). Implementation
waits for a measured source that establishes the eligible mode.
Scope: entry protocol 6 and a prospective song/M4 input version.
No runtime implementation or validation-lock change is authorized by this ADR.
The [measured-input design](jo-measured-input-design.md) specifies source evidence,
asset fields, acquisition and falsifiable qualification cases.

## Context

Protocol 6 requires measured JO-A/B/D band-pass/carrier-responsive input. Existing
song stimulation encodes an engineered envelope as voltage kicks and matches
counts across conditions. A kick is neither an observed source spike nor a
physical current. Input follows threshold evaluation; stimulated JO cells bypass
ordinary refractory deadlines and retain recurrent excitation. Reusing this path
for measured outgoing spikes would introduce a second, uncalibrated neural
transfer and could add recurrently generated source events.

The audited sources primarily measure calcium, compound extracellular signals,
or postsynaptic central-neuron currents. None yet establishes an eligible
absolute native JO input over the admitted domain. Anatomical subgroup identity,
physiological calibration and sex compatibility are independent gates. Female
anatomical isomorphism alone cannot justify male physiological parameters. A
numerical design cannot supply missing measurements.

## Decision

Adopt a small versioned input contract with mutually exclusive source modes,
subject to acceptance and subsequent implementation qualification.

**Observed spikes prescribe outgoing JO events.** Replay native trial timestamps
without synthetic resampling. Source-clamped rows cannot also emit autonomous
LIF spikes. Preserve existing outgoing chemical edge weights, signs, fan-out and
delays. Record excluded feedback and scope the scientific intervention to the
network driven by observed receptor output. Audit incident electrical contacts;
reject unsupported gap coupling rather than inventing a voltage for an event-only
source. Record prescribed and actually emitted events independently.

**Measured absolute rates require an explicit synthetic event model.** Keep them
distinct from observed spikes. Source-only evidence must justify the timing,
refractory and covariance assumptions at the claimed resolution. Do not infer
independence from a pooled trace or clone a single train across bodies. Register
integrated intensity, sampler/version, uncertainty and deterministic realization.
Do not silently dead-time-filter, equalize counts or select gain from downstream
responses. Missing support leaves the measured-rate claim blocked.

**Calibrated membrane injection is a separate mode.** Admit current/conductance
or membrane evidence only with units, recording site/holding conditions,
conversion parameters and independent JO membrane calibration. Specify the
physical intervention and keep its recurrence/refractory treatment explicit.
It must not simultaneously prescribe outgoing events. Existing voltage impulses
cannot acquire pA/nS labels by declaration. Calcium remains a native validation
observable unless an independently validated electrical measurement model
justifies conversion; normalized band-pass proxies remain engineered diagnostics.

Freeze source/mapping/transform/event hashes and ordered bodyIds. Mapping
resolution cannot exceed the source's evidence; `-unclear` labels remain coarse.
Unknown required metadata and missing acquisition intervals produce typed
refusal, never default zeros. Define `[t0,t1)` source intervals and half-open
bookkeeping bins with exact boundaries entering the next bin. Physical emission
uses `q(t) = ceil((t−t0)/dt)`: exact-tick events stay on that tick and no event
emits before its native timestamp. At dt=100 µs, 0/99/100-µs events dispatch at
0/100/100 µs, so multiplicity is checked at dispatch ticks, not acquisition bins.
Preserve all multiplicity or refuse incompatible resolution. Retain native times
and quantization error `[0,dt)`, separately accounting for clock uncertainty;
no downstream-fitted shift. Check source end t1 exclusively before quantization.
An admitted event rounding to the run horizon requires explicit continuation or
horizon refusal, never silent loss. Independently qualify stimulus
carrier processing and neural timing, clock alignment and anti-alias filtering.
No frequency/amplitude/state extrapolation without validated source evidence.

Prefer immutable complete event materialization before simulation. A keyed
sampler is acceptable if asset/algorithm/seed/condition/trial/body/bin identity
makes chunking, worker order and restart invariant. Integrate rates over bins.
Extend consumed-input and numerical-semantics identity through the existing
runstore contract; a global run-manifest rewrite is unnecessary.

## Consequences

The event clamp changes numerical and scientific semantics and therefore needs
a new protocol/input version, explicit acceptance and independent implementation
tests. Analytic event/delivery fixtures must detect double emissions, latency,
bin errors, loss of multiplicity and hidden feedback effects. Hash checks alone
cannot establish that the measurement-to-drive transformation occurred.

Source acquisition, identity/sex review, native-unit calibration and animal-level
independent source validation precede eligibility. Their thresholds must derive
from instrument error, source variability and intended claims in a prospective
protocol; this proposal invents no empirical tolerance or gain. A subgroup-only
source does not silently satisfy the complete A/B/D scope.

Historical song v1, failed benchmark verdicts and locks remain immutable. Source
qualification does not authorize Baker/Pacheco response access or scoring. A
later manifest v2, fresh eligible evidence partition and S0/readout gates require
separate review. Current implementation status and measured-input eligibility
remain **not implemented / blocked**, respectively.

## Alternatives

**Reuse voltage kicks:** smallest code change but does not enforce observed
emissions and retains uncalibrated threshold/recurrent effects. Preserve it as
a historical synthetic control.

**Fit current to reproduce a source PSTH:** a legitimate inferred model only
with identifiable parameters and independent source validation; adds an inverse
membrane/recurrent problem and cannot be called observed replay.

**Silence JO and inject downstream directly:** risks changing fan-out, signs,
weights and delays; use a source-event boundary that preserves edge delivery.

**Universal receptor/mechanotransduction framework:** premature before a second
qualified observable requires it. Implement only the accepted minimal source
boundary once actual measurements establish the eligible mode.
