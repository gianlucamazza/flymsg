# Certified bounded skeleton runtime

The accepted [runtime ADR](../adr/adr-bounded-skeleton-runtime.md) extends the
[fixed-view experiment](../report/quest-performance-2026-10-16.md). The implementation is
explicitly diagnostic: use `?check&representation=skeleton-bounded`. It requires
paged uploads; `uploads=0` is rejected. The normal viewer default is unchanged.
Do not describe this mode as admitted or XR qualified without device evidence.

The page worker prepares complete source-order pages and independently verified
spatial levels. Global branches remain anchors across page boundaries. A neuron
containing a cycle conservatively retains its complete original graph. One shared packed path index encodes all ten dyadic levels from 1 to 512 source
nanometres, considered coarse first. Each entry stores a vertex, its last retained
level and a path-end bit. A path with m edges needs m+1 <= 2m entries, so the
entire encoding fits within one additional full-index byte budget. Temporary
level indices are independently verified and discarded; the worker reconstructs
requested levels from the shared encoding. A missing useful level causes full geometry, never a relaxed error bound.

At each draw, a conservative certificate uses the actual float32 matrices and
physical viewport of both eyes. Preferred selections target 0.4 pixels and are
usable only while the upper bound remains at most 0.5 pixels. Clipping, unknown
precision or stale poses force full indices immediately. Worker replies and GPU
uploads publish complete selections atomically; context loss discards ownership.
Picking and diagnostic depth/ID always use full source indices.

Independent diagnostics read back actual native buffers, compare source positions
and original edge order, detect global cycles with union-find, walk the complete
original graph and project every omitted source vertex with the pinned vector
implementation. Direct colour differences must remain within the full-original
ID stroke support expanded by two pixels. Desktop support propagates through
all actual pinned bloom mips; its coverage is reported because this conservative
mask can cover the complete image. A support check does not certify appearance,
photometric equivalence or stereo comfort.

Every measured bounded desktop or XR frame retains its upper bound and actual/full index counts. Final XR receipts carry all raw certificates for an independent host check; summaries alone cannot pass that check. Ordinary device readiness also requires native Browser focus, separately from DOM visibility and wakefulness.
The comparison rejects missing certificates, error above 0.5 pixels, resource
errors or inconsistent counts. It explicitly requires original / bounded /
bounded / original order; all other content and display invariants stay equal.

## Reproduce software checks

```bash
node --test tests/js/*.test.mjs
uv run pytest tests/test_quest_compare.py tests/test_quest_xr.py tests/test_quest_bounded.py
bg uv run python scripts/check_geometry_pages.py --oracle viewer-bounded \
  --timeout-seconds 240 --out /tmp/flymsg-bounded-correctness
```

The viewer fixture contains two declared source neurons and uses SwiftShader.
It checks geometry, auxiliary passes, colour support and context reconstruction.
It cannot establish complete-scene device speed or hardware qualification.

## Collect device evidence

Run only from clean committed source. Use the existing
[Wi-Fi protocol](../plan/quest-wifi-trials.md), preserving its full-content and quality
requirements, independent correctness pages and all three repeats of all views:

```bash
ANDROID_ADB_SERVER_PORT=5038 bg uv run python scripts/quest_compare.py \
  --serial 192.168.1.146:5555 --out runs/quest-bounded-comparison \
  --scene looming --representation skeleton-bounded --keep-awake \
  --unattended --stop-on-regression
```

Temporary virtual proximity is restored and checked at cleanup. Unattended
results remain desktop diagnostics; they cannot qualify normal physical XR.
An admitted configuration still requires the assisted visual, stereo, head-motion,
entry/exit and sustained XR session. Keep the mode diagnostic if no configuration
passes, and retain exclusions rather than rescoring them as improvements.

## Startup diagnosis

The first frozen startup was stopped before cadence collection to complete the
six-plane clipping fallback. It produced no eligible timing arms; cleanup verified
physical proximity control, zero wake leases and the original powered-display
setting. Do not interpret this operator stop as a device performance rejection.

Worker stage counters distinguish graph/path preparation, hierarchy construction,
spatial verification, index assembly and source packing. On the initial four-page
Quest diagnostic these stages totalled about three seconds, whereas application
callbacks were initially sparse. A controlled continuous-draw diagnostic later
observed 92 callbacks in 1.2 seconds. The runtime therefore keeps drawing in the
existing application loop only while a complete GPU generation is preparing or
warming; it returns to its ordinary idle behavior after readiness. This does not
add an animation loop, change refresh rate or relax quality. Native Guardian focus
was also observed early, but that observation alone does not establish causality.
No Guardian configuration was changed.
