<!-- What changes and why, in a few lines. -->

- [ ] A lock that decides anything was merged before its run, and the run started from a commit on `main`
- [ ] Every value is sourced or named as a compensation; defaults (`w_syn`, `th_jump`) unchanged
- [ ] `results/` and figures regenerated if a cited output changed
- [ ] Docs, README and `CHANGELOG.md` (Unreleased) updated
- [ ] `uv run ruff check`, `ruff format --check src tests scripts`, `uv run pytest`, prettier on Markdown; no `noqa` or `fmt: skip`
