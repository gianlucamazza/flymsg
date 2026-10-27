# Exact Quest and desktop performance work

The [accepted exact-fidelity decision](../adr/adr-exact-observer-performance.md) controls
this work. Neither bounded geometry nor another representation is a substitute
for the original selected source. This is an execution ledger, not a claim of
performance improvement or hardware qualification.

## Completed implementation

- Stopped the bounded collector after the owner's fidelity correction. The
  interrupted attempt's `cleanup.json` passed every owned cleanup operation.
  Retain its partial evidence; it is not exact qualification data.
- Original skeleton/surface preflight now requires the requested representation
  and explicit source geometry, including readback-only preparation.
- Desktop frame identity records source fidelity. Transient identity changes
  invalidate an entire arm. XR content identity uses the same fidelity field and
  rejects missing/false original geometry on original representations.
- Independent ABBA scoring rejects missing source-geometry receipts and a
  consistently approximate representation in the exact comparison path.
  Historical receipts remain historical; do not rewrite them to add this field.

## Remaining execution gates

1. Freeze a clean source and verify exact hardware identity, Browser native focus,
   complete source/context/GPU readiness and unchanged quality. ADB connectivity
   alone is not readiness. Record transport failures as exclusions.
2. Profile original versus exact paged skeletons and surfaces separately. Use the
   existing application CPU stages and bounded passive process/GPU sampling;
   unavailable counters remain unavailable. Keep readbacks and diagnostic shader
   substitutions outside cadence windows.
3. Choose an intervention only after a measured stage identifies its cost. Preserve
   original Float32 data, primitive order, IDs, colours, transparency and selection.
   Re-run independent exact geometry/colour/depth/ID checks before timing. If no
   justified intervention exists, retain the baseline and report that limitation.
4. Complete 4/16/64 MiB, four-view, three-repeat ABBA admission under the unchanged
   [Wi-Fi protocol](../plan/quest-wifi-trials.md). The mandatory negative veto may stop a
   rejected candidate; it cannot admit a winner with missing views.
5. Qualify an admitted exact candidate on physical XR: three 120-second sessions
   per scene, 20 minutes on the heavier scene, ten entry/exit cycles, stereo/head
   motion/clipping and immersive recovery. Keep the actual-refresh p95/p99 and
   missed-slot criteria. Human visual observations cannot be inferred from ADB.

## Reproduction

Run from clean committed source. All output directories must be new. Exact
skeleton comparison uses:

```bash
ANDROID_ADB_SERVER_PORT=5038 bg uv run python scripts/quest_compare.py \
  --serial <quest-ip>:5555 --out /new/exact-skeleton-evidence \
  --scene looming --representation skeleton --keep-awake \
  --unattended --stop-on-regression
```

Run `--representation surface` into a different new directory for complete original
surfaces. Unattended virtual proximity is temporary and cleanup-verified; its
measurements are desktop diagnostics and cannot qualify physical XR. A preparation
timeout is not proof that the full configuration is unsupported.

`quest_profile.py` supplies bounded read-only device samples. Run diagnostic
sampling separately from primary cadence comparisons so its overhead cannot
asymmetrically favour an arm. Do not alter clocks, Guardian, resolution or MSAA.

Software viewer/context fixtures use `check_geometry_pages.py --oracle
viewer-skeleton` and `--oracle viewer-surface`. They exercise the real viewer on
explicitly declared small fixtures, not the full Quest workload. SwiftShader
results establish correctness only. Preserve failures and compare the unchanged
baseline before diagnosing a regression.

## Delivery boundary

Publish raw evidence, source identities, independent checks, exclusions and
cleanup, then gate the exact PR/merge/deploy. Keep #177 open until its actual
physical matrix passes. The phone portion of #24, Xbox and scientific evidence
are outside this work. A demonstrated Quest hardware limit leaves the affected
fluidity requirement unqualified; it never authorizes hidden quality reductions.
