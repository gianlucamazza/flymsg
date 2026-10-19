# ADR: logical module boundaries and staged organization

Status: accepted by the owner through the merge instruction, 2026-10-18 (proposed the
same day). Each implementation step remains its own reviewed PR with the gates below.
The accepted [architecture](architecture.md) remains unchanged.

## Context

The architecture audit inspected `10cae55499d7fd2f42d4aed0217c4a94f31341cf`
on 2026-10-18: 74 Python modules, mostly flat, and 50 scripts. Its AST graph
includes nested imports but excludes dynamic imports, scripts, JS and native code.
It is acyclic; the core (`sim`, `runtime`, `electrical`, `graph`, `wiring`)
has no experiment imports. In particular, `sim` imports only `electrical`
(`src/flymsg/sim.py:28`), and `runtime` imports `electrical` and `sim`
(`src/flymsg/runtime.py:12`). Flat files alone are not a dependency defect.

Concrete boundaries worth improving:

- Generic `locks` imports battery policy through `prereg`
  (`src/flymsg/locks.py:10`). Parsing and hashing (`src/flymsg/prereg.py:123`,
  `:194`) share a module with battery live fields (`:210`).
- Looming calls `song.dead_time` (`src/flymsg/gf_looming.py:174`;
  implementation `src/flymsg/song.py:240`). APL uses KC protocol/spent seeds
  and stimuli (`src/flymsg/apl_claws.py:75`, `:78`, `:190`) and plasticity's
  depression (`:112`); KC also imports plasticity (`src/flymsg/kc_sparseness.py:31`).
  Shared operations and deliberate scientific dependencies must be distinguished.
- `managed` owns asset preparation and experiment identity/lifecycle
  (`src/flymsg/managed.py:31`, `:72`, `:134`): it is application orchestration.
- Scripts import scripts: console helpers (`scripts/console_bench.py:29`, `:30`),
  Quest transport (`scripts/quest_compare.py:19`) and a dynamic archive import
  (`scripts/replication_index.py:22`). Reused helpers need explicit homes.
- Exactly 21 package modules use `parents[2]` for root resolution, including
  `src/flymsg/song.py:33` and `src/flymsg/pages.py:20`. Moving files changes
  resource lookup; defaults such as `load(path=PATH)` capture their original path.
- Pages has explicit sources/stems (`src/flymsg/pages.py:54`), a global filename
  map (`src/flymsg/pages.py:115`), URL rewriting that strips `docs/` rather than resolving against
  source (`src/flymsg/pages.py:147`), and adjacent CSS (`src/flymsg/pages.py:212`). `tests/test_pages.py:42` covers
  built pages, not every Markdown file; `tests/test_pages.py:69` pins validation anchors.

## Decision

Propose these **logical layers**, not immediate directories. The table lists
allowed dependency directions (importer → dependency); omitted directions require
an explicit review. Same-layer dependencies must remain acyclic. This is a target
for staged work, not a claim that all existing imports already follow it.

| Layer         | Responsibilities / examples                                                      | Allowed dependencies                                                            |
| ------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| engine        | sim, runtime, electrical, units                                                  | engine                                                                          |
| connectome    | data, graph, wiring, quality, homology; MANC data adapter                        | engine, connectome                                                              |
| provenance    | neutral lock codec, locks, evidence, manifest, runstore                          | engine, connectome, provenance                                                  |
| execution     | parallel, draws, progress                                                        | engine, connectome, provenance, execution                                       |
| sensory       | eye, medulla, odors, optics, stimulus primitives                                 | engine, connectome, sensory                                                     |
| body          | embodiment, pose, closedloop, flygym_body, jump, loop, ttm                       | engine, connectome, provenance, execution, sensory, body                        |
| backends      | native, console; compiled native lane remains separate                           | engine, backends                                                                |
| experiments   | protocol policy, battery policy, null families, scoring                          | engine, connectome, provenance, execution, sensory, body, backends, experiments |
| presentation  | viz, viz_static, pages, figures                                                  | engine, connectome, presentation                                                |
| cli           | area commands, parser, managed application orchestration; exploratory operations | all runtime layers above, cli                                                   |
| qualification | opt-in fixtures, console/Quest transport and checks                              | runtime layers above, qualification; no production dependency on qualification  |

Protocol modules retain thresholds, verdicts, cohorts, held-out access order,
seed exclusions and RNG consumption. APL/KC cross-lock checks stay explicit.
`compare`/`dimorphism` may remain experiments when scoring dominates; body locks
retain their scientific policy. Closed-loop clock/scheduler authority stays together.
The table is not permission to relocate a mixed module without separating its roles.

Extract real boundaries before moving files. Later physical moves are optional,
leaf-first, one cluster per PR; move the engine last, only if useful. Preserve old
public imports with ordinary facades, including exception identity, monkeypatch
behavior and importable top-level multiprocessing callables. Resolve package assets
and repository roots explicitly; test from another cwd and in built packages.

Keep one package and one process per command with existing worker pools. No plugin,
dynamic registry, service, queue or database framework; retain the existing explicit
command mapping. This follows `docs/architecture.md:42` and `:66`. Do not introduce
a ProtocolSpec framework now. A later two-command pilot may justify a small explicit
adapter using existing `managed`, `runstore`, `progress` and `draws` contracts.

## Invariants

- Preserve raw bytes of `validation/**`, `results/**`, `docs/evidence/**`, canonical
  lock payloads/hashes, historical `VERSION_HASHES`, error classes and public APIs.
  Parsed rationale strings affect hashes (`src/flymsg/prereg.py:198`); comments
  also stay frozen for byte comparison. No rehashing to accommodate organization.
