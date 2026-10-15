# Archived results

Small outputs of runs the docs cite, copied from `runs/` (ignored by git) by
`scripts/archive_results.py`, each directory with its run manifest. Local paths are removed
from the manifests; nothing else is edited. A directory here is never overwritten: a rerun
is a new version. `scripts/build_figures.py` draws `docs/img/*.svg` from these files. A
directory a doc cites is added to the table below in the same commit.

| Directory                               | Command                                                           |
| --------------------------------------- | ----------------------------------------------------------------- |
| `behavior/`                             | `flymsg behavior --run` (one-bit loop, behavior v1)               |
| `silence-scan/v1/` … `v3/`              | `flymsg silence-scan --run` (residual partner scan, #20)          |
| `jump/intact/`, `jump/dnp01/`           | `flymsg jump --sim LC4_R [--silence DNp01]` (M1)                  |
| `loop/`                                 | `flymsg loop --sim LC4_R …` (M2)                                  |
| `sensitivity/v1/`                       | `flymsg sensitivity --run` (#28)                                  |
| `convergence/v1.executions/…/output/`   | `flymsg convergence --run` (#148), SF2                            |
| `gf_looming/v1/`                        | `flymsg gf-looming --run` (#34), G3: uninformative, the no-go     |
| `mb-plasticity/v1/`                     | `flymsg mb-plasticity --run` (#85)                                |
| `kc-sparseness/v1/` … `v5/`             | `flymsg kc-sparseness --run` (#95); `docs/img/kc-sparseness.svg`  |
| `kc-sparseness/v7.executions/…/output/` | `flymsg kc-sparseness --run` (#95), v7                            |
| `kc-sparseness/v8.executions/…/output/` | `flymsg kc-sparseness --run` (#95), v8                            |
| `jump3d/v1/`                            | `flymsg jump3d --run` (#90, #94); `docs/img/jump-range.svg`       |
| `t4t5/v1/`, `v2/`, `v3.executions/…/`   | `flymsg t4t5 --run` (#84, #97, #140)                              |
| `weight-rule/v1.executions/…`           | `flymsg weight-rule --run` (#139), the managed execution's output |
| `partner-followup/v1/`                  | `flymsg partner-followup --run` (#76), every null draw            |
