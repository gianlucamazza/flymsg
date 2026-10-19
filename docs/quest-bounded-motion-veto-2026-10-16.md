# Quest bounded motion veto, 2026-10-16

Result: **16 MiB is not admitted** on frozen runtime
`febbfc285969ac7d433ed21c59fc0a3bd8661fb6`. Static gain did not survive motion.
This is a desktop diagnostic result, not physical XR qualification.

Quest 2 `1WMHHA43LY1466`, Wi-Fi-only `192.168.1.146:5555`, isolated ADB server
5038; full looming source, 1,128 selected neurons / 8,258,589 original segments.
Each block contains four fresh-document, 30-second original / bounded / bounded /
original arms with the same source, camera, viewport, content and quality.

| View              | Repeat | Original p95 ms | Bounded p95 ms | Ratio    |
| ----------------- | ------ | --------------- | -------------- | -------- |
| Dense             | 0      | 350.75          | 178.10         | 0.507769 |
| Dense             | 1      | 244.95          | 178.25         | 0.727700 |
| Dense             | 2      | 300.60          | 178.15         | 0.592648 |
| Anatomical motion | 0      | 245.00          | 345.20         | 1.408980 |
| Anatomical motion | 1      | 222.70          | 345.15         | 1.549843 |
| Anatomical motion | 2      | 245.00          | 345.25         | 1.409184 |

The median candidate/original ratio is 0.592648 dense (40.7% lower p95) and
1.409184 in motion (40.9% higher p95). The three valid motion repeats establish
the pre-registered >10% regression veto, irrespective of the static gain.
Remaining views of that configuration were skipped under the accepted rule.
Four MiB initial readiness was excluded while Guardian held native focus;
64 MiB was operator-excluded before cadence to replace the defective scheduler.
Neither exclusion is a negative performance measurement. No page size is admitted.

## Audit and interpretation

A separate Python implementation replayed all six blocks and all 2,087 bounded
frame certificates: complete 30-second windows, raw p95 recomputation,
original/bounded order, native Browser focus, source module hashes, full selected
neuron counts and unchanged quality/camera. It found no uncertified captured frame.
This replay does not independently recompute the static geometry proof or measure
compositor drops. Static native-buffer/geometry/raster evidence remains separate
in [the readback report](quest-bounded-readback-2026-10-16.md).

The first candidate motion arm discarded 99 requests and fell back on 72 of 166
captured frames. This motivated the [selection follow-up](report/quest-bounded-motion-followup.md),
including seven failing-before/passing-after unit regressions. The corrected
runtime `b4427da` passed 187 Node tests (one network skip), its real-viewer
bounded/context fixture and Linux/Windows/Python CI. These software results do
not demonstrate its device speed; its replacement 4/16/64 MiB campaign is separate.

The operator stop decision was recorded before the third motion repeat; SIGINT
was sent only after independent replay established the veto. All ordinary cleanup
operations succeeded, including physical proximity restoration (DISABLED, locks
[0,0,0]) and the original powered-display setting. No Guardian configuration,
clock, refresh rate or quality setting was changed. The replacement session must
resolve Guardian and establish native Browser focus before ordinary timing.

## Reproducible artifact

[Campaign archive](evidence/quest-bounded-motion-veto-2026-10-16.zip): 8,004,865 bytes,
288 entries, SHA-256
`fb9b607675364d98a8a0ee79734646f0058155099468791ee8b111f34aa33c7b`.

The ZIP contains raw trials, every captured certificate, preparation exclusions,
correctness readbacks, the pre-stop decision and cleanup, measured source scripts,
software fixture evidence and a per-file hash/size manifest. CRC and every
manifested member were independently checked after ZIP creation. After extraction,
run `python independent/audit.py` using the standard library; default paths are
relative to the extracted artifact. Source files are included for hash replay,
not as a complete exported browser site. Historical timeout/failure artifacts
remain present and are not rescored as successful timing.
