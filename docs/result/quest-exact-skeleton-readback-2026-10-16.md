# Quest exact skeleton readbacks — 2026-10-16

**Result: exact sampled raster and reported primitive-span checks pass.**
This is static correctness evidence, not performance admission or physical XR
qualification. The [exact-fidelity decision](../adr/adr-exact-observer-performance.md)
requires original geometry; no bounded-path candidate is used here.

## Source and device

- Clean runtime `cf068d955b15af2b666f2718dbda002508704a3a`, subsequently merged
  without a tree change in #234 as `8dc67e8163a3660f250d21de23a7233c8bf96f16`.
- Physical Quest 2 `1WMHHA43LY1466`, explicit Wi-Fi ADB `192.168.1.146:5555`.
- Complete looming skeleton selection: **1,128 neurons and 8,258,589 original
  segments**, 4 MiB pages. This report does not cover the 16/64 MiB candidates or
  original surfaces.
- Source-module SHA-256 attestations and scene/activity identities are in the
  raw receipts. The original renderer supplies the independent image reference.

## Checks

Six direct captures use replay times 0, 20 and 350 ms with two eye offsets at
256 x 256 pixels. Original and paged **colour, neuron ID and packed depth are
byte-identical**. Three desktop captures at the same replay times also have
byte-identical colour, unchanged 1280 x 670 viewport, 4x MSAA and bloom.

The standalone Python verifier recomputes decoded pixel hashes and compares raw
bytes, camera/quality identities and reported original primitive spans. It checks
that every expected source span is covered once without gaps or overlaps and
that the total remains 8,258,589. It imports no renderer or candidate selection
code. Negative controls reject a broken pixel hash, changed colour with a
recomputed valid hash, and a primitive-coverage gap.

This replay does **not** recompute native GPU buffer hashes or reconstruct source
geometry from actual buffer bytes. Reported inventory provenance and exact raster
checks remain distinct evidence. The eye-offset captures are not a human physical
stereo or head-motion test.

## Reproduction and integrity

Download and extract the [immutable evidence archive](../evidence/quest-exact-skeleton-readback-2026-10-16.zip),
then run from its extracted root:

```bash
python independent/audit.py readbacks
```

Archive: **5,515,670 bytes; 43 entries**. SHA-256:

```text
a6748965d8a042c0d1bb8a85b30a569d1d7f7701876beb5ec4eb827006415ffc
```

`manifest.json` inventories member hashes. ZIP CRC and every inventoried member
hash were checked after creation. Source modules matching the loaded attestations,
raw captures, original primitive counts, inventory, verifier and negative-control
receipt are included. Check out the runtime commit for the complete implementation
and original source-asset loading procedure.

## Limits and remaining work

The parent campaign is separate and was still active when this immutable snapshot
was created. Native Guardian focus excluded ordinary cadence readiness; static
readback-only readiness cannot qualify a timing arm. Two partial timing arms do
not constitute an ABBA block or a performance result.

`readbacks/cleanup.json` verifies diagnostic-state restoration only. The archive
contains no final parent-session cleanup receipt; its temporary proximity lease
and owned resource cleanup must be verified when that session ends. Intermediate
`progress.json` may retain a running state; `oracle.json` is the final static
verdict.

Complete exact-skeleton and original-surface comparisons under the unchanged
[Wi-Fi protocol](../plan/quest-wifi-trials.md), then physical XR/session/context/thermal
qualification remain open in #177. Phone work under #24 is separate. No speed
gain, hardware-limit verdict or normal-XR qualification is established here.
