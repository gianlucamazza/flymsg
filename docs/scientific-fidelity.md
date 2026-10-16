# Scientific fidelity, evidence and validation architecture

Status: proposed, 2026-10-13; SF1 implemented 2026-10-14 (#147). SF2 timestep convergence v1 converged (2026-10-14) and simple baselines v1 are specific (2026-10-16). Path-metrics v1 (2026-10-16, seeds 5000–5004) leaves latency not converged for sugar → MN9; jitter at 0.1 ms is within range except the indeterminate bitter silence; recruitment and rate converge under the pre-registered seed-range rule. The identifiability re-read is post-hoc and every listed parameter stays blocked. Uncertainty propagation remains. SF5's replication package ([replication](replication.md)) exists (2026-10-14). Neither SF2 nor SF5 is complete. No changes to scored results or model defaults.

## Scientific baseline

The calibrated battery passes [29/29](validation.md#current-status), but held-out [ORN_DM1](benchmarks.md) fails. [T4/T5 v2](eye.md#t4t5-version-2-graded-photoreceptors-and-lamina-lock-2026-10-13-84-97) and [v3](eye.md#t4t5-version-3-graded-medulla-inputs-lock-2026-10-13-140) do not activate T4/T5 (robust neither), [Kenyon cell sparseness v1–v5](model.md#kenyon-cell-sparseness-diagnostic-2026-10-13) is dense or silent and v7 is sparse only with the variant eLN set, and the [NeuroMechFly jump](embodiment.md#a-ttm-driven-jump-of-neuromechfly-lock-2026-10-13-90-94) is short. The [scored motor map](../validation/motor_map.yaml) remains unmapped even though [406 of 708 motor neurons](embodiment.md#existing-evidence-and-blockers) have a MANC muscle annotation. Numerical agreement does not imply biological validity.

## Evidence contract

Every biological parameter and mapping in a scored experiment should declare:

- Source DOI/accession, dataset version, license and SHA-256 digest.
- Species, sex, stage, cell identity and mapping uncertainty.
- Quantity, physical unit, measured value or distribution, measurement method and uncertainty.
- Status: measured, inferred, calibrated, scanned, compensatory or unknown.
- Applicable circuit and limits of transfer between datasets.
- Transformation code and derived-data digest.
  Unknown values stay unknown. An inference must never be presented as a measurement.

### SF1 in the code (#147)

[`validation/evidence.yaml`](https://github.com/gianlucamazza/flymsg/blob/main/validation/evidence.yaml)
holds one record per sourced quantity with every field above; `flymsg.evidence` refuses a
record with a missing field, an unknown status, an unknown citation, locator or user, or a
measured status without value and unit. A field the source does not state is written
`unknown`, and `scripts/evidence_audit.py` lists them per record. Every lock written with
`yaml_subset: 2` (all locks after #159) must name its records in `evidence`; historical
locks keep their prose `sources`, unchanged. The first records are the coupling, spike and
sparseness values of Kenyon cell sparseness v5–v7 and the medulla voltages of T4/T5 v3;
the test suite checks them against the values the locks and the code use. A numerical lock
that uses only the live defaults writes `evidence: none` with an `evidence_none` reason
(the timestep convergence check of SF2 is the first).

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
SF2 Numerical and uncertainty: unit/convergence tests, sensitivity, path metrics, the identifiability re-read and simple baselines. `flymsg.units` parses every evidence-registry unit and reads `sim._constants` (the decays, `gv` and the kick) and `sim.graded_arrays`. Time-ratio decays are dimensionless, `g*gv` keeps `g` a voltage, and the kick is the voltage added to `v`. Uncertainty propagation remains blocked: the registry stores text, not a distribution.
SF3 Physiology: independently preregistered T4/T5 and Kenyon-cell benchmarks.
SF4 Embodiment: cited neuron-to-muscle-to-actuator mapping, neuromechanical calibration and held-out animal behavior.
SF5 External replication: frozen reproduction package and independent evaluation.

## Non-goals

No microservices, generic plugin framework, wholesale Hodgkin-Huxley conversion, fabricated biological values or retroactive alteration of scored experiments. A missing external measurement is a blocker, not a software defect.

## Related

[Roadmap](roadmap.md) · [Architecture](architecture.md) · [Approximations](approximations.md) · [Run integrity](run-integrity.md) · [Validation](validation.md) · [Embodiment](embodiment.md). Existing issues #19, #24, #34, #36, #84, #85, #95, #97, #139 and #140.
