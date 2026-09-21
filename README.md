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

The data directory defaults to `./data`; override with `--data DIR` or `FLYMSG_DATA`.

Neurons are addressed by cell type (`LC4`), instance (`LC4_R`) or bodyId (`10001`).

## Commands

```bash
uv run flymsg info DNp01                  # annotations, top up/downstream types, Neuroglancer link
uv run flymsg path LC4 TTMn               # strongest chain between two populations
uv run flymsg sim LC4_R --rate 100 --duration 500 \
    --superclass descending_neuron vnc_motor   # LIF simulation, report responding types
```

`path` minimises the sum of `-log(input fraction)`: each hop is the one that carries the largest
share of the next neuron's input. Edges below `--min-weight` synapses are not traversed but still
count in each neuron's input total.
`LC4 → DNp01 (Giant Fiber) → TTMn` recovers the textbook looming-escape circuit.

`sim` is the leaky integrate-and-fire model of Shiu et al. (Nature 2024): synapse sign from the
predicted transmitter (ACh +, GABA/Glu/histamine −, modulators and "unclear" 0), `--w-syn` mV per
synapse, Poisson drive on the stimulated neurons (each input spike weighs 250 × `w_syn`).
`--rate` is the *input* rate: one Poisson kick triggers a short burst, so stimulated neurons fire
about twice as fast (≈ 200 Hz at `--rate 100`). `--stim-ms` gives a pulse instead of a sustained
input, `--out rates.csv` dumps per-neuron rates. The summary lists, per type, all neurons (`n`),
those that fired (`active`), and mean/max rate over all of them.

### Adaptive threshold (deviation from Shiu)

With plain Shiu parameters (`--th-jump 0`) the whole CNS falls into self-sustained activity:
Shiu tuned the model on the brain alone, and adding the VNC raises the recurrent gain. Each spike
now raises the neuron's threshold by `--th-jump` mV, relaxing with τ = 100 ms; stimulated neurons
are exempt so the drive stays as requested.

Neurons still firing 400–700 ms after a 300 ms pulse:

| stimulus          | th_jump 2 | th_jump 4 (default) | th_jump 6 |
| ----------------- | --------: | ------------------: | --------: |
| LC4_R @ 100 Hz    |     7,744 |                  65 |         0 |
| DNp01 @ 150 Hz    |        80 |                   0 |         0 |

4 mV is the smallest value that stops the runaway on both stimuli while keeping the
LC4 → Giant Fiber → TTMn response. It is calibrated on two stimuli only, not on physiology.

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
