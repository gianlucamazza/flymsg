# Archived results

Small outputs of runs the docs cite, copied from `runs/` (ignored by git) by
`scripts/archive_results.py`, each directory with its run manifest. Local paths are removed
from the manifests; nothing else is edited. A directory here is never overwritten: a rerun
is a new version. `scripts/build_figures.py` draws `docs/img/*.svg` from these files.

| Directory                     | Command                                                  |
| ----------------------------- | -------------------------------------------------------- |
| `behavior/`                   | `flymsg behavior --run` (one-bit loop, behavior v1)      |
| `silence-scan/v1/` … `v3/`    | `flymsg silence-scan --run` (residual partner scan, #20) |
| `jump/intact/`, `jump/dnp01/` | `flymsg jump --sim LC4_R [--silence DNp01]` (M1)         |
| `loop/`                       | `flymsg loop --sim LC4_R …` (M2)                         |
| `sensitivity/v1/`             | `flymsg sensitivity --run` (#28)                         |
| `mb-plasticity/v1/`           | `flymsg mb-plasticity --run` (#85)                       |
| `kc-sparseness/v1/`, `v2/`    | `flymsg kc-sparseness --run` (#95)                       |
| `partner-followup/v1/`        | `flymsg partner-followup --run` (#76), every null draw   |
