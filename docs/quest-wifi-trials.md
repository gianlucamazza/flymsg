# Quest Wi-Fi observer trials

This protocol implements the accepted observer-rendering decision. It does not
qualify a renderer or change the selected anatomy. Run from clean committed source
with the Quest connected through its explicit TCP ADB serial. Keep USB disconnected
from the test transport; there is no USB recovery fallback.

```bash
ANDROID_ADB_SERVER_PORT=5038 uv run python scripts/quest_compare.py \
  --serial 192.168.1.146:5555 --out runs/quest-wifi-comparison \
  --scene looming --representation skeleton --keep-awake
```

The wearer keeps Quest Browser foreground and does not enter VR during this desktop
comparison. Ordinary keep-awake is temporary; presence sensors, display resolution,
GPU clocks and browser rendering flags are unchanged. Each owned tab, forward,
reverse, server and keep-awake setting receives an independent cleanup attempt.
`cleanup.json` records failures; `device.json` retains the original setting for
Wi-Fi recovery. A failed restore never excuses skipping subsequent cleanup steps.

Preparation permits up to 600 seconds for complete selected anatomy and GPU context.
A timeout is an excluded preparation, not evidence that the scene is unsupported.
Source attestation uses Debugger before warmup and after measurement only. During
timing, callbacks and submissions come from the existing application animation
loop. All intervals survive, including long stalls and windows longer than 600
frames. Readbacks, GPU inventory and correctness checks use separate pages.

The independent original renderer supplies colour, depth and neuron IDs at 0, 20
and 350 ms for two eye offsets. Primitive spans must cover every original selected
primitive exactly once; full-quality desktop captures must also agree. A candidate
that fails this gate is not timed. Fresh documents prevent readback work from
contaminating the cadence arms.

For each of 4, 16 and 64 MiB pages, run A/B/B/A, where A is original and B paged,
for 30 seconds per arm after three seconds of warmup. Repeat three times in each
of dense-all, anatomical-motion, close-motion and close-static. Dense-all disables
culling. Motion uses the application loop timestamp with yaw amplitude 0.15 rad
and period 10 seconds; close views scale the frozen camera position by 0.35.
Replay stays at 20 ms. Geometry, viewport, source and image quality must agree.
A failed measurement invalidates its entire block, with at most three invalid
blocks per page configuration. Failed preparation stops that configuration.

Admission requires at least 10% median p95 gain in one motion view with a favorable
sign in every repeat, and no view with over 10% median regression. Raw intervals
are independently summarized in Python. Within one percentage point, measured GPU
memory breaks the tie. `comparison.json` retains every result and admission reason.
No admitted candidate means no XR performance claim. It does not establish that
all Quest configurations are unsupported.

Repeat surface admission separately, without replacing missing surfaces by
skeletons. Validate any winner against the original anatomy scene if that complete
scene is admissible. Neither a partial scene nor another representation substitutes
for these gates.

Only an admitted candidate proceeds to the assisted physical XR window: three
120-second sessions per admitted scene, then 20 minutes on the heavier scene.
Check stereo, scale, clipping and head movement; ten enter/exit/menu cycles; context
recovery and suspend/resume. Use `scripts/quest_xr.py --wifi-only --check` with the
winning page size and retain session reports. Source attestation finishes before
READY; subsequent device sampling is passive. The document identity in each XR
report must match the attested document. Existing qualification thresholds remain
p95 <= 1.1 actual budgets, p99 <= 2 budgets and missed-slot estimate <= 1%; unknown
or mixed refresh rates are indeterminate. Record human observations explicitly;
automated timing cannot certify stereo comfort or menu responsiveness.

These commands are collection infrastructure. Hardware qualification remains open
until complete, valid device evidence and the physical checks exist. Scientific
validation, Xbox hard-stop/GPU-fault recovery and surface admission remain separate.

## Optional mandatory-veto stopping rule

After discussing the measured collection cost with the owner on 2026-10-16, use
`--stop-on-regression` to stop a candidate after three valid repeats in any one
view establish a median ratio above 1.10. This is the existing mandatory rejection
criterion. It can reject a candidate with explicitly unmeasured views; it cannot
admit one. Positive admission still requires every repeat of every view. The
first 4 MiB campaign used this amendment after its three dense blocks completed;
its interruption and independent veto record remain alongside all raw samples.
Subsequent configurations record the option in their protocol before collection.