- Preserve CLI names, lock paths and registry keys. Replication combines current
  command/PATH mapping with archived manifest hashes (`scripts/replication_index.py:31`,
  `:38`, `:68`); generated index bytes and exception categories must stay identical.
- Preserve semantic IDs such as `flymsg.gap/...`; they are not import paths.
  Preserve script entry points, output schemas, job ordering, checkpoints and seeds.
  No deprecated APIs, `noqa`, silent identity migration or numerical cleanup.
- Preserve Markdown source paths, Pages output stems, relative assets and anchors,
  including `validation.html#findings-log`, `#protocol`, `#references`. Document
  moves require source-aware links and old landing paths before migration.
- New source identity is new evidence. Historical results remain tied to their
  source commits. A lock hash does not select a historical checkout; the operator
  does that (`docs/replication.md:59`). Software parity is not hardware or animal
  qualification; never reuse changed candidate logic as its independent oracle.

## PR sequence and gates

Test names below are under `tests/`. Each row is a separate reviewable scope;
stop on invariant drift or an unexplained failure, establish the baseline first.
Owner acceptance of this ADR is required before PR 2 or any structural implementation.

| PR  | Scope                                                                                        | Checks and stop conditions                                                                                                                                                                                                                                                                                                                                                   |
| --- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Proposed ADR and module map; documentation catalog; no moves                                 | Verify source references, README links, Pages build and `test_pages.py`; freeze protected bytes. Stop before implementation pending acceptance.                                                                                                                                                                                                                              |
| 2   | Neutral YAML subset codec/hash; prereg facade retains battery checks/errors                  | `test_preregistration.py`, `test_contracts.py`, `test_evidence.py`; compare canonical payload/hash for every validation YAML and quote-aware cases. Remove locks → battery edge; no VERSION_HASHES changes.                                                                                                                                                                  |
| 3   | Exact dead-time stimulus primitive with song facade; other utilities separately if justified | `test_song.py`, `test_gf_looming.py`, `test_apl_claws.py`, `test_kc_sparseness.py`, `test_plasticity.py`; independent exact array/shape/dtype/RNG-state parity. Keep scientific cross-lock checks local; split PR if risk grows.                                                                                                                                             |
| 4   | Importable qualification helpers; runnable old script wrappers                               | `test_native.py`, `test_console.py`, `test_qualification.py`, `test_quest_xr.py`, `test_quest_compare.py`, `test_quest_bounded.py`, `test_quest_profile.py`, `test_bench_check.py`, `test_bench_viewer.py`; import/--help without devices, synthetic JSON/binary equality. Use existing Portal; keep independent oracles separate; hardware qualification remains unclaimed. |
| 5   | Two-command convergence/path-metrics publication pilot                                       | `test_managed_cli.py`, `test_runstore.py`, `test_progress.py`, `test_parallel.py`, convergence/path-metrics tests; stable report/CSV/manifest comparison, normalize only timestamps/temp paths. Completed/failed replay must not recompute; corruption refuses; workers 1/2 preserve order. Leave GF/song lifecycle alone; stop if abstraction exceeds removed duplication.  |
| 6   | Pure archive/index tooling behind unchanged script paths and DIRS                            | `test_replication.py`, `test_replication_audit.py`, `test_results.py`; index --check, full index-byte and exception-category parity. Do not regenerate evidence.                                                                                                                                                                                                             |
| 7   | Source-aware doc links, then one category per PR with old stems/landing paths                | Pages build, `test_pages.py`, all-Markdown link scan including unlisted reports; old URLs/fragments and relative images/evidence resolve. Freeze evidence/live artifacts and locked prose paths.                                                                                                                                                                             |
| 8   | Optional leaf package moves with flat facades; engine last                                   | Full non-slow suite, B1–B6 contracts, runtime coverage in contracts/closedloop/native (`test_runtime.py` if added), `test_closedloop.py`, `test_closedloop_experiment.py`, native fixtures; old/new imports and roots from another cwd, built CSS/JS/vendor/subpackage inventory. Stop on changed numerical outputs, worker imports or resources.                            |

Every implementation PR records starting HEAD/status and compares raw SHA-256
inventories of all protected files before/after, plus historical VERSION_HASHES.
Run relevant unit tests first and the ordinary non-slow suite before merge; run
`python scripts/replication_index.py --check`, read-only
`python scripts/replication_audit.py`, and
`python scripts/build_pages.py --out <scratch>`. Require ruff and Markdown
`npx --yes prettier@3.8.1 --check` to pass for changed files. Use tiny synthetic
fixtures; do not rerun scored/held-out protocols, contact devices, archive outputs
or forge old identities as part of organization.

## Consequences

Boundaries become reviewable before relocation, with small independently checked
changes. Facades and resource checks add temporary maintenance cost; logical layer
names need not become directories. Acceptance does not authorize scientific changes
or close any qualification gate. The [catalog](../catalog.md) records document authority
without moving or promoting historical material.

## Alternatives rejected

- Bulk move: changes resource depth, imports, pickling and links together before
  boundaries are proven; directory aesthetics do not justify provenance risk.
- ProtocolSpec framework now: obscures local science and duplicates existing lifecycle
  machinery without a demonstrated two-command reduction.
- Leave as is: the graph is healthy, but locks → battery, cross-experiment utilities
  and script imports remain concrete maintenance coupling without an explicit plan.
