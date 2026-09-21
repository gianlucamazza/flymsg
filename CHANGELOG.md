# Changelog

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
- GF → TTMn evaluated against *shak-B²* physiology; kept as a documented limit.

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
