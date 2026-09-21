# Model

`flymsg sim` runs a leaky integrate-and-fire (LIF) network with one unit per traced neuron
(165,122) and one synaptic weight per connection (25.6M). It follows the whole-brain model of
Shiu et al. (_Nature_ 2024, built on the female FlyWire brain), extended to the whole male CNS,
plus one deliberate addition: an adaptive threshold. Code: `src/flymsg/sim.py`.

The model predicts **which circuits a stimulus recruits and in what order**. It does not
predict exact firing rates: there is no dendritic geometry, neuromodulation, plasticity or gap
junctions, and the parameters are shared by all neurons.

## Dynamics

For neuron _i_ with membrane potential _v_, synaptic drive _g_ and threshold offset _θ_:

```
dv/dt = (g − (v − v_rest)) / τ_m          (frozen at v_rest during the refractory period)
dg/dt = −g / τ_syn
dθ/dt = −θ / τ_th

if v ≥ v_th + θ:  spike;  v ← v_rest;  refractory for t_ref;  θ ← θ + th_jump
```

A spike of presynaptic neuron _j_ reaches _i_ after a fixed `delay` and adds
`sign_j · n_ij · w_syn` to _g_i_, where `n_ij` is the synapse count of the connection.
Stimulated neurons get independent Poisson input spikes at `--rate` Hz, each adding
`poisson_scale · w_syn` to _g_.

Integration uses a fixed step `dt` = 0.1 ms: forward Euler for _v_, exact exponential decay for
_g_ and _θ_. Spikes in flight sit in a ring buffer of `delay / dt` steps. Each step, in order:
deliver delayed spikes → add Poisson input → update _v_ of non-refractory neurons → decay _g_
and _θ_ → detect spikes.

## Parameters

| Parameter                 |                                               Value | CLI flag    | Source                                   |
| ------------------------- | --------------------------------------------------: | ----------- | ---------------------------------------- |
| `v_rest` (also the reset) |                                              −52 mV |             | Shiu et al. 2024                         |
| `v_th`                    |                                              −45 mV |             | Shiu et al. 2024                         |
| `tau_m`                   |                                               20 ms |             | Shiu et al. 2024                         |
| `tau_syn`                 |                                                5 ms |             | Shiu et al. 2024                         |
| `t_ref`                   |                                              2.2 ms |             | Shiu et al. 2024                         |
| `delay`                   |                                              1.8 ms |             | Shiu et al. 2024                         |
| `w_syn`                   |                                0.275 mV per synapse | `--w-syn`   | Shiu et al. 2024; checked by calibration |
| `poisson_scale`           | 250 (one input spike = 68.75 mV at default `w_syn`) |             | Shiu et al. 2024                         |
| `th_jump`                 |                                    6.0 mV per spike | `--th-jump` | **flymsg**, calibrated (calibrate-v2)    |
| `tau_th`                  |                                              100 ms |             | **flymsg**                               |
| `dt`                      |                                              0.1 ms |             | Shiu et al. 2024                         |

Scale check: one synapse moves _v_ by about `w_syn · τ_syn / τ_m` ≈ 0.07 mV, so a silent neuron
needs roughly 100 coincident synapses to cross the 7 mV gap to threshold.

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

- `--rate` is the rate of the Poisson **input**, not the firing rate of stimulated neurons.
  Each 68.75 mV kick triggers about two spikes on average, so at `--rate 100` stimulated
  neurons fire at about 200 Hz (measured on LC4_R).
- `--stim-ms` stops the input early, which lets you measure decay and self-sustained activity.
- Results are binned (default 10 ms). `sim` reports per type the stimulus-window rate with all
  neurons of the type counted (silent ones included), the share of seeds where the type fired
  (`p_active`), the across-seed SD, the latency of its earliest neuron, and the post-stimulus
  rate.
- **Self-sustained** neurons are those still firing from `stim end + 100 ms` to the end of the
  run.

## Adaptive threshold (deviation from Shiu)

With plain Shiu parameters (`--th-jump 0`), the whole CNS falls into self-sustained activity
after a strong stimulus: thousands of neurons keep firing once the input stops, most of them
Kenyon cells of the mushroom body together with antennal-lobe and central-complex neurons.
Shiu et al. tuned the model on the brain alone. The likely cause is the added recurrence
of the ventral nerve cord, but this has not been tested in isolation.

Each spike therefore raises that neuron's threshold by `th_jump`, and the offset relaxes with
τ = 100 ms. This is a standard spike-frequency adaptation mechanism, not a measured property of
fly neurons. **Stimulated neurons are exempt**, so the input rate stays as requested.

**This is a compensation, named as such.** It stands in for what the connectome cannot
provide: gap junctions, neuromodulation, per-cell intrinsic properties and the real balance of
recurrent inhibition. Its value, 6 mV, is chosen by grid search against the validation battery
(calibrate-v2, see [validation](validation.md)), not measured in flies. `--th-jump 0` restores
the published model.

## Performance

Pure NumPy/SciPy on one core: about 20 s per simulated second for the whole CNS. Time grows
with the number of spikes, because each step sums the weight columns of the neurons that
spiked. `calibrate` runs parameter sets in parallel processes.

## Reference

Shiu, P. K. et al. A _Drosophila_ computational brain model reveals sensorimotor processing.
_Nature_ (2024).
