# 3D view

`flymsg viz` writes only `scene.json` (neurons, groups, rates) and, for a replay,
`activity.bin` (spike counts per 10 ms bin). The page (`src/flymsg/viz_static/`) streams all
geometry at source resolution from the public MaleCNS volumes on GCS
(`gs://flyem-male-cns/v1.0/segmentation`, CORS and Range requests, no token). Example frames,
and what each colour means, are in the README gallery.

## Live on the site

The Pages site serves three scenes with this page: the LC4_R and pIP10 replays and the
pIP10/dPR1/dMS9 anatomy, at <https://gianlucamazza.github.io/flymsg/live/looming/>,
`…/live/song/` and `…/live/anatomy/`. Their `scene.json`, `activity.bin` and run manifest
are committed in `docs/live/`; `scripts/build_live_scenes.py` regenerates them from the
local tables with the gallery commands, exporting every scene before it writes any, so each
manifest records a clean tree. The site build copies the page next to each scene. Geometry
is not stored: it streams from GCS as it does locally.

A scene draws the stimulus and the neurons that respond, not all 165,122. The README links
add `?neuropils=1`, so the 114 brain and VNC shells outline the whole CNS around the
activity; without it a replay starts with the shells hidden. The shells stream in after the
neurons and cost GPU time while the replay plays.

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
