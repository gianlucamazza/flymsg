# 3D view

`flymsg viz` writes only `scene.json` (neurons, groups, rates) and, for a replay,
`activity.bin` (spike counts per 10 ms bin). The page (`src/flymsg/viz_static/`) streams all
geometry at source resolution from the public MaleCNS volumes on GCS
(`gs://flyem-male-cns/v1.0/segmentation`, CORS and Range requests, no token). Example frames,
and what each colour means, are in the README gallery.

## Live on the site

The Pages site serves nine scenes with this page: the LC4_R and pIP10 replays and the
pIP10/dPR1/dMS9 anatomy, at <https://gianlucamazza.github.io/flymsg/live/looming/>,
`…/live/song/` and `…/live/anatomy/`; the LC4_R replay with DNp01, DNp01 + DNp02 and
DNp01 + DNp06 silenced (`looming-dnp01-silenced`, `looming-dnp01-dnp02-silenced`,
`looming-dnp01-dnp06-silenced`); and the left-eye and both-eye replays (`looming-left`,
`looming-bilateral`); and an ON edge through the right eye with graded potentials (`eye-on`,
[below](#graded-neurons)). Four comparisons pair them (below), and `cns/` holds the whole-CNS
soma layer shared by all. Their `scene.json`, `activity.bin` and run manifest are committed
in `docs/live/`; `scripts/build_live_scenes.py [NAME ...]` regenerates them from the local
tables, all or only the named ones, exporting every requested scene before it writes any, so
each manifest records a clean tree. The site build copies the page next to each scene. Geometry
is not stored: it streams from GCS as it does locally.

A scene draws the stimulus and the neurons that respond, not all 165,122. On the site a
**whole-CNS layer** adds every soma in the volume as a point, coloured by region: optic lobe
blue, central brain orange, ventral nerve cord green, descending violet, ascending red.
`scripts/build_somata.py` writes it once to `docs/live/cns/` from `somaLocation` in the
MaleCNS body annotations (1.8 MB, 140,024 somata). The 25,098 neurons without a soma in the
volume are counted in `somata.json`, not drawn: mostly sensory neurons, whose cell bodies lie
in the periphery, and optic-lobe neurons whose soma falls outside the imaged volume. The layer
is context: its points are not picked and do not show activity. `?somata=0` hides it; the
panel's "Whole CNS" folder sets opacity and point size. A local `flymsg viz` export has no
layer unless `?somata=<url>` points to a soma file. `?chrome=0` does not build the control
panel and hides the performance readout; the colour legend stays, and a page without the
flag is unchanged. The README links
add `?neuropils=1`, so the 114 brain and VNC shells outline the whole CNS around the
activity; without it a replay starts with the shells hidden. The shells stream in after the
neurons and cost GPU time while the replay plays.

## Graded neurons

Non-spiking neurons do not glow by spikes. `flymsg viz --eye POLARITY DIRECTION [--eye-config
N]` replays one edge of the locked T4/T5 protocol (`validation/t4t5.yaml`) at one of its
configurations and also writes `graded.bin`: per 10 ms bin, each graded neuron's potential
relative to rest (and, for the graded medulla under a lock that anchors it, to its settled dark
potential), as a signed step of its scale over 127. The scale, at which a neuron glows like one spike, is the
configuration's photoreceptor response for photoreceptors, its LMC range for L1–L3, and the
measured swing of the type (Groschner et al. 2022) for the medulla. A depolarized graded neuron
glows in its own colour, a hyperpolarized one in violet, so the lamina's inversion of contrast is
visible. Spiking neurons glow by spikes as everywhere else. The scene is the right eye: per
class the `--eye-top` (default 300) graded neurons whose potential moves most, at least 1 mV,
and as many spiking neurons of the T4/T5 pathway (T4/T5 included) that fire most; the selection
is written in the manifest.

## Legend and caption

Under the clock a caption says what the scene is, from its run manifest: the stimulated
types with their input rate and window, silenced types and seed (`input: LC4_R at 100 Hz for
300 of 600 ms · seed 0 · model replay`), or the cell types of an anatomy scene. A comparison
has its own panel instead. The legend follows the colouring with the same precedence: a
selection's roles, then a comparison's difference classes (more or fewer spikes in B, same,
in one export only), then the colour mode. By group, each group shows its neuron count and
its largest instances (`stimulus (55): LC4_R ×55`), so the stimulated side is visible. In a
replay a line states that the glow is spikes per bin of the model, not a recording; while
the soma layer is shown, its region colours are listed.

## Selecting a neuron

A click, the `select` field of the panel, or `?select=<bodyId|instance|type>` selects a
neuron. The panel lists its identifiers and annotations, with missing ones written as
unknown or not annotated, and its simulated rate, labelled as model output. It then lists the
ten strongest input and output cell types by synapse count, the totals over every partner
type, how many more types there are, and how many partner neurons are in the scene. Those
partners are recoloured by role (input, output, both); every other neuron stays drawn in a
dark context colour. Esc or `clear` ends the selection, and the URL keeps `?select=` so a
selection can be shared.

The counts come from `partners.json`, which `flymsg viz` writes next to `scene.json` with
`graph.partner_table`. A test checks that table against `graph.partners`, the function behind
`flymsg info`, neuron by neuron, ties included, so the panel and `flymsg info <bodyId>` show
the same numbers. The page loads the table on the first selection. It is anatomy from the
dataset, not simulation output, and it is chemical synapses only.

## Raster

In a replay, a selection also opens a raster of the selected neuron and its partners in the
scene (up to 40 rows; the rest are counted). A cell is the spike count of that neuron in one
bin of `activity.bin`, not an exact spike time. The stimulus window is shaded, and the cursor
marks the bin the 3D glow is showing: both take it from `raster.binAt`, and a node test checks
they agree at every time. Dragging on the raster moves the replay time, the arrow keys step
one bin, and a neuron with no spike is labelled so. `export` downloads the rows with the
scene manifest's commit, seeds and configuration.

## Comparing two runs

`flymsg viz-compare A B --labels … --status … [--notes …]` pairs two existing replay exports
without simulating. It refuses two runs whose dataset (name, release, file hashes) or time
base (bins, bin width, stimulus window) differ. The neuron set is the union; a neuron one
export does not hold is "not exported" there, never silent, because an export lists only the
neurons that fired during its stimulus. Each run carries a status, `validated`,
`exploratory` or `failed`, and a note; the page shows both, the dataset, and every manifest
key that differs. A failed protocol reads "failed protocol: not evidence for a mechanism".

The page switches between A, B and `|A − B|` per bin (`?run=a|b|difference`). In the
difference view, neurons are coloured by more, fewer or the same spikes in B than in A, or
grey when one export lacks them; a selected neuron lists its spikes and first bin in each
run. Two identical runs give zero difference in every bin (tested in Python and in node).

The site serves four pairs; the fourth, right against left, is described under **Sides**. [LC4_R against LC4_R with both DNp01 silenced](https://gianlucamazza.github.io/flymsg/live/looming-vs-dnp01/?run=difference&t=60&paused&select=800146)
is the failed silence check of the one-bit protocol ([behavior](behavior.md)): `TTMn_R`
fires 22 times in A, first in the 10–20 ms bin, and still 7 times in B, first in the
60–70 ms bin. [DNp01 against DNp01 + DNp02](https://gianlucamazza.github.io/flymsg/live/dnp01-vs-dnp02/?run=difference&t=60&paused&select=800146)
and [DNp01 against DNp01 + DNp06](https://gianlucamazza.github.io/flymsg/live/dnp01-vs-dnp06/?run=difference&t=60&paused&select=800146)
replay the arms of the residual partner scan on seed 0: `TTMn_R` goes from 7 spikes to 0.

`viz --sim … --keep NAMES` exports the named neurons even when they stay silent, in a group
`kept`, so a comparison shows them at zero spikes instead of "not exported". The looming
scenes keep `TTMn_R`, DNp01, DNp02 and DNp06.

**Sides.** `_R` and `_L` are the fly's right and left: seen from the front, `_R` is on the
viewer's left. The looming scenes drive one eye (`LC4_R`, 55 neurons), so the stimulus is
one-sided by design while the response spreads to both sides. The volume is one animal, not a
symmetric template: the tissue is slightly tilted and pairs differ (71 `LC4_L` against 55
`LC4_R`). `looming-left` drives `LC4_L` and `looming-bilateral` drives both, a frontal
approach; both keep `TTMn` on both sides. Seed 0, 600 ms: with `LC4_R`, `TTMn_R` fires 22
times and `TTMn_L` not at all; with `LC4_L`, `TTMn_L` fires 12 times (first in the 30–40 ms
bin) and `TTMn_R` 8; with both eyes, `TTMn_R` 24 and `TTMn_L` 12. The left motor neuron
receives fewer synapses (2,424 against 3,608), and the asymmetry follows the wiring of this
animal, not the stimulus. [Right against left](https://gianlucamazza.github.io/flymsg/live/right-vs-left/?run=difference&t=60&paused&select=804642)
compares the two one-eyed arms; [both eyes](https://gianlucamazza.github.io/flymsg/live/looming-bilateral/)
is a single scene. Exploratory replays, not scored runs.

## Replaying a native or console run

`flymsg viz --native OUTPUT FIXTURE` replays a run of the native executor or of the console worker: the `output.bin` a job returns and the `fixture.bin` it ran.

- **What it reads.** `native.as_result` turns the decoded spike counts per bin and first spikes into a `sim.Result`, and `native.stimulated` reads the fixture's stimulated rows.
- **What it shows.** The usual selection follows: the stimulated neurons, then those firing above `--min-rate` while the fixture's input lasts (up to its last step with a kick).
- **Fixture.** It must hold the whole dataset in row order, as `scripts/console_bench.py` exports it.

A 2,000-step full-connectome console run exports 856 neurons above 5 Hz.

## On an Xbox or a TV

With `?tv=1`, or in a browser whose user agent names an Xbox, the page starts in a TV layout:

- larger text in the title-safe area;
- the panel closed;
- controller hints;
- a leaner start: 1 M triangles at 512 px detail, instead of 8 M at 256 px.

`?tv=0` turns it off, and `?budget=` and `?detail=` still override the defaults. A game controller with the standard mapping drives the view (`gamepad.js`):

| Control                 | Action                   |
| ----------------------- | ------------------------ |
| Left stick              | Rotate around the target |
| Right stick or triggers | Zoom                     |
| A                       | Play or pause the replay |
| LB / RB                 | Step one bin back or on  |
| Y                       | Reset the view           |
| X                       | Clear the selection      |
| View                    | Open or close the panel  |

X clears rather than B, because Edge keeps B for going back a page.

**On an Xbox console, the 3D view does not run in the browser.** Checked on a Series S on 2026-10-15:

- **No WebGL.** Edge offers neither WebGL 1 nor WebGL 2, and the viewer needs WebGL 2.
- **Memory.** At the desktop defaults, the tab was stopped with `SBOX_FATAL_MEMORY_EXCEEDED`.
- **User agent.** It does not name the Xbox, so give the console `?tv=1`.

The page loads, but no scene is drawn. On the console, a run is watched on the worker's dashboard or replayed in a desktop browser.

The worker can open the viewer itself. That matters where its browser has WebGL, which today means the worker's desktop build.

- **The address.** It is configuration, not code: the host writes `LocalState/viewer.json` (`{"schema": "flymsg.worker_viewer/v1", "url": "http://..."}`).
- **Opening it.** The controller's Y on the worker's dashboard opens it in the browser. So does an uploaded `LocalState/open_viewer.json`, which the worker consumes.
- **Serving.** A run exported with `flymsg viz --native` can be served from the host on the local network for this.

## Phones and tablets

On a screen up to 600 px wide the control panel starts closed and the performance readout
is hidden; the clock, legend and hints stay. A touch screen gets touch hints (tap, drag,
pinch), a 12 px tap slop instead of 4 px, the panel's clear button instead of Esc, and
44 px buttons. Panels keep clear of notches through the safe-area insets. With
`prefers-reduced-motion` a replay opens paused, as with `?paused`. A dropped WebGL context,
common in a background tab on a phone, shows a notice and is restored; time spent in a
background tab does not advance the replay. These are layout and input checks in an emulated
390×844 viewport; frame rates on a real phone are not measured yet (#24).

## Optional WebXR observation (experimental)

Quest 2 development setup, the session-wide measurement collector and the qualification
criteria are in the [VEE qualification runbook](vee-qualification.md). An available headset
is not a passed hardware trial.

The first Quest 2 default-scene trial (2026-10-15) failed the timing gate; the
[raw diagnostic](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/quest2-first-diagnostic-2026-10-15.json) is retained. No Quest 2
configuration is qualified yet. Desktop frame measurements now distinguish continuous
rendering from on-demand idle redraws explicitly: slow active frames are retained even
without a GPU timer, while idle redraws display `idle` instead of a stale frame rate.

`?xr=1` adds an Enter VR button when the browser reports `immersive-vr` support, for example
`live/looming/?xr=1&paused`; without the flag nothing changes, and with `?chrome=0` the button
is not built. No session is requested on load: the reader starts and ends it, and a browser
without immersive VR keeps the desktop view and says so. In a session the whole scene is scaled
from micrometres to about 1.2 m and placed 2 m in front of the headset's starting point; that
transform is display-only. three.js renders the two eye views directly, so the glow shows
without the bloom halo and without MSAA, and clicks do not select neurons. Ending the session
restores the scene, the desktop camera and the orbit controls. The observer replays existing
exports and never runs the simulation. It is experimental and qualified on no headset: stereo,
frame times against the stereo budget (this page's laptop baseline is far below it, see
[measurements](#measurements)) and the session lifecycle on real hardware are open in
[#177](https://github.com/gianlucamazza/flymsg/issues/177). The decision is in the
[ADR](adr-virtual-experimental-environment.md).

## Sources

| data            | format                                                     | use                                                                      |
| --------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------ |
| neuron surfaces | `neuroglancer_multilod_draco`, sharded (murmurhash3, gzip) | octree LOD, Draco decoded in workers                                     |
| skeletons       | Neuroglancer precomputed skeletons, unsharded              | fallback beyond the triangle budget, and placeholder while surfaces load |
| neuropils       | 114 legacy single-resolution meshes (brain + VNC ROIs)     | translucent context shells                                               |

## Pipeline

1. **Selection** (`lod.js`), when the camera settles (≤ 4 Hz while it moves): neurons in
   priority order (stimulus first, then rate × projected size) get the finest octree
   fragments whose chunks stay under `detail` px, coarsened step by step until they fit the
   triangle budget; a neuron that does not fit even at its coarsest LOD is drawn as its
   skeleton. The budget is derived from the real capacity of the GPU buffers with learned
   ratios (triangles per compressed byte, vertices per triangle).
2. **Surfaces**: fragments are fetched with merged Range requests, decoded by
   `DRACOLoader`, then dequantized and given normals in a module worker pool
   (`geometry-worker.js`). All of them live in one `THREE.BatchedMesh`; a neuron's new
   selection is swapped in atomically. Winding is outward counter-clockwise (checked with the
   signed volume from the centroid, `?check`), so back faces are culled.
3. **Skeletons**: every skeleton gets levels of detail in the worker (`skeletonLevels`):
   unbranched paths between branch points and ends are simplified with Douglas-Peucker at
   tolerances 32 nm × 2^l. A level is drawn only while its tolerance projects to ≤ ½ device
   pixel at the neuron's nearest point, so the image matches the full skeleton to within half
   a pixel and zooming in brings back every source vertex. All skeletons share one vertex
   buffer and draw in a single call; the index lists the current level of every skeleton that
   is on, so hidden ones cost nothing.
4. **Replay**: activity per neuron (spikes decayed with τ 15 ms) goes to per-instance and
   per-neuron textures, uploaded only when the replay time changes. Active neurons glow in
   their colour (bloom above threshold 1); silent surfaces and skeletons are desaturated and
   see-through (screen-door dither, `silent surfaces` in the GUI, default 0.3), so large or
   dense silent neurons do not hide activity behind them.
5. **Colours**: by group, transmitter, cell type, or the sex annotations (`dimorphism`:
   male-specific / dimorphic, "potentially" calls included; `fru/dsx`: fru / dsx / both),
   from `colors.js`; `?color=` picks the initial mode.
6. **Picking**: an 11 × 11 px render of neuron ids under the cursor (surfaces and skeletons).

## Rendering quality

The page renders on demand: every frame while the camera moves or a replay plays, otherwise
only after the scene changed. At rest frames get 4× MSAA at the native pixel ratio. While
frames are live and over the 60 fps budget, MSAA goes first, then the pixel ratio scales down
(to 0.5×), but a lower ratio is kept only if it really shortens the frame; at rest full quality
returns. Geometry is never reduced to meet a frame rate.

Multisampling belongs to the scene target, not to the composer. The scene is resolved into the
single-sampled buffers, and bloom samples only that picture: pixels above threshold 1, blurred
through five mips, added back on top.

The widest of those mips is an 11-tap blur into a target about 44×29. That pass wrote NaN on
this GPU. The composite stretched the NaN across the empty part of the frame, and the additive
copy turned those pixels black, so a paused pIP10 replay went black while the page still
counted its surfaces. With bloom off, the same frame (4× MSAA still on) is the whole circuit.
The blur inlines its weights and unrolls the taps, and a non-finite sample adds nothing, so
one bad mip cannot erase the picture.

The clip planes track the camera. The volume is a sphere about the origin, and near/far bracket
that sphere, so the depth buffer covers the CNS. A fixed far plane of 50 mm left the whole
volume in the last fraction of the depth range.

## Measurements

Intel Iris Xe (TGL GT2), Chromium with ANGLE on OpenGL, 1400 × 900, replay of LC4_R playing
(2,740 neurons: 78 surfaces with 7.2 M triangles, 2,662 skeletons), `?bench=110` after
loading, same conditions for both columns ("before" is commit `da10e5d`, which had no MSAA
in effect: the composer's targets were not multisampled):

|                         | before | now               |
| ----------------------- | ------ | ----------------- |
| GPU frame (p50)         | 71 ms  | 52 ms             |
| fps (p50)               | 12     | 18                |
| CPU frame (p50)         | 25 ms  | 1 ms              |
| draw calls              | 2,677  | 16                |
| skeleton segments drawn | 18.9 M | 10.2 M (½ px LOD) |

Cost split of one frame (ratio 1): surfaces 10 ms, skeletons 24 ms (94 ms as 2,662 separate
full-resolution draws), post-processing 2 ms,
4× MSAA +33 ms (the lines), neuropils +40 ms (11.3 M translucent triangles; hidden by default
in replays, `?neuropils=1`). Skeleton cost does not scale with the pixel ratio (it is bound by
primitive count), which is why the adaptive step checks that a lower ratio pays off. An
anatomy view (LC4 → DNp01 → TTMn with all neuropils) takes ~30 ms per frame.

Reproduce headless on the real GPU:

```bash
GL=gl node scripts/shoot.mjs "http://127.0.0.1:8000/?bench=110" out.png 115
```

`GL=vulkan` uses ANGLE on Vulkan, the default `GL=swiftshader` software rendering.

### Baseline of the live scenes (issue #24)

Same laptop and backend, 1400 × 900, `scripts/bench_viewer.py` at commit `2574001`: five
complete runs on 2026-10-13, each scene opened for 30 s in a fresh profile and then reloaded
(warm cache). A pass counts when other processes used at most one core on average during it;
23 of the 30 warm passes did. Ranges over those passes (minimum–maximum):

| scene             | passes | fps p50   | GPU frame p50 | first surface | all represented |
| ----------------- | ------ | --------- | ------------- | ------------- | --------------- |
| looming           | 4      | 13.3–27.5 | 21–45 ms      | 2.54–3.77 s   | 19.55–25.07 s   |
| song              | 4      | 29.2–39.1 | 20–27 ms      | 1.12–3.09 s   | 2.03–5.56 s     |
| anatomy           | 4      | –         | 21–22 ms      | 1.29–1.91 s   | 0.51–0.52 s     |
| looming-bilateral | 3      | 15.5–15.8 | 28–32 ms      | 2.54–2.88 s   | –               |
| dnp01-vs-dnp02    | 4      | 13.6–34.1 | 24–42 ms      | 1.19–3.62 s   | 10.52–26.09 s   |
| right-vs-left     | 4      | 13.8–16.8 | 25–35 ms      | 2.04–2.84 s   | –               |

The frame rate of one scene varies up to 2.5× between idle passes drawing the same
triangles, with the GPU time following it: the noise is the laptop GPU's, not the load of
other processes, so no tolerance narrower than these ranges can be stated from this machine.
anatomy redraws only on change, so its passes hold one frame interval, not a frame rate;
looming-bilateral and right-vs-left do not finish loading every neuron within 30 s. Cold
passes include the download and are not part of the baseline. The runs are in
[`docs/evidence/viewer-bench-2026-10-13/`](https://github.com/gianlucamazza/flymsg/tree/main/docs/evidence/viewer-bench-2026-10-13). Compare a new
run with them:

```bash
GL=gl uv run python scripts/bench_viewer.py --cooldown 3600
uv run python scripts/bench_check.py runs/viewer-bench/<time>.jsonl
```

`bench_check.py` exits 1 when an fps p50 falls below the range or a load mark lands after
it. With three or four passes per scene that is a reason to look, not proof of a
regression: an interrupted run from the same day already fell outside the ranges, on the
better side. A physical phone has not been measured yet.
