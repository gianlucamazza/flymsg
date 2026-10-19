# VEE and Quest 2 qualification

Execution plan accepted on 2026-10-15. The [WebXR ADR](../adr-virtual-experimental-environment.md)
and [body-wiring ADR](../adr-body-wiring.md) remain the decisions. This page records operational
criteria; it does not promote a synthetic experiment to an animal result.

The subsequent accepted [rendering ADR](../adr-observer-rendering.md) and
[implementation status](../report/observer-rendering.md) address the failed Quest workload.
The collector now requires an explicit representation for diagnostic comparisons;
its default requests full surfaces and never silently substitutes skeletons.

## Run the headless engineering fixture

From clean committed source, with Python 3.13 and the locked dependencies:

```bash
uv sync --locked
uv run flymsg closedloop examples/closedloop-nmf.yaml --check
uv run flymsg closedloop examples/closedloop-nmf.yaml --out runs/closedloop
```

The versioned config selects `nmf-optics-chain/v1`: two invented neurons, four test optical
axes, a synthetic identity eye registration, the coverage-to-rate and torque functions of
the existing NeuroMechFly fixture. Their numerical values are fixed in the fixture source;
they are not biological calibrations. The config explicitly names the clock, duration,
seed, checkpoint period and all five arms. A biological config refuses before constructing
the body. `--check` loads neither the connectome nor a physical body.

The command reuses `CpuRuntime`, `Clock`, `FlyGymBody`, `closedloop/v1` and `runstore.Run`.
Unlike dataset CLI writers wrapped by `managed`, it has no connectome input; the same
runstore source, environment, locking, finalization and corruption policies apply directly.
Identity includes the config bytes and every FlyGym asset. Each arm records exact input
event counts, spikes, commands, contacts, sampled and resulting poses.

Repeat the identical command to resume checkpoints or verify completed output. A changed
source, config, asset or environment selects another execution. A corrupt completed result
refuses. Checkpoints live outside output staging, one directory per arm. The replay must
reproduce the intact spikes exactly. Silencing is applied to the runtime, not just labeled.

`summary.json` reports the observed pose/optics difference, input and spike event counts,
per-arm wall time, newly computed simulated seconds per wall second, tick-time percentiles
and process peak RSS. Resumed/cached ticks do not count as new work. Tick timing includes
checkpoint work on control boundaries, but excludes setup and final publication; per-arm
wall time includes runtime construction and body settling. These are tiny-fixture figures,
not full-connectome throughput. Timing never enters a scientific record or clock.

## Quest 2 development and measurement

