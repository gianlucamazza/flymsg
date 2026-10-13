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
`poisson_scale · w_syn` (48.1 mV at the default `w_syn`) directly to _v_, and have no refractory period, so they
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

| Parameter                 |                                              Value | CLI flag    | Source                                                                                              |
| ------------------------- | -------------------------------------------------: | ----------- | --------------------------------------------------------------------------------------------------- |
| `v_rest` (also the reset) |                                             −52 mV |             | Shiu et al. 2024                                                                                    |
| `v_th`                    |                                             −45 mV |             | Shiu et al. 2024                                                                                    |
| `tau_m`                   |                                              20 ms |             | Shiu et al. 2024                                                                                    |
| `tau_syn`                 |                                               5 ms |             | Shiu et al. 2024                                                                                    |
| `t_ref`                   |                                             2.2 ms |             | Shiu et al. 2024                                                                                    |
| `delay`                   |                                             1.8 ms |             | Shiu et al. 2024                                                                                    |
| `w_syn`                   |                0.192 mV per synapse (0.275 / 1.43) | `--w-syn`   | Shiu et al. 2024 (0.275 on FAFB), scaled for MaleCNS synapse density; model selection + replication |
| `poisson_scale`           | 250 (one input spike = 48.1 mV at default `w_syn`) |             | Shiu et al. 2024                                                                                    |
| `th_jump`                 |                          0 (off; 2.0 in v0.3–v0.4) | `--th-jump` | **flymsg**, optional compensation                                                                   |
| `tau_th`                  |                                             100 ms |             | **flymsg**                                                                                          |
| `dt`                      |                                             0.1 ms |             | Shiu et al. 2024                                                                                    |

Scale check: at the default `w_syn` one synapse moves a resting _v_ by at most 0.030 mV
(peak 9.2 ms after the spike, `w_syn · τ_syn/(τ_m − τ_syn) · (e^(−t/τ_m) − e^(−t/τ_syn))`
with τ_m 20 ms, τ_syn 5 ms), so a silent neuron needs about 230 coincident synapses to cross
the 7 mV gap to threshold. Both numbers scale with `w_syn`: at Shiu's 0.275 they are
0.043 mV and ~160 synapses.

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
confidence ≥ 0.65. A second source changes little: 1,381 of them match a FlyWire type
(`flywireType`), 540 of those types are at least 90% one transmitter in FAFB, and 288 neurons
would get a fast one, 0.34% of all synapses; many of the rest are dopaminergic or
serotonergic there (`scripts/brain_coverage.py`). Re-signing them is therefore not worth the
added uncertainty. Motor neurons are
glutamatergic, which only matters where they synapse onto central neurons.

## Stimulus and rates

- `--rate` is the rate of the Poisson input; stimulated neurons fire at that rate (minus the
  ~`rate · dt` share lost to the reset, see above).
- `--stim-ms` stops the input early, which lets you measure decay and self-sustained activity.
- **Graded input.** `sim.run(..., kicks=K)` takes the input per step and stimulated neuron
  in units of the Poisson kick (`poisson_scale · w_syn` mV). `K` may be real, not only a
  count: the kernel adds `kick · K[t, s]` in float64 at the same phase as Poisson input, so
  integer values given as floats reproduce the Poisson run spike for spike (tested), and a
  fraction per step integrates like a current. The eye uses it for photoreceptors
  (`eye.photoreceptor_kicks`). `CpuRuntime` and the native executor accept integer counts
  only and refuse anything else.
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
(`poisson_scale · w_syn` = 48.1 mV) stays far above the 7 mV gap, so stimulated neurons still
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

## Extensions not adopted (2026-10-11)

Issue #9 asks for one added mechanism only where a measured discrepancy comes with a
parameter that transfers into this LIF. None of the four candidates has one. No variant
is added. `w_syn` and `th_jump` stay at the default.

