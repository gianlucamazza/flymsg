# Scientific fidelity, evidence and validation architecture

Status: proposed, 2026-10-13. Documentation-only; no changes to scored results or model defaults.

## Scientific baseline

The calibrated battery passes 29/29, but held-out ORN_DM1 fails. T4/T5 v2 does not activate T4/T5, Kenyon cell sparseness v1–v5 is dense or silent, and the NeuroMechFly jump is short. The scored motor map remains unmapped even though 406 of 708 motor neurons have a MANC muscle annotation. Numerical agreement does not imply biological validity.

## Evidence contract

Every biological parameter and mapping in a scored experiment should declare:

- Source DOI/accession, dataset version, license and SHA-256 digest.
- Species, sex, stage, cell identity and mapping uncertainty.
- Quantity, physical unit, measured value or distribution, measurement method and uncertainty.
- Status: measured, inferred, calibrated, scanned, compensatory or unknown.
- Applicable circuit and limits of transfer between datasets.
- Transformation code and derived-data digest.
  Unknown values stay unknown. An inference must never be presented as a measurement.

## Model and execution contracts

Retain the single Python package and B1–B6 boundaries. For each run, identify the model family (LIF, graded, conductance-based or compartmental), solver, timestep, parameter provenance and applicable benchmark. Add complexity only when independent tests show that simpler models fail. Keep optional mechanisms off by default until validated.

## Three separate validation gates

1. Numerical: oracle/runtime parity, convergence, dimensional checks, checkpoint integrity.
2. Physiological: independently measured voltage, latency, tuning, rates and causal perturbations.
3. Behavioral: held-out animal latency, direction, trajectory and success, with controls.

Passing one gate does not imply passing the others. Report failed, undecided, ineligible and blocked outcomes.

## Experiment protocol

Preregister the hypothesis, baselines, primary metric, acceptance threshold, negative controls, sample-size justification, multiplicity correction, calibration/held-out partition and permissible parameter tuning. Preserve immutable data, code, environment, seed, protocol and output hashes. Run global sensitivity and identifiability checks and propagate measurement uncertainty to predictions. Publish ablations and negative results. Never tune against scored held-out data.

## Claims taxonomy

- Reproduction: fit or replay of known data.
- Prediction: unseen measurement predicted before evaluation.
- Causal prediction: intervention effect predicted in advance.
- Discovery: independently confirmed new relation.

## Roadmap

SF1 Evidence inventory: provenance and uncertainty coverage for scored parameters; CI rejects missing fields in new evidence records.
SF2 Numerical and uncertainty: unit/convergence tests, sensitivity, identifiability and simple baselines.
SF3 Physiology: independently preregistered T4/T5 and Kenyon-cell benchmarks.
SF4 Embodiment: cited neuron-to-muscle-to-actuator mapping, neuromechanical calibration and held-out animal behavior.
SF5 External replication: frozen reproduction package and independent evaluation.

## Non-goals

No microservices, generic plugin framework, wholesale Hodgkin-Huxley conversion, fabricated biological values or retroactive alteration of scored experiments. A missing external measurement is a blocker, not a software defect.

## Related

[Roadmap](roadmap.md) · [Architecture](architecture.md) · [Approximations](approximations.md) · [Run integrity](run-integrity.md) · [Validation](validation.md) · [Embodiment](embodiment.md). Existing issues #19, #24, #34, #36, #84, #85, #95, #97, #139 and #140.
