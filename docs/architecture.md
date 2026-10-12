# Architecture

ADR for issue [#30](https://github.com/gianlucamazza/flymsg/issues/30), 2026-10-12. Status:
accepted. It records the modules as they are, the contracts between them, and the order in
which the planned work (#25–#28, #31) attaches to them. It changes no protocol, seed, model
default or manifest. The contract tests are `tests/test_contracts.py`.

## Context

flymsg is one Python package run from one command line, plus a static browser page. Every
command loads the tables, builds a weight matrix, simulates, scores, and writes outputs with
a manifest. Long batches fan out to worker processes on one machine.

| Layer        | Modules                                                                       | Role                                                                                                                                |
| ------------ | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Data         | `data`, `quality`                                                             | fetch and compact MaleCNS and FAFB; resolve names; reconstruction audit                                                             |
| Engine       | `sim`, `runtime`                                                              | the LIF kernel (numba), its NumPy oracle in `tests/reference_sim.py`, and the incremental `CpuRuntime` that runs the same step loop |
| Graph        | `graph`, `wiring`, `nulls`                                                    | paths and partners; one shuffle (N1); the null families                                                                             |
| Experiments  | `validate`, `dimorphism`, `compare`, `benchmarks`, `behavior`, `silence_scan` | stimulate, silence and score; T1–T4; held-out cases; the one-bit loop; the scan                                                     |
| Locks        | `prereg`, the `validation/*.yaml` files, `motor_map`                          | frozen protocols with content hashes; a run refuses a drifted protocol                                                              |
| Outputs      | `manifest`, `parallel`, `runs/`                                               | run manifests (`flymsg.run_manifest/v1`); a process pool; checkpointed draws                                                        |
| Presentation | `cli`, `viz`, `viz_static/`, `pages`                                          | commands; the 3D bundle and page; the Pages site                                                                                    |
| Embodiment   | `embodiment`                                                                  | M0 neural/body contract with a mock body ([embodiment](embodiment.md))                                                              |

### Pain points

- **The lock pattern is copied five times.** `behavior`, `benchmarks`, `motor_map`,
  `silence_scan` and `prereg` each define `load`, `content_hash`, `assert_locked` and a
  `VERSION_HASHES` table with the same code.
- **The draw engine lives in an experiment.** Matched draws, checkpointed null draws and the
  job map are private functions of `dimorphism`; `silence_scan` imports them by their
  underscore names.
- **`cli.py` is 1,100 lines.** Each command parses, runs, prints and writes its own outputs and
  manifest.
- **The viewer bundle had no version** until v0.8.26 (`flymsg.scene/v1`).
- **Runs are not indexed.** Every output directory has a manifest, but nothing lists or
  compares them (#27).
- **The engine records spikes only.** `sim.run(trace=...)` returns spike bits for chosen
  neurons. `CpuRuntime.snapshot()` exposes the whole state at a step boundary, but nothing
  records membrane potential or synaptic drive over time (#26).

## Decision

Keep one Python package and one process per command, with worker processes for batches. No
service, queue, database or plugin system. An execution backend other than the CPU (the GPU
lane of [runtime](runtime.md), #39 and #40) sits behind B2: it must reproduce `sim.run` on the
fixtures that ADR names before any experiment uses it, and it does not change this layout. Name six boundaries, pin each with a contract
test, and move code only behind a boundary that already has its test.

| Boundary               | Contract                                                                                                                                                                                                                                  | Modules on each side                                      | Test                          |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ----------------------------- |
| B1 dataset tables      | `neurons`: annotation columns, `nt`, `sign` (int8), sorted by bodyId; `edges`: `pre`, `post`, `weight` (int32), rows of `neurons`                                                                                                         | `data` → every consumer                                   | `test_b1_dataset_tables`      |
| B2 engine              | `sim.run(W, stim, rate_hz, duration_ms, stim_ms, p, seed, bin_ms, silence, kicks, trace)` → `Result`; `dt` 0.1 ms; `CpuRuntime` runs the same `sim._advance` with the same `sim._delays` and `sim._constants` and gives the same `Result` | `sim`, `runtime` → experiments, `viz`, `behavior`, bodies | `test_b2_*`                   |
| B3 protocol locks      | a YAML file, its `content_sha256`, and the module's `VERSION_HASHES` agree; a change needs a new version                                                                                                                                  | `validation/*.yaml` → `prereg` and lock modules           | `test_b3_*`                   |
| B4 run manifest        | `flymsg.run_manifest/v1` with commit, dataset hashes, config, seeds, packages, platform, timestamps                                                                                                                                       | `manifest` → `runs/`, `docs/live/`                        | `test_b4_run_manifest_schema` |
| B5 viewer bundle       | `scene.json` neuron keys, `activity.bin` (uint8, bin-major), `partners.json` keyed by bodyId                                                                                                                                              | `viz` → `viz_static/`                                     | `test_b5_viewer_bundle`       |
| B6 embodiment contract | `flymsg.embodiment/v1`, `flymsg.clock/us-v1`, neural tick = `sim.Params.dt`; `motor_map.command` refuses while rows are unmapped                                                                                                          | `embodiment`, `motor_map` → bodies                        | `test_b6_embodiment_contract` |

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
3. **Draw engine.** Move matched draws, checkpointed null draws and the job map from
   `dimorphism` into a public module; `dimorphism` and `silence_scan` import it. Existing
   checkpoints must replay (same pick hashes).
4. **Viewer bundle version** (done in v0.8.26). `scene.json` carries `schema:
flymsg.scene/v1` (`viz.SCENE_SCHEMA`); the page warns in the console on another or no
   version. B5 checks that exporter and page name the same version.
5. **Extension points.**
   - #26 state tracing (done in v0.8.28): `flymsg.tracing` records `v`, `g` and `th` of
     chosen neurons through `CpuRuntime`; the oracle and the kernel agree bit for bit and the
     spikes do not change.
   - #27 workbench: index `runs/` from B4 manifests; configs validate against a versioned
     schema before a run; exploratory, pre-registered, held-out and failed are labels that
     cannot be promoted.
   - #25 causal explorer: generalise the `silence_scan` pattern (lock → rule-chosen set →
     screen → fresh-seed confirmation against a matched null) on top of step 3.
   - #28 robustness: sensitivity grids as locks (B3), never editing `sim.Params` defaults.
   - #31 embodiment: bodies attach through B6 only.
