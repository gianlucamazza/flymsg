# Changelog

## Unreleased

- `dimorphism --silencing` reports one-sided p for a drop and for a rise (`p_drop`,
  `p_rise`); `dimorphism --loop` tests the predicted dMS9 loop against silencing matched
  active neurons (pre-registered tests T1 and T2, docs/dimorphism.md).
- Worker processes start from a forkserver (`parallel.py`) instead of forking a
  multi-threaded caller; long silencing runs report progress with a measured ETA, save
  every null draw and resume from `--checkpoint FILE`, running the confirmatory tests first.
- `validate.respond(duration_ms=STIM_MS)` stops a run at the end of the stimulus: identical
  rates at 2–2.7× less cost, used by all silencing analyses.

## 0.5.2 — 2026-09-22

Documentation only.

- **References verified.** Every entry was checked against PubMed or bioRxiv and given
  volume, pages and DOI. Corrections: Allen & Murphey 2007 has two authors (was "Allen et
  al."), the full title of King & Wyman 1980, and the MaleCNS paper's published _Cell_ title
  and DOI (10.1016/j.cell.2026.08.015), which differ from the preprint's. Gordon & Scott 2009,
  Shiu et al. 2024 and Tastekin et al. 2025 were added to the list, and the FlyWire papers
  to `docs/data.md`.
- Fixed a stale limit (the control has matched class for sensory stimuli since criterion
  v4), a duplicated paragraph in `docs/model.md` and the table layout in the README.

## 0.5.1 — 2026-09-22

- `flymsg audit` (`quality.py`): left/right asymmetry of every bilateral cell type (robust
  z over 11,095 types, 355 flagged), traced-input share, and the same pair in FAFB.
- **Correction:** v0.5.0 reported a lateralised male MN9. MN9_R has 556 input synapses
  against MN9_L's 6,012 (symmetric in FAFB), so it is most likely incompletely
  reconstructed. The sex comparison now reads the contralateral pathway through MN9_L, as
  Shiu et al. do: male vs female MN9 30 vs 76 Hz at 100 Hz, 80 vs 88 Hz at 200 Hz.
- LB3c (right sugar GRNs 2.5× the input of the left) is flagged too; the neurons of the
  validation circuits and of the predicted dMS9 loop are symmetric.

## 0.5.0 — 2026-09-22

### Model

- **No compensation by default.** The pre-registered replication (fresh seeds 10–19 and
  control draws) tied A and B− at 29/29, so B− became the default: Shiu's weight scaled for
  MaleCNS synapse density (`w_syn` 0.275 / 1.43 = 0.192) and no adaptive threshold (kept as an
  option). Zero self-sustained neurons in every validation case.
- Compiled kernel (numba): 2× faster, spikes identical to the previous NumPy loop (kept as the
  test oracle in `tests/reference_sim.py`).
- `sim.SHIU_W_SYN` names the published weight used on FAFB.

### Analyses

- LB3 split in FAFB (`compare.nearest_male_type`): Shiu's sugar set is 14 LB3b/c-like and 6
  LB3d-like neurons; in the published model the former carry 72 % of the MN9 response.
- Silencing with 100 null draws: silencing fru/dsx+ or dimorphic neurons doubles dPR1;
  `dimorphism --by-type` locates a predicted feedback loop dPR1 → dMS9 → vPR9_a/IN00A038 → dPR1.
- Male MN9 is lateralised: only MN9_L responds, only to right sugar GRNs (corrected in
  0.5.1: MN9_R is most likely incompletely reconstructed).

### Public release

- MIT licence, `CITATION.cff`, GitHub Actions CI (lint + unit and browser-module tests),
  README rewritten for a public audience, `docs/validation.md` opens with the current status.
- Fixed: `.gitignore` excluded the vendored `three.module.min.js` (any `build/` directory).
- Removed the unused `networkx` dependency.

## 0.4.0 — 2026-09-21

### Validation

- Criterion v4: class-matched control for sensory stimuli (resolves the sugar → MN9
  specificity failure: random gustatory neurons leave MN9 silent) and a negative case,
  bitter GRNs (LB1a–d, two agreeing lines of evidence) → MN9. 29/29 with the defaults.
- `flymsg select-model`: pre-registered comparison at 10 seeds of the calibrated model (A,
  28/29) and the published model at MaleCNS synapse density without compensation (B, 26/29);
  A stays the default. The sensitivity variant B− (`w_syn` 0.192, no compensation) passes
  29/29 and is the candidate for a confirmatory replication.
- Bootstrap 95 % intervals on target and control rates.
- Finding: in the density-scaled model MN9 responds to LB3b+c+d but not to LB3b+c.

### Model and analyses

- `sim.run(silence=...)`; `flymsg dimorphism --silencing`: response drop when fru/dsx+,
  male-specific or dimorphic neurons are silenced, against as many other neurons. Courtship
  responses survive (they run through direct links); silencing male-specific neurons lowers
  dPR1 by ~20 %, silencing all fru/dsx+ neurons raises it; looming is unaffected.

### 3D view

- Colour by dimorphism or fru/dsx (`?color=`).

## 0.3.0 — 2026-09-21

### Model

- The engine now reproduces the published brian2 model step by step (Poisson input into v,
  reset of v and g, v and g frozen while refractory, synaptic input lost while refractory,
  stimulated neurons without refractory period). Checked against the Shiu et al. code on the
  same FAFB connectome. Stimulated neurons now fire at the input rate, not about twice it.
- Defaults re-derived with calibrate-v3: `w_syn` 0.275, `th_jump` 2 mV (was 6). Criterion v3
  passes 27/28; sugar → MN9 specificity fails under every parameter set (documented).
- The faithful engine keeps the previous speed (refractory neurons handled as a small set).
- Exploratory: MaleCNS has 1.81× the synapses per neuron of FAFB; with `w_syn` scaled to
  0.152 the model is stable without the adaptive threshold (26/28).

### Validation

- Criterion v3: latency order along chains and dose-response checks, pre-registered.
- New case: sugar GRNs → MN9. Sugar GRNs (LB3b, LB3c) chosen where two independent lines agree.
- GF → TTMn evaluated against _shak-B²_ physiology; kept as a documented limit.

### Data and comparisons

- `--dataset fafb`: the female FlyWire v783 brain in the same schema; `build` keeps
  `flywireType`, `subclass`, `entryNerve`, `receptorType`.
- `flymsg dimorphism`: dimorphic/fru-dsx neurons among responders vs a superclass-matched null.
- Male vs female comparison of shared cases, corrected for synapse detection density
  (`docs/comparison.md`); dimorphism enrichment results in `docs/dimorphism.md`.

## 0.2.0 — 2026-09-21

### Model and validation

- Validation criterion v2: a case passes when the best target neuron fires ≥ 3 spikes in the
  window in ≥ 2/3 of seeds and beats a size-matched random control (≥ 3× its rate + 2 Hz),
  with ≤ 100 self-sustained neurons; latencies reported. GF → DLMn excluded (gap junctions).
- `calibrate` re-derived the defaults with a pre-registered ranking: `th_jump` 6 mV, the one
  named compensation (adaptive threshold); the battery passes 16/16.
- `path --alt K`: further routes, each avoiding the intermediate cell types of the previous
  ones (LC4 → TTMn: via DNp01, then DNp02, then DNp11).

### 3D view (`flymsg viz`)

- Streams real neuron surfaces (multi-resolution Draco), skeletons and neuropils from the
  public GCS volumes; the export holds only metadata and activity.
- Octree LOD within a triangle budget derived from the GPU buffers' real capacity; neurons
  beyond it drawn as skeletons, simplified only below half a pixel on screen.
- One draw for all surfaces (`BatchedMesh`) and one for all skeletons; fragments finished in
  workers; GPU picking; render on demand; 4× MSAA at rest, adaptive quality while moving.
- Replays: silent neurons desaturated and see-through, so activity is not hidden.
- Performance HUD and `?bench=<s>`; `scripts/shoot.mjs` measures headless on SwiftShader or
  the real GPU. Numbers in [docs/viz.md](docs/viz.md).

### Docs

- `docs/data.md`, `docs/model.md`, `docs/validation.md` (with the negative results),
  `docs/viz.md`.

## 0.1.0 — 2026-09-21

- `fetch` / `build`: MaleCNS v1.0 tables compacted to Parquet (165,122 traced neurons,
  25.6 M connections).
- `info`, `path` (strongest chain by input fraction), `sim` (whole-CNS LIF after Shiu et
  al. 2024, time-binned, multi-seed summary).
- `validate` battery of known circuits with controls, `calibrate` grid search.
