# Research program: evidence gates for embodied FlyMSG

Status: proposed research protocol, not empirical findings. Updated 2026-10-12.

## Objective

Demonstrate whether a physically parameterized stimulus can produce a
causally defensible neural response and body movement through MaleCNS,
without fitting against the same trials used to assess the result.

## Baselines already in this repository

- MaleCNS v1.0: 165,122 traced neurons, 25.6M connections.
- Shiu-style LIF simulator: calibrated feed-forward circuits; not a
  cell-specific electrophysiological reconstruction.
- `LC4_R` stimulation is Poisson injection, **not** a rendered looming object.
- The existing one-bit jump is an artificial decoder and fails the
  DNp01-silencing criterion. See `docs/behavior.md`.
- The olfactory held-out case fails specificity and stability.
- M0 embodiment has a synthetic mock body and no verified muscle map.

## Workstream A — looming transduction (#49)

**Questions.** What does LC4 encode (angular size, angular expansion, contrast,
time-to-collision), over which stimulus regime and with what trial-to-trial
variability? Are LC4 and LPLC2 responses interchangeable? What is the effect
of left/right stimulation and recording modality?

**Source anchors to verify and extract.**
- von Reyn et al. (2014), DOI: 10.1038/nn.3741.
- Ache et al. (2019), DOI: 10.1016/j.cub.2019.01.079.
- MaleCNS source and type annotations (see `docs/data.md`).

**Evidence schema.** DOI; data accession; licence; fly sex; genotype; stimulus
radius/distance/speed; contrast; angular size and velocity; neural identity;
recording modality; sampling frequency; latency distribution; replicates;
confidence interval; preprocessing; whether raw trials are accessible.

**Gate A.** Hold out animals/trials before model selection. Fit only
documented quantities with uncertainty. No raw data => synthetic-only label.

## Workstream B — motor mapping (#50)

**Questions.** Which TTMn body IDs innervate which jump muscles? Is the
mapping bilateral? What measured muscle activation, force, and timing exist?
Does FlyBody's actuator convention represent that muscle?

**Evidence schema.** MaleCNS bodyId; cell type; muscle; laterality; source;
anatomical evidence; confidence; force or activation units; morphology sex;
FlyBody actuator index; version/commit.

**Gate B.** Every activated muscle requires evidence; otherwise
`validation/motor_map.yaml` remains unmapped and actuator commands fail.

## Workstream C — physical body (#51)

Pin FlyBody and MuJoCo versions; isolate dependencies from Python 3.13 LIF;
record morphology/sex mismatch; validate timebase, units, collision behavior,
integration stability, and available jump tasks. Compare simulated kinematics
against independent recordings. Do not treat a walking policy as a connectome
motor decoder.

**Gate C.** Repeatable synthetic smoke test first; measured kinematics and
verified actuator mapping before biological claims.

## Workstream D — falsification (#53)

Freeze prospective protocols and seeds before running:
1. Real versus shuffled-connectome response.
2. Looming versus matched non-looming visual controls.
3. Intact versus bilateral DNp01 silencing.
4. Body-feedback enabled versus open-loop matched input.
5. Parameter sensitivity, multiple seeds, and cross-dataset generalization.

Record effect sizes, confidence intervals, preregistered failure thresholds,
and all negative results. Existing calibration tasks are not held-out evidence.

## Implementation gates (#52, #54)

- Schedule future neural input only after its sensor timestamp and latency.
- Preserve `CpuRuntime` ordering and batch-equivalent spike behavior.
- Record geometry, stimulus rates, sampled kicks, neural events, body state,
  sensor feedback, mapping versions, seeds and SHA-256 hashes.
- Reject unknown IDs, invalid units, nonfinite values, incompatible clocks.
- CI: lint/format/tests; independent full-data validation and performance
  report before release.

## Definition of done

**Engineering demonstrator:** deterministic synthetic feedback changes later
neural input and reproduces from a versioned trace.

**Biological validation:** independent recordings support sensory and motor
transfers, and frozen behavioral tests pass. Until then, publish as an
experimental connectome-driven simulation, not a realistic digital fly.
