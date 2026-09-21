# flymsg

Explore and simulate the complete male _Drosophila_ CNS connectome
([MaleCNS v1.0](https://janelia-flyem.github.io/male-cns/), Janelia FlyEM + Google, CC-BY 4.0):
165,122 traced neurons, 25.6M connections, 124M synapses, brain + optic lobes + ventral nerve cord.

## Setup

```bash
uv sync
uv run flymsg fetch   # ~1.1 GB of Feather tables into data/raw/, no token needed
uv run flymsg build   # compact to data/neurons.parquet + data/edges.parquet (~10 s)
```

Neurons are addressed by cell type (`LC4`), instance (`LC4_R`) or bodyId (`10001`).

## Commands

```bash
uv run flymsg info DNp01                  # annotations, top up/downstream types, Neuroglancer link
uv run flymsg path LC4 TTMn               # strongest chain between two populations
uv run flymsg sim LC4_R --rate 100 --duration 500 \
    --superclass descending_neuron vnc_motor   # LIF simulation, report responding types
```

`path` minimises the sum of `-log(input fraction)`: each hop is the one that carries the largest
share of the next neuron's input (edges below `--min-weight` synapses are ignored).
`LC4 → DNp01 (Giant Fiber) → TTMn` recovers the textbook looming-escape circuit.

`sim` is the leaky integrate-and-fire model of Shiu et al. (Nature 2024): synapse sign from the
predicted transmitter (ACh +, GABA/Glu/histamine −, modulators 0), `w_syn` mV per synapse,
Poisson drive on the stimulated neurons. `--stim-ms` gives a pulse instead of a sustained input,
`--out rates.csv` dumps per-neuron rates.

### Adaptive threshold (deviation from Shiu)

With plain Shiu parameters (`--th-jump 0`) the whole CNS falls into self-sustained activity:
after a 300 ms LC4 pulse, ~12.6k neurons (most Kenyon cells, central-complex ring) keep firing.
Shiu tuned the model on the brain alone; adding the VNC changes the recurrent gain. A 2 mV
spike-triggered threshold increase (τ 100 ms, default) cuts the late activity to ~80 neurons
(mostly flight motor neurons) while keeping the LC4 → Giant Fiber → TTMn response.

## Limits

- One animal: no inter-individual variability.
- Wiring only: no gap junctions, neuromodulation, or plasticity; transmitter identity is a
  prediction and motor neurons are glutamatergic (their sign only matters for central targets).
- Rates are qualitative: use the model to rank which circuits a stimulus recruits, not to
  predict exact firing.

## Tests

```bash
uv run pytest
```
