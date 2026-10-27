# Optic system audit — 2026-10-27

**Engineering delivery, not a completed physiological eye.** Baseline inspected:
`299c749c45d7d0313bb8c9cad4d559d6bac0ad9b`. The current T4/T5 v4 verdict remains
**FAILED: robust neither**. No historical lock, score, global model parameter or
held-out response was changed. This audit does not claim exhaustive discovery of
all published physiology.

## Repository and reproduction

Read issues #84, #97, #140, #179 and #180 and their comments. Their early descriptions
are historical: graded neurons, optical columns and closed-loop float input already
exist. Dependencies remain #19/#35 (motor map), #36 (held-out behavior), #39 (hardware),
#148/#149 (numerics/evidence), and the sensory physiology gates. Recent main history
includes shared pathway extraction, graded runtime/closed-loop v2, DN arena v2
negative results, cylinder-bar optics (#295), DN arena v3 lock (#297), and privacy
redaction (#298/#299). The open PR at discovery was #288, motor/proprioception ADR;
this work does not duplicate it. Baseline Python tests and pages CI were successful;
the recent failed scheduled workflows were dependency-update jobs, not that test run.

From a fresh clone, `uv sync --frozen`, `flymsg fetch`, `flymsg build` and `flymsg eye`
succeeded. Reconstructed: **165,122 neurons, 25,563,197 edges, 124,025,046 synapses**.
Raw and derived input SHA-256 values are in the
[source audit](../evidence/optic-source-audit-2026-10-27.json).
GPL eye-map inputs and per-column derivatives remain local under `data/`; aggregate
coverage and source digests are recorded here.

| Availability audit                 | Left | Right |
| ---------------------------------- | ---: | ----: |
| L1-defined columns                 |  875 |   892 |
| Columns with transferred direction |  835 |   843 |
| Columns without direction          |   40 |    49 |

Of 4,107 simulated photoreceptors, 3,936 have a strongest-output assignment and 3,903
have a direction. Thus 171 lack an assignment and 33 assigned cells lack a direction.
Two assigned cells reference a column absent from the L1-defined table; these remain
explicitly masked rather than silently counted as reconstructed columns.
All 3,936 assigned cells agree with their annotated side; 171 have unknown mapping
laterality. These are reconstruction-availability counts, not confidence intervals.
Untraced biological receptors are outside this denominator. The dorsal-rim median
is 67.6845 degrees versus 3.7203 degrees for other R7/R8, reproducing the existing
independent anatomical check, not measuring registration error.

The Groschner/Edmond fetch failed at `fig3_Mi1.npy` with HTTP 503 after three attempts.
The five raw physiological files were therefore **not reverified locally**. Archived
T4/T5 CSVs and manifests are in the clone; they support a historical-result audit,
not a fresh execution of the 18.9-hour full-connectome campaign. Its stored aggregates
cannot recover latency or temporal kernels. No Gruntman held-out response was opened.

## Evidence vocabulary

- **MEASURED:** an original source observation, with preparation and units retained.
- **VALIDATED:** a named comparison passes within its specified domain; always name
  whether that domain is software, geometry or physiology.
- **INFERRED:** a mapping or parameter derived with explicit assumptions.
- **SYNTHETIC:** engineered fixtures, release gains or imposed input.
- **UNKNOWN:** absent, unavailable or non-identifiable evidence; never silently zero uncertainty.
- **FAILED:** a tested criterion fails; keep its result and configuration.

A measured female eye ray does not make its transferred MaleCNS direction measured.
Zhao et al. (2025, doi:10.1038/s41586-025-09276-5) align different preparations using
retinotopic landmarks. Here the integer hex correspondence is implemented, left/right
mirroring and cross-sex transfer are assumptions, and eye-to-body registration remains
unmeasured. The existing approximate one-column error statement is not a measured
per-column covariance. Rigid rotations do not remove this uncertainty.

## Requirement/evidence matrix

| ID  | Verifiable requirement and implementation                                          | Evidence/status                                                                              | Remaining gate                                                                        |
| --- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| O01 | MaleCNS columns and R1–R6/R7/R8 assignment: `eye.columns`, `photoreceptors`        | INFERRED transfer of MEASURED anatomy; counts reproduced                                     | Individual/sex correspondence uncertainty; tied-output ambiguity                      |
| O02 | Missing anatomy and side audit: `eye.receptor_masks`, CLI `receptor_masks.parquet` | VALIDATED software on SYNTHETIC fixtures; aggregate real-data counts above                   | Cannot infer missing cells or rays                                                    |
| O03 | Pinned source integrity: `eye.fetch`, `lenses` verify both RData hashes            | VALIDATED software, corrupt-cache/download tests                                             | External source availability; hashes do not validate anatomy                          |
| O04 | Eye/head/body/world transforms: `pose`, `optics`                                   | VALIDATED software geometry with explicit synthetic registration                             | UNKNOWN measured head/body registration and angular covariance                        |
| O05 | Sphere/bar coverage, optical flow and occlusion: `optics`                          | Existing independent Sobol oracle and synthetic camera evidence; regression tested           | Full qualification matrix; overlapping coverage is per-object, not exact union        |
| O06 | Coverage-to-drive contracts: `eye.photoreceptor_kicks`                             | VALIDATED software; fractions, masks, empty retina, bounds and gain tested                   | SYNTHETIC gain, no irradiance calibration                                             |
| O07 | Graded voltage and delayed saturating release: `sim.Graded`, `CpuRuntime`          | VALIDATED numerical parity; threshold-linear release is SYNTHETIC                            | UNKNOWN identified Drosophila voltage-to-release kinetics                             |
| O08 | Histamine sign, L1–L3 and selected medulla: `data.SIGN`, `visual_pathway`          | Sign/model implemented; source ranges and inferred timing distinguished                      | L4/L5, Tm1/2/9 and remaining types lack an eligible measured transfer here            |
| O09 | Light adaptation, recovery and receptor noise                                      | UNKNOWN in this model; membrane relaxation and release clipping are not phototransduction    | Obtain identifiable stimulus/voltage/release data before adding mechanisms            |
| O10 | T4/T5 ON/OFF, direction and speed tuning: `t4t5`                                   | FAILED historical v4; four cardinal directions, fixed speed, gain envelope                   | No physiological v5 without sourced transfer, independent scoring and held-out design |
| O11 | LC4/LPLC2, central and descending pathways                                         | Graph and circuit baselines exist; retinal physiological transfer UNKNOWN                    | Calcium/voltage are not LC4 firing-rate calibration; no forced spikes                 |
| O12 | Optical input → graded network → downstream causality                              | New SYNTHETIC witness passes all seven locked gates                                          | Does not establish MaleCNS motion vision or behavior                                  |
| O13 | Body movement changes later optics: `closedloop`, `flygym_body`                    | Existing SYNTHETIC intervention, five-arm and replay/checkpoint tests retained               | Biological sensor/motor coupling and independent behavior remain UNKNOWN              |
| O14 | Viewer/Quest observer and synchronized graded replay                               | Existing `cli/simulate.eye_replay`, `graded.js`, XR pipeline reused; software tests retained | No new physical Quest session or complete retinal/release dashboard qualification     |
| O15 | Determinism, ablations, timestep refinement                                        | VALIDATED for the new SYNTHETIC fixture                                                      | Not full-connectome convergence, parameter identifiability or biological uncertainty  |

## Implemented changes and verification

PR #300 rejects fractional/out-of-range receptor indices, invalid coverage and gains,
handles an empty retina with all receptors unassigned, and prevents duplicate lens
keys from duplicating anatomical columns. Historical valid drive is bit-identical.

The follow-up adds an explicit row for every simulated receptor, nullable laterality,
separate assignment/column/direction masks and INFERRED/UNKNOWN direction status.
Masks are diagnostics and do not rewrite the historical strongest-output assignments.
Both cached and downloaded RData files are checked against their pinned source bytes;
a mismatch refuses and preserves the suspect file for inspection.

`validation/optic-causality-v1.json` was committed before its first execution and is
SHA-256-locked. Its three graded neurons and two arbitrary signed edges are explicitly
SYNTHETIC, not named biological cells. The same existing simulator/runtime implements
both paths; no scheduler or alternative neuronal backend was added. The
[recorded result](../evidence/optic-causality-2026-10-27.json) reports:

- Light raises receptor voltage and lowers the two downstream voltages.
- Disconnecting the first edge or silencing receptor release removes the downstream
  light/dark difference exactly; an unassigned receptor equals zero drive.
- Batched and chunked runtime results, repetition and checkpoint/restore match exactly.
- All three graded neurons emit zero spikes.
- Final-bin refinement error at 0.05 ms relative to 0.025 ms is below 0.001 mV for
  both stimuli, smaller than at 0.1 ms and below the preregistered 0.1 mV ceiling.

This is a deterministic fixture: different random seeds would not be independent
biological replicates. No confidence interval is fabricated from identical repeats.
The envelope's non-identifiability is not resolved by a software pass.

Local full suite on committed implementation: **1,199 passed, 6 failed, 3 deselected**.
Five failures are multiprocessing semaphore `PermissionError` in this execution
container; one is the host process-accounting test. The earlier dirty-worktree
manifest failure passed when rerun on committed source. The 97-test original optical
regression subset passed; subsequent eye/mask/causality additions pass too. See PR CI
for the unrestricted runner results. Lint and format checks pass. Slow full-connectome
scientific tests and physical Quest/Series S trials were not newly executed.

## Reproduce

```sh
uv sync --frozen
uv run flymsg fetch
uv run flymsg build
uv run flymsg eye
uv run python scripts/audit_optic_sources.py --out /tmp/optic-sources.json
uv run python scripts/check_optic_causality.py --out /tmp/optic-causality.json
uv run pytest tests/test_eye.py tests/test_optic_causality.py tests/test_optics.py tests/test_optics_oracle.py tests/test_visual_pathway.py tests/test_t4t5.py tests/test_graded.py tests/test_runtime.py tests/test_sensory_runtime.py tests/test_closedloop.py tests/test_flygym_body.py
```

Run evidence commands from clean committed source. The audit records input hashes,
code commit and local physiology-file availability. It does not download physiology,
rebuild stale derived tables, or declare an unavailable comparison passed. `flymsg eye`
rebuilds the tables first. Historical lock/result hashes are recorded for comparison.

## Scientific no-go and remaining work

1. **Registration:** acquire independent eye/head/thorax landmarks and their errors.
   Represent systematic individual/sex effects separately from sample noise, then
   preregister propagation through the existing optics and independent camera oracle.
   No Gaussian angular error or fabricated missing-column interpolation is justified now.
2. **Transduction:** restore access to source recordings; record preparation, units,
   stimulus, cell identity and uncertainty. Identify luminance/adaptation/release jointly
   before selecting a new mechanism. Voltage ranges alone cannot identify release gains.
3. **Circuit validation:** preserve v4 as FAILED; only after the evidence gate, commit a
   new v5 lock with eight-direction, polarity, contrast/speed and latency criteria,
   competing-mechanism ablations, sensitivity, numerical convergence and held-out data.
   Do not calibrate on Gruntman responses or rewrite prior locks.
4. **End-to-end physiology:** require independent retinal→LC4/LPLC2/descending readouts
   and a supported motor map. Keep Poisson circuit baselines and synthetic movement
   interventions separate; an equal closed/open outcome remains a valid result.
5. **Observation:** extend the existing replay with full column/release views only with
   explicit record identity and observer invariance tests. New Quest hardware parity
   requires a connected headset; historical evidence is not a new device trial.

Issues #84/#97/#140/#179/#180 remain open. The work improves engineering integrity and
reproducibility; it does **not** fulfill a claim of a physiologically complete optic system.
