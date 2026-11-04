# Prospective optic observable qualification

Status: proposal, 2026-11-04. Related issues: #148, #149, #302, #303.
This is a design for review, not a lock or authorization for a counted run.

## Entry gates

Verify original source digests and preparation metadata before choosing an observable.
Assign calibration and held-out roles before opening reserved responses. Missing sex,
registration, units or stimulus calibration remains UNKNOWN. Source integrity does
not establish physiological transfer from one preparation to MaleCNS.

## Observable matrix

| Observable             | Units                      | Independent check                                                  | Eligibility gate                                                                               |
| ---------------------- | -------------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| Graded voltage         | mV                         | NumPy reference and raw whole-cell ranges                          | Match holding current, baseline, cell identity and stimulus history.                           |
| Synaptic release       | spike-equivalents per step | Independent integration of the declared release law                | Requires sourced voltage-to-release transfer; binned voltage cannot reconstruct mean release.  |
| First response latency | ms                         | Timestamp oracle and timestep refinement                           | Exclude silent trials explicitly; sugar/MN9 remains nonconvergent under its archived protocol. |
| Direction selectivity  | dimensionless              | Independently implemented contrast with fixed direction convention | Requires eligible stimulus geometry, physiological input and held-out responses.               |

## Protocol to freeze before scoring

For the chosen channel, specify full stimulated network, solver, timestep grid,
trial count, seed list, primary statistic, baseline model and disconnected/shuffled
controls. Fix numerical tolerances from source precision and acquisition sampling,
not from observed model success. If these cannot be justified, do not freeze a lock.
Require convergence separately for voltage, release, latency and selectivity; a
synthetic three-neuron witness is insufficient for the complete network.

Separate calibration from scoring and retain failures, silence and indeterminate
outcomes. Compare against a stimulus-following baseline. Parameter uncertainty
must come from a measured distribution; assignment vote margins are descriptive
support, not probabilities. No invented confidence intervals or gain retuning.

## Review exit

A reviewer must approve source eligibility, untouched holdout partition, numerical
metrics and justified thresholds before a versioned lock is proposed. Only after
that lock is merged may a clean-main counted run start. This proposal does not
close #148 or #149 and does not authorize T4/T5 v5.
