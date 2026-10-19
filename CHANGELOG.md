# Changelog

## Unreleased

- **DN arena ADR (accepted).** Gianluca Mazza accepted `docs/adr-dn-arena.md` on 2026-10-19. It is a synthetic steering fixture behind `closedloop.Body`, not the sensorimotor plan's VEE-0 take-off. Commands are `yaw` in `rad/s` and `forward` in `m/s`: `arena-2` extends the `ActuatorRef` allow-list and leaves schema `flymsg.embodiment/v2` unchanged. Synthetic `closedloop._commands` already checks the compiled table and does not call `pose.command`. Gains stay in the experiment lock, not in `validation/evidence.yaml`. The null is intact yaw inside the wiring-null seed range; the script control is reported and does not decide. Follow-ups are `arena-1` through `arena-6`, one PR at a time. This commit changes no code. Docs only.

- **CLAIMS (measured, engineered, not claimed).** `docs/claims.md` states, for each part of the closed loop, what is measured from published data already cited here, what is engineered, what stays unmapped and what is not claimed. It restates the body-wiring and DN-arena ADRs, the existing synthetic fixture and the documented bit-identical replay commands. Docs only.

- **G2 landmark placement decided.** The eyemap → head-capsule landmarks will be placed by an algorithm committed with synthetic-volume tests before any volume is processed, with a ±1 voxel / ±10 % threshold sensitivity check against the same 25 µm gate instead of two raters. The measurement is deferred until a head-to-thorax angle source exists. Docs only.

