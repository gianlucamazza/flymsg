# Architecture

ADR for issue [#30](https://github.com/gianlucamazza/flymsg/issues/30), 2026-10-12. Status:
accepted. It records the modules as they are, the contracts between them, and the order in
which the planned work (#25–#28, #31) attaches to them. It changes no protocol, seed, model
default or manifest. The contract tests are `tests/test_contracts.py`.

## Context

flymsg is one Python package run from one command line, plus a static browser page. Every
command loads the tables, builds a weight matrix, simulates, scores, and writes outputs with
a manifest. Long batches fan out to worker processes on one machine.

| Layer        | Modules                                                                                                                                                                                                                                                   | Role                                                                                                                                                                                                                                                                                           |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data         | `data`, `quality`, `homology`, `odors`, `medulla`, `manc_muscles`                                                                                                                                                                                         | fetch and compact MaleCNS and FAFB; resolve names; reconstruction audit; male/female mapping; DoOR odors, medulla voltages and MANC muscles fetched by hash                                                                                                                                    |
| Engine       | `sim`, `runtime`, `electrical`, `native`                                                                                                                                                                                                                  | the LIF kernel (numba), its NumPy oracle in `tests/reference_sim.py`, the incremental `CpuRuntime` that runs the same step loop, electrical coupling (dense and Taylor solvers), the native fixture executor                                                                                   |
| Graph        | `graph`, `wiring`, `nulls`, `draws`                                                                                                                                                                                                                       | paths and partners; one shuffle (N1); the null families and their matched draws                                                                                                                                                                                                                |
| Experiments  | `validate`, `dimorphism`, `compare`, `benchmarks`, `behavior`, `silence_scan`, `partner_followup`, `sensitivity`, `convergence`, `baselines`, `plasticity`, `kc_sparseness`, `eye`, `t4t5`, `weight_rule`, `intervention`, `tracing`, `workbench`, `song` | stimulate, silence and score; T1–T4; held-out cases; the one-bit loop; the scans; locked diagnostics and the timestep convergence check; exploratory tools                                                                                                                                     |
| Locks        | `prereg`, `locks`, `evidence`, the `validation/*.yaml` files, `motor_map`, `jump3d_lock`                                                                                                                                                                  | frozen protocols with content hashes and evidence records; a run refuses a drifted protocol                                                                                                                                                                                                    |
| Outputs      | `manifest`, `parallel`, `progress`, `runstore`, `managed`, `runs/`                                                                                                                                                                                        | run manifests (`flymsg.run_manifest/v1`); a process pool; resumable step tables; immutable execution directories                                                                                                                                                                               |
| Presentation | `cli`, `viz`, `viz_static/`, `pages`, `figures`                                                                                                                                                                                                           | commands; the 3D bundle and page; the Pages site; the doc figures                                                                                                                                                                                                                              |
| Embodiment   | `embodiment`, `pose`, `optics`, `closedloop`, `flygym_body`, `jump`, `loop`, `sensory`, `sensory_runtime`, `ttm`, `jump3d`                                                                                                                                | M0 neural/body contract with a mock body, the B6 v2 6-DoF pose types, geometric optics onto the columns, the G5 closed-loop schedule, record and checkpoints with a FlyGym body adapter, M1/M2 bodies, sensory drive, the TTM actuator and the NeuroMechFly jump ([embodiment](embodiment.md)) |

### Pain points

- **The lock pattern is copied five times.** `behavior`, `benchmarks`, `motor_map`,
  `silence_scan` and `prereg` each define `load`, `content_hash`, `assert_locked` and a
  `VERSION_HASHES` table with the same code.
- **The draw engine lived in an experiment** until v0.8.29 (`flymsg.draws`).
- **`cli.py` was about 2,100 lines** until step 6. Each command parses, runs, prints and
  writes its own outputs and manifest.
- **The viewer bundle had no version** until v0.8.26 (`flymsg.scene/v1`).
- **Runs were not indexed** until v0.8.32: every output directory had a manifest, but
  nothing listed or compared them (#27, now `flymsg runs`).
- **The engine recorded spikes only** until v0.8.28: `sim.run(trace=...)` returned spike
  bits for chosen neurons and nothing recorded membrane potential or synaptic drive over
  time (#26, now `flymsg.tracing`).

## Decision

Keep one Python package and one process per command, with worker processes for batches. No
service, queue, database or plugin system. An execution backend other than the CPU (the GPU
lane of [runtime](runtime.md), #39 and #40) sits behind B2: it must reproduce `sim.run` on the
fixtures that ADR names before any experiment uses it, and it does not change this layout. Name six boundaries, pin each with a contract
test, and move code only behind a boundary that already has its test.

| Boundary               | Contract                                                                                                                                                                                                                                                                                                                                                                               | Modules on each side                                                     | Test                          |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ----------------------------- |
| B1 dataset tables      | `neurons`: annotation columns, `nt`, `sign` (int8), sorted by bodyId; `edges`: `pre`, `post`, `weight` (int32), rows of `neurons`                                                                                                                                                                                                                                                      | `data` → every consumer                                                  | `test_b1_dataset_tables`      |
| B2 engine              | `sim.run(W, stim, rate_hz, duration_ms, stim_ms, p, seed, bin_ms, silence, kicks, trace, graded, gap, membrane)` → `Result`; `dt` 0.1 ms; `CpuRuntime` runs the same `sim._advance` with the same `sim._delays` and `sim._constants` and gives the same `Result`                                                                                                                       | `sim`, `runtime` → experiments, `viz`, `behavior`, bodies                | `test_b2_*`                   |
| B3 protocol locks      | a YAML file, its `content_sha256`, and the module's `VERSION_HASHES` agree; a change needs a new version. New locks declare `yaml_subset: 2`, quote-aware ([#159](https://github.com/gianlucamazza/flymsg/issues/159))                                                                                                                                                                 | `validation/*.yaml` → `prereg` and lock modules                          | `test_b3_*`                   |
| B4 run manifest        | `flymsg.run_manifest/v1` with commit, dataset hashes, config, seeds, packages, platform, timestamps                                                                                                                                                                                                                                                                                    | `manifest` → `runs/`, `docs/live/`                                       | `test_b4_run_manifest_schema` |
| B5 viewer bundle       | `scene.json` neuron keys, `activity.bin` (uint8, bin-major), optional `graded.bin` (int8, bin-major, steps of `scale_mv`/127, rows in `scene.graded.k`), `partners.json` keyed by bodyId                                                                                                                                                                                               | `viz` → `viz_static/`                                                    | `test_b5_viewer_bundle`       |
| B6 embodiment contract | `flymsg.embodiment/v1`, `flymsg.clock/us-v1`, neural tick = `sim.Params.dt`; `motor_map.command` refuses while rows are unmapped; `flymsg.embodiment/v2` (`pose`): 6-DoF body and eye frames (types only); `flymsg.closedloop/v1` (`closedloop`): [body-wiring ADR](adr-body-wiring.md) order, biological runs refuse unmeasured components; `flygym_body` is the first body behind it | `embodiment`, `pose`, `closedloop`, `motor_map` → bodies (`flygym_body`) | `test_b6_embodiment_contract` |

Scored outputs stay immutable. A run writes a new directory and its manifest; nothing edits a
previous run, a lock or a frozen partition. Exploratory UI state (selection, camera, colour
mode) lives in the page URL and never in a run.

## Alternatives

- **Services behind an API** (simulation server, results database). Rejected: one user, one
  machine, batch runs of hours; a service adds deployment and failure modes and no
  scientific capability.
- **A plugin framework for experiments.** Rejected: six experiment modules share two helpers;
  a registry would hide the protocol behind indirection.
- **Leave it as it is.** Rejected: the copied lock code and the private-import draw engine
  are where the next protocol would drift.

## Consequences

- A contract change fails `tests/test_contracts.py` until this note and the test change
  together.
- New protocol modules reuse the lock and draw helpers instead of copying them.
- The viewer can reject a bundle it does not understand once B5 carries a version.

## Migration, in order

Each step is its own change with its tests green before and after. None reruns a scored
result.

1. **Contract tests** (this change).
2. **Lock helper** (done in v0.8.25). `flymsg.locks` holds `load` and the common
   `check`; `behavior`, `benchmarks`, `motor_map` and `silence_scan` keep their names, error
   classes and `VERSION_HASHES` and call it. `prereg` keeps its own check, which also owns
   the parser and the canonical hash. B3 stays green.
3. **Draw engine** (done in v0.8.29). `flymsg.draws` holds matched draws, checkpointed null
   draws and the job map (`matched_draw`, `matched_pool_shortfall`, `null_rates`,
   `pick_hash`, `partial_path`, `map_jobs`, `CheckpointMismatch`); `dimorphism` and
   `silence_scan` import them by public name. Pick hashes and partial file names are
   unchanged: the T4 checkpoint resumes and gives the same rows.
4. **Viewer bundle version** (done in v0.8.26). `scene.json` carries `schema:
flymsg.scene/v1` (`viz.SCENE_SCHEMA`); the page warns in the console on another or no
   version. B5 checks that exporter and page name the same version.
5. **Extension points.**
   - #26 state tracing (done in v0.8.28): `flymsg.tracing` records `v`, `g` and `th` of
     chosen neurons through `CpuRuntime`; the oracle and the kernel agree bit for bit and the
     spikes do not change.
   - #27 workbench (done in v0.8.32): `flymsg experiment CONFIG` runs a versioned
     `flymsg.experiment/v1` config into `runs/experiments/<config hash>/`, never overwrites
     it, and accepts only the `exploratory` label; `flymsg runs` indexes every B4 manifest
     with its label. See "Experiments and the run index" below.
   - #25 causal explorer (done in v0.8.33): `flymsg explore` and `flymsg confirm` on top
     of step 3. See "Causal explorer" below.
   - #28 robustness (tool in v0.8.31): `flymsg.sensitivity` runs a locked grid (B3) and
     reports every cell; `sim.Params` defaults never change.
   - #31 embodiment: bodies attach through B6 only. The accepted
     [body-wiring ADR](adr-body-wiring.md) fixes the one closed loop (`closedloop`, #180);
     `flygym_body` puts FlyGym's NeuroMechFly behind it, for synthetic runs until the
     transducer, registration and motor map are measured.
6. **CLI modules** (done in v0.8.45). `flymsg.cli` is a package: `__init__` keeps `main`, the
   command table and the error handling; `parser` builds the whole argparse tree; the
   commands live in `connectome`, `simulate`, `validation`, `experiments`, `body` and
   `sensory`, with `common` for labels, links and `stamp`. Commands, flags, help, output
   and written files are unchanged.

## Experiments and the run index

An exploratory experiment is a YAML file:

```yaml
schema: flymsg.experiment/v1
label: exploratory # the only label a config may carry
stimulus: [LC4_R] # types, instances or bodyIds
targets: [DNp01, TTMn]
silence: [DNp01] # optional
rate_hz: 100.0
stim_ms: 300.0
duration_ms: 600.0
seed0: 0
seeds: 3
w_syn: 0.192 # optional; default sim.Params
note: "free text" # optional
```

`flymsg experiment FILE --check` validates it against the schema and the dataset: an unknown
schema, a missing, mistyped or unknown field, an empty stimulus, a stimulus window outside the
run, a name the dataset lacks, or any label but `exploratory` is refused with the reason.
Without `--check` it simulates and writes `metrics.csv` (per seed and target: the best
neuron, its rate and first spike, and how many neurons fired), the config and a manifest into
`runs/experiments/<first 16 hex of the config hash>/`. The same config maps to the same
directory, and a second run is refused, so a result is never overwritten.

`flymsg runs [ROOT …]` reads every `flymsg.run_manifest/v1` under `runs/` and `docs/live/`
without loading the dataset and lists command, label, outcome, start, commit, dataset and
seeds. A manifest written before labels existed gets one from its command (a command that
executes a lock is `preregistered`; the held-out benchmark is `held-out`). The outcome is
`failed` when the recorded verdict is FAIL or none, so a failed held-out run stays
`held-out`; `--label failed` filters on it. A label is read, never written back, so nothing
is promoted.

A run whose manifest a doc will cite starts from a commit on `main`, in a clean detached
worktree, after the code or lock it needs is merged. Pull requests are squash-merged, so a
manifest that records a branch commit points at a commit `main` never contains.

## Causal explorer

`flymsg explore SOURCE TARGET [--silence …]` lists up to three distinct strongest routes
(`evidence: anatomy`, synapse counts) and then silences each intermediate cell type on them
and reports the target's change with a bootstrap interval (`evidence: simulation,
exploratory`). Every arm reads one target neuron, the one the baseline arm fires most (`target_neuron`);
the pre-registered T1–T4 tests instead read the type's most active neuron in each condition,
by their own definition, and stay so. It writes `explore.json` and a manifest labelled
exploratory into a directory
keyed by its configuration, and `--replay DIR` reruns a saved exploration and checks that the
contrast reproduces. It chooses nothing, attaches no p-value, and says when the target is
governed by an existing lock: `TTMn_R` belongs to issue #20 and
`validation/silence_scan.yaml`, and an exploration of it may not choose a later version's sets.

`flymsg confirm LOCK` runs a `flymsg.intervention/v1` lock: stimulus, target, optional base
silencing, named sets of cell types, seeds disjoint from the `explored_seeds` it declares,
draws, alpha and tail. A lock runs only once its hash is registered in
`intervention.VERSION_HASHES` by a commit, so it is fixed before it runs; an edited lock
without a new version is refused. Each set is compared with a matched null (the base arm's
responders, same superclass and sign) that never draws from any set of the lock, with
Bonferroni over the sets, and the result goes to `runs/interventions/<lock>/v<n>/`, which is
never overwritten. All of this is model simulation, not evidence from animals. No lock is
registered yet.
