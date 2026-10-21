# Quest bounded skeleton static readback, 2026-10-16

Status: sampled static correctness passed. No cadence or physical XR admission.

## Identity and reproduction

Quest 2 hardware serial `<quest-serial>`, ADB over Wi-Fi at
`<quest-ip>:5555` using isolated server 5038. The active full-scene runtime was
clean frozen commit `febbfc285969ac7d433ed21c59fc0a3bd8661fb6`, 16 MiB pages,
looming, explicit `skeleton-bounded&check`. The independent host verifier was
`a81cd5b4c6bcf0ae2d9a873528dc362cfd2640b6`; production viewer files are identical
between these commits. Script hashes and the exact target URL are archived.

The separate verifier used `observer_oracle.mjs --readback-only`, owned and
cleaned its own ADB forward, and restored diagnostic state. It did not acquire
or restore the running collector's proximity lease. Its cleanup receipt is true.
Static readback readiness does not require callback progress and cannot admit
ordinary cadence or XR. The ABBA collector uses separate fresh documents and
ordinary readiness gates; its results are not part of this archive.

## Results and limits

- All 1,128 selected source neurons and 8,258,589 original segments were covered.
- Six direct captures: two offset eyes at 0, 20 and 350 ms, each 256 by 256 pixels.
  Actual native-buffer source positions, edge order, global anchors/cycles and
  projected omitted source vertices were independently audited. Maximum actual
  projected error was below 0.214 pixels, within the 0.5-pixel criterion.
- Neuron ID and packed depth matched exactly in all six cases. Direct colour
  changed 332, 377, 1,311, 1,361, 405 and 435 pixels respectively; all changes lay
  within the original neuron-ID stroke support expanded by two pixels.
- Three desktop bloom-support checks passed. Their conservative radius was
  706 by 704 pixels and may cover the entire image. This is a support check,
  not photometric equivalence or visual comfort proof.
- A separate Python replay decoded and hash-checked saved images, compared exact
  ID/depth, and rebuilt original-ID summed-area tables to check every changed
  pixel independently of the JavaScript footprint implementation. All nine
  cases passed. This offline replay does not recompute the geometric audit.

These diagnostic capture dimensions and segment counts do not describe native
viewport cadence. No speed improvement, moving-eye stereo comfort, physical
head motion, lifecycle or sustained XR acceptance follows from these checks.

## Artifact

[Readback archive](../evidence/quest-bounded-readback-2026-10-16.zip): 6,596,572 bytes,
27 entries, SHA-256
`d4d4fee3e2c6e271a087c56330563cb8bb1d8b80c5335b451db2f90dc170aa43`.
The archive includes image receipts, native geometry audit reports, source
primitive inventory, verifier provenance, cleanup, offline replay and a per-file
hash/size manifest. ZIP CRC and every manifested member hash were rechecked after
creation.

Separately, the software surface fixture hit its 60-second internal preparation
deadline both on this renderer and on baseline `c2205a1`. That is an unresolved
surface qualification, not evidence of a bounded-renderer regression. Original
skeleton and bounded software fixtures completed including context recovery.
