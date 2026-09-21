# Model

`flymsg sim` runs a leaky integrate-and-fire (LIF) network with one unit per traced neuron
(165,122) and one synaptic weight per connection (25.6M). It follows the whole-brain model of
Shiu et al. (_Nature_ 2024, built on the female FlyWire brain), extended to the whole male CNS,
with one change of scale: the synapse weight is divided by the ratio of synapse detection
density between the datasets (an optional adaptive threshold, used until v0.4, is off by
default). Code: `src/flymsg/sim.py`.

The model predicts **which circuits a stimulus recruits and in what order**. It does not
predict exact firing rates: there is no dendritic geometry, neuromodulation, plasticity or gap
junctions, and the parameters are shared by all neurons.

## Dynamics

For neuron _i_ with membrane potential _v_, synaptic drive _g_ and threshold offset _θ_:

```
dv/dt = (g − (v − v_rest)) / τ_m          (v and g frozen during the refractory period)
dg/dt = −g / τ_syn
dθ/dt = −θ / τ_th

if v > v_th + θ:  spike;  v ← v_rest;  g ← 0;  refractory for t_ref;  θ ← θ + th_jump
```

A spike of presynaptic neuron _j_ reaches _i_ after a fixed `delay` and adds
`sign_j · n_ij · w_syn` to _g_i_, where `n_ij` is the synapse count of the connection.
Stimulated neurons get independent Poisson input spikes at `--rate` Hz, each adding
`poisson_scale · w_syn` (68.75 mV) directly to _v_, and have no refractory period, so they
fire once per input spike.

The update reproduces the published brian2 model (Shiu et al. repository, `model.py`,
`method='linear'`, default schedule) with a fixed step `dt` = 0.1 ms. Each step, in order:

1. state update of non-refractory neurons, integrated exactly (the pair _v_, _g_ is linear);
   _θ_ decays;
2. threshold: non-refractory neurons with _v_ > `v_th` + _θ_ spike;
3. synaptic delivery: spikes emitted `delay` ago add to _g_ of non-refractory neurons (input
   reaching a refractory neuron is lost, as brian2 does for these equations: checked directly,
   a 5 mV input arriving 0.2 ms after a spike leaves _g_ at 0); Poisson input adds to _v_;
4. reset of the spiking neurons (_v_ and _g_).

Input that arrives in the step of a neuron's own spike is wiped by the reset, as in brian2;
for a stimulated neuron this loses about `rate · dt` of its input (1 % at 100 Hz). Spikes in
flight sit in a ring buffer of `delay / dt` steps. A neuron that spikes at step _s_ integrates
again from step _s_ + `t_ref / dt` (21 frozen steps for 2.2 ms), as in brian2.

