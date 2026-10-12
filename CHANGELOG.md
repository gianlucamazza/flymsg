# Changelog

## 0.8.19 — 2026-10-12

### Embodiment

- **M0 neural/body contract (#32, PR #37).** `flymsg.embodiment` defines versioned
  contracts for spike events, motor commands, body state, sensor samples and
  provenance, and a deterministic multirate scheduler on an integer microsecond
  clock whose neural tick is `sim.Params.dt`. A synthetic one-DOF mock body closes a
  spike → command → sensor round trip. Invalid versions, datasets, timestamps, maps or
  masses fail before the first actuator call; any adapter exception stops the run as
  a `ContractError`. Fixture `bodyId`s are synthetic: `validation/motor_map.yaml`
  stays all `unmapped`, so no real motor command can be issued. The LIF engine is not
  coupled online. ADR in `docs/embodiment.md`. `w_syn` stays 0.192.

## 0.8.18 — 2026-10-12

### Site

- **The 3D view runs live on GitHub Pages.** The LC4_R and pIP10 replays and the
  pIP10/dPR1/dMS9 anatomy are served under `/live/` with the same page `flymsg viz`
  writes; geometry streams from the public MaleCNS volumes. The scenes are committed in
  `docs/live/` with their run manifests (clean tree, seed 0, default parameters) and
  rebuilt by `scripts/build_live_scenes.py`. The README gallery links each frame to its
  live scene. No scored run changed. `w_syn` stays 0.192.

## 0.8.17 — 2026-10-12

### Validation

- **The scan runner, before the run.** `flymsg silence-scan --run` executes
  version 1 of `validation/silence_scan.yaml` as written: base arms, the
  candidate rule, the screen, then confirmation with checkpointed null draws.
  Synthetic tests check that the only remaining route is named and that a
  base arm under the bar stops the scan. The lock is unchanged. Nothing was
  run on MaleCNS. `w_syn` stays 0.192.

## 0.8.16 — 2026-10-12

### Validation

- **Residual TTMn_R partner scan, before the run.** `validation/silence_scan.yaml`
  version 1 freezes the measurement issue #20 asks for. Candidates are every cell
  type with at least 5 synapses onto `TTMn_R` and an active neuron in the
  `DNp01`-silenced arm, computed by the runner, not read from a ranking. A screen
  on seeds 0–2 chooses what is confirmed; fresh seeds 10–12 confirm against the
  T2/T3 matched-responder null with max(1000, 20 _m_) draws and Bonferroni over
  the _m_ screen passes. `names_partner` also needs the behavior v1 silence bar.
  `flymsg silence-scan` prints the protocol and does not simulate. Provenance
  cites the authored motor map. Nothing was run. `w_syn` stays 0.192.

## 0.8.15 — 2026-10-12

### Documentation

- **Authored motor map, every row unmapped.** `validation/motor_map.yaml`
  lists the 59 walking actuators and both `TTMn` neurons. A published source
  names none of them together with an actuator, so a command is refused.
  Vaxenburg et al. 2025 states that the body is female. Version 1 of the
  behavior lock is unchanged. Provenance cites the documentary-issue note.
  Nothing was rerun. `w_syn` stays 0.192.

## 0.8.14 — 2026-10-12

### Documentation

- **Two documentary issues, no run.** #19 records the FlyBody re-read at
  `d015e9b`: same timesteps, 59 named walking actuators, no MaleCNS motor map.
  #20 keeps the residual `TTMn_R` partner unnamed. The synapse list read the
  same day cannot choose the next silencing. Version 1 is unchanged. Provenance
  cites the numeric-lock note. Nothing was rerun. `w_syn` stays 0.192.

## 0.8.13 — 2026-10-12

### Dependencies

- **numba 0.68.0 and actions/setup-node 7.1.0.** llvmlite is 0.50.0. Node stays 24. The unit suite matches the NumPy reference kernel. The scored runs were
  not repeated, so their manifests stay on numba 0.67.0. Provenance cites the
  empty-queue note. `w_syn` stays 0.192.

## 0.8.12 — 2026-10-12

### Documentation

- **No scientific task is queued.** Provenance cites the queue close, the
  held-out no-go and the prose alignment. The validated-behavior milestone
  stays unmet. Nothing was rerun. `w_syn` stays 0.192.

## 0.8.11 — 2026-10-12

### Documentation

- **Status prose matches the closed record.** The validation heading no longer
  carries a version. The calibration battery is six cases, and its limits note
  the held-out failure. The silence failure does not name a partner. Issues #10
  and #11 are closed as blocked. The inventory's exploratory, excluded and not
  scored rows are the lock's `exploratory` list. Nothing was rerun. `w_syn`
  stays 0.192.

## 0.8.10 — 2026-10-11

### Results

- **No held-out behavior is eligible.** The frozen partition assigned every mapped
  behavior to calibration or to a disqualified exploratory row. Nothing is promoted
  and nothing is rerun. The validated-behavior milestone stays unmet. `w_syn` stays
  0.192.

## 0.8.9 — 2026-10-11

### Results

- **The extension queue is closed as blocked.** Neuromodulation and associative
  learning have no parameter table, so no module is added. The validated-behavior
  milestone is not met. Provenance now cites the sensitivity corners, the looming
  protocol, the silence failure, the extension no-go and the TTMn_R raster.
  Nothing was rerun.

## 0.8.8 — 2026-10-11

### Results

- **TTMn_R spike times are drawn.** The raster shows the open loop continuing
  through the 300 ms drive, the closed loop stopping at the third spike, and both
  DNp01 silenced still reaching three spikes later. The times are the v0.8.6 run.
  Nothing was rerun.

## 0.8.7 — 2026-10-11

### Results

- **No biological extension is added.** Cell-type parameters, gap junctions, short-term
  synaptic dynamics and compartments have no value that transfers into this LIF. The
  looming silence failure is not a giant-fiber gap junction: silencing DNp01 removes that
  cell's output, and TTMn_R still fires. Neuromodulation (#10) and associative learning
  (#11) stay blocked. `w_syn` stayed 0.192. Nothing was retuned.

## 0.8.6 — 2026-10-11

### Results

- **The one-bit looming jump fails silence.** `TTMn_R` jumps on time in 3/3 seeds
  (43.0, 50.7, 47.8 ms), the drive cuts on that spike, and the prefix matches the
  open loop. With both DNp01 neurons silenced, `TTMn_R` still emits 3 spikes in
  every seed (third spike 154.8, 145.1, 115.6 ms) and the drive is then cut.
  Closed-loop stability is 0 neurons still firing from 400 to 600 ms and does not
  decide. The loop took 90.5 s. `w_syn` stayed 0.192. The protocol was not edited.

## 0.8.5 — 2026-10-11

### Validation

- **One-bit looming jump, before the run.** The closed-loop task is `LC4_R` →
  `TTMn_R`: the third spike cuts the drive. Jump, feedback, DNp01 silence, and a
  decoder-prefix check are required. The claim is a calibration feasibility check,
  because looming escape selected the model. FlyBody (Apache-2.0) was compared and
  not embedded. `flymsg behavior` prints the protocol and does not simulate.
  Criterion v4, N1, and the held-out manifest are unchanged.

## 0.8.4 — 2026-10-11

### Results

- **The held-out failure survives both sensitivity corners.** At the Shiu weight
  (`w_syn` 0.275, `th_jump` 0) DM1_lPN is 301.1 Hz against a 200 Hz control, and 7797
  neurons stay active. With adaptation (`w_syn` 0.192, `th_jump` 2) it is 185.6 Hz
  against 105.6 Hz, and 2669 neurons stay active. Specific and stability fail at both
  corners. ORN_V does not decide. The scored result stays the verdict. The manifest
  was not edited.

## 0.8.3 — 2026-10-11

### Results

- **Held-out ORN_DM1 → DM1_lPN fails.** Positive passes (284.4 Hz, 3/3 seeds, first
  spike 3.4 ms). Specific fails: the class-matched olfactory control reaches 185.6 Hz,
  and the check needs it at or below 94.1 Hz. Stability fails: 4894 neurons still fire
  after the stimulus (limit 100). ORN_V → V_ilPN and V_l2PN shows the same pattern and
  does not decide. `w_syn` stayed 0.192. The manifest was not edited.

## 0.8.2 — 2026-10-11

### Validation

- **Held-out manifest, before the run.** Calibration, exploratory and held-out cases are
  partitioned in `validation/benchmarks.yaml`. The one confirmatory case is ORN_DM1 →
  DM1_lPN, scored with the v4 positive, specific and stability checks at the default
  parameters. `flymsg benchmarks` prints that case and does not simulate. Criterion v4
  and N1 are unchanged.

## 0.8.1 — 2026-10-11

### Results

- **T4, whether AVLP717m relays P1's drive to pIP10.** The pre-registered null finished.
  Silencing AVLP717m (2 neurons) drops pIP10 after P1 by 43% (104 → 60 Hz), p = 0.001.
  The same silencing drops dPR1 after P1 by 28%; that row does not decide. After the
  pIP10 stimulus the matched null is not defined, and dPR1 is unchanged. `w_syn` stayed
  0.192.

## 0.8.0 — 2026-10-11

### Reproducibility

- **Pre-registration file** (`validation/preregistration.yaml`, version 1). Hypotheses,
  criterion v4 thresholds, N1, the four null families, pathway list and draw counts are
  locked. The test suite fails if the live code or a confirmatory run differs without a
  version bump.
- **Null families** (`flymsg nulls`). Degree-preserving (N1's permutation, many seeds),
  cell-type-preserving, weight shuffle within presynaptic cell type, and sign shuffle.
  Each draw is seeded. The score is signed stim→target weight (`sum` and `max`); every
  pathway is reported. Default `--draws` is 2 (CI). `flymsg nulls --full` is the locked
  20-draw command. N1's one-draw battery is not redrawn. On MaleCNS v1.0 with 20 draws
  the headline (4077) is above every draw of every family (_p_ = 1/21). Four one-hop
  pathways are 0, including sugar → MN9.
- **Run manifests.** Commands that write outputs also write `manifest.json` (git commit,
  dataset name and file hashes, config, seeds, package versions, platform, timestamps).
- **Provenance.** `docs/provenance.md` lists the public source and introducing commit for
  each existing idea. Public literature and public repositories only.

## 0.7.4 — 2026-10-11

### Results

- **T3, how dMS9 restrains dPR1.** The run pre-registered on 2026-09-23 finished from its
  checkpoint. Silencing IN03B024 (2 neurons) raises dPR1 by 101% after pIP10 and 100% after
  P1. Silencing vMS12_a+b+c (12) raises it by 67% and 78%. All four rises have p = 0.001.
  Silencing dMS9 together with IN03B024 raises it by 100% and 99%, and the 95% bootstrap
  intervals of the per-seed rise overlap in both cases. The chain is supported. `w_syn`
  stayed 0.192.

## 0.7.3 — 2026-10-11

### Docs

- **GitHub Pages.** The README and the docs are published at
  <https://gianlucamazza.github.io/flymsg/>. `scripts/build_pages.py` builds the site, and
  heading anchors stay the ones the docs already use.

## 0.7.2 — 2026-10-11

### Docs

- **Gallery.** The README collects the viewer frames and says what each colour means:
  LC4_R at 120 ms, the pIP10 pathway at 150 ms, that replay coloured by the sex annotation
  (male-specific, dimorphic, no label), and pIP10, dPR1 and dMS9 in the neuropil shells.
  `docs/viz.md` points at the gallery.

## 0.7.1 — 2026-10-11

### Viewer

- **A bad bloom mip no longer erases a replay.** The 11-tap blur into a target about 44×29
  wrote NaN on this GPU. The composite stretched it over the empty part of the frame, and
  adding the glow back turned those pixels black, so a paused pIP10 replay went black while
  the page still counted its surfaces. The blur inlines its weights and unrolls the taps, and
  a non-finite sample adds nothing. With bloom off and 4× MSAA still on, the same frame was
  already the whole circuit. Clip planes track the volume. The unexplained black-viewport note
  in `docs/viz.md` is replaced by this account. Geometry is unchanged.

### Docs

- **README.** The traced graph still passes 29/29. On N1's shuffle the same battery is 5/29,
  all five the `stability` check, and every `specific` check fails. `w_syn` stays 0.192.
  Figures from the fixed viewer: LC4_R at 120 ms, the pIP10 pathway at 150 ms, and pIP10,
  dPR1 and dMS9 in the neuropil shells.

### Licence

- Exclusions for the connectome data and the vendored three.js and lil-gui live in `NOTICE`.
  `LICENSE` is the plain MIT text. The README points at `NOTICE`.

## 0.7.0 — 2026-10-11

### Results

- **N1, the degree-preserving shuffle** (`docs/related.md`). Seed 0, default model, criterion
  v4. The traced graph passes 29/29. The shuffle passes 5/29, all five the `stability` check:
  activity still dies out. Every `specific` check fails (7/7). `positive`, `order`, `dose`
  and `negative` fail too. `w_syn` was not changed.

### Docs

- **Related work** (`docs/related.md`): MaleCNS 211,577 is the raw body table, not a second
  animal; BANC's published backbone-proofread count sits beside the 188,508 / 13,620,865
  figures used by the embodied model. README links the note.
- Stale lines brought in line with 0.6.0: an input spike adds 48.1 mV (`docs/model.md`), the
  validation status heading is v0.6, and the courtship enrichment sentence matches its table
  (4.3–18.6×).

### Tools

- **`flymsg wiring-null`**: N1's shuffle (`wiring.shuffle_targets`, seed 0). `--stats` prints
  self-loops and duplicate pairs and does not simulate. Without `--stats` the command runs
  criterion v4 on the traced graph and on the shuffle, at the default `w_syn` and `th_jump`,
  seeds 0–2, and writes `runs/n1-real.csv` and `runs/n1-shuffle.csv`. No flag changes the
  seed or the weights.

## 0.6.0 — 2026-09-23

### Results

- **Pre-registered silencing tests (T1, T2), 1,000 null draws each.** Silencing the 948
  sexually dimorphic neurons raises dPR1 by 61–64 % after either courtship stimulus
  (p = 0.001): confirmed. fru/dsx+ is not confirmed (p 0.011 after P1): silencing ~4,900
  neurons raises dPR1 by +21 % on average by itself. Looming escape depends on none of the
  three categories, now with 1,000 draws.
- **Correction:** v0.5 predicted the loop dPR1 → dMS9 → vPR9_a / IN00A038 → dPR1. T2 keeps
  dMS9 (+67 %, +74 %, p 0.001 against matched active neurons) and rejects the inhibitory
  half: silencing vPR9_a + IN00A038 lowers dPR1 after pIP10 and stays inside the null after
  P1. The route by which dMS9 restrains dPR1 is open.
- **Post-hoc lead, pre-registered as T3 for the next run:** with dMS9 silenced, the
  inhibitory neurons that actually stop driving dPR1 are IN03B024 (1,533 synapses onto dPR1,
  90 → 29 Hz), fed by vMS12_a/b/c, which dMS9 drives with 6,562 synapses and which fall
  silent. Chain: dPR1 → dMS9 → vMS12 → IN03B024 → dPR1.

### Tools

- **`flymsg compare`**: the male-vs-female numbers of `docs/comparison.md` (density factor,
  the same model on both sexes, subtype fingerprints, the FAFB LB3 split and MN9 per part)
  are regenerated by a command instead of lost scratch scripts. Shiu et al.'s Ir94e set was
  added to `compare`, and their four sets were checked id by id against `figures.ipynb` at
  the pinned commit.
- Clear messages instead of tracebacks: `--progress` without `--checkpoint`, a bad
  `--duration`, an unknown case or category, `--checkpoint` with `--by-type`. `--null`
  defaults to 1,000 everywhere, as the docs say.
- Corrected stale numbers in `docs/model.md` (an input spike adds 48.1 mV, not 68.75; a
  synapse's peak is 0.030 mV and ~230 coincident synapses reach threshold) and one
  fingerprint value in `docs/validation.md`.
- Tests: `compare`'s numeric functions, `graph`, `data.download`, `data.build_fafb`,
  `validate.calibrate` and `compare_models`, and a smoke test per CLI subcommand (72 tests).
  Two defects they found are fixed: `build_fafb`'s integrity check raised `IndexError`
  instead of its message for an id above every known one, and `audit` on a dataset with one
  side only failed with a bare `L`.

### Internals

- One job runs every silencing test (category, cell-type set, per type); `sim.network`
  replaces seven hand-written weight-matrix calls; `validate.run` splits into per-check
  helpers and `cli.main` into `build_parser` plus a command table (217 lines to 33).
- The viewer's pure logic moves out of `main.js` into `budget.js`, `activity.js`,
  `colors.js` and `lod.js`, each with node tests; `flymsg viz` now collects the page's
  modules instead of listing them.

- `dimorphism --silencing` reports one-sided p for a drop and for a rise (`p_drop`,
  `p_rise`); `dimorphism --loop` tests the predicted dMS9 loop against silencing matched
  active neurons (pre-registered tests T1 and T2, docs/dimorphism.md).
- Worker processes start from a forkserver (`parallel.py`) instead of forking a
  multi-threaded caller; long silencing runs report progress with a measured ETA, save
  every null draw and resume from `--checkpoint FILE`, running the confirmatory tests first.
- `dimorphism --progress --checkpoint FILE`: draws per job of a checkpointed run, read-only.
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