Use Quest Browser standalone. Enable Developer Mode for this headset in Meta Horizon,
connect USB data and authorize this computer. An enabled developer account alone does not
enable the device's ADB interface. On this host systemd's existing Android `uaccess` rule
grants the active seat access when the headset exposes `ff4201`; no custom `/etc` rule is
needed. See [Meta device setup](https://developers.meta.com/vr/documentation/native/android/mobile-device-setup/)
and [remote browser debugging](https://developers.meta.com/vr/documentation/web/browser-remote-debugging/).

```bash
adb devices -l
uv run python scripts/quest_xr.py --serial QUEST_SERIAL --scene looming --seconds 1800
```

For a long trial launched from an agent, run the collector as an owned transient user
service so it survives the launching command's lifetime (use the checkout's absolute paths):

```bash
systemd-run --user --collect --unit=flymsg-quest-trial --slice=background.slice \
  --property=WorkingDirectory=/absolute/flymsg \
  --property=KillSignal=SIGINT --property=TimeoutStopSec=90s \
  /absolute/flymsg/.venv/bin/python /absolute/flymsg/scripts/quest_xr.py \
  --serial QUEST_SERIAL --scene looming --port 8890 --seconds 1800
journalctl --user -u flymsg-quest-trial.service -f
```

Stop only that owned service with `systemctl --user stop flymsg-quest-trial.service`.
No persistent unit or system configuration is installed.

The script refuses another model and dirty source. It builds the current site in an owned
temporary directory, serves only on loopback, adds a device-specific reverse mapping and
opens Quest Browser. `localhost` is the trusted context; security bypass flags are not used.
It never restarts the shared ADB server. An occupied reverse port refuses; use another
`--port`. Normal exit removes only the mapping the script created. A forcibly killed
collector may leave that mapping; inspect `adb -s QUEST_SERIAL reverse --list` before cleanup.

Device/browser versions, source commit, power/wakefulness, battery, thermal status and browser memory are
captured before, every 30 seconds and after the trial. Browser reports are appended and
fsynced in `runs/quest-xr/<timestamp>/sessions.jsonl`. The opt-in `xrcollect=1` flag posts
measurements to this local collector; ordinary viewer pages make no such request. CPU/GPU
overrides, resolution overrides, disabled thermals and disabled headset safety systems are
not part of the profile. Wireless ADB is unnecessary. Record charging state and keep it the
same across comparisons. USB debugging authorization is persistent; reverse mappings are
trial resources.

Wireless ADB is also usable through an explicitly selected transport; see the
[issue-resolution procedure](../report/issue-resolution.md#physical-trial-procedure). A transport
change starts a new trial. Record temporary user-requested keep-awake settings and restore
their original values; such diagnostic runs must not silently inherit the original
qualification profile. Page visibility alone does not prove that the headset is awake.

Wait for scene loading before entering VR. The user activates the session and performs
head motion/menu actions. Capture three two-minute active sessions per scene, `looming` and
`anatomy`, then twenty minutes on the heavier measured scene. Retain cold-load observations
separately. Compare the desktop baseline at the same source and scene configuration.

The one existing animation loop collects complete active-session frame intervals, including
stalls longer than 100 ms and samples older than 600 frames. Visibility interruptions are
events and split active timing segments. CPU time covers the frame callback; GPU time is
available only with valid timer queries. Resource samples include geometries, textures,
programs, draws and triangles. LOD uses the XR eye viewport and projection, not desktop CSS.

For observed refresh `Hz`, the predeclared budget is `B = 1000 / Hz` ms:

- interval p95 ≤ `1.1 B`, p99 ≤ `2 B`;
- estimated missed slots ≤ 1% of observed plus estimated missed slots;
- unavailable refresh or mixed refresh produces `indeterminate`, never a pass;
- missing-slot estimates from intervals are not compositor drop measurements;
- no crash, incorrect stereo/clipping, failed state restoration or monotonic resource growth.

The report's timing verdict covers timing only. Full hardware qualification also requires
the operator checklist: scale/orientation and stereo, LOD under head motion, ten entry/exit
cycles, headset-menu exit, reload, suspension/resumption, and WebGL context loss/recovery.
Record the action, observed result and session identity for each. Do not qualify another
device or an untested scene from this result. Page unload or collector disconnection can
prevent delivery of the final report: partial periodic reports are retained, but are not a
completed trial. No report means no hardware verdict.

## Gate ledger

| Gate | Implemented or observed                                                                      | Remaining exit condition                                                                                                             |
| ---- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| G0   | First task, component inventory, source and no-go rules documented                           | Eligible independent looming behavioral dataset and qualified interfaces; do not infer absence of data from absence in this checkout |
| G1   | B6 v2 pose/frame/time contracts; #178 closed                                                 | No new implementation required                                                                                                       |
| G2   | Geometric projection, independent Sobol ray oracle and six rendered FlyGym camera cases pass | Measured micro-CT → body registration; #179 remains open                                                                             |
| G3   | LC4/LPLC2 circuit-only controls; GF timing v1/v2 uninformative; T4/T5 v4 neither             | Measured optical → neural transfer and independent physiological qualification                                                       |
| G4   | FlyGym adapter and TTM-only experiment, with named compensations                             | Supported muscle → actuator mapping; velocity-first jump protocol and qualified actuation                                            |
| G5   | Synthetic pose-dependent loop, all arms, exact replay, interruption/resume and CLI           | Biological loop refuses until registration, transducer, motor map and body are measured                                              |
| G6   | Song v1 #207 stopped as uninformative before opening held-out recordings                     | Measured auditory tuning and a new lock; looming behavior requires its own eligible dataset/lock                                     |
| G7   | Source-bound outputs, cold-clone procedure and fixture performance instrumentation           | Record actual reproduction and Quest hardware evidence; fixture speed does not establish whole-CNS real time                         |

G2's geometric implementation is not its complete qualification. This distinction also
applies to G5's tested synthetic integration versus biological readiness.

The [cold-clone record](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/vee-synthetic-2026-10-15.json) verifies that all five
scientific traces are byte-identical across the original run and a fresh clone at source
`1223551`; timing differs as expected. The [first Quest 2 diagnostic](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/quest2-first-diagnostic-2026-10-15.json)
records a **failure** of the default looming view: median active stereo interval 118 ms,
p95 239 ms, p99 297 ms, with approximately 13 million triangles per stereo frame. It is an
early failure diagnostic, not the full two-minute qualification matrix. The collector
process was terminated; the final record was recovered directly from the device. A
transient collector service is used for subsequent trials. The initial-refresh event
preceded the first frame; independent scoring uses the runtime's recorded 90 Hz and
distinguishes estimated missed slots from unavailable compositor drop statistics.

## Evidence audit and scientific no-go

The checked model remains fail-closed. [NeuroMechFly's primary project](https://neuromechfly.org/)
describes the body as based on a female micro-CT; it does not establish registration to the
MaleCNS eye frame. [Ache et al. 2019](https://doi.org/10.1016/j.cub.2019.01.079) models giant-fiber
responses from size/velocity terms; those terms do not themselves calibrate a measured
retinal-column → LC4/LPLC2 spike generator. [Card & Dickinson 2008](https://doi.org/10.1242/jeb.012682)
is the sourced takeoff-speed comparison already recorded in [leads](../leads.md), not an actuator
assignment. The existing [eye](../reference/eye.md), [motor](../embodiment.md) and [GF](../benchmarks.md) results
remain unchanged. These sources and the repository audit supply no newly qualified mapping.

Do not rerun or retune already scored protocols to make these gates green. A new transfer,
actuation model or scientific hypothesis needs cited parameters, an explicit protocol
version and a prospective lock before confirmatory execution. Missing evidence is recorded
as blocked, and existing negative or uninformative results are preserved.
