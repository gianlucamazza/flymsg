# flymsg

[![tests](https://github.com/gianlucamazza/flymsg/actions/workflows/tests.yml/badge.svg)](https://github.com/gianlucamazza/flymsg/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Simulate and view in 3D the first complete central nervous system of a male fruit fly:
[MaleCNS v1.0](https://male-cns.janelia.org/) (Janelia FlyEM + Google, CC-BY 4.0), with
165,122 traced neurons, 25.6 M connections and 124 M synapses across the brain, optic lobes
and ventral nerve cord.

flymsg turns the wiring diagram into a spiking network, checks the simulation against
circuits whose function is known from experiments, and streams the real neuron shapes into a
browser to replay the activity.

The same pages are published at <https://gianlucamazza.github.io/flymsg/>.

## Gallery

Paused frames from the page `flymsg viz` writes, 1400×900, adaptive quality off, with the
geometry loaded. A replay colours neurons by group unless a frame says otherwise, keeps
silent neurons desaturated, and hides the neuropil shells. An anatomy view draws the shells
and does not replay spikes. Rebuild the scenes with `flymsg viz --sim LC4_R`, `--sim pIP10`
and `--types pIP10 dPR1 dMS9`. The page takes `?t=`, `?paused`, `?color=` and `?select=<bodyId>`; clicking a neuron lists its partners. Rendering is
described in [viz](docs/viz.md).

Each scene also runs live in the browser on the published site: the page streams the
neuron surfaces from the public MaleCNS volumes, and the scenes are the committed exports
in `docs/live/` (rebuild them with `scripts/build_live_scenes.py`). Around every scene the
site draws all 140,024 somata of the volume as faint points coloured by region, so the whole
CNS is visible. A desktop GPU helps.

![Looming stimulus LC4_R at 120 ms. Responding neurons fill the brain and the ventral nerve cord, and silent neurons stay desaturated.](docs/img/replay.png)

**Looming, LC4_R, 120 ms, stimulus on.** The pulse lasts 300 ms. The stimulus is the 55
LC4_R neurons. The response fills the brain and the ventral nerve cord.
[Open live](https://gianlucamazza.github.io/flymsg/live/looming/?t=120&paused&neuropils=1).

![pIP10 song pathway at 150 ms. The two stimulus neurons are cyan, responding neurons are magenta, and silent neurons stay desaturated.](docs/img/pathway.png)

**Song pathway, pIP10, 150 ms, stimulus on.** Both pIP10 neurons are the cyan stimulus.
Recruited neurons are magenta. [Open live](https://gianlucamazza.github.io/flymsg/live/song/?t=150&paused&neuropils=1).

![The same pIP10 replay at 150 ms, coloured by sex annotation. Male-specific neurons are magenta, dimorphic neurons are yellow, and neurons without that label are grey.](docs/img/dimorphism.png)

**Same replay, coloured by the sex annotation.** "Potentially …" calls join their class.
Magenta is male-specific, and both pIP10 neurons are in it. Yellow is dimorphic, and both
dMS9 neurons are in it. Grey has no dimorphism label; both dPR1 neurons are there, and they
carry `fru+dsx` on the other field. Enrichment for the whole cases is in
[dimorphism](docs/dimorphism.md). [Open live](https://gianlucamazza.github.io/flymsg/live/song/?t=150&paused&color=dimorphism&neuropils=1).

![Anatomy of pIP10, dPR1 and dMS9, one colour per type, inside the neuropil shells of the brain and the ventral nerve cord.](docs/img/anatomy.png)

**Anatomy, no replay.** One colour per type for the six neurons, drawn inside all 114
neuropil shells. pIP10 is male-specific, dMS9 is sexually dimorphic, and dPR1 is `fru+dsx`
with no dimorphism label. [Open live](https://gianlucamazza.github.io/flymsg/live/anatomy/).

**Intervention, LC4_R with both DNp01 silenced.** The failed silence check, against the
intact replay: `TTMn_R` still fires. [Open the comparison](https://gianlucamazza.github.io/flymsg/live/looming-vs-dnp01/?run=difference&t=60&paused&select=800146).

**Residual partner, DNp02 or DNp06 silenced as well.** With DNp01 already silenced, `TTMn_R`
goes from 7 spikes to 0 ([DNp02](https://gianlucamazza.github.io/flymsg/live/dnp01-vs-dnp02/?run=difference&t=60&paused&select=800146),
[DNp06](https://gianlucamazza.github.io/flymsg/live/dnp01-vs-dnp06/?run=difference&t=60&paused&select=800146)). The pre-registered
scan named both ([v2](docs/img/silence-scan-v2.svg)) and a replication on fresh seeds named
them again ([v3](docs/img/silence-scan-v3.svg)).

**Left eye and both eyes.** The same looming drive from the left (`LC4_L`) or from both
sides. MaleCNS is one animal, not a symmetric template: `TTMn_L` fires about half as often as
`TTMn_R`. [Right against left](https://gianlucamazza.github.io/flymsg/live/right-vs-left/?run=difference&t=60&paused&select=804642),
[both eyes](https://gianlucamazza.github.io/flymsg/live/looming-bilateral/).

## What it does

- **Explore the wiring**: annotations and partners of any cell type (`info`); the strongest
  chain between two cell types, plus alternative routes (`path`).
- **Simulate**: a whole-CNS leaky integrate-and-fire model after Shiu et al.
  (_Nature_ 2024) (`sim`). On the same connectome the engine reproduces their published
  brian2 model within noise.
- **Validate**: a battery of known circuits with controls, dose-response and latency-order
  checks (`validate`). Model choices go through pre-registered rules (`calibrate`,
  `select-model`).
- **Check the wiring**: one shuffle of who connects to whom, each neuron keeping its degree
  and its outgoing weights (`wiring-null`); four pre-registered null families with many
  seeded draws (`nulls`). Every run that writes outputs also writes a
  [manifest](docs/nulls.md) (commit, dataset hashes, config, seeds, packages, platform).
- **Ask questions about sex differences**: how much simulated responses run through
  dimorphic neurons, and what silencing them does (`dimorphism`); the same model on the
  female FlyWire brain (`--dataset fafb`).
- **Test causal claims**: silencing scans and follow-ups locked before they run, each with a
  matched null and a stated failure rule (`silence-scan`, `partner-followup`), and one
  measured plasticity rule (`mb-plasticity`).
- **See it**: a three.js page streams source-resolution neuron surfaces, skeletons and
  neuropils from the public data, and replays the simulated activity (`viz`). The frames are
  in the gallery.

## Results so far

- **The model passes every validation check on the traced graph, with no compensation**
  (29/29, criterion v4). The cases are looming escape (LC4 → Giant Fiber → jump motor
  neuron), Giant Fiber output, P1 courtship drive and the pIP10 song pathway, sugar →
  proboscis motor neuron MN9, and bitter taste leaving MN9 silent. The only departure from
  the published model is a synapse weight scaled for MaleCNS's denser synapse detection,
  chosen by a pre-registered model selection and confirmed on fresh seeds
  ([validation](docs/validation.md)).
- **Those specific checks need the measured partners.** One shuffle of who connects to whom,
  with each neuron keeping its degree and its outgoing weights, drops the same battery from
  29/29 to 5/29. The five that remain are the `stability` check of every case:
  self-sustained activity still dies out. All 7 `specific` checks fail, and so do
  `positive`, `order`, `dose` and `negative`. The synapse weight stays 0.192
  ([related](docs/related.md)). Four further null families, 20 draws each on MaleCNS v1.0,
  put the one-hop signed pathway weights above every draw (_p_ = 1/21): degree-preserving
  null mean 21.4 against a real headline of 4077; cell-type-preserving 3196; weight-within-type
  680; sign 1314. Four pathways have no direct synapses (including sugar → MN9). See
  [nulls](docs/nulls.md).
- **The engine matches the published model.** On the female FlyWire brain, with the same
  sugar neurons, flymsg and Shiu et al.'s brian2 code agree within noise (r ≥ 0.998 over all
  active neurons). The check uncovered six places where an earlier version of flymsg had
  departed from the published model ([comparison](docs/comparison.md#engine-check)).
- **Courtship circuits run through the dimorphic network; escape and feeding do not.**
  Responders to P1 and pIP10 stimulation are 4–19× enriched in fru/dsx+, male-specific and
  dimorphic neurons over superclass-matched chance. Two pre-registered silencing tests with
  1,000 matched null draws each then asked what is necessary: silencing the 948 sexually
  dimorphic neurons raises the song neuron dPR1 by 61–64 % after either stimulus (confirmed),
  and silencing the two dMS9 neurons alone raises it by two thirds, more than silencing any
  matched active neurons. The same tests reject the other half of v0.5's prediction: the
  inhibitory neurons vPR9_a and IN00A038 are not the route by which dMS9 holds dPR1 back.
  T3 supports the route fixed before the run: silencing IN03B024, or vMS12_a+b+c, raises
  dPR1 after both courtship stimuli (p = 0.001), and silencing dMS9 together with IN03B024
  raises it no more, because the 95% intervals overlap.
  T4 passes its one test: silencing AVLP717m drops pIP10 after P1 by 43% (p = 0.001).
  The same silencing after the pIP10 stimulus has no matched null, so that case has no p
  ([dimorphism](docs/dimorphism.md)). The gallery colours the pIP10 replay by the sex annotation.
- **The held-out olfactory case fails.** ORN_DM1 recruits DM1_lPN (284.4 Hz, 3/3 seeds),
  and the CO2 ORNs recruit their PNs, but neither is specific against other olfactory
  neurons and both leave thousands of neurons firing after the stimulus. The same
  failure survives the Shiu weight and adaptation. The scored weight stays 0.192
  ([benchmarks](docs/benchmarks.md)).
- **Why the held-out olfactory case keeps firing** (exploratory). Most of the neurons still
  active after the stimulus are Kenyon cells, and 73% of the excitatory synapses onto Kenyon
  cells come from other Kenyon cells; in a point LIF that loop sustains itself. A model limit,
  not a fit ([benchmarks](docs/benchmarks.md)). Those synapses are metabotropic in the fly
  (Manoim et al. 2022); a locked diagnostic shows that treating them so lowers an odor's share
  of Kenyon cells from 25% to 17%, but two odors still share 95%. The overlap is made in the
  antennal lobe, where the model turns the electrical coupling of excitatory local neurons into
  fast chemical excitation: without it one ORN type drives 4.5% of the projection neurons, not 73%. With
  real odors (DoOR) the code is either dense or silent, never sparse: the measured electrical
  coupling is what the model lacks
  ([model](docs/model.md#kenyon-cell-sparseness-diagnostic-2026-10-13)).
- **The measured dopamine-gated depression is not odor-specific in the model.** Applying the
  Kenyon cell → MBON11 depression of Hige et al. 2015 after pairing silences MBON11 for the
  paired and the unpaired odor alike: the two odors share 95% of their ~1,000 Kenyon cells,
  against 30–33% in the fly. The same Kenyon cell limit, seen from learning
  ([model](docs/model.md#dopamine-gated-depression-at-kenyon-cell-to-mbon11-synapses-optional-2026-10-13)).
- **The one-bit looming jump fails silence.** `TTMn_R` reaches three spikes on time
  in 3/3 seeds, and the closed loop stops there. With both DNp01 silenced it still
  reaches three spikes, later. The raster is
  [TTMn_R](docs/img/looming-jump.svg), explained in [behavior](docs/behavior.md).
  `w_syn` stays 0.192.
- **The residual `TTMn_R` drive goes through DNp02 and DNp06, in the model.** With both
  DNp01 silenced, silencing either one as well removes every `TTMn_R` spike. Version 1 of the
  pre-registered scan missed its threshold because each null contained the other unit;
  version 2, fixed after that result but before its own run, excludes it and names both
  (p 0.001 each against 0.025) ([behavior](docs/behavior.md#result-of-version-2-2026-10-12)).
  Version 3 repeats version 2 on fresh seeds 30–32 and names both again
  ([behavior](docs/behavior.md#result-of-version-3-2026-10-12)): the naming replicates.
  A follow-up, locked before its run, finds the same on the left side, and shows that DNp06
  driven at 200 Hz reaches the jump bit alone while DNp02 alone does not; together they are
  far above random descending pairs ([behavior](docs/behavior.md#result-of-version-1-2026-10-13)).
- **Extensions only where a measurement transfers.** Cell-type parameters, gap junctions,
  short-term synaptic dynamics and compartments have no value that transfers into
  this LIF, and none is added. Silencing DNp01 removes that cell's output, and `TTMn_R` still fires,
  so the silence failure is not a missing giant-fiber gap junction; the residual
  drive goes through DNp02 and DNp06. Neuromodulation stays out; associative learning has
  one optional rule, the measured dopamine-gated depression at Kenyon cell → MBON11,
  locked before its run ([model](docs/model.md#dopamine-gated-depression-at-kenyon-cell-to-mbon11-synapses-optional-2026-10-13)).
- **No held-out behavior is eligible.** The frozen partition has no remaining task that
  can fill the validated-behavior milestone. Exploratory rows stay exploratory
  ([validation](docs/validation.md)).
- **Synapse counts are not comparable across datasets.** A male neuron has a median 1.81× the
  synapses of its female counterpart over 7,327 matched cell types, a difference between the
  reconstructions. Male vs female simulations are corrected for it
  ([comparison](docs/comparison.md)).
- **Part of the published sugar response comes from LB3d-like taste neurons**, a subtype one
  study matched to high-salt receptor lines. In the female model the "sugar" set of Shiu et
  al. splits into 14 sugar-like and 6 LB3d-like neurons; the latter add about a quarter of
  the MN9 response.

Negative results are kept as well: the [findings log](docs/validation.md#findings-log)
records what failed and why.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (Python 3.13) and, for the browser tests, Node ≥ 22 (CI: Node 24).

```bash
git clone https://github.com/gianlucamazza/flymsg && cd flymsg
uv sync
uv run flymsg fetch     # ~1.1 GB of public Feather tables into data/raw/, no account needed
uv run flymsg build     # compact to data/*.parquet (~10 s)

uv run flymsg path LC4 TTMn --alt 3
uv run flymsg sim LC4_R --duration 600 --stim-ms 300 --seeds 3 --superclass descending_neuron vnc_motor
uv run flymsg viz --sim LC4_R && python -m http.server -d runs/viz 8000   # open http://localhost:8000
```

Neurons are addressed by cell type (`LC4`), instance (`LC4_R`) or bodyId (`10001`). The data
directory defaults to `./data` (`--data DIR` or `FLYMSG_DATA` to change it).

## Commands

| Command                                                         | What it does                                                                                            |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `compare [--sex \| --fingerprint TYPE… \| --lb3-split]`         | male vs female: synapse density, the same model on both, the FAFB LB3 split                             |
| `fetch`, `build`                                                | download and compact the connectome (`--dataset fafb` for the female brain, ~135 MB)                    |
| `info TYPE`                                                     | annotations, top partner types, Neuroglancer link                                                       |
| `path SRC DST [--alt K]`                                        | strongest chain by input fraction; `--alt` adds routes avoiding the previous intermediate types         |
| `sim STIM…`                                                     | simulate a Poisson stimulus; per-type rates, reliability across seeds, latency, self-sustained activity |
| `validate`                                                      | the validation battery (a few minutes)                                                                  |
| `behavior`                                                      | print the frozen one-bit looming-jump protocol, or run the closed loop with `--run`                     |
| `wiring-null [--stats]`                                         | N1: shuffle who connects to whom; `--stats` counts self-loops and stops                                 |
| `nulls [--full]`                                                | four wiring-null families; default 2 draws (CI); `--full` is the locked 20-draw run                     |
| `calibrate`, `select-model`                                     | parameter grid search and pre-registered model comparison                                               |
| `audit`                                                         | reconstruction completeness: flags bilateral neurons with one side far below the other                  |
| `dimorphism [--silencing \| --loop \| --by-type CASE CATEGORY]` | dimorphic neurons among responders; silencing by category, by cell type, or of the predicted dMS9 loop  |
| `viz --sim STIM \| --path SRC DST \| --types …`                 | export a 3D scene; the page streams geometry from the public volumes                                    |
| `trace STIM --neurons N…`                                       | record v, g, threshold, spikes and input of chosen neurons; model states, not recordings                |
| `viz-compare A B --labels … --status …`                         | pair two replay exports; refuses mismatched datasets or time bases; no simulation                       |
| `sensitivity [--run]`                                           | the locked w_syn × th_jump grid around the defaults: every cell, spreads, a figure; a report            |
| `benchmarks [--run \| --corners]`                               | the frozen held-out manifest, scored with `--run`                                                       |
| `silence-scan [--run]`                                          | the locked residual `TTMn_R` partner scan (#20); prints the protocol without `--run`                    |
| `partner-followup [--run]`                                      | the locked left mirror and direct drive of DNp02 + DNp06 (#76)                                          |
| `mb-plasticity [--run]`                                         | the locked dopamine-gated KC → MBON11 depression (#85), applied between trials                          |
| `kc-sparseness [--run]`                                         | the locked diagnostic of why an odor recruits 25% of Kenyon cells (#95): KC → KC and APL arms           |
| `odor NAME`                                                     | a DoOR odorant as a response per MaleCNS ORN type (fetched, CC BY-SA)                                   |
| `eye`                                                           | optic-lobe column → viewing direction (Zhao 2025 eye map, fetched) and photoreceptor → column           |
| `experiment FILE [--check]` · `runs`                            | run an exploratory config into an immutable directory; index every run manifest with its label          |
| `explore SRC DST` · `confirm LOCK`                              | paths and exploratory silencing; run a registered intervention lock against a matched null              |
| `jump --sim STIM --gain-n G --mass-kg M`                        | M1: a one-DOF jump body driven by a motor neuron through an engineered decoder (not a motor map)        |
| `loop --sim STIM …`                                             | M2: looming closed loop with disconnected, shuffled and replay controls; engineered parameters          |
| `homology`                                                      | versioned male/female type mapping (flywireType) and the LC4 → DNp01 pilot                              |

The 3D page takes URL options such as `?t=<ms>&paused`, `?color=dimorphism`, `?detail=`,
`?adaptive=0`,
`?neuropils=0|1`, `?somata=0` (hide the whole-CNS soma layer), `?budget=<M triangles>` and
`?bench=<s>` ([viz](docs/viz.md)).

## How it works

1. **Data.** The MaleCNS tables list every traced neuron with its annotations (cell type,
   predicted transmitter, sex-related labels) and every connection with its synapse count.
   flymsg keeps the 165,122 traced neurons and the connections among them
   ([data](docs/data.md)).
2. **Model.** Each neuron is a leaky integrate-and-fire unit. A connection of _n_ synapses
   adds ±*n* · `w_syn` to its target after 1.8 ms. The sign follows the presynaptic
   transmitter: acetylcholine excites; GABA, glutamate and histamine inhibit; modulators have
   no fast effect. Stimulated neurons receive Poisson input spikes. All parameters are Shiu
   et al.'s, except `w_syn`, which is divided by the synapse-density factor
   ([model](docs/model.md)).
3. **Validation.** Each case stimulates a population and checks the expected target:
   - it fires reliably;
   - it fires far more than when the same number of random, similar neurons is stimulated;
   - it responds more to stronger input;
   - successive stages fire in order;
   - activity dies out after the stimulus.
4. **Rules before results.** Criteria, calibrations, model selections and every confirmatory
   experiment are written down in [validation](docs/validation.md) and a versioned, hashed
   lock in `validation/*.yaml` before they run; the runner refuses a lock edited without a new
   version, and a failure is recorded rather than tuned away.
5. **3D view.** The export holds only metadata and activity. The page reads the public
   multi-resolution meshes and skeletons directly from Google Cloud Storage, refining detail
   near the camera within a triangle budget ([viz](docs/viz.md)).

## Limits

- **One animal per dataset.** There is no measure of individual variability, and sex
  differences cannot be separated from reconstruction differences. `flymsg audit` flags
  incompletely reconstructed bilateral neurons (3.2 % of types, including MN9_R).
- **Wiring only, by default.** No gap junctions, neuromodulation or cell-specific
  properties; one optional, locked plasticity rule (KC → MBON11) changes nothing unless
  called; transmitters are machine predictions, and 2.6% of synapses carry no sign. What of the
  brain is in the model is counted in [roadmap](docs/roadmap.md#brain-coverage). The Giant Fiber, for example, behaves like a
  `shak-B²` mutant lacking its electrical synapse.
- **Qualitative rates.** Use the model to rank which circuits a stimulus recruits and in what
  order, not to predict exact firing.
- **Few, short cases.** The validation cases are mostly 1–2-hop feed-forward chains.

## Documentation

| Document                             | Content                                                                       |
| ------------------------------------ | ----------------------------------------------------------------------------- |
| [data](docs/data.md)                 | sources, files, filtering, schema, the female FAFB dataset, citations         |
| [model](docs/model.md)               | equations, parameters, signs, density scaling, extensions, optional KC→MBON11 |
| [validation](docs/validation.md)     | current status, protocol, cases, calibration, model selection, findings log   |
| [benchmarks](docs/benchmarks.md)     | held-out partition, the ORN_DM1 failure, both corners fail                    |
| [behavior](docs/behavior.md)         | one-bit looming jump; silence fails; residual partner DNp02/DNp06 replicated  |
| [architecture](docs/architecture.md) | module layers, the six contracts and their tests, migration order             |
| [embodiment](docs/embodiment.md)     | M0 neural/body contract, synthetic body, no motor map; the E1–E4 roadmap      |
| [runtime](docs/runtime.md)           | incremental CPU runtime, checkpoints, backend ADR; GPU lane planned           |
| [nulls](docs/nulls.md)               | pre-registered null families, scores, draw counts, methods                    |
| [provenance](docs/provenance.md)     | date, public source and commit for each existing idea                         |
| [comparison](docs/comparison.md)     | engine check against the published model, male vs female, the LB3 split       |
| [dimorphism](docs/dimorphism.md)     | dimorphic neurons among responders, silencing                                 |
| [related](docs/related.md)           | adjacent whole-CNS models, the raw 211,577 count, wiring null N1              |
| [viz](docs/viz.md)                   | 3D pipeline, whole-CNS soma layer, sides, levels of detail, GPU measurements  |
| [roadmap](docs/roadmap.md)           | brain coverage in numbers; what is blocked on evidence or hardware, and why   |
| [CHANGELOG](CHANGELOG.md)            | what changed in each version                                                  |

## Development

```bash
uv run pytest            # unit tests on synthetic networks + browser-module tests (node --test)
uv run pytest -m slow    # plus the full validation battery (needs the data) and a live GCS read
uv run ruff check && uv run ruff format --check src tests scripts
```

- `tests/reference_sim.py` keeps the previous NumPy simulator as an oracle: the compiled
  kernel must reproduce its spikes exactly.
- `scripts/shiu_reference.py` runs the published brian2 model for the engine check. It needs
  brian2 in its own environment.
- `scripts/shoot.mjs` screenshots the 3D view headless (`GL=gl` for the real GPU).
- `scripts/vendor-js.sh` refreshes the vendored three.js and lil-gui.
- `scripts/bench_viewer.py` measures the 3D view on every scene and refuses a loaded machine;
  `scripts/brain_coverage.py` prints what of MaleCNS the model uses;
  `scripts/archive_results.py` copies cited run outputs into `results/`;
  `scripts/build_figures.py` redraws `docs/img/*.svg` from them.
- The code carries no lint or formatter suppressions (`noqa`, `fmt: skip`, …); a test fails if
  one appears. A run a doc cites starts from a commit on `main` ([architecture](docs/architecture.md)).

## Citation

If you use flymsg, cite the data and the model it builds on (see also
[CITATION.cff](CITATION.cff)):

- MaleCNS: Berg, S. et al. Sexual dimorphism in the complete _Drosophila_ male central
  nervous system connectome. _Cell_ 189, 5504–5526 (2026). doi:10.1016/j.cell.2026.08.015.
  CC-BY 4.0.
- Model: Shiu, P. K. et al. A _Drosophila_ computational brain model reveals sensorimotor
  processing. _Nature_ 634, 210–219 (2024). doi:10.1038/s41586-024-07763-9
- For `--dataset fafb`: FlyWire (Dorkenwald et al. 2024; Schlegel et al. 2024; Matsliah et
  al. 2024; Berg et al., the MaleCNS paper above), as listed in [data](docs/data.md).

## License

Code: [MIT](LICENSE). The connectome data are not part of this repository; they are
downloaded from their public sources under their own licences. Vendored three.js and lil-gui
are MIT (`src/flymsg/viz_static/vendor/`). See [NOTICE](NOTICE) for what the licence does not cover.
