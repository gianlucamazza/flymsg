# flymsg

Explore, simulate and view in 3D the complete male _Drosophila_ central nervous system
([MaleCNS v1.0](https://janelia-flyem.github.io/male-cns/), Janelia FlyEM + Google, CC-BY 4.0):
165,122 traced neurons, 25.6M connections, 124M synapses, brain + optic lobes + ventral nerve cord.

## Setup

```bash
uv sync
uv run flymsg fetch   # ~1.1 GB of Feather tables into data/raw/, no token needed
uv run flymsg build   # compact to data/neurons.parquet + data/edges.parquet (~10 s)
```

The data directory defaults to `./data`; override with `--data DIR` or `FLYMSG_DATA`.
Neurons are addressed by cell type (`LC4`), instance (`LC4_R`) or bodyId (`10001`).

## Commands

```bash
uv run flymsg info DNp01                 # annotations, top partner types, Neuroglancer link
uv run flymsg path LC4 TTMn --alt 3      # LC4 -> DNp01 (Giant Fiber) -> TTMn, then via DNp02, DNp11
uv run flymsg sim LC4_R --duration 600 --stim-ms 300 --seeds 3 \
    --superclass descending_neuron vnc_motor   # simulate, report responding types per window
uv run flymsg validate                   # battery of known circuits + controls (~3 min)
uv run flymsg calibrate                  # grid search of the model parameters (~45 min)
uv run flymsg viz --sim LC4_R            # 3D replay; also --path SRC DST, --types ...
python -m http.server -d runs/viz 8000   # then open http://localhost:8000
```

- **path** follows, hop by hop, the connection carrying the largest share of the next neuron's
  input (cost `-log(input fraction)` over each neuron's full input); `--alt K` lists further
  routes, each avoiding the intermediate cell types of the previous ones.
- **sim** is a whole-CNS leaky integrate-and-fire model after Shiu et al. (_Nature_ 2024),
  with one named compensation, an adaptive threshold (`th_jump` 6 mV), for biology the
  connectome does not contain. `--rate` is the Poisson _input_ rate (stimulated neurons fire
  ≈ 2×). The summary gives per type: share of seeds active, mean ± SD rate with silent neurons
  counted, latency, post-stimulus rate, and how many neurons stay self-sustained.
- **validate** passes 16/16 with the defaults: looming escape, Giant Fiber output, P1
  courtship drive and pIP10 song pathway, each with a size-matched random control and a
  stability check. **calibrate** re-derives the defaults with a pre-registered rule.
- **viz** exports only metadata and activity; the page streams the real neuron surfaces
  (multi-resolution Draco meshes), skeletons and neuropils straight from the public volumes on
  GCS, refining detail near the camera within a triangle budget; neurons beyond the budget are
  drawn as skeletons, simplified only below half a pixel on screen. Replays include every
  neuron that fired; silent neurons are see-through so the activity stays visible. Rendering
  is on demand, with 4× MSAA at rest and adaptive quality while moving. The HUD shows fps,
  CPU/GPU frame time, draw calls, triangles and lines. URL options: `?t=<ms>&paused`,
  `?neuropils=0|1`, `?budget=<M triangles>`, `?detail=<px>`, `?adaptive=0`, `?bench=<s>` (log
  a JSON performance summary after that many seconds). See [docs/viz.md](docs/viz.md).

## Documentation

- [docs/data.md](docs/data.md): source, files, filtering, schema, citation
- [docs/model.md](docs/model.md): equations, parameters and their origin, synapse signs,
  the adaptive-threshold compensation
- [docs/validation.md](docs/validation.md): protocol, cases, calibration, findings log
  (including the negative results)
- [docs/viz.md](docs/viz.md): 3D view pipeline, levels of detail, rendering quality,
  measurements on an Iris Xe

## Limits

- One animal; wiring only (no gap junctions, neuromodulation, plasticity); transmitters are
  predictions.
- One weight per synapse: giant synapses are underweighted (GF → TTMn needs several summed
  spikes, first spike at ~19 ms instead of a few ms).
- Rates are qualitative: use the model to rank which circuits a stimulus recruits and in what
  order, not to predict exact firing.

## Tests

```bash
uv run pytest            # Python + browser-module tests (node --test tests/js)
uv run pytest -m slow    # plus the full validation battery and a live read from GCS
```

Browser dependencies (three.js 0.170.0, lil-gui 0.20.0) are vendored by
`scripts/vendor-js.sh`; `node scripts/shoot.mjs <url> <png> [wait]` screenshots the 3D view
headless with its console output (`GL=gl|vulkan` renders on the real GPU instead of
SwiftShader, `CLICK=x,y` clicks first, `EVAL=<js>` evaluates in the page;
`?check` logs pick results and surface winding and exposes `window.flymsg` for diagnostics).

## Citation

Data: _Sexual dimorphism in the complete connectome of the Drosophila male central nervous
system_, Cell (2026), and the bioRxiv preprint doi:10.1101/2025.10.09.680999. Model after Shiu,
P. K. et al., _Nature_ (2024).