Until 2026-09-21 the engine differed in six points (input into _g_, no reset of
_g_, _g_ decaying while refractory, stimulated neurons refractory, synaptic input kept while
refractory, one extra refractory step), which made stimulated neurons fire about twice the
input rate; see the [findings log](validation.md#findings-log) and
[comparison](comparison.md#engine-check).

## Parameters

| Parameter                 |                                               Value | CLI flag    | Source                                   |
| ------------------------- | --------------------------------------------------: | ----------- | ---------------------------------------- |
| `v_rest` (also the reset) |                                              −52 mV |             | Shiu et al. 2024                         |
| `v_th`                    |                                              −45 mV |             | Shiu et al. 2024                         |
| `tau_m`                   |                                               20 ms |             | Shiu et al. 2024                         |
| `tau_syn`                 |                                                5 ms |             | Shiu et al. 2024                         |
| `t_ref`                   |                                              2.2 ms |             | Shiu et al. 2024                         |
| `delay`                   |                                              1.8 ms |             | Shiu et al. 2024                         |
| `w_syn`                   |           0.192 mV per synapse (0.275 / 1.43) | `--w-syn`   | Shiu et al. 2024 (0.275 on FAFB), scaled for MaleCNS synapse density; model selection + replication |
| `poisson_scale`           |  250 (one input spike = 48 mV at default `w_syn`) |             | Shiu et al. 2024                         |
| `th_jump`                 |                         0 (off; 2.0 in v0.3–v0.4) | `--th-jump` | **flymsg**, optional compensation        |
| `tau_th`                  |                                              100 ms |             | **flymsg**                               |
| `dt`                      |                                              0.1 ms |             | Shiu et al. 2024                         |

Scale check: one synapse moves a resting _v_ by at most 0.043 mV (peak 9.2 ms after the spike,
`w_syn · τ_syn/(τ_m − τ_syn) · (e^(−t/τ_m) − e^(−t/τ_syn))`), so a silent neuron needs about 160
coincident synapses to cross the 7 mV gap to threshold.

## Synapse sign

The sign comes from the presynaptic neuron's predicted transmitter (`consensus_nt`):

| Transmitter                     | Sign | Why                                                                         |
| ------------------------------- | ---: | --------------------------------------------------------------------------- |
| acetylcholine                   |   +1 | fast nicotinic excitation                                                   |
| GABA                            |   −1 | GABA-A chloride channels                                                    |
| glutamate                       |   −1 | GluCl, the dominant central glutamate receptor in flies (as in Shiu et al.) |
| histamine                       |   −1 | HisCl chloride channels (e.g. photoreceptors → lamina)                      |
| dopamine, octopamine, serotonin |    0 | metabotropic modulators, no fast effect                                     |
| unclear, missing                |    0 | unknown                                                                     |

4,143 traced neurons get sign 0 and have no effect on their targets. Of these, the 3,602
`unclear`/missing ones send only 1.65% of all synapses (modulatory neurons another 0.95%), and
the release offers no better label for them: their cell-type-level prediction is also
unclear or modulatory, and only 107 have a neuron-level fast-transmitter prediction with
confidence ≥ 0.65. Re-signing them is therefore not worth the added uncertainty. Motor neurons are
glutamatergic, which only matters where they synapse onto central neurons.

## Stimulus and rates

- `--rate` is the rate of the Poisson input; stimulated neurons fire at that rate (minus the
  ~`rate · dt` share lost to the reset, see above).
- `--stim-ms` stops the input early, which lets you measure decay and self-sustained activity.
- Results are binned (default 10 ms). `sim` reports per type the stimulus-window rate with all
  neurons of the type counted (silent ones included), the share of seeds where the type fired
  (`p_active`), the across-seed SD, the latency of its earliest neuron, and the post-stimulus
  rate.
- **Self-sustained** neurons are those still firing from `stim end + 100 ms` to the end of the
  run.

## Synapse weight: scaled for synapse density

MaleCNS neurons carry a median 1.81× the synapses of their FAFB counterparts (7,327 matched
types; interquartile range of the per-type ratio about 1.4–2.4), a methodological difference
between the reconstructions (docs/comparison.md). Shiu's `w_syn` 0.275 was tuned on FAFB, so
in MaleCNS it acts like a ~1.8× stronger synapse. The default divides it by 1.43, the lower
quartile of the ratio: of the density-scaled variants this one passed every validation check
(29/29) at the model selection and again on fresh seeds and controls (docs/validation.md).
The median ratio (1.81, `w_syn` 0.152) fails sugar → MN9. Even a stimulated neuron's kick
(`poisson_scale · w_syn` = 48 mV) stays far above the 7 mV gap, so stimulated neurons still
fire once per input spike.

## Adaptive threshold (optional; off by default since v0.5)

With Shiu's FAFB weight (0.275) and no adaptation, the whole male CNS falls into
self-sustained activity after a strong stimulus: thousands of neurons keep firing once the
input stops, most of them Kenyon cells with antennal-lobe and central-complex neurons. Until
v0.4 flymsg compensated with an adaptive threshold: each spike raises that neuron's threshold
by `th_jump` (2 mV from calibrate-v3; 6 mV with the engine before the fidelity fix), relaxing
with τ = 100 ms, stimulated neurons exempt. It is a standard spike-frequency adaptation
mechanism, not a measured property of fly neurons, and it stood in for what the connectome
cannot provide (gap junctions, neuromodulation, intrinsic properties, the real balance of
recurrent inhibition).

The runaway turned out to come from the synapse scale, not the ventral nerve cord: with the
density-scaled weight the plain model stays stable (zero self-sustained neurons in every
validation case). The adaptive threshold is therefore off by default and kept as an option;
`--th-jump 2 --w-syn 0.275` restores the v0.3–v0.4 model.

## Performance

One compiled kernel (numba) on one core: about 5 s per simulated second for the whole CNS,
2× the previous vectorised NumPy loop, whose spikes it reproduces exactly (same operations,
order and float32/float64 rounding; `tests/reference_sim.py` keeps that loop as the oracle).
Parallel commands (`calibrate`, `select-model`, `dimorphism --silencing`) run one process per
worker. Time grows
with the number of spikes, because each step sums the weight columns of the neurons that
spiked. `calibrate` runs parameter sets in parallel processes.

## Reference

Shiu, P. K. et al. A _Drosophila_ computational brain model reveals sensorimotor processing.
_Nature_ (2024).