| Candidate                    | Discrepancy already on record                                                      | Why it is not added                                                                                                                                                         |
| ---------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cell-type parameters         | One membrane time constant and one threshold for every neuron                      | MaleCNS does not measure τ_m, threshold or refractory period per type. A per-type value would be invented.                                                                  |
| Gap junctions                | GF → TTMn follows like a `shak-B²` fly, not like wild type. GF → DLMn was excluded | The published numbers are conductances fitted inside a compartmental model ([validation](validation.md)). They do not transfer, and the connectome has no electrical edges. |
| Short-term synaptic dynamics | None is measured in this repository                                                | No facilitation or depression time constant is in the tables or in a frozen protocol.                                                                                       |
| Compartments                 | One point neuron per traced cell                                                   | No compartment map is loaded by the simulator. Expanding the CNS to detailed cells is the expansion the no-go forbids.                                                      |

The looming silence failure is not a reason to add a giant-fiber gap junction. Silencing
`DNp01` removes that cell's output, chemical and electrical together. `TTMn_R` still
reaches 3 spikes, so some other partner still drives it. A synapse that starts at `DNp01`
cannot put those spikes back. Which partner is not named here: that would be a new
measurement, and it is not this decision. Issue #20 records that limit. It does not
name the partner and it does not run.

Issue #10 is closed as blocked (v0.8.9). Dopamine, octopamine and serotonin have sign 0.
The sugar and bitter cases are stimulus identity, not a feeding state. No
receptor-to-parameter map is in the repository. A variable named hunger is not this
experiment.

Issue #11 is closed as blocked (v0.8.9). No synapse set, learning rule or reinforcement
signal is specified. A network-wide STDP rule is not the task. A body is not required.
The missing piece is the evidence. #11 depends on #10 only if that modulator is the
reinforcement signal, and #10 added none.

## Dopamine-gated depression at Kenyon cell to MBON11 synapses (optional, 2026-10-13)

The evidence #11 lacked exists for one synapse set. Hige et al. 2015
(doi:10.1016/j.neuron.2015.11.003) paired a 1 s odor with four 1 ms pulses to the
PPL1-γ1pedc dopamine neurons at 2 Hz from 0.2 s after odor onset. The Kenyon cell input to
MBON-γ1pedc>α/β fell by 90 ± 3.7% in charge (n = 5), and the odor response by 80 ± 5.7% in
spikes (n = 7, 118 → 24), against 27 ± 7.1% for the unpaired odor. Pairing with the dopamine
pulses before the odor did nothing, and the depression lasted at least 40 min.

