# Replication: rerun an archived result, and what a rerun shows

Status on 2026-10-14 (SF5, [#151](https://github.com/gianlucamazza/flymsg/issues/151)). This
page is for an operator outside the project. It says how to rerun any archived result, how
to compare the rerun with the archive, and what a match does and does not establish.

## What a match establishes

A rerun that reproduces an archived output shows that the software, the data and the
protocol give the same numbers again. It is numerical parity, not validation: no result of
flymsg becomes a fact about the fly because it can be rerun. Each result's standing against
animal data is in the [claims audit](#claims-audit) below.

## Index

[`docs/evidence/replication-index.json`](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/replication-index.json)
lists every archived result of [`results/`](https://github.com/gianlucamazza/flymsg/blob/main/results/README.md)
with:

- the command and the source commit it ran from;
- the lock file, its version and content hash (each checked by the test suite against the
  hashes the code registers);
- the dataset release and the sha256 of its compact tables; managed runs (KC v7/v8, T4/T5
  v3, the weight rule) also hash every other input they read (DoOR odors, the eye map, the
  Groschner et al. 2022 voltages), while historical entries carry only the two tables;
- the command's configuration (the arguments of `jump` and `loop` are only there);
- the seeds, the recorded result (`verdict`, or the keys a command used instead, such as the
  partner follow-up's `drive` and `left`), the Python and flymsg versions;
- the sha256 of every archived output file except the manifest, from which local paths were
  removed when it was archived.

`uv run python scripts/replication_index.py` rebuilds it; `--check` fails when it differs
from the archive, and the test suite runs that check.

## Environment

Python 3.13 and [uv](https://docs.astral.sh/uv/). `uv sync` installs the versions pinned in
`uv.lock` at the source commit. Each manifest records the interpreter, the platform and every
installed package version; a rerun on another platform or BLAS may differ in the last digits
of a float, and that difference has not been measured yet.

## Data

| Source                                     | How it is acquired                        | Licence                            |
| ------------------------------------------ | ----------------------------------------- | ---------------------------------- |
| MaleCNS v1.0 (Berg et al. 2026)            | `flymsg fetch`, then `flymsg build`       | CC BY 4.0 ([data](data.md))        |
| FAFB / FlyWire (comparison only)           | `flymsg --dataset fafb fetch`, then build | see [data](data.md)                |
| Eye map (Zhao et al. 2025, `reiserlab`)    | fetched on first use by `flymsg eye`      | GPL-3.0, fetched, not shipped      |
| DoOR odor responses (Münch & Galizia 2016) | fetched on first use by `flymsg odor`     | CC BY-SA 4.0, fetched, not shipped |
| Groschner et al. 2022 medulla voltages     | fetched by sha256 by `flymsg.medulla`     | CC BY 4.0                          |
| MANC muscles (Cheong et al. 2024, supp. 3) | fetched by sha256 by `flymsg muscles`     | CC BY 4.0                          |

Compare the sha256 of `neurons.parquet` and `edges.parquet` (and of any other input) with
the index before a run: a different hash is a different input, and the run is then not a
replication.

## Rerun one result

1. Clone the repository and check out the result's `source_commit` in a clean worktree:
   `git worktree add --detach ../rerun <source_commit>`.
2. In it, `uv sync`, then set `FLYMSG_DATA` to the data directory (or pass `--data`).
3. Run the result's `command` with its `config` (for example `uv run flymsg weight-rule
--run`). Managed commands write to `runs/<command>/v<N>.executions/<id>/output`. The id
   also covers the CPU and every installed package version, so it equals the index's
   `execution_sha256` only on the same machine; elsewhere compare the `inputs`, `protocol`
   and `config` of the new `execution.json` with the archived manifest's `extra.execution`.
4. Compare the sha256 of every output file with `outputs_sha256` in the index.

Four results ran from a modified working tree before cited runs started from clean
worktrees (v0.8.41): `results/behavior`, `results/jump/intact`, `results/jump/dnp01` and
`results/loop`. Their source commit alone does not reproduce them; the index marks them
`dirty`.

## Local inventory audit (2026-10-16)

`uv run python scripts/replication_audit.py --out NEW_FILE.json` independently checks
the indexed source commits, the protocol content hash **at each run's source commit**,
and the complete archived output inventory and checksums. It never runs a simulation
or reads external held-out recordings. Output creation is exclusive. Integrity failure
returns a nonzero exit status. Known historical provenance exceptions are reported
separately from checksum failures, and external sign-off remains absent.

The [29-result ledger](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/replication-audit-2026-10-16.json) records four dirty
historical source trees and three unversioned jump/loop protocols. The replication
index now identifies the GF looming v1/v2 and song v1 locks even though those commands
do not use `managed.PROTOCOLS`; execution semantics and archived results are unchanged.
Input licences and acquisition obligations remain in the data table above. Local
integrity success does not establish that an external operator can acquire every input.

## A rerun done here

The synapse weight rule v1 was rerun from its source commit `78f0673` in a clean detached
worktree on 2026-10-14: same execution id, verdict `undecided`, and its three output files
are byte-identical to the archive
([record](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/reproduction-weight-rule-v1-2026-10-14.json)).
It ran on the machine that produced the archive, so it checks the procedure, not
cross-platform equality; that needs an outside operator.

## Claims audit

The four categories of the [scientific fidelity](scientific-fidelity.md#claims-taxonomy)
taxonomy, plus two used here: a model diagnostic compares the model with itself, another
model or another dataset and makes no claim about the animal; a reproduction is
"attempted" when the measurement was published before the lock and the model is scored
against it.

| Result (see [roadmap](roadmap.md#results))          | Category                                          | Standing                                                                         |
| --------------------------------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------- |
| Validation battery, criterion v4                    | Reproduction                                      | calibrated on known circuits; 29/29                                              |
| N1 shuffle; four null families                      | Model diagnostic                                  | specificity against rewired graphs                                               |
| Engine against Shiu et al. brian2                   | Model diagnostic                                  | numerical agreement with another implementation                                  |
| Dimorphism T1–T4                                    | Model diagnostic                                  | which pathways run through fru/dsx in this connectome                            |
| Held-out ORN_DM1 → DM1_lPN                          | Reproduction (held out, locked before simulation) | fails specific and stability                                                     |
| Kenyon cell sparseness v1–v8                        | Reproduction (attempted)                          | measured sparseness known before the locks; v7/v8 within only with a variant set |
| KC → MBON11 depression v1                           | Reproduction (attempted)                          | inconsistent                                                                     |
| One-bit looming jump                                | Reproduction (attempted)                          | silence fails                                                                    |
| Residual partner scan v2/v3; partner follow-up v1   | Causal prediction                                 | DNp02 and DNp06; DNp06 alone reaches the jump bit; no animal test yet            |
| Held-out behavior milestone                         | none                                              | no eligible case left in the frozen partition                                    |
| Sensitivity grid v1; timestep convergence v1        | Model diagnostic                                  | where responses hold over w_syn and th_jump; rates converge at 0.1 ms            |
| T4/T5 v1–v4                                         | Reproduction (attempted)                          | neither                                                                          |
| GF looming v1/v2                                    | Reproduction (attempted)                          | no-go / uninformative; no validated transducer                                   |
| Song v1                                             | Reproduction (attempted)                          | uninformative; stopped before held-out access                                    |
| APL claw contrast v1                                | Reproduction (attempted)                          | uninformative; KC readout saturates or averages below rest                       |
| Simple wiring baselines v1                          | Model diagnostic                                  | seven positive responses specific against shuffles; no physiological validation  |
| Synapse weight rule v1                              | Reproduction (attempted)                          | undecided                                                                        |
| NeuroMechFly jump v1                                | Reproduction (attempted)                          | short                                                                            |
| Male vs female synapse counts; sugar set, LB3 split | Model diagnostic                                  | dataset comparisons                                                              |
| Motor map                                           | none                                              | every row `unmapped`                                                             |

No result is a discovery: none has been confirmed independently. The causal predictions
are listed for an animal test in [roadmap](roadmap.md#what-an-animal-test-could-check).
