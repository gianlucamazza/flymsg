# Corrected bounded runtime: Quest static readback

Clean frozen runtime and host verifier:
`b4427daa400fbe3ea723b7ec0eb569265c7539c3`, Quest 2
`<quest-serial>`, Wi-Fi transport `<quest-ip>:5555`, isolated ADB server 5038,
4 MiB pages, full looming source.

The readback-only oracle passed on all 1,128 neurons / 8,258,589 original
segments. Six cases use two offset diagnostic cameras at 0, 20 and 350 ms,
256 by 256 pixels. Actual native-buffer geometry, original edge order, global
anchors/cycles and all projected omitted source vertices passed independent
verification. Maximum measured projected error was 0.2132621695 pixels.
Neuron-ID and packed depth matched exactly in all six cases.

A separate Python implementation hash-checked the saved images and rebuilt
original-ID summed-area tables. It reproduced all six direct colour-support
checks and all three desktop bloom-support checks. Direct changed pixels were
332, 376, 1,311, 1,360, 410 and 435, all within the original stroke support
expanded by two pixels. Desktop support uses radius 706 by 704 pixels and can
cover the entire output; it does not establish photometric equivalence or comfort.
The offline replay does not recompute the geometric proof.

Guardian held native focus during these static diagnostics. This is allowed only
by explicit `--readback-only`, saved as `readback_only:true` and
`normal_xr_qualification:false`. Ordinary timing remained excluded with
`native-browser-not-focused`. These data demonstrate sampled static correctness,
not speed, motion cadence, physical eye poses, XR comfort or normal admission.
Diagnostic state restoration succeeded; the still-active campaign's final
proximity cleanup is separate from this snapshot.

[Readback archive](../evidence/quest-bounded-corrected-readback-2026-10-16.zip):
6,658,002 bytes, 27 entries, SHA-256
`692beaf59ae14c5c316c7d8c8bfff81c470d4432a449ed7d18240e282f906230`.
The archive was redacted on 2026-10-21 for privacy (device serial and LAN IP
replaced), so it differs from the original; the original hash is in git history.
It contains exact source/runtime/verifier provenance and script hashes, native
inventory and proof reports, original/candidate images, diagnostic cleanup,
campaign protocol, portable Python raster replay and a per-file hash/size manifest.
ZIP CRC and every manifested member were rechecked after creation. Extract and
run `python offline-raster-audit.py` using only the standard library.

The previous runtime's [three-repeat motion veto](quest-bounded-motion-veto-2026-10-16.md)
remains authoritative for that version. It also showed substantial main-thread
work: the first two candidate motion arms had median measured CPU times 74.25
and 76.60 ms, versus 1.40 and 1.50 ms for the paired originals; no GPU timer
samples were available. The scheduling correction does not establish that all
remaining CPU or GPU costs are resolved. The unchanged full ABBA protocol and
assisted physical XR gates remain necessary.