- **SF5 local replication protocol (#151).** Added a source-pinned clean-clone harness with isolated installation caches, compact-input hashes, a held-out read guard and exact archive comparisons. Registered three local reproduction candidates before execution; the harness has not been run. Added synthetic resume parity and checkpoint refusal coverage. Independent-operator replication remains open.

- **Stimulus primitive.** `song.dead_time` moves verbatim to `flymsg.stimulus` (same object re-exported by `song`); giant-fiber looming no longer imports the song experiment. Behaviour, locks and outputs unchanged.

- **Lock codec.** The YAML-subset parser and canonical content hash move from `prereg` to `flymsg.lock_codec`, so `locks` and `manifest` no longer depend on battery policy. Old names stay importable as the same objects; every lock hashes byte-identically.

- **Module boundaries (ADR accepted 2026-10-18).** Added an ADR with logical layers, compatibility invariants and eight staged PR gates, plus a documentation authority catalog. No modules or scientific artifacts moved.

- **Native sparse inputs.** Explicit `input_encoding="sparse"` exports version-3 ordered nonzero kick records; DX12 streams whole-step event blocks under the 512 MiB input budget. Legacy dense exports retain their bytes. New fixture/worker semantics are versioned explicitly.
- **Native per-neuron membranes.** Version-4 fixtures carry Python-precomputed per-neuron float32 membrane constants through the CPU executor and shader, including sparse/graded combinations. Uniform membranes retain the scalar format; Gap-node and continuous-clamp refusals remain. Acceptance adds 48 synthetic cases, with CPU byte-parity, resume and export-size checks. Physical GPU qualification of the new formats remains pending.

- **GPU device removal on Series S (#224).** Test-only `fault.json` triggers `ID3D12Device5::RemoveDevice`; the requalified worker (72/72 parity) fails the job with `0x887A0005`, exits and recovers bit for bit, with and without a checkpoint (`docs/evidence/series-s-gpufault-2026-10-18.json`).

- **GPU device-removal protocol (#224).** Added an inert-by-default test-only `fault.json` control using supported `ID3D12Device5::RemoveDevice`, HRESULT-bearing quarantine errors, a prospective two-case harness and fake-Portal tests. Requires new-binary full GPU parity before measurement; hardware fault/recovery remains unmeasured.

- **Noncooperative termination protocol (#224).** Prospective two-case process-kill harness, fake-Portal tests and Series S result: both cases pass (`docs/evidence/series-s-hardstop-2026-10-18.json`), recovering bit for bit from step 0 and from the last complete checkpoint. GPU fault and gamepad remain open.

- **Measured JO input design (ADR accepted 2026-10-18).** `docs/jo-measured-input-design.md` and `docs/adr-measured-jo-input.md` define protocol 6 source, identity, calibration, causal replay and experimental gates; The owner accepted the ADR on 2026-10-18; implementation waits for a measured source. Six mathematical controls pass 19 assertions. This does not qualify measured input; no runtime or frozen lock changed.

- **Baker anatomical correspondence.** A coordinate-anchored CAVE v783 audit extends complete named MaleCNS type coverage from 2 to 12 of 28 Baker classes, including the still-excluded dimorphic AVLP_pr36. Fourteen remain partial and two absent. All 404 anchors agree with both historical ID lineages and independent annotation supervoxels; 332 have named MaleCNS routes. No response data opened, no benchmark scored, no scientific eligibility claimed. See `docs/baker-crossmatch.md` and the captured evidence.

- **M4 v2 proposal (docs only).** `docs/m4-v2-proposal.md` records prospective eligibility, candidate cross-matches and blockers for #36/S3. No manifest is locked and nothing is scored.

- **Entry protocols.** `docs/issue-resolution.md` states, per blocked front (eye, junctions and modulation, looming, head, muscles, completion), the stimulus, readout, only admissible input and control. No new version is written before its input exists. Docs only.

- **Entry protocol checks.** The frozen v1 benchmark partition has no unused confirmatory case, so M4 needs a new manifest version. The v4 medulla reaches the order of the measured amplitudes, not their shape (roadmap, eye and ledger wording corrected). A post-hoc audit of the archived v4 counts finds a direction bias shared by all four T4 subtypes and no T5 spike; timing is not in the archive. Looming v3 and the APL readout get written prerequisites; both TTMn agree at neuron level; Whitehead et al. 2015 is listed as excluded for G2. Docs only. No lock, seed, or model default changed.

- **Eye-path status.** Embodiment, approximations and the WebXR ADR name G2 geometric projection as implemented coverage. The micro-CT → NeuroMechFly registration has no source, and the projection is not a photoreceptor response. T4/T5 v1 is neither and v2–v4 are robust neither. Docs only. No lock, seed, or model default changed.

- **Sustained console workload (#224).** `scripts/console_sustained.py` records [Series S v1 full-connectome evidence](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/series-s-sustained-2026-10-16.json): two 20,000-step cold/warm setup jobs and four back-to-back 500,000-step jobs each for looming and bitter pass bit for bit against the CPU oracle, with identical outputs per case. Median sustained advance is 2,649 and 3,693 steps/s without throughput decline; transfer, submit latency, peak app memory and GPU engine-0 utilisation are recorded. Attempt 1 failed with HTTP 500 after job files accumulated; protocol revision 2 cleans up verified outputs and records Portal errors. Full-connectome v2, noncooperative termination, GPU fault, gamepad and GPU temperature remain unmeasured; #224 stays open. No lock, seed or model default changed.

- **Exact observer qualification.** Original skeleton/surface preflights and raw ABBA scoring reject missing source-geometry evidence or a changed representation. Desktop and XR frame identities retain source fidelity; transient changes invalidate the observation. Approximate experiments remain diagnostic. No performance gain or headset qualification is claimed.

- **Checkpoint publish record.** `docs/runtime.md`, `docs/milestones.md`, `docs/issue-resolution.md` and `native/README.md` record that a non-growing checkpoint publish is `failed` and is not replaced. The interrupted million-step trial was not rerun and does not meet the exit of #224. Docs only.

- **Checkpoint publish.** A native checkpoint whose temporary file does not grow is recorded as `failed` and is not replaced. A temporary file that grows is replaced and recorded as `completed`. A status that stays `checkpointing` still times out with its last state. The interrupted million-step trial on worker `90249e45` was not rerun. No lock, seed, or model default changed.

- **Milestone baseline.** `docs/milestones.md` records `main` at `f5e3709`. Merged #227 and #230 keep the bounded skeleton renderer diagnostic. The 16 MiB motion campaign is a veto and does not meet the exit of #177 or #24. The unit check still does not meet the #148 exit. Docs only.

- **Milestone baseline.** `docs/milestones.md` records `main` at `1123a63`. Draft #227 is not an accepted result. The unit check in #226 and #228 does not meet the #148 exit. Docs only.

- **SF2 unit check** (#148). `flymsg.units` parses every evidence-registry unit and reads `sim._constants` and `sim.graded_arrays`: time-ratio decays are dimensionless, `gv` keeps `g*gv` a voltage, and the kick `poisson_scale*w_syn` is a voltage. Graded release per step is the count `graded_arrays` returns. No record carries a distribution, so uncertainty is not propagated. No lock, seed, or model default changed.

- **Evidence-gated planning (docs only).** Added `docs/milestones.md` with
  S0–S4 scientific and H1/H2 engineering gates, issue ownership, dependencies,
  entry/exit and blocked/no-go semantics; indexed from the roadmap, the README
  and the Pages nav.
  After #221 merged and #40 closed, remaining Series S adversarial hardware
  acceptance is separately tracked by #224. No model, lock, result or issue
  outcome changed by the documentation PR.

- **Architecture index and the completion list.** The experiments row names `path_metrics`, `identifiability`, `gf_looming`, `apl_claws` and `closedloop_experiment`. The roadmap's second completion step lists runs already read. A graded million-step publish on worker `90249e45` stays interrupted; the collector (#222) names the last state and step. Docs only.

- **Lifecycle collector.** A throughput wait that expires names the worker's last state and step. A package-lineage mismatch stays a finished state whose commit differs from the declared one. No console trial was rerun.

- **Weak-pathway timestep metrics v1** (#148, SF2): latency is not converged. On seeds 5000–5004 the sugar → MN9 first spike moves from 77.4 ms at 0.025 ms to 35.3 ms at 0.1 ms, past the finest seed range of 37.275 ms. Jitter at 0.1 ms stays within range except the silent bitter response, which is indeterminate. Recruitment and rate converge; sugar's recruited count still moves by 119 neurons inside a 274-neuron seed range. Convergence v1 is unchanged. `results/path-metrics/v1.executions/0c616b34…/output/`.

- **Identifiability re-read v1** (#148, SF2): a post-hoc reading of the sensitivity grid, not a new experiment and not a score. Equivalence classes use the default cell's seed range. Looming → DNp01's default cell is alone in its class. pIP10 → dPR1 is undecidable: the seed range covers the grid. All five parameters (`w_syn`, `th_jump`, `sensory_gains`, `membrane`, `release`) stay blocked, with no interval. The ±20% weight factors remain an engineering envelope.

- **Version-2 fixtures on the GPU, qualified** (#39, #215). The DX12 lane runs graded neurons and electrically coupled groups, spikelets included: the groups step in float64 in the CPU's order, and the graded release divides as a correctly rounded float32. On a Series S all 72 acceptance fixtures (12 version 1, 60 version 2) match the CPU oracle bit for bit (`docs/evidence/series-s-gpu-parity-v2-2026-10-16.json`), and the whole-connectome battery still matches in all 30 runs. The host also refuses a graded span whose reciprocal would leave the normal float32 range. Only the dynamic continuous clamp stays refused, as on the C++ executor.

- **Status and the 2026-10-16 literature re-read.** The roadmap, the README and the status lines name the verdicts already recorded in 0.8.48. The literature re-read changed no lock, no scored run, and no model default. Version-2 GPU fixtures (#215) now have the Series S measurement recorded above (#216); the dynamic continuous clamp stays refused. `docs/leads.md` records what was re-read; the four blockers stay.

- **Lighter batch preparation** (#40, #214). A console batch builds its runtimes one at a time and exports each fixture in memory: the whole-connectome battery prepares in 25.2 s instead of 97.6 s, peaking at 2.6 GB instead of 11.3 GB, with byte-identical files.

- **Worker capabilities and batch timing** (#40, #213). The worker lists the batch outputs it writes and refuses others; the console backend stops a job at once on a worker that does not list the output it asked for. The battery's 164 s now break down by phase: 61 s preparing the batch on the host, 10 s uploading, 70 s of advance, 5 s rebuilding runs on the console, 12 s downloading.

- **Sparse counts from the console** (#40, #211). A batch can ask each run for only its nonzero counts and first spikes (`FMS1`, `native.read_counts`), and the console backend does. The whole-connectome battery matched in all 30 runs and took 180 s end to end instead of 243 s; the advance is 69 s, and one host core ran the same battery in 29 s that day (46–62 s on 2026-10-15).

## 0.8.48 — 2026-10-16

### Result

- **Simple baselines v1** (#148, SF2): every positive response of the battery is specific. Against 199 degree-preserving shuffles, no shuffle reaches the measured rate in any of the seven positive responses (p = 0.005, Holm 0.04), and the shuffles' 95th percentile is 0 Hz everywhere. The bitter negative stays silent in both, as named in the lock. The measured wiring also recruits several times more neurons. `results/baselines/v1.executions/f89ed1c3…/output/`.

- **Pulse vs sine song v1** (#36): uninformative, the no-go.
  - **The no-go.** At 100 Hz only 14 of 32 neuropils resolve a sign over the seeds (0.44, below 0.5), so the run stopped before the Pacheco et al. 2021 data were opened.
  - **The model.** It barely tells the songs apart: the median |index| is 0.046, and the resolved neuropils split 7 and 7. This is consistent with the no-go's stated reason (LIF neurons without a band-pass may smooth the 27.8 Hz envelope), which the run does not test.
  - **The run.** 1,045 simulations, including 99 shuffles. `results/song/v1`.
  - **Archive guard.** `results/` now allows 450 kB for its per-cell table.

- **Exact float32 on the console GPU, and a dashboard** (#40, #203).
  - **The divergence.** A 20,000-step full-connectome run differed from the CPU oracle in `g` alone, in 4,329 subnormal conductances that the console flushed to zero, even with `-denorm preserve`.
  - **The fix.** The shader now does every float32 operation on state through double and rounds once, which is correct since 53 ≥ 2·24 + 2. It handles subnormals as bits. 600,000 random operations, subnormals included, match numpy float32 bit for bit offline.
  - **Qualification.** The run is bit for bit at about 2,320 steps/s, and parity, cancel, suspension and resume pass.
  - **The dashboard.** The worker shows a TV dashboard: job state, progress, steps per second, ETA, memory, recent jobs, and the last job's spikes per bin. The gamepad's B cancels through the cancel file.

- **Full connectome on the Series S** (#40, #202): the MaleCNS default model (165,122 neurons,
  24.5 million synapses) runs on the console bit for bit with the CPU oracle
  (`docs/evidence/series-s-full-connectome-2026-10-15.json`, `scripts/console_bench.py`).
  - Event-driven delivery raises its throughput from 28 to about 1,630 steps/s. Inputs move to
    a default heap, spiking neurons set delivery bits, and targets sum their set bits in the
    pull loop's order.
  - The 2,048-neuron fixture rises from about 44,000 to about 70,000 steps/s.
  - Parity holds on the 12 version-1 fixtures, and cancel, suspension and resume pass.
  - `native_acceptance.check` now compares only the traced neurons, not the runtime's
    placeholder column.

- **APL claw contrast v1** (#85): uninformative, the no-go.
  - **APL intact.** The KCs' mean potential sits below rest for both odors (−0.69 and −0.97
    mV), with 30–37% of KCs spiking, so the claws have no positive depolarization to contrast.
  - **APL output removed.** Every KC spikes, and the contrast is clipped to about zero.
  - **Outside the verdict.** The relations hold in 5/5 seeds. They mean little, because
    c_on contrasts two potentials below rest
    (`results/apl-claws/v1.executions/b914035a…/output/`).

- **Series S worker lifecycle** (#40): on a 2,048-neuron synthetic version-1 fixture of
  1,000,000 steps, the worker's lifecycle behaves on the console
  (`docs/evidence/series-s-lifecycle-2026-10-15.json`, `scripts/console_lifecycle.py`):
  - it advances about 44,000 steps/s, timed by the worker, at about 133 MB of app memory;
  - a cancel ends the job in `cancelled`;
  - a Device Portal stop suspends the app with a checkpoint, and after a restart and a resume
    the job completes bit for bit with the CPU oracle.

  Two worker races were found and fixed on the way:
  - a Device Portal read of `status.json` made the atomic status replacement fail, so the
    worker now retries for up to a second and writes progress at most four times a second;
  - a control file still uploading was parsed empty, so it is now read on a later pass.

  `result.json` now records the advance's wall time and steps.

- **Series S GPU parity** (#39, #40): on a Series S in Dev Mode the DX12 lane matches the CPU
  oracle bit for bit on all 12 version-1 acceptance fixtures (adapter `SraKmd_arden`,
  `docs/evidence/series-s-gpu-parity-2026-10-15.json`, `scripts/console_gpu_parity.py`). The
  worker had refused to launch (0x80070002): it is now a minimal XAML application whose
  declared `Flymsg.App` ships `Flymsg.winmd`. Version-2 fixtures on the GPU, the console
  lifecycle, memory and throughput remain.

- **T4/T5 v4** (#140): robust neither. The dark anchor settles, and a 16-fold lamina → medulla
  gain at an LMC rate of 200 Hz brings the graded medulla to about ±10 mV, the order of the
  measured swings, but where T4 fires in thousands it lacks the preferred polarity and
  direction (indices −0.15 to 0.18) and T5 is neither
  in all 12 configurations (`results/t4t5/v4.executions/7a550844…/output/`).
- **Looming → giant fiber timing v1** (#34, G3): uninformative, the no-go. In all 15 gain cells
  and 300 runs the model's giant fiber fires, so no cell stays graded like the recordings and
  none is scored; the recordings were not opened. One disc through LC4 or LPLC2 at the lowest
  gains fires it, early in the expansion (`results/gf_looming/v1`).

- **Looming → giant fiber timing v2** (#34, G3): uninformative.
  - **Model.** With passive giant fibers, all 15 cells respond, stay graded and are scored. α
    is 1.39 to 2.13; ten cells lie inside the stimulus-follower band (1.73 to 2.01), so the
    passive giant fiber peaks as its drive does.
  - **Data.** The ten control flies give a median α of 3.32. Three flies sit at the onset slope,
    so the flies' interval (2.95 to 12.58) holds the onset slope 11.43, and the timing cannot
    separate the circuit from a stimulus-locked peak.
  - **Outside the verdict.** The model's α lies below the flies' interval in every cell
    (`results/gf_looming/v2`).

### Validation

- **APL claw contrast lock** (#85): `validation/apl_claws.yaml` v1, `flymsg apl-claws [--run]`,
  evidence record `apl_claw_odor_contrast`.
  - **Design.** Arms `on` (default) and `off` (every APL synapse removed), driven by the KC
    sparseness locks' DoOR odors, seeds 420–424. Per seed, the OCT/MCH contrast of the KCs'
    mean depolarization in each arm against the ALPNs' spike contrast in arm on; scored on the
    seed medians: pass if blocking APL raises the claw contrast and brings it nearer the
    boutons', partial if it only raises it, fail if it does not raise it, uninformative if
    the PNs carry no positive contrast.
  - **Status.** Scored, locked before any run. No run yet.

- **Simple baselines lock** (#148, SF2): `validation/baselines.yaml` v1, `flymsg baselines
[--run]`.
  - **Design.** The battery's eight responses run on the measured connectome and on 199
    degree-preserving shuffles (seeds 4000–4198), seeds 0–4. Per response, an empirical p in
    the locked tail, Holm-corrected, decides whether the response needs the measured
    partners.
  - **Status.** A report, not a score. No run yet.
  - **Fix.** The timestep convergence entry of 0.8.47 and `docs/validation.md` counted ten
    battery responses; the battery has eight.

- **Looming → giant fiber timing v2 lock** (#34, G3): `validation/gf_looming.yaml` v2. Version
  1's model fired the giant fiber in every cell, and a model-only probe found it firing at gains
  4 to 32 times lower; v2 makes the two giant fibers passive (threshold out of reach) so their
  potential integrates the drive as a graded recording. Everything else is v1's; seeds 350–354.
  No run.

- **Pulse vs sine song lock** (#36, first held-out benchmark of M4): `validation/song.yaml` v1,
  `flymsg song [--run]`.
  - Johnston's organ JO-A, JO-B and JO-D get the same number of kicks in a pulse train
    (16/20 ms, Pacheco et al. 2021), a sine and an aperiodic train. Per neuropil, the
    synapse-weighted activity gives a pulse/sine preference sign.
  - Scored against the paper's per-fly response magnitudes in 16 male flies, with balanced
    accuracy against permuted signs and 99 degree-preserving shuffles. A model-only no-go runs
    before the data are read.
  - Secondary weighting by Yamakoshi et al. 2025's JO-A/JO-B ratio, reported only.
  - Four evidence records. Locked before any response value was read. No run.

- **Looming → giant fiber timing lock** (#34, G3): `validation/gf_looming.yaml` v1,
  `flymsg gf-looming [--run]`.
  - LC4 driven by the disc's angular velocity and LPLC2 by its size (engineered forms, gains
    scanned on a 4 × 4 grid). The model's DNp01 peak time before collision is fitted as
    α · r/v − δ, against the same fit of Dombrovski et al. 2025's giant-fiber recordings
    (Zenodo, CC BY 4.0) at r/v 10–80 ms.
  - Timing only, never amplitude; only cells where both model giant fibers stay graded are
    scored, and a fly interval overlapping the slopes of stimulus followers makes the run uninformative. A
    model-only no-go runs first. Two evidence records. Locked before the files are downloaded,
    except what an agent had opened during the search (recorded). No run.

### Engineering

- **Batch jobs and the console as a backend** (#40).
  - **Batch format.** Several runs of one network travel as one base fixture and exact per-run patches (`native.export_batch`), so the network is uploaded once.
  - **Worker.** It runs them in order, keeps each run's output and resumes after the last completed one.
  - **Library.** `flymsg.console` turns `sim.run` calls into such a batch on the Series S, and the decoded results are `sim.run`'s, bit for bit.
  - **Baselines.** `flymsg baselines --backend console` runs each graph's battery that way, and `--backend hybrid` adds the console to the CPU workers on one queue (`parallel.imap_shared`). `sensitivity.measure` accepts results from any backend.
  - **Export cost.** The network's edge order is computed once per batch.
  - **Memory.** Batches export one run at a time, and outputs are decoded on demand.
  - **Qualification.** One graph's battery on the whole connectome, 30 runs, matches `sim.run` on the console in every run.
  - **Cost.** The console's advance (70 s) is about one host core's (46–62 s). End to end, returning whole states makes a batch take 243 s, so the SF2 run stayed on the CPU (`docs/evidence/series-s-battery-2026-10-15.json`).

- **The 3D viewer on an Xbox.**
  - **TV layout.** It is on by default in a console's browser, or with `?tv=1`: larger text in the title-safe area, the panel closed, and controller hints.
  - **Controller.** A game controller drives the view (`gamepad.js`, standard mapping): the sticks and triggers rotate and zoom, A plays or pauses, LB and RB step a bin, Y resets the view, X clears the selection, and View opens or closes the panel.
  - **From the worker.** The worker opens the viewer with Y, or when the host uploads `open_viewer.json`, at the address in `LocalState/viewer.json`.
  - **Not on a Series S.** Edge there has no WebGL, so the page loads but draws nothing. The TV layout also starts leaner (1 M triangles), because the console's tab was stopped for memory at the desktop defaults.
  - **Native replays.** `flymsg viz --native` now takes the stimulus from the fixture's own input.

- **Viewer replays native and console runs**: `flymsg viz --native OUTPUT FIXTURE` turns a
  native `output.bin` into the viewer's replay (`native.as_result`, `native.stimulated`), so a
  run computed on the Series S can be watched in the browser.

- **B6 v2 pose contract** (G1, #178): `flymsg.pose` (`flymsg.embodiment/v2`) types world,
  body, eye and eye-map frames in SI units with (w, x, y, z) quaternions, a body state with
  velocities, eye mounts read from FlyGym 2.1.0, a no-future-pose clock lookup, actuators by
  compiled MuJoCo id that still refuse through the motor map, and a canonical JSON trace. No
  body is wired; M0 v1 is unchanged. FlyGym's default `fusestatic` compile moves both eye
  cameras of a simulated fly 0.44 mm to the thorax origin; the mounts are read without it.
- **Geometric optics onto measured columns** (G2, #179): `flymsg.optics` turns dark spheres and
  a B6 v2 pose into per-column angle, angular radius and its rate, angular velocity relative
  to the eye, acceptance coverage and the first sphere on each axis; no photoreceptor gain, no
  viewer. The micro-CT → NeuroMechFly head registration is unmeasured, so the real eye needs a
  sourced `Registration` first. The planar Rice coverage is within 0.0076 of the spherical
  integral at 8.23° acceptance.
- **Body-wiring ADR and G5 groundwork** (#178, #180): `docs/adr-body-wiring.md` (accepted)
  fixes one clock and one causal order for a 3D body through B6 v2.
  - `flymsg.closedloop` implements it without a body: the schedule, a per-component evidence
    gate, intact/disconnected/shuffled/replay/silenced arms, replay parity and a
    `flymsg.closedloop/v1` record.
  - A biological run refuses unless registration, transducer, motor map and body are all
    measured; none is today. Tested on a toy circuit and body only.
- **G5 adapters and checkpoints** (#180): `closedloop.optical` turns `optics.sample` into the
  per-column stimulus; `flymsg.flygym_body` puts NeuroMechFly behind the closed-loop body
  adapter (SI units at the boundary, contacts per fly body); runs checkpoint and resume, and
  a resumed run equals the uninterrupted one, also on NeuroMechFly. Synthetic only.
  `optics.config_sha256` is public. Architecture note aligned (modules, solved pain points,
  B6).

### Documentation

- **Leads for the sensorimotor gates** (#179, #34, #19, #35): no published head-to-thorax
  registration for the micro-CT eye map; no deposited LC4/LPLC2 firing rates, but the giant
  fiber's looming responses at four r/v values are on Zenodo (CC BY 4.0, Dombrovski et al.
  2025), so a giant-fiber-scored transducer no longer waits for a data request (disc sizes and sex still to be read; not an LC4/LPLC2 rate); no source names a
  motor neuron or muscle with a FlyBody actuator, and FlyGym 2.1.0 ships a front-leg muscle
  model.

## 0.8.47 — 2026-10-14

### Result

- **Timestep convergence v1: converged** (SF2, #148). All ten battery responses converge at the
  default 0.1 ms against 0.025 ms: same holds verdicts, seed-median rates within the finest
  seed range (giant fiber → TTMn exactly at it). First-spike latencies and recruitment of weak
  pathways move with the step (TTMn under giant fiber output 35 → 82 ms, sugar-recruited
  neurons 439 → 155) and do not decide. Run from the lock commit `7c4d34d` in one attempt.

### Validation

- **T4/T5 v4 lock** (#140): each graded medulla neuron's measured range anchored at its own
  settled dark potential (six passes), a lamina → medulla gain scanned over 1, 4, 16 at LMC and
  medulla rates of 50 and 200 Hz (12 configurations, seed 98), and Behnia et al. 2014's delays
  (Mi1 18 ms after Tm3, Tm1 13 ms after Tm2) set through the synaptic time constant at
  unchanged steady gain. Evidence record `medulla_filter_delays`. Decides on T4 as v3. No run.
- **Timestep convergence lock** (SF2, #148): `validation/convergence.yaml` v1 runs the six
  sensitivity cases at dt 0.1, 0.05 and 0.025 ms (seeds 0–4) and judges a response
  converged when its holds verdict matches the finest step and its seed median lies within
  the finest seed range; `flymsg convergence [--run]`. A numerical lock may declare
  `evidence: none` with a reason. No run.

### Engineering

- **Faster per-neuron membranes**: with a `sim.Membrane` on a minority of neurons the kernel
  keeps its scalar loops and recomputes only those neurons with their own constants, the same
  float32 operations, so results are bit-identical (oracle tests for a minority and a majority;
  on the whole CNS with Mi1 and Tm1 membranes, identical spikes in 5.3 s against 7.2 s).

### Viewer

- **Optional WebXR observer** (`?xr=1`, experimental): an Enter VR button where the browser
  supports `immersive-vr`; the session shows the existing replay in stereo, scaled to about
  1.2 m, without bloom or MSAA, and its end restores the scene, the desktop camera and the
  controls. Installed after the first frame; no selection in XR. Unqualified on any headset
  (#177); the decision is `docs/adr-virtual-experimental-environment.md`.
- **Graded neurons in the 3D replay**: `flymsg viz --eye POLARITY DIRECTION [--eye-config N]
[--eye-top N]` replays one edge of the locked T4/T5 protocol and writes `graded.bin`, each
  non-spiking neuron's potential per bin relative to rest (or its dark anchor); the page lets
  them glow by potential, in their colour when depolarized and violet when hyperpolarized. The
  site gains the `eye-on` scene (right eye, ON edge, v4 configuration 11).

### Documentation

- **Sensorimotor environment plan** (#176): `docs/sensorimotor-environment-plan.md` sets
  three grades (VEE-0 geometry, VEE-1 biological interfaces, VEE-2 held-out prediction), gates
  G0–G7 linked to their issues, a reuse inventory and no-go rules, subordinate to the roadmap's
  completion plan. A plan, not a result.
- **Replication package** (SF5, #151): `docs/replication.md` tells an outside operator how to
  rerun any archived result and what a match shows (parity, not validation), with the data
  sources and licences and a claims audit by the scientific-fidelity taxonomy (no result is a
  discovery). `scripts/replication_index.py` writes `docs/evidence/replication-index.json`:
  per archived result its command, source commit, lock version and hash, input and output
  sha256, seeds and verdict; the tests check it against the archive and every lock hash
  against the registered versions. Four historical results ran from a modified tree and are
  marked. The synapse weight rule v1, rerun here from its commit, gives byte-identical tables.
- **Post-review alignment** (#184): provenance rows for every feature of this release, docs
  aligned with the latest merges, and the viewer-bundle contract test covers `graded.bin`.

## 0.8.46 — 2026-10-14

### Result

- **Kenyon cell sparseness v8: within, only with the variant set; v7 replicates** (#85, #95,
  #155). Under the exact continuous clamp (Taylor action) with seeds 95–97, 8 of 10
  lLN2T+lLN1_bc arms are within (2.0–2.3% / 1.4–1.7% of Kenyon cells); the two E arms out miss
  the 64.6% overlap bound at 65–66%, where v7 lost one. lLN2T alone is not within (16–23% of
  Kenyon cells, 80–96% shared). Every arm is within 19 cells of its v7 count and coupling moves
  none by more than 21. Run from the lock commit `ad7b71e` in one attempt (35 min).
- **T4/T5 v3: robust: neither** (#140, #84). With Mi1, Tm3, Mi4, Mi9 and C3 graded over the in
  vivo voltages of Groschner et al. 2022, no T4 neuron spikes in any of 25 configurations. The
  edge reaches the medulla at ≤1.4 mV (at most about 5% of the measured swings), with the
  measured sign only in Tm3, C3 and Mi9; tonic lamina release holds Mi1 below its release
  threshold from an LMC rate of 100 Hz. Run from the lock commit `406f622` in one attempt. The
  archive guard rises to 250 kB for its 202 kB of required tables.
- **Kenyon cell sparseness v7: within, only with the variant set** (#95, #85). With
  lLN2T+lLN1_bc (43 neurons) as eLNs, 9 of 10 arms are sparse and distinct: 2.0–2.2% /
  1.5–1.7% of Kenyon cells, 43–65% shared (one arm misses by 0.5 points of overlap). With
  lLN2T alone, the set Eckstein et al. 2024 liken to the eLNs, Kenyon cells stay dense
  (16–23% / 14–19%, 79–96% shared). Coupled arms match their uncoupled bases within 17
  cells: removing the chemical cholinergic contacts onto PNs separates the sets, not the
  electrical coupling. Run from the lock commit `45c0641`; the unread v6 step store was lost
  with its worktree.

- **Synapse weight rule v1: undecided** (#139). On Liu et al. 2022's 57 PN → LHN pairs of
  six matched LHN types, density (count over mesh area) ranks the measured amplitudes
  barely better than count (Spearman 0.581 against 0.567; Δρ interval −0.011 to +0.054);
  count stays the rule. MaleCNS counts rank the female amplitudes at ρ 0.81 on the 13 nonzero
  pairs.

### Validation

- **Kenyon cell sparseness v8 lock** (#85, #95, #155): version 7 under the continuous clamp
  by the Taylor action (`flymsg.gap/continuous-clamp-taylor-v1`) instead of the boundary
  reset, seeds 95–97; arms, bounds and decision unchanged. First lock with `yaml_subset: 2`
  and evidence records. No run.
- **Evidence records** (SF1, #147): `validation/evidence.yaml` and `flymsg.evidence` record
  source, locator, organism, cell mapping, unit, uncertainty, status and transformation for
  each sourced quantity, fail closed on missing fields, and require every new lock
  (`yaml_subset: 2`) to name its records. Six records (seven with `medulla_filter_delays`, added with T4/T5 v4) cover the Kenyon cell coupling,
  spike, sparseness and overlap values (`kc_odor_overlap` added with the v8 lock) and the T4/T5 v3 medulla voltages; unstated fields (license,
  sex) are recorded as unknown. `scripts/evidence_audit.py` prints the audit.

- **Kenyon cell sparseness v7 lock** (#85, #95): v6 with the boundary reset of v5. The v6 run
  was stopped after its uncoupled arms (never read, later lost with its worktree): under the continuous clamp each new
  refractory mask of the 688-cell coupled component costs a dense exponential of ~1–1.6 s
  (#155). On 50 ms of arm E/lLN2T (seed 0) the two modes give identical spikes for every
  neuron (`scripts/qualify_boundary_reset.py`, `docs/evidence/`). Seeds 92–94. No run.
- **T4/T5 v3 lock** (#140): T4's medulla inputs Mi1, Tm3, Mi4, Mi9 and C3 become graded over
  the potentials Groschner et al. 2022 recorded in vivo (Edmond, CC BY 4.0, fetched by
  sha256 by `flymsg.medulla`); the LMC and medulla release rates are scanned (25
  configurations, seed 94) and the verdict is on the four T4 subtypes, since T5's inputs have
  no measured voltage in mV. No run.
- **Kenyon cell sparseness v6 lock** (#85, #95): the eLNs are the types Eckstein et al. 2024
  liken to the cholinergic krasavietz LNs (lLN2T_a/b/c, 13 neurons; with lLN1_bc as a
  variant set), not the whole cholinergic ALLN class; every other cholinergic local neuron
  stays chemical. Arms E, F and the eight coupled arms run once per set (16 coupled arms), seeds 89–91. No run.
- **Synapse weight rule lock** (#139): `validation/weight_rule.yaml` v1 compares count
  against density (count over the postsynaptic mesh area) on Liu et al. 2022's measured
  PN → LHN unitary EPSPs: 57 pairs of the six LHN types MaleCNS matches exactly, Spearman
  per rule, paired bootstrap interval of the difference. `flymsg weight-rule --areas`
  measures the meshes before `--run`. No count or area was computed before the lock.

### Engineering

- **Taylor solver for the continuous clamp** (#155): `Gap(solver="taylor")`,
  `flymsg.gap/continuous-clamp-taylor-v1`, applies the clamped step's exponential to the
  state as a truncated Taylor series whose remainder is bounded by the float64 unit
  roundoff, instead of building a dense map per refractory mask. On the Kenyon cell
  couplings (688 and 726 cells) it gives the dense solver's spikes neuron for neuron in
  3.6–4.9 s against 1,412–1,655 s per 50 ms; a 1,000 ms odor takes 14.7 s. Decided in the
  [electrical ADR](docs/adr-gap-refractory.md), accepted 2026-10-14; new locks may name it.

- **Lock parser, subset 2** (#159): the lock parser cut ` #` inside quoted strings and read
  a quoted list item holding `:` as a one-key map. A lock with the top-level line
  `yaml_subset: 2` is parsed quote-aware (no escapes; a list item that opens a quote must be
  one quoted string); the seven registered locks the old parse misreads keep it, since their
  hashes were taken on it, and a test refuses any other lock, or new version of those seven,
  that depends on it. In `silence_scan.yaml` v3 the hash covers `replication.on_failure`
  only up to "issue"; the full clause is in git at the lock commit.

- **Mesh areas skip empty fragments** (#139): `scripts/mesh_area.mjs` failed on a neuron
  whose full-resolution mesh has an empty fragment (bodyId 517804); it now skips them as the
  viewer does, and `flymsg weight-rule --areas` reports Node's error instead of an exit code.

### Body

- **Neuron-level MANC matches recorded, not used** (#19): `flymsg muscles` adds each
  neuron's own MANC match type and whether it agrees with its type (140 of 623 disagree,
  107 with another target); the muscle stays the type's.

### Viewer

- **Baseline of the live scenes** (#24): five runs of six of the live pages (the gallery scenes
  and the heaviest comparisons) on one laptop GPU, their ranges in `docs/viz.md` and the runs
  in `docs/evidence/viewer-bench-2026-10-13/`. `scripts/bench_viewer.py` judges a pass by the
  CPU other processes used during it (not the load its own browser makes) and waits
  (`--cooldown`) for an idle machine; `scripts/bench_check.py` compares a new run with the
  baseline ranges.

### Documentation

- **Drift audit** (#166): every page checked against code, locks, results and issue states;
  README, roadmap, model, approximations, leads, runtime, architecture, provenance and others
  aligned. The runtime ADR is accepted (#167): R0 and the native CPU executor are done, GPU
  parity and the console stay open.

## 0.8.45 — 2026-10-13

### Result

- **T4/T5 through the eye v2: robust: neither** (#84, #97). With graded photoreceptors and
  L1–L3 over 17 configurations of the measured voltage ranges, no T4 or T5 neuron spikes.
  Contrast crosses the lamina (L1–L3 hyperpolarize by 14–33 mV under light) and stops in the
  medulla: Mi1, Tm3 and Mi4 never fire, the OFF inputs only at LMC release rates of
  200–400 Hz. Run from the lock commit `17173c2`, resumed once from saved configurations.
- **Kenyon cell sparseness v5: none** (#95, #85). With the measured asymmetric eLN ↔ PN
  coupling, sister PNs at 0.013 and eLN spikes crossing as 40 mV spikelets of 0–2 ms, every
  coupled arm stays silent (0.22–0.30% of Kenyon cells, floor 1%), as without coupling, and
  the spikelet duration does not change it. At the measured coefficients the coupling is not
  the missing excitation. Run from the lock commit `00aff9c`, resumed once from saved arms.

- **Kenyon cell sparseness v4: none** (#95, #85). With the cholinergic local neuron → PN
  contacts as electrical synapses (coupling 0–1, sister PNs at Kazama & Wilson's 0.013), no
  arm is sparse: Kenyon cells stay at ≤ 0.3% and fall silent as coupling grows. Coupling
  that passes only subthreshold potentials drains active PNs. The fly's lateral excitation
  rides on eLN spikes (spikelets). This run carried none: its lock set no spike term, and a
  LIF reset draws no waveform.

### Model

- **Per-neuron membranes** (`sim.Membrane`): listed neurons get their own membrane and
  synaptic time constants, rest and threshold, stated by a lock with no defaults. Without one
  the spikes are unchanged bit for bit; the kernel, the oracle and `CpuRuntime` agree with
  one; coupled neurons and the native executor refuse it. Contract B2 gains `membrane`.
  Measured cost of the uniform path: about 5% per step on the whole CNS.
- **Weight rules beyond count** (`sim.weight_matrix(post_scale=...)`, `sim.density_scale`):
  a lock can scale every weight onto a neuron, e.g. by synapse density (Liu et al. 2022);
  without it the weights are unchanged. `scripts/mesh_area.mjs` measures a neuron's surface
  area from its published mesh at full resolution with the viewer's readers.
- **Spikelets and asymmetric junctions** (#85): `sim.Gap` takes a coupling per side of a
  junction and, with `spike_mv` and `spike_ms`, lets a spike cross as a rectangular term
  integrated exactly with the rest (third Van Loan block); CPU, NumPy reference, runtime
  checkpoints and the native executor agree bit for bit (60 native acceptance cases).
- **Native executor with graded neurons and electrical synapses**: fixture version 2 carries
  both; the C++ executor matches the CPU runtime bit for bit, checkpoints included (60
  acceptance cases); corrupt extensions are rejected; the DX12 lane refuses version 2 until
  hardware qualifies it (#39).
- **Exact electrical coupling**: each connected group of electrically coupled neurons is
  integrated exactly over a step (matrix exponential, Van Loan's block form for the synaptic
  input) instead of by an explicit first-order step.
- **Resumable long runs**: `t4t5 --run` and `kc-sparseness --run` print measured progress
  and ETA, store each finished configuration or arm under the run directory bound to the
  lock's hash, resume an interrupted run, and record the resumed steps in the manifest.
- **Electrical synapses** (#85): `sim.Gap` couples pairs of neurons through their
  potentials (junction over leak conductance; a coupling coefficient c gives c / (1 − c)).
  Bit-identical without them; exact parity of kernel, NumPy reference and `CpuRuntime`.
- **Graded neurons** (#97): `sim.Graded` makes chosen neurons non-spiking, with a
  threshold-linear release curve stated by the caller (no defaults). Bit-identical without
  them; exact parity of kernel, NumPy reference and `CpuRuntime` with them. `Result.graded_v` holds their mean potential per bin.

### Validation

- **Kenyon cell sparseness v5 lock** (#95, #85): measured, asymmetric eLN ↔ PN coupling
  (Yaksi & Wilson 2010 Fig. 4C/4F) and sister-PN coupling (Kazama & Wilson 2009), with eLN
  spikes crossing as 40 mV spikelets of 0, 0.5, 1 or 2 ms (unmeasured, scanned).
- **Kenyon cell sparseness v4 lock** (#95, #85): the cholinergic local neuron → PN contacts
  as electrical synapses, scanned from 0 to 1, with sister PNs at the measured coefficient
  (Kazama & Wilson 2009); the least coupling that makes the code sparse is reported as a
  prediction.
- **T4/T5 v2 lock** (#84, #97): graded photoreceptors and L1–L3, release scanned over 17
  configurations within the voltage ranges measured in Drosophila (no release curve is
  measured there); verdict `robust` only if every configuration agrees.

### Body

- **Neuron → muscle from MANC** (motor map Phase C): `flymsg muscles` fetches MANC's
  Supplementary file 3 (Cheong et al. 2024, eLife 13:RP96084, CC BY 4.0, sha256 pinned) and
  gives 406 of 708 MaleCNS motor neurons (49 types) the muscle MANC published, with its match
  certainty where one exists (76 neurons). 270 neurons get a body part only, 17 sit in merged
  types, 6 have no target and 9 no type. The table is derived data under `data/motor/`; the
  motor map lock is unchanged and `motor_map.command` still refuses.
- **Closed loop** (#90): `jump3d.closed_loop` runs the connectome (incremental runtime) and
  NeuroMechFly in 1 ms blocks at the 0.1 ms neural step and cuts the looming input at the
  first boundary after takeoff; before the cut the spikes equal the open-loop run (tested).

### Viewer

- **Legend and caption.** A caption under the clock names the scene's input (types, rate,
  window, silenced types, seed) from its manifest, or an anatomy scene's types. By group the
  legend gives each group's neuron count and largest instances (`stimulus (55): LC4_R ×55`);
  it also explains the glow and lists the soma regions while that layer is shown. Fixed: in
  a comparison's difference view the legend showed the group colours instead of the
  difference classes the neurons were drawn with.
- **Phones and tablets.** Up to 600 px wide the control panel starts closed and the
  performance readout is hidden; the site's page links scroll in one row. Touch screens get
  touch hints, a 12 px tap slop, the clear button instead of Esc and 44 px buttons; panels
  respect safe-area insets. `prefers-reduced-motion` opens a replay paused. A lost WebGL
  context is restored behind a notice, and time spent in a background tab does not advance
  the replay. Checked in an emulated 390×844 viewport; real-phone frame rates
  remain #24.

### Documentation

- **Approximations and leads.** `docs/approximations.md` lists every simplification of the
  model with its status (measured, scanned, selected, compensation, blocked) and what would
  remove it; `docs/leads.md` collects the 2026-10-13 literature and data search by the
  approximation each source could lift, each row marked as checked on data, in full text or
  from the abstract.
- **One status index.** The roadmap holds the verdict table, and the README points at it.
  Validation's dated notes moved under a status log. The eye and the T4/T5 locks moved out
  of the embodiment note into `docs/eye.md`. Provenance records the mechanisms added on
  2026-10-13. Present-tense sentences describe the default model; a dated sentence stays
  under its date.
- **Present tense matches spikelets.** A spike crosses `sim.Gap` only when a lock sets
  `spike_mv` and `spike_ms`. Provenance cites `936000d`. Kenyon cell v4 stays the
  subthreshold result; version 5 is locked and has no run.
- **Gallery frames and two figures.** The stills are reshot with the neuropil shells, the
  soma layer, and `?chrome=0`: the control panel is not built, the performance readout is
  hidden, and the colour legend stays. `docs/img/looming-vs-dnp01.png` shows the failed
  DNp01 silence check. Kenyon cell sparseness v1–v4 and the NeuroMechFly jump v1 range
  have figures (`kc-sparseness.svg`, `jump-range.svg`).

### Engineering

- **The command line is a package.** `cli.py` (2,158 lines) is split into
  `flymsg/cli/` modules by area, with `flymsg.cli:main` as the entry point; every command,
  flag, default, help text, printed line and written file is unchanged (architecture step 6).

## 0.8.44 — 2026-10-13

### Result

- **NeuroMechFly jump v1: short** (#90, #94). LC4 on both sides drives `TTMn_R` before
  `TTMn_L`; the body takes off at 28–32 ms but at 0.05 m/s, a range of 0.3–0.5 mm against
  Zumstein et al.'s 28.6–37.75 mm. One leg, one twitch and no TLM are not a jump.

### Body

- **TTM actuator and a NeuroMechFly jump** (#90, #94): `flymsg.ttm` (measured twitch: 101 µN,
  8.2 ms, 0.85 ms delay) and `flymsg.jump3d` (FlyGym v2.1.0, now a dependency: TTM torque on
  the mesothoracic coxa-trochanter hinges, posture held, 0.1 ms steps). Lock
  `validation/jump3d.yaml`: LC4 on both sides → TTMn spikes → jump range against Zumstein et
  al.'s wingless 28.6–37.75 mm; `flymsg jump3d`.

## 0.8.43 — 2026-10-13

### Result

- **T4/T5 v1: neither** (#84). Photoreceptors fire through the measured eye, but L1–L3 and
  everything downstream stay silent: inhibitory photoreceptor synapses cannot move silent
  spiking lamina neurons, where the fly's are graded with a resting tone. The concrete case
  for graded neurons (#97).

- **Kenyon cell sparseness v3: none** (#95, #96). With Hige et al. 2015's odors as DoOR
  vectors the model is either dense (default 36% / 30% of Kenyon cells, 82–99% shared, against
  30–33% measured) or silent (0.2% without the chemical local neuron → PN contacts). The
  sparse regime needs the measured electrical coupling the model lacks (#85).

### Pre-registration

- **T4/T5 direction selectivity v1** (#84): moving ON/OFF edges in four directions through
  the measured eye (`eye.edge_coverage`), 30°/s, acceptance 8.23°; decides polarity and
  preferred direction against Maisak et al. 2013, prior from Lappalainen et al. 2024 stated.
  Locked before its run; `flymsg t4t5`.

- **Kenyon cell sparseness diagnostic v3** (#95, #96): Hige et al. 2015's odors (3-octanol,
  4-methylcyclohexanol) as DoOR receptor vectors, the same four arms, seeds 80–82, and a
  lower bound (1%) next to the upper ones; the shared share is reported against the 30% and
  33% measured for these odors. Locked before its run.

### Odors

- **`flymsg odor`** (#96): DoOR consensus responses (fetched at run time, CC BY-SA 4.0, not
  redistributed) as one response per MaleCNS ORN type, and per-neuron Poisson input
  (`odors.kicks`). 3-octanol drives 31 ORN types, 4-methylcyclohexanol 22.

## 0.8.42 — 2026-10-13

### Result

- **Partner follow-up v1** (#76): the left mirror `replicates` (DNp02 p 0.001, DNp06 p 0.003),
  and the direct drive gives `single_sufficient: DNp06_R`: at 200 Hz DNp06_R alone brings
  `TTMn_R` to the jump bit (3–6 spikes), DNp02_R alone does not (0), the pair gives 8–11
  against a matched null mean of 0.013 (p 0.001). Conjunction rejected; figure
  `partner-followup.svg`; outputs with every null draw in `results/partner-followup/v1/`.
- **Kenyon cell sparseness v2: within E, F, by undershoot** (#95). Without the cholinergic
  local neuron → PN chemical contacts (electrical in the fly) one ORN type drives 4.5% of the
  PNs instead of 73%, and the Kenyon cells fall to 0.2% (measured 6 ± 5%): the overlap was an
  antennal-lobe artefact, and single-receptor stimuli no longer reach the Kenyon cells. The
  lock had no lower bound; stated. Next: odors as receptor vectors (#96).
- **Kenyon cell sparseness v1: not_recurrence** (#95). KC → KC without fast effect lowers
  the responding Kenyon cells from 25% to 17.4% (bound 17%), but the two odors still share
  95%; APL removal recruits all. The overlap is upstream of the Kenyon cells.
- **KC → MBON11 depression v1: inconsistent** (#85). The measured rule silences MBON11 for
  both odors (272–286 → 0 spikes, seeds 50–52): each odor recruits about 1,000 Kenyon cells
  and the two share 95%, against 30–33% in the fly. The model's Kenyon cell code is not
  sparse, the same limit as the held-out ORN_DM1 failure. Nothing is retuned.

### Documentation

- **Realism plan** in `docs/roadmap.md`: five steps (eye, Kenyon cell sparseness, odors as
  receptor vectors, body and TTM actuator, non-spiking neurons), each with its evidence and an
  independent test; tracked in #84, #95, #96, #90, #94, #97.
- **`docs/roadmap.md`** (on the site as Roadmap): what of the brain the model uses and leaves
  out, in numbers from `scripts/brain_coverage.py` (signs, the FlyWire cross-check of the
  unsigned neurons, somata, photoreceptor columns), and every open item with what blocks it
  and what would unblock it. New issues #84 (eye encoder) and #85 (electrical synapses and
  neuromodulation, evidence audit).

### Eye

- **Graded photoreceptor input:** `eye.photoreceptor_kicks` (gain × light left per column, in
  units of the Poisson kick). `sim.run` already accepted real-valued `kicks`; it is now
  documented and tested (integer values as floats reproduce the Poisson run spike for spike).
  `CpuRuntime` and the native executor still take integer counts only.
- **Looming per column:** `eye.looming_radius_deg` (constant-speed approach, von Reyn et al. 2014) and `eye.disk_coverage` (share of each column's Gaussian acceptance profile covered
  by a dark disk, exact in the small-angle limit). The acceptance angle is an argument for
  the lock to source, not a default.
- **`flymsg eye`** (#84): every MaleCNS optic-lobe column gets a measured viewing direction
  from the Zhao et al. 2025 eye map (fetched at run time, GPL-3.0, not redistributed) through
  the published hex convention; nothing is fitted. 843 of 892 right and 835 of 875 left
  columns have one. Photoreceptors are assigned to columns by their strongest output; the
  dorsal-rim R7d/R8d land at a median elevation of 67.7° against 3.7° for the other R7/R8.
  New dependency `rdata` (MIT) to read the R files.

### 3D view

- **Whole-CNS layer:** every soma in the volume (140,024 of 165,122 neurons) drawn as a point
  coloured by region around the scene's neurons, from `somaLocation` in the MaleCNS
  annotations (`scripts/build_somata.py`, `docs/live/cns/`). Context only; `?somata=0` hides
  it. Sensory neurons, whose somata are in the periphery, are counted, not drawn.

### Tooling

- **GitHub templates:** a pre-registered experiment issue form (question, sources,
  protocol and verdicts, what was seen before the lock, compensations), a bug form, and a PR
  checklist with the project's rules. Labels `preregistration`, `result`, `architecture`,
  `embodiment`.
- **`scripts/bench_viewer.py`** (#24): builds the site, opens each scene with `?bench=` in a
  fresh browser profile and appends the summary, the GL backend and the load average to
  `runs/viewer-bench/`. It refuses to start above a 1-minute load of 1.0, so a baseline is
  taken only on an idle machine, and a timed-out page no longer leaves its browser running.

### Live scenes

- **Every scene re-exported from `main`** (`8f2a076`): the manifests of the scenes made before
  the rule pointed at branch commits that squash merges dropped; now all record a commit on
  `main`. Activity is unchanged byte for byte.
- **Left eye and both eyes on the site:** `looming-left` (`LC4_L`), `looming-bilateral`
  (`LC4`) and the `right-vs-left` comparison, exported from `main`. Seed 0: `TTMn_R` 22
  spikes with the right eye, `TTMn_L` 12 with the left, 24 and 12 with both. `docs/viz.md`
  states the side convention. `build_live_scenes.py NAME ...` rebuilds only those scenes.

### Pre-registration

- **Kenyon cell sparseness diagnostic v2** (#95): after v1, an antennal-lobe arm. Cholinergic
  local neuron → PN contacts are electrical in the fly (Yaksi & Wilson 2010) and fast chemical
  in the model; v2 removes them (arm E), alone and with KC → KC (arm F), on fresh seeds 70–72,
  same measured bounds. Locked before its run.
- **Kenyon cell sparseness diagnostic v1** (#95): four weight matrices (default; KC → KC
  without fast effect, since these synapses act through the metabotropic mAChR-B, Manoim et
  al. 2022; APL → KC removed; both) compared on the share of Kenyon cells responding to an
  odor (measured 6 ± 5%, ≤ 17%) and the share shared between two odors (≤ 64.6%). Locked
  before any run; `flymsg kc-sparseness`.
- **Dopamine-gated depression at KC → MBON11, v1** (#85): the one plasticity measured on an
  identified synapse (Hige et al. 2015: −90% charge, forward pairing only, ≥ 40 min) as an
  optional rule applied between trials to the weight matrix; the kernel and the defaults are
  unchanged. Seven compensations named; the test asks whether the paired odor's MBON11
  response drops ≥ 49.8% and the unpaired ≤ 64.6%. `flymsg mb-plasticity`.
- **Residual partner follow-up v1** (#76): two model-side tests of the scan v3 naming,
  locked before any run on fresh seeds 40–42. Left: the scan arm mirrored (`LC4_L` →
  `TTMn_L`), testing only DNp02 and DNp06 with the scan's null. Drive: `DNp02_R`, `DNp06_R`
  and the pair driven directly at 200 Hz without LC4, against matched descending-neuron
  pairs, with the verdicts `single_sufficient`, `conjunction`, `pair_sufficient`,
  `not_specific` and `insufficient`. Every null draw is kept. `flymsg partner-followup`.

### Exploratory

- **Mirrored scan arms** (`scripts/silence_mirror.py`, seeds 0–2, disclosed in the lock):
  the left side follows the right (DNp02 or DNp06 with DNp01 silenced: 0 `TTMn_L` spikes),
  the effect follows the pair on the side of the stimulus, and the left residual is weak
  (2, 1, 3 spikes).

## 0.8.41 — 2026-10-12

### Result

- **Residual partner scan v3 replicates v2** (#20): names_partner: DNp02, DNp06 again, on
  fresh confirm seeds 30–32 (0 `TTMn_R` spikes on every seed, p 0.001 each against 0.025).
  The run started from `1bbf60e` on `main` and took 2 h 23 min. The descriptive output shows
  the other pass still firing (DNp06 45–50 spikes with DNp02 silenced, DNp02 58–59 with DNp06
  silenced) while `TTMn_R` stays at 0: in this model `TTMn_R` needs both. Figure
  `silence-scan-v3.svg`; outputs in `results/silence-scan/v3/`. Model-side;
  `gf_required_for_the_jump_bit` stays `unverified`.

### Pre-registration

- **Residual partner scan v3, a replication of v2** (#20). Every rule of v2 unchanged,
  confirm seeds 30–32 (the runner refuses the spent 10–12 and 20–22), a failure rule fixed
  before the run, and one descriptive output: the other screen pass's spikes in each confirm
  arm. Committed before the run.
- **Runs start from `main`.** A run a doc cites starts from a merged commit in a clean
  worktree, since squash merges drop branch commits ([architecture](docs/architecture.md)).

### Reproducibility

- **`results/`** holds the small outputs the docs cite (123 KB), copied from `runs/` with
  their manifests by `scripts/archive_results.py`, which drops local paths and refuses to
  overwrite a differing directory. `scripts/build_figures.py` now reads from it, so a clone
  can redraw every figure; only the Kenyon cell figure still needs the MaleCNS tables.
  Its CSV files were caught by the `*.csv` ignore rule when #74 merged; they are now
  tracked, and a test fails if git ignores any archived file.
- **`looming-jump.svg`** replaces the hand-made `looming-jump.png`: the same TTMn_R raster of
  the behavior v1 run, now drawn by the script from `results/behavior/replay.npz`.

## 0.8.40 — 2026-10-12

### Figures and live scenes

- **Every result of 2026-10-12 has a figure.** `scripts/build_figures.py` draws SVG from the
  run outputs with `flymsg.figures` (standard library only, deterministic): the scan v2
  screen and confirmation (`silence-scan-v2.svg`), M1/M2 embodiment (`embodiment.svg`), the
  Kenyon cell persistence of the held-out ORN_DM1 case (`kc-persistence.svg`, one
  exploratory rerun of the scored corner) and the homology pilot (`homology-pilot.svg`).
  Nothing is recomputed into a result.
- **Sensitivity figure** redrawn with y ticks, the v4 floor (10 Hz) and a legend that no
  longer covers a curve.
- **Two new comparisons on the site:** DNp01 silenced against DNp01 + DNp02 and against
  DNp01 + DNp06 (seed 0 replays of the scan arms). `TTMn_R` goes from 7 spikes to 0; DNp06
  and DNp02 still fire when the other is silenced, so in the model `TTMn_R` needs both.
- **`viz --keep NAMES`** exports chosen neurons even when silent (group `kept`), so a
  comparison shows them at zero instead of "not exported". All scenes were re-exported.

## 0.8.39 — 2026-10-12

### Results

- **Sensitivity grid v1** (#28; a report, not a score). Over `w_syn` × 0.8–1.2 and `th_jump`
  0/2, looming, giant fiber, P1 and pIP10 hold in every cell but one corner, and bitter →
  MN9 stays at a median of 0 Hz. Sugar → MN9 holds only from the default `w_syn` up
  (`th_jump` 0) or from × 1.1 (`th_jump` 2): its v4 pass sits at the edge. Persistent activity
  appears only at the grid's edges. Nothing is chosen from it; `sim.Params` is unchanged.
  Report in `docs/validation.md`, figure `docs/img/sensitivity-rate.svg`.

### Fixes

- The `holds` table of `flymsg sensitivity --run` printed 1.0/0.0 instead of yes/no; the
  v1 `report.txt` reads that way, `holds.csv` is unaffected.

## 0.8.38 — 2026-10-12

### Results

- **Residual partner scan v2: names_partner: DNp02, DNp06** (#20). With both `DNp01`
  silenced, silencing DNp02 or DNp06 as well leaves `TTMn_R` at 0 spikes on screen seeds
  0–2 and confirm seeds 20–22; with every screen pass out of the null pool no draw reached
  0, p 0.001 each against 0.025. Run from `764af9e`, clean. Version 2 was fixed after the
  version 1 result was seen and before its own run; the result is model-side and
  `gf_required_for_the_jump_bit` stays `unverified`.

### Changes

- **The run index keeps a run's kind when it fails.** `flymsg runs` has an `outcome`
  column: a failed held-out run is listed as `held-out`, `failed` instead of only `failed`.
  `--label failed` filters on the outcome.

## 0.8.37 — 2026-10-12

### Fixes

- **Every arm reads the same target neuron.** `explore` and `confirm` report a
  `target_neuron` but picked the best target neuron again in each arm and in each null draw,
  so with a multi-neuron target a silenced arm could be read on another neuron; the
  baseline's choice is now used in every arm. The pre-registered T1–T4 tests read the type's
  most active neuron in each condition by their own definition and are unchanged.
  `experiment` picked it per seed; it is now chosen once over the seeds, as the battery
  does. No published result used either path. Tests with two target neurons fail on the old
  code.
- **An exploratory `nulls` run is indexed as exploratory.** The `--exploratory` flag is now
  in the run manifest, and `flymsg runs` reads it.

### Documentation

- The sensitivity grid states that each cell picks its own best neuron per target type. The
  README lists the Kenyon cell loop behind the held-out olfactory failure.

## 0.8.36 — 2026-10-12

### Comparison

- **Male/female type mapping and a pilot (#29).** `validation/homology/` holds a versioned
  mapping of every male cell type to FAFB through MaleCNS `flywireType`, with one category
  each (matched 7,422; outside FAFB tissue 3,118; annotation not in FAFB 715; male-specific
  288; not mapped 208; 1,511 female types unnamed), and the LC4 → DNp01 pilot: the LC4 share
  of the giant fiber's input is about twice as large in the male (16–18% against 8–9%), a
  difference between two reconstructions that is not attributed to sex.

## 0.8.35 — 2026-10-12

### Embodiment

- **M2 closed loop (#34).** `flymsg loop` recomputes the drive of the stimulated neurons from
  a looming disc and the body's height at every control period, through an engineered
  transducer, and moves the body from the motor neuron's spikes; disconnected, shuffled and
  replay controls run with the same seed. Tests show a jump changes the next input and the
  controls hold. On MaleCNS at realistic scales (a 10 µm jump, a disc centimetres away) the
  feedback changes no input: closed and disconnected runs are identical. Reported as is.
  `CpuRuntime.traced_spikes` reads the traced neurons' spikes of steps already run.

## 0.8.34 — 2026-10-12

### Embodiment

- **M1 jump body (#33).** `flymsg.jump.JumpBody` (gravity, floor contact, one vertical
  actuator) runs through the M0 contract; `flymsg jump` decodes a motor neuron's spikes with
  an engineered gain stated by the caller, labelled as not a MaleCNS motor map, and writes
  the trajectory with a manifest. LC4_R lifts the body at 18.0 ms; with both DNp01 silenced
  it still lifts at 67.0 ms, the failed silence check carried into the body. The M0 contract
  now takes the sensor frame from the body.

## 0.8.33 — 2026-10-12

### Research tooling

- **Causal explorer (#25).** `flymsg explore SRC DST` reports distinct strongest routes
  (anatomy) and the target's change when each intermediate type is silenced (exploratory
  simulation, bootstrap interval), writes it with a manifest, and `--replay` checks a saved
  exploration reproduces. `flymsg confirm LOCK` runs a `flymsg.intervention/v1` lock only
  once it is registered by a commit, on seeds disjoint from the explored ones, against a
  matched null that never draws from any set, and never overwrites a result. `TTMn_R` is
  marked as governed by #20. No lock is registered.

## 0.8.32 — 2026-10-12

### Platform

- **Exploratory experiments and the run index (#27).** `flymsg experiment FILE` validates a
  versioned `flymsg.experiment/v1` config (schema, fields, names in the dataset) and runs it
  into `runs/experiments/<config hash>/` with metrics and a manifest; the same config is
  refused a second time, and only the `exploratory` label is accepted. `flymsg runs` lists
  every run manifest with its label without loading the dataset; older manifests are
  labelled from their command and verdict. A golden end-to-end test runs on the tiny CI
  dataset. The shared test dataset moved to `tests/conftest.py`.

## 0.8.31 — 2026-10-12

### Analysis

- **Sensitivity grid, before its run (#28).** `validation/sensitivity.yaml` fixes a
  `w_syn` × `th_jump` grid around the defaults (10 cells, 6 cases, seeds 0–4) and its
  metrics. `flymsg sensitivity --run` reports every cell, whether each target holds at the
  v4 floor, the seed spread apart from the parameter spread, and an SVG figure, with a
  manifest. A report, not a score: nothing is chosen from it and no default changes. The
  grid has not run yet.

## 0.8.30 — 2026-10-12

### Viz

- **Compare two replays (#23).** `flymsg viz-compare` pairs two existing exports without
  simulating, refusing a mismatched dataset or time base; a neuron one export lacks is "not
  exported", never silent. The page switches A, B and `|A − B|`, colours neurons by more,
  fewer or the same spikes, and shows each run's label, status and the manifest keys that
  differ; a failed protocol is labelled as such. `flymsg viz --silence` exports an
  intervention. The site adds LC4_R against LC4_R with both DNp01 silenced, the failed
  silence check: `TTMn_R` fires 22 times, and still 7 times silenced.

## 0.8.29 — 2026-10-12

### Architecture

- **The null-draw engine is its own module (ADR step 3).** `flymsg.draws` holds matched
  draws, checkpointed null draws and the job map that `dimorphism` kept private and
  `silence_scan` imported by underscore name. Pick hashes and partial file names are
  unchanged; the T4 checkpoint resumes with the same rows. No result changes.

## 0.8.28 — 2026-10-12

### Diagnostics

- **Record neuron states (#26).** `flymsg trace` and `flymsg.tracing.record` record `v`, `g`,
  threshold offset, refractory state, spikes and input of chosen neurons. They drive
  `CpuRuntime`, so the run equals `sim.run`; the recorded states equal the NumPy oracle bit
  for bit. Large requests warn or are refused.
- **Why the held-out ORN case keeps firing (exploratory).** 4,907 neurons outlast the
  stimulus, most of them Kenyon cells; 73.4% of the excitatory synapses onto Kenyon cells
  come from other Kenyon cells, and in a point LIF that loop sustains itself. A model limit,
  not a fit: no score changes (`scripts/orn_persistence.py`, `docs/benchmarks.md`).

### Viz

- **Spike raster of the selection (#22).** Spikes per bin of the selected neuron and its
  partners, the stimulus window, a cursor on the bin the 3D glow shows (shared `binAt`),
  drag to move in time, arrow keys to step, and an export with the scene manifest.

## 0.8.27 — 2026-10-12

### Results

- **Residual TTMn_R scan, version 1: none.** Thirteen units met the candidate rule; DNp02
  and DNp06 passed the screen. Silenced with both `DNp01`, each removed every `TTMn_R` spike
  on seeds 0–2 and 10–12, against 5–7 spikes in the base arm, but the matched nulls gave
  p 0.036 and 0.041 above the corrected 0.025. Post-hoc (`scripts/silence_scan_posthoc.py`):
  the draws that reached 0 spikes match in number those that contained the other unit's
  right-hand neuron (35 with DNp06_R, 40 with DNp02_R). The verdict stands. `w_syn` stays
  0.192.

### Validation

- **Residual TTMn_R scan, version 2, before its run.** The null pool also excludes every
  other screen pass; confirmation moves to fresh seeds 20–22. Everything else is version 1.
  Outputs go to `runs/silence-scan/v<version>/`, so a version never overwrites another.

### Fixes

- **A run manifest records git as it was when the command started.** A long run whose
  checkout moved meanwhile recorded the later commit; the v1 scan manifest says `7d939b2`
  for a run that started from `6709f13`.

## 0.8.26 — 2026-10-12

### Viz

- **The scene bundle has a version (ADR step 4).** `scene.json` carries
  `schema: flymsg.scene/v1`; the page warns in the console when a bundle has another or no
  version. The live scenes are re-exported from a clean tree: only the `schema` field and
  the manifests change; `activity.bin` and `partners.json` are identical.

## 0.8.25 — 2026-10-12

### Architecture

- **One lock check (ADR step 2).** `flymsg.locks` holds the version, hash-table and
  `content_sha256` check that `behavior`, `benchmarks`, `motor_map` and `silence_scan` each
  copied; they keep their names, error classes and hash tables. A contract test checks that
  each module still raises its own error. No lock file or hash changes.

## 0.8.24 — 2026-10-12

### Runtime

- **Native LIF fixture executor, DX12 shader and UWP worker (runtime R1 lane, PR #55).**
  `flymsg.native` exports a bounded, versioned fixture from a fresh `CpuRuntime`; the C++
  executor in `native/` runs the same four ordered phases and checkpoints and resumes. On 12
  synthetic fixtures, state, spikes, counts, refractory deadlines and delayed spikes match the
  Python oracle exactly at step 217 and after resume to step 1000. The HLSL compute shader,
  the hardware-only DX12 host and the UWP worker compile in CI; GPU parity, console
  installation, suspension timing and throughput are unmeasured and gate #39 and #40. No
  scored path or default changes. `w_syn` stays 0.192.

## 0.8.23 — 2026-10-12

### Embodiment

- **Exploratory looming encoder (E2, PR #47).** `flymsg.sensory.encode_looming` maps an
  approaching disc to angular size, expansion rate and a bounded drive rate; gain and
  ceiling have no default because no measured value exists. `schedule_sensory_drive` turns
  the rates into seeded Poisson input blocks on a `CpuRuntime`, taking the neural tick and
  input width from the runtime (`tick_us`, `n_inputs`). Not an LC4 tuning curve and not
  mapped to bodyIds; no scored path changes. Documented under E2 in `docs/embodiment.md`,
  which now holds one map of the M, E and research issue series and the evidence each step
  needs.
  `w_syn` stays 0.192.

## 0.8.22 — 2026-10-12

### Architecture

- **Architecture ADR with contract tests (#30).** `docs/architecture.md` records the module
  layers, the pain points (copied lock code, a draw engine private to `dimorphism`, an
  unversioned viewer bundle, unindexed runs, spike-only recording) and six boundaries:
  dataset tables, engine (`sim.run` and `CpuRuntime`), protocol locks, run manifest, viewer
  bundle, embodiment contract. `tests/test_contracts.py` pins each one; the engine test runs
  `CpuRuntime` in blocks against `sim.run` on a synthetic chain. The migration order puts
  the lock helper and the draw engine first, then the bundle version, then #26, #27, #25,
  #28 and #31 on those boundaries. Nothing is moved yet; no protocol, seed, default or
  manifest changes.

## 0.8.21 — 2026-10-12

### Engine

- **Incremental CPU runtime (PR #41).** `flymsg.runtime.CpuRuntime` advances the LIF kernel
  to explicit step boundaries, takes explicit input-count blocks at the current boundary,
  returns detached snapshots, and checkpoints neural state to a non-pickle NPZ with an
  identity hash and a state checksum; a restore validates everything before it replaces
  state. `sim.run` and the runtime share one compiled step loop (`sim._advance`), one delay
  rule and one set of float32 constants. On MaleCNS, `sim.run` gives bit-identical counts,
  first spikes and traces before and after the change (LC4_R, LC4_R with DNp01 silenced,
  pIP10), and the runtime advanced in blocks through a checkpoint and restore matches
  `sim.run` bit for bit. `docs/runtime.md` is the backend ADR; the GPU lane (#39, #40) is
  planned, not implemented. Defaults, seeds and protocols are unchanged. `w_syn` stays
  0.192.

## 0.8.20 — 2026-10-12

### Viz

- **Select a neuron and read its partners (#21).** A click, the GUI field or
  `?select=<bodyId>` selects a neuron in any scene. The panel gives its annotations
  (missing ones say unknown), its simulated rate labelled as model output, and its ten
  strongest input and output cell types with totals and the count not shown. Partners in
  the scene are recoloured by role and the rest stays as context; Esc clears. `flymsg viz`
  writes `partners.json` from `graph.partner_table`, tested equal to `graph.partners`
  (`flymsg info`) per neuron. The live scenes now carry it; their `scene.json` and
  `activity.bin` are unchanged.

### Fixes

- **The dataset symlink committed by #37 is removed.** The ignore rule is now `/data`, which
  also matches a link. Pulling #37 had replaced the local `data/` with that link; the tables
  were rebuilt and their sha256 matches the recorded manifests.

## 0.8.19 — 2026-10-12

### Embodiment

- **M0 neural/body contract (#32, PR #37).** `flymsg.embodiment` defines versioned
  contracts for spike events, motor commands, body state, sensor samples and
  provenance, and a deterministic multirate scheduler on an integer microsecond
  clock whose neural tick is `sim.Params.dt`. A synthetic one-DOF mock body closes a
  spike → command → sensor round trip. Invalid versions, datasets, timestamps, maps or
  masses fail before the first actuator call; any adapter exception stops the run as
  a `ContractError`. Fixture `bodyId`s are synthetic: `validation/motor_map.yaml`
  stays all `unmapped`, so no real motor command can be issued. The LIF engine is not
  coupled online. ADR in `docs/embodiment.md`. `w_syn` stays 0.192.

## 0.8.18 — 2026-10-12

### Site

- **The 3D view runs live on GitHub Pages.** The LC4_R and pIP10 replays and the
  pIP10/dPR1/dMS9 anatomy are served under `/live/` with the same page `flymsg viz`
  writes; geometry streams from the public MaleCNS volumes. The scenes are committed in
  `docs/live/` with their run manifests (clean tree, seed 0, default parameters) and
  rebuilt by `scripts/build_live_scenes.py`. The README gallery links each frame to its
  live scene. No scored run changed. `w_syn` stays 0.192.

## 0.8.17 — 2026-10-12

### Validation

- **The scan runner, before the run.** `flymsg silence-scan --run` executes
  version 1 of `validation/silence_scan.yaml` as written: base arms, the
  candidate rule, the screen, then confirmation with checkpointed null draws.
  Synthetic tests check that the only remaining route is named and that a
  base arm under the bar stops the scan. The lock is unchanged. Nothing was
  run on MaleCNS. `w_syn` stays 0.192.

## 0.8.16 — 2026-10-12

### Validation

- **Residual TTMn_R partner scan, before the run.** `validation/silence_scan.yaml`
  version 1 freezes the measurement issue #20 asks for. Candidates are every cell
  type with at least 5 synapses onto `TTMn_R` and an active neuron in the
  `DNp01`-silenced arm, computed by the runner, not read from a ranking. A screen
  on seeds 0–2 chooses what is confirmed; fresh seeds 10–12 confirm against the
  T2/T3 matched-responder null with max(1000, 20 _m_) draws and Bonferroni over
  the _m_ screen passes. `names_partner` also needs the behavior v1 silence bar.
  `flymsg silence-scan` prints the protocol and does not simulate. Provenance
  cites the authored motor map. Nothing was run. `w_syn` stays 0.192.

## 0.8.15 — 2026-10-12

### Documentation

- **Authored motor map, every row unmapped.** `validation/motor_map.yaml`
  lists the 59 walking actuators and both `TTMn` neurons. A published source
  names none of them together with an actuator, so a command is refused.
  Vaxenburg et al. 2025 states that the body is female. Version 1 of the
  behavior lock is unchanged. Provenance cites the documentary-issue note.
  Nothing was rerun. `w_syn` stays 0.192.

## 0.8.14 — 2026-10-12

### Documentation

- **Two documentary issues, no run.** #19 records the FlyBody re-read at
  `d015e9b`: same timesteps, 59 named walking actuators, no MaleCNS motor map.
  #20 keeps the residual `TTMn_R` partner unnamed. The synapse list read the
  same day cannot choose the next silencing. Version 1 is unchanged. Provenance
  cites the numeric-lock note. Nothing was rerun. `w_syn` stays 0.192.

## 0.8.13 — 2026-10-12

### Dependencies

- **numba 0.68.0 and actions/setup-node 7.1.0.** llvmlite is 0.50.0. Node stays 24. The unit suite matches the NumPy reference kernel. The scored runs were
  not repeated, so their manifests stay on numba 0.67.0. Provenance cites the
  empty-queue note. `w_syn` stays 0.192.

## 0.8.12 — 2026-10-12

### Documentation

- **No scientific task is queued.** Provenance cites the queue close, the
  held-out no-go and the prose alignment. The validated-behavior milestone
  stays unmet. Nothing was rerun. `w_syn` stays 0.192.

## 0.8.11 — 2026-10-12

### Documentation

- **Status prose matches the closed record.** The validation heading no longer
  carries a version. The calibration battery is six cases, and its limits note
  the held-out failure. The silence failure does not name a partner. Issues #10
  and #11 are closed as blocked. The inventory's exploratory, excluded and not
  scored rows are the lock's `exploratory` list. Nothing was rerun. `w_syn`
  stays 0.192.

## 0.8.10 — 2026-10-11

### Results

- **No held-out behavior is eligible.** The frozen partition assigned every mapped
  behavior to calibration or to a disqualified exploratory row. Nothing is promoted
  and nothing is rerun. The validated-behavior milestone stays unmet. `w_syn` stays
  0.192.

## 0.8.9 — 2026-10-11

### Results

- **The extension queue is closed as blocked.** Neuromodulation and associative
  learning have no parameter table, so no module is added. The validated-behavior
  milestone is not met. Provenance now cites the sensitivity corners, the looming
  protocol, the silence failure, the extension no-go and the TTMn_R raster.
  Nothing was rerun.

## 0.8.8 — 2026-10-11

### Results

- **TTMn_R spike times are drawn.** The raster shows the open loop continuing
  through the 300 ms drive, the closed loop stopping at the third spike, and both
  DNp01 silenced still reaching three spikes later. The times are the v0.8.6 run.
  Nothing was rerun.

## 0.8.7 — 2026-10-11

### Results

- **No biological extension is added.** Cell-type parameters, gap junctions, short-term
  synaptic dynamics and compartments have no value that transfers into this LIF. The
  looming silence failure is not a giant-fiber gap junction: silencing DNp01 removes that
  cell's output, and TTMn_R still fires. Neuromodulation (#10) and associative learning
  (#11) stay blocked. `w_syn` stayed 0.192. Nothing was retuned.

## 0.8.6 — 2026-10-11

### Results

- **The one-bit looming jump fails silence.** `TTMn_R` jumps on time in 3/3 seeds
  (43.0, 50.7, 47.8 ms), the drive cuts on that spike, and the prefix matches the
  open loop. With both DNp01 neurons silenced, `TTMn_R` still emits 3 spikes in
  every seed (third spike 154.8, 145.1, 115.6 ms) and the drive is then cut.
  Closed-loop stability is 0 neurons still firing from 400 to 600 ms and does not
  decide. The loop took 90.5 s. `w_syn` stayed 0.192. The protocol was not edited.

## 0.8.5 — 2026-10-11

### Validation

- **One-bit looming jump, before the run.** The closed-loop task is `LC4_R` →
  `TTMn_R`: the third spike cuts the drive. Jump, feedback, DNp01 silence, and a
  decoder-prefix check are required. The claim is a calibration feasibility check,
  because looming escape selected the model. FlyBody (Apache-2.0) was compared and
  not embedded. `flymsg behavior` prints the protocol and does not simulate.
  Criterion v4, N1, and the held-out manifest are unchanged.

## 0.8.4 — 2026-10-11

### Results

- **The held-out failure survives both sensitivity corners.** At the Shiu weight
  (`w_syn` 0.275, `th_jump` 0) DM1_lPN is 301.1 Hz against a 200 Hz control, and 7797
  neurons stay active. With adaptation (`w_syn` 0.192, `th_jump` 2) it is 185.6 Hz
  against 105.6 Hz, and 2669 neurons stay active. Specific and stability fail at both
  corners. ORN_V does not decide. The scored result stays the verdict. The manifest
  was not edited.

## 0.8.3 — 2026-10-11

### Results

- **Held-out ORN_DM1 → DM1_lPN fails.** Positive passes (284.4 Hz, 3/3 seeds, first
  spike 3.4 ms). Specific fails: the class-matched olfactory control reaches 185.6 Hz,
  and the check needs it at or below 94.1 Hz. Stability fails: 4894 neurons still fire
  after the stimulus (limit 100). ORN_V → V_ilPN and V_l2PN shows the same pattern and
  does not decide. `w_syn` stayed 0.192. The manifest was not edited.

## 0.8.2 — 2026-10-11

### Validation

- **Held-out manifest, before the run.** Calibration, exploratory and held-out cases are
  partitioned in `validation/benchmarks.yaml`. The one confirmatory case is ORN_DM1 →
  DM1_lPN, scored with the v4 positive, specific and stability checks at the default
  parameters. `flymsg benchmarks` prints that case and does not simulate. Criterion v4
  and N1 are unchanged.

## 0.8.1 — 2026-10-11

### Results

- **T4, whether AVLP717m relays P1's drive to pIP10.** The pre-registered null finished.
  Silencing AVLP717m (2 neurons) drops pIP10 after P1 by 43% (104 → 60 Hz), p = 0.001.
  The same silencing drops dPR1 after P1 by 28%; that row does not decide. After the
  pIP10 stimulus the matched null is not defined, and dPR1 is unchanged. `w_syn` stayed
  0.192.

## 0.8.0 — 2026-10-11

### Reproducibility

- **Pre-registration file** (`validation/preregistration.yaml`, version 1). Hypotheses,
  criterion v4 thresholds, N1, the four null families, pathway list and draw counts are
  locked. The test suite fails if the live code or a confirmatory run differs without a
  version bump.
- **Null families** (`flymsg nulls`). Degree-preserving (N1's permutation, many seeds),
  cell-type-preserving, weight shuffle within presynaptic cell type, and sign shuffle.
  Each draw is seeded. The score is signed stim→target weight (`sum` and `max`); every
  pathway is reported. Default `--draws` is 2 (CI). `flymsg nulls --full` is the locked
  20-draw command. N1's one-draw battery is not redrawn. On MaleCNS v1.0 with 20 draws
  the headline (4077) is above every draw of every family (_p_ = 1/21). Four one-hop
  pathways are 0, including sugar → MN9.
- **Run manifests.** Commands that write outputs also write `manifest.json` (git commit,
  dataset name and file hashes, config, seeds, package versions, platform, timestamps).
- **Provenance.** `docs/provenance.md` lists the public source and introducing commit for
  each existing idea. Public literature and public repositories only.

## 0.7.4 — 2026-10-11

### Results

- **T3, how dMS9 restrains dPR1.** The run pre-registered on 2026-09-23 finished from its
  checkpoint. Silencing IN03B024 (2 neurons) raises dPR1 by 101% after pIP10 and 100% after
  P1. Silencing vMS12_a+b+c (12) raises it by 67% and 78%. All four rises have p = 0.001.
  Silencing dMS9 together with IN03B024 raises it by 100% and 99%, and the 95% bootstrap
  intervals of the per-seed rise overlap in both cases. The chain is supported. `w_syn`
  stayed 0.192.

## 0.7.3 — 2026-10-11

### Docs

- **GitHub Pages.** The README and the docs are published at
  <https://gianlucamazza.github.io/flymsg/>. `scripts/build_pages.py` builds the site, and
  heading anchors stay the ones the docs already use.

## 0.7.2 — 2026-10-11

### Docs

- **Gallery.** The README collects the viewer frames and says what each colour means:
  LC4_R at 120 ms, the pIP10 pathway at 150 ms, that replay coloured by the sex annotation
  (male-specific, dimorphic, no label), and pIP10, dPR1 and dMS9 in the neuropil shells.
  `docs/viz.md` points at the gallery.

## 0.7.1 — 2026-10-11

### Viewer

- **A bad bloom mip no longer erases a replay.** The 11-tap blur into a target about 44×29
  wrote NaN on this GPU. The composite stretched it over the empty part of the frame, and
  adding the glow back turned those pixels black, so a paused pIP10 replay went black while
  the page still counted its surfaces. The blur inlines its weights and unrolls the taps, and
  a non-finite sample adds nothing. With bloom off and 4× MSAA still on, the same frame was
  already the whole circuit. Clip planes track the volume. The unexplained black-viewport note
  in `docs/viz.md` is replaced by this account. Geometry is unchanged.

### Docs

- **README.** The traced graph still passes 29/29. On N1's shuffle the same battery is 5/29,
  all five the `stability` check, and every `specific` check fails. `w_syn` stays 0.192.
  Figures from the fixed viewer: LC4_R at 120 ms, the pIP10 pathway at 150 ms, and pIP10,
  dPR1 and dMS9 in the neuropil shells.

### Licence

- Exclusions for the connectome data and the vendored three.js and lil-gui live in `NOTICE`.
  `LICENSE` is the plain MIT text. The README points at `NOTICE`.

## 0.7.0 — 2026-10-11

### Results

- **N1, the degree-preserving shuffle** (`docs/related.md`). Seed 0, default model, criterion
  v4. The traced graph passes 29/29. The shuffle passes 5/29, all five the `stability` check:
  activity still dies out. Every `specific` check fails (7/7). `positive`, `order`, `dose`
  and `negative` fail too. `w_syn` was not changed.

### Docs

- **Related work** (`docs/related.md`): MaleCNS 211,577 is the raw body table, not a second
  animal; BANC's published backbone-proofread count sits beside the 188,508 / 13,620,865
  figures used by the embodied model. README links the note.
- Stale lines brought in line with 0.6.0: an input spike adds 48.1 mV (`docs/model.md`), the
  validation status heading is v0.6, and the courtship enrichment sentence matches its table
  (4.3–18.6×).

### Tools

- **`flymsg wiring-null`**: N1's shuffle (`wiring.shuffle_targets`, seed 0). `--stats` prints
  self-loops and duplicate pairs and does not simulate. Without `--stats` the command runs
  criterion v4 on the traced graph and on the shuffle, at the default `w_syn` and `th_jump`,
  seeds 0–2, and writes `runs/n1-real.csv` and `runs/n1-shuffle.csv`. No flag changes the
  seed or the weights.

## 0.6.0 — 2026-09-23

### Results

- **Pre-registered silencing tests (T1, T2), 1,000 null draws each.** Silencing the 948
  sexually dimorphic neurons raises dPR1 by 61–64 % after either courtship stimulus
  (p = 0.001): confirmed. fru/dsx+ is not confirmed (p 0.011 after P1): silencing ~4,900
  neurons raises dPR1 by +21 % on average by itself. Looming escape depends on none of the
  three categories, now with 1,000 draws.
- **Correction:** v0.5 predicted the loop dPR1 → dMS9 → vPR9_a / IN00A038 → dPR1. T2 keeps
  dMS9 (+67 %, +74 %, p 0.001 against matched active neurons) and rejects the inhibitory
  half: silencing vPR9_a + IN00A038 lowers dPR1 after pIP10 and stays inside the null after
  P1. The route by which dMS9 restrains dPR1 is open.
- **Post-hoc lead, pre-registered as T3 for the next run:** with dMS9 silenced, the
  inhibitory neurons that actually stop driving dPR1 are IN03B024 (1,533 synapses onto dPR1,
  90 → 29 Hz), fed by vMS12_a/b/c, which dMS9 drives with 6,562 synapses and which fall
  silent. Chain: dPR1 → dMS9 → vMS12 → IN03B024 → dPR1.

### Tools

- **`flymsg compare`**: the male-vs-female numbers of `docs/comparison.md` (density factor,
  the same model on both sexes, subtype fingerprints, the FAFB LB3 split and MN9 per part)
  are regenerated by a command instead of lost scratch scripts. Shiu et al.'s Ir94e set was
  added to `compare`, and their four sets were checked id by id against `figures.ipynb` at
  the pinned commit.
- Clear messages instead of tracebacks: `--progress` without `--checkpoint`, a bad
  `--duration`, an unknown case or category, `--checkpoint` with `--by-type`. `--null`
  defaults to 1,000 everywhere, as the docs say.
- Corrected stale numbers in `docs/model.md` (an input spike adds 48.1 mV, not 68.75; a
  synapse's peak is 0.030 mV and ~230 coincident synapses reach threshold) and one
  fingerprint value in `docs/validation.md`.
- Tests: `compare`'s numeric functions, `graph`, `data.download`, `data.build_fafb`,
  `validate.calibrate` and `compare_models`, and a smoke test per CLI subcommand (72 tests).
  Two defects they found are fixed: `build_fafb`'s integrity check raised `IndexError`
  instead of its message for an id above every known one, and `audit` on a dataset with one
  side only failed with a bare `L`.

### Internals

- One job runs every silencing test (category, cell-type set, per type); `sim.network`
  replaces seven hand-written weight-matrix calls; `validate.run` splits into per-check
  helpers and `cli.main` into `build_parser` plus a command table (217 lines to 33).
- The viewer's pure logic moves out of `main.js` into `budget.js`, `activity.js`,
  `colors.js` and `lod.js`, each with node tests; `flymsg viz` now collects the page's
  modules instead of listing them.

- `dimorphism --silencing` reports one-sided p for a drop and for a rise (`p_drop`,
  `p_rise`); `dimorphism --loop` tests the predicted dMS9 loop against silencing matched
  active neurons (pre-registered tests T1 and T2, docs/dimorphism.md).
- Worker processes start from a forkserver (`parallel.py`) instead of forking a
  multi-threaded caller; long silencing runs report progress with a measured ETA, save
  every null draw and resume from `--checkpoint FILE`, running the confirmatory tests first.
- `dimorphism --progress --checkpoint FILE`: draws per job of a checkpointed run, read-only.
- `validate.respond(duration_ms=STIM_MS)` stops a run at the end of the stimulus: identical
  rates at 2–2.7× less cost, used by all silencing analyses.

## 0.5.2 — 2026-09-22

Documentation only.

- **References verified.** Every entry was checked against PubMed or bioRxiv and given
  volume, pages and DOI. Corrections: Allen & Murphey 2007 has two authors (was "Allen et
  al."), the full title of King & Wyman 1980, and the MaleCNS paper's published _Cell_ title
  and DOI (10.1016/j.cell.2026.08.015), which differ from the preprint's. Gordon & Scott 2009,
  Shiu et al. 2024 and Tastekin et al. 2025 were added to the list, and the FlyWire papers
  to `docs/data.md`.
- Fixed a stale limit (the control has matched class for sensory stimuli since criterion
  v4), a duplicated paragraph in `docs/model.md` and the table layout in the README.

## 0.5.1 — 2026-09-22

- `flymsg audit` (`quality.py`): left/right asymmetry of every bilateral cell type (robust
  z over 11,095 types, 355 flagged), traced-input share, and the same pair in FAFB.
- **Correction:** v0.5.0 reported a lateralised male MN9. MN9_R has 556 input synapses
  against MN9_L's 6,012 (symmetric in FAFB), so it is most likely incompletely
  reconstructed. The sex comparison now reads the contralateral pathway through MN9_L, as
  Shiu et al. do: male vs female MN9 30 vs 76 Hz at 100 Hz, 80 vs 88 Hz at 200 Hz.
- LB3c (right sugar GRNs 2.5× the input of the left) is flagged too; the neurons of the
  validation circuits and of the predicted dMS9 loop are symmetric.

## 0.5.0 — 2026-09-22

### Model

- **No compensation by default.** The pre-registered replication (fresh seeds 10–19 and
  control draws) tied A and B− at 29/29, so B− became the default: Shiu's weight scaled for
  MaleCNS synapse density (`w_syn` 0.275 / 1.43 = 0.192) and no adaptive threshold (kept as an
  option). Zero self-sustained neurons in every validation case.
- Compiled kernel (numba): 2× faster, spikes identical to the previous NumPy loop (kept as the
  test oracle in `tests/reference_sim.py`).
- `sim.SHIU_W_SYN` names the published weight used on FAFB.

### Analyses

- LB3 split in FAFB (`compare.nearest_male_type`): Shiu's sugar set is 14 LB3b/c-like and 6
  LB3d-like neurons; in the published model the former carry 72 % of the MN9 response.
- Silencing with 100 null draws: silencing fru/dsx+ or dimorphic neurons doubles dPR1;
  `dimorphism --by-type` locates a predicted feedback loop dPR1 → dMS9 → vPR9_a/IN00A038 → dPR1.
- Male MN9 is lateralised: only MN9_L responds, only to right sugar GRNs (corrected in
  0.5.1: MN9_R is most likely incompletely reconstructed).

### Public release

- MIT licence, `CITATION.cff`, GitHub Actions CI (lint + unit and browser-module tests),
  README rewritten for a public audience, `docs/validation.md` opens with the current status.
- Fixed: `.gitignore` excluded the vendored `three.module.min.js` (any `build/` directory).
- Removed the unused `networkx` dependency.

## 0.4.0 — 2026-09-21

### Validation

- Criterion v4: class-matched control for sensory stimuli (resolves the sugar → MN9
  specificity failure: random gustatory neurons leave MN9 silent) and a negative case,
  bitter GRNs (LB1a–d, two agreeing lines of evidence) → MN9. 29/29 with the defaults.
- `flymsg select-model`: pre-registered comparison at 10 seeds of the calibrated model (A,
  28/29) and the published model at MaleCNS synapse density without compensation (B, 26/29);
  A stays the default. The sensitivity variant B− (`w_syn` 0.192, no compensation) passes
  29/29 and is the candidate for a confirmatory replication.
- Bootstrap 95 % intervals on target and control rates.
- Finding: in the density-scaled model MN9 responds to LB3b+c+d but not to LB3b+c.

### Model and analyses

- `sim.run(silence=...)`; `flymsg dimorphism --silencing`: response drop when fru/dsx+,
  male-specific or dimorphic neurons are silenced, against as many other neurons. Courtship
  responses survive (they run through direct links); silencing male-specific neurons lowers
  dPR1 by ~20 %, silencing all fru/dsx+ neurons raises it; looming is unaffected.

### 3D view

- Colour by dimorphism or fru/dsx (`?color=`).

## 0.3.0 — 2026-09-21

### Model

- The engine now reproduces the published brian2 model step by step (Poisson input into v,
  reset of v and g, v and g frozen while refractory, synaptic input lost while refractory,
  stimulated neurons without refractory period). Checked against the Shiu et al. code on the
  same FAFB connectome. Stimulated neurons now fire at the input rate, not about twice it.
- Defaults re-derived with calibrate-v3: `w_syn` 0.275, `th_jump` 2 mV (was 6). Criterion v3
  passes 27/28; sugar → MN9 specificity fails under every parameter set (documented).
- The faithful engine keeps the previous speed (refractory neurons handled as a small set).
- Exploratory: MaleCNS has 1.81× the synapses per neuron of FAFB; with `w_syn` scaled to
  0.152 the model is stable without the adaptive threshold (26/28).

### Validation

- Criterion v3: latency order along chains and dose-response checks, pre-registered.
- New case: sugar GRNs → MN9. Sugar GRNs (LB3b, LB3c) chosen where two independent lines agree.
- GF → TTMn evaluated against _shak-B²_ physiology; kept as a documented limit.

### Data and comparisons

- `--dataset fafb`: the female FlyWire v783 brain in the same schema; `build` keeps
  `flywireType`, `subclass`, `entryNerve`, `receptorType`.
- `flymsg dimorphism`: dimorphic/fru-dsx neurons among responders vs a superclass-matched null.
- Male vs female comparison of shared cases, corrected for synapse detection density
  (`docs/comparison.md`); dimorphism enrichment results in `docs/dimorphism.md`.

## 0.2.0 — 2026-09-21

### Model and validation

- Validation criterion v2: a case passes when the best target neuron fires ≥ 3 spikes in the
  window in ≥ 2/3 of seeds and beats a size-matched random control (≥ 3× its rate + 2 Hz),
  with ≤ 100 self-sustained neurons; latencies reported. GF → DLMn excluded (gap junctions).
- `calibrate` re-derived the defaults with a pre-registered ranking: `th_jump` 6 mV, the one
  named compensation (adaptive threshold); the battery passes 16/16.
- `path --alt K`: further routes, each avoiding the intermediate cell types of the previous
  ones (LC4 → TTMn: via DNp01, then DNp02, then DNp11).

### 3D view (`flymsg viz`)

- Streams real neuron surfaces (multi-resolution Draco), skeletons and neuropils from the
  public GCS volumes; the export holds only metadata and activity.
- Octree LOD within a triangle budget derived from the GPU buffers' real capacity; neurons
  beyond it drawn as skeletons, simplified only below half a pixel on screen.
- One draw for all surfaces (`BatchedMesh`) and one for all skeletons; fragments finished in
  workers; GPU picking; render on demand; 4× MSAA at rest, adaptive quality while moving.
- Replays: silent neurons desaturated and see-through, so activity is not hidden.
- Performance HUD and `?bench=<s>`; `scripts/shoot.mjs` measures headless on SwiftShader or
  the real GPU. Numbers in [docs/viz.md](docs/viz.md).

### Docs

- `docs/data.md`, `docs/model.md`, `docs/validation.md` (with the negative results),
  `docs/viz.md`.

## 0.1.0 — 2026-09-21

- `fetch` / `build`: MaleCNS v1.0 tables compacted to Parquet (165,122 traced neurons,
  25.6 M connections).
- `info`, `path` (strongest chain by input fraction), `sim` (whole-CNS LIF after Shiu et
  al. 2024, time-binned, multi-seed summary).
- `validate` battery of known circuits with controls, `calibrate` grid search.