`flymsg.plasticity` applies that measurement and nothing else, locked in
[`validation/mb_plasticity.yaml`](../validation/mb_plasticity.yaml) before any run
([#85](https://github.com/gianlucamazza/flymsg/issues/85)). The depression outlasts a trial,
so it acts between trials: a pairing run records which Kenyon cells spike up to 800 ms before
a pulse, their synapses onto both MBON11 neurons (41,460 synapses from 3,623 Kenyon cells,
88–89% of MBON11's input) are scaled by 0.10 in the weight matrix, and the test runs use
that matrix. The kernel, `sim.Params` and every other protocol are unchanged; only
`flymsg mb-plasticity` applies the rule. The lock names seven compensations, among them the
shape of the eligibility window, all-or-none induction, both sides together, and no
recovery. Its test asks whether the model's MBON11 response to the paired odor drops by at
least 49.8% and the unpaired one by at most 64.6% (the measured means ∓ 2 SD), with
`ORN_VA1d` and `ORN_DL3` as the two odors by a stated rule. It is a model-side consistency
check of one rule, not a learning model of the mushroom body.

**Result of version 1 (2026-10-13): inconsistent.** The run started from `ce20fce` on `main`
(clean) and took 8 min. Before pairing, MBON11 fired 272–286 spikes to each odor; after,
0 to both, on all three seeds, so the CS+ and the CS− drop are both 100% and the CS− bound
(64.6%) fails. The descriptive columns show why: each odor recruits about 1,000 of the 4,064
Kenyon cells (25%), the two odors share 95% of them (965–998), and 1,055–1,071 Kenyon cells
were eligible. In the fly the Kenyon cell code is sparse and the two odors of the experiment
overlap by 30–33% (Hige et al. 2015, Fig 7I). The rule did what was measured; the model's odor
representation is not separated enough for it to be odor-specific. This is the same limit as
the held-out ORN_DM1 failure: excitatory Kenyon cell to Kenyon cell synapses, which a point
LIF turns into a self-sustaining loop ([benchmarks](benchmarks.md)). Nothing is retuned.
Outputs: `results/mb-plasticity/v1/`.

## Kenyon cell sparseness: the KC → KC synapses (diagnostic, 2026-10-13)

73.4% of the excitatory synapses onto Kenyon cells come from other Kenyon cells (1,153,845
of 1,572,610), and the model makes each of them a fast excitatory input. The only functional
measurement of these connections disagrees: they are axo-axonic, act through the metabotropic
receptor mAChR-B, and suppress the odor responses of neighbouring Kenyon cells (Manoim et al.
2022, doi:10.1016/j.cub.2022.09.007). The model already gives metabotropic transmission no
fast effect. [`validation/kc_sparseness.yaml`](../validation/kc_sparseness.yaml), locked
before its run ([#95](https://github.com/gianlucamazza/flymsg/issues/95)), compares four
weight matrices — default, KC → KC without fast effect, APL → KC removed, both — on the share
of Kenyon cells that respond to an odor and the share shared between two odors, against the
measured 6 ± 5% (Turner et al. 2008), at most 17% in single flies (Honegger et al. 2011),
and 64.6% shared for similar odors (Campbell et al. 2013). It diagnoses; the default model
does not change with its result.

## Recording neuron states

`flymsg trace STIM --neurons ...` (module `flymsg.tracing`) records, for chosen neurons, the
membrane potential `v`, synaptic drive `g` and threshold offset `th` (mV) at the end of every
recorded step (`--every N` steps), whether each is refractory at the next step, its spikes at
every step and the Poisson input it received. It writes `trace.npz` and a run manifest. These
are model states, not recordings.

It drives `CpuRuntime`, which advances the same compiled step loop as `sim.run` and matches it
bit for bit when run in blocks, so recording cannot change a spike; `tests/test_tracing.py`
checks the returned run against `sim.run` and the recorded `v`, `g` and `th` against the NumPy
oracle (`tests/reference_sim.py`), bit for bit, with and without the adaptive threshold. A
request above 10 M values per state array warns; above 100 M it is refused.

## Performance

One compiled kernel (numba) on one core: about 5 s per simulated second for the whole CNS,
2× the previous vectorised NumPy loop, whose spikes it reproduces exactly (same operations,
order and float32/float64 rounding; `tests/reference_sim.py` keeps that loop as the oracle).
Time grows with the number of spikes, because each step sums the weight columns of the
neurons that spiked. Parallel commands (`calibrate`, `select-model`, `dimorphism
--silencing | --loop | --by-type`) run one process per worker, started from a forkserver
(the caller holds pyarrow's threads, and forking it could deadlock) and fed the tables once.
`wiring-null` runs the validation battery twice, on one core, with the default parameters
and no worker flag. The 1,000-draw silencing tests take many CPU hours. They stop each run
at the end of the stimulus, since they use only its rates, which are identical to those of
the full run.
They report progress with a measured ETA and, with `--checkpoint FILE`, save every null
draw and resume from it. `flymsg dimorphism --progress --checkpoint FILE` shows how far a
run has got, reading the files only.

## Reference

Shiu, P. K. et al. A _Drosophila_ computational brain model reveals sensorimotor processing.
_Nature_ (2024).
