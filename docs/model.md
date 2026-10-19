# Model

`flymsg sim` runs a leaky integrate-and-fire (LIF) network with one unit per traced neuron
(165,122) and one synaptic weight per connection (25.6M). It follows the whole-brain model of
Shiu et al. (_Nature_ 2024, built on the female FlyWire brain), extended to the whole male CNS,
with one change of scale: the synapse weight is divided by the ratio of synapse detection
density between the datasets (an optional adaptive threshold, used until v0.4, is off by
default). Code: `src/flymsg/sim.py`.

The model predicts **which circuits a stimulus recruits and in what order**. It does not
predict exact firing rates: the default model has no dendritic geometry, neuromodulation, plasticity
or gap junctions (the last two exist only inside locks), and the parameters are shared by all neurons.

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
[comparison](result/comparison.md#engine-check).

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
- **Odors as receptor vectors.** `flymsg.odors` reads a DoOR odorant as one response per
  MaleCNS ORN type (receptor → glomerulus → `ORN_<glomerulus>`); a neuron-level recording
  wins over a receptor recording, else the largest co-expressed receptor. Each ORN of a type
  gets Poisson input at a rate proportional to the response, drawn per neuron by
  `odors.kicks` (equal rates reproduce `sim.poisson_kicks`). 3-octanol reaches 31 ORN types
  (1,456 neurons), 4-methylcyclohexanol 22 (1,095); receptors DoOR has not measured for an
  odorant get no input. The rate for a response of 1 is stated by each lock.
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

**Other weight rules (optional, 2026-10-13).** `sim.weight_matrix(..., post_scale=...)`
multiplies every weight onto a neuron by that neuron's value, so a lock can state a rule
other than count × `w_syn`; without it the weights are unchanged. `sim.density_scale(area,
ref)` gives the rule of Liu et al. (2022), where a unitary EPSP increases linearly with
synapse density on the postsynaptic neuron (count over surface area; they report no
count-only comparison): `ref / area`, with the
reference area stated by the lock. `scripts/mesh_area.mjs BODYID ...` measures a neuron's
surface area from its published mesh at full resolution with the viewer's own readers and
Draco decoder (DNp01_R, bodyId 10001: about 59,800 µm² over 45 M triangles); holes in a
published mesh are not closed. No rule other than count is used by any result.
`validation/weight_rule.yaml` (#139) locks the comparison of the two rules on Liu et al.'s
measured pairs before any MaleCNS count or area between those neurons is computed.

**Result of version 1 (2026-10-13): undecided.** Run from `78f0673`; 56 LHN meshes measured
before the run, none missing. On the 57 primary pairs Spearman ρ is 0.567 for count and 0.581
for density: Δρ = +0.015, 95% paired-bootstrap interval −0.011 to +0.054, so neither rule
wins and the default (count) stays. The measured-only pairs (13) give 0.813 and 0.841
(interval −0.073 to +0.168), the sensitivity set (76) 0.582 and 0.591. Pearson r² of the
amplitudes against MaleCNS density is 0.80, next to Liu et al.'s 0.77 on the hemibrain:
synapse counts from a different (male) animal rank the measured female amplitudes well, with
or without the area. As the lock states, the two rules differ only across six LHN types, so
the test has little power. Outputs: `results/weight-rule/v1.executions/…/output/`.

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

## Decision of 2026-10-11 (default model)

Issue #9 asks for one added mechanism only where a measured discrepancy comes with a
parameter that transfers into this LIF. On that date none of the four candidates had one,
and none entered the default model. `w_syn` and `th_jump` stay at the default.

Four later mechanisms stay off unless a lock names them, and none of them changes
`sim.Params`: `sim.Gap` (electrical synapses; a spike crosses only when that lock sets
`spike_mv` and `spike_ms`), `sim.Graded` (non-spiking release), `sim.Membrane` (per-neuron
membranes) and the dopamine-gated depression at Kenyon cell → MBON11. Each has its own section below. The table is the
decision of 2026-10-11. The gap-junction row is about the default model and the giant-fiber
conductance, which is still not in the model.

| Candidate                    | Discrepancy already on record                                                      | Why it is not added                                                                                                                                                         |
| ---------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cell-type parameters         | One membrane time constant and one threshold for every neuron                      | MaleCNS does not measure τ_m, threshold or refractory period per type. A per-type value would be invented.                                                                  |
| Gap junctions                | GF → TTMn follows like a `shak-B²` fly, not like wild type. GF → DLMn was excluded | The published numbers are conductances fitted inside a compartmental model ([validation](validation.md)). They do not transfer, and the connectome has no electrical edges. |
| Short-term synaptic dynamics | None is measured in this repository                                                | No facilitation or depression time constant is in the tables or in a frozen protocol.                                                                                       |
| Compartments                 | One point neuron per traced cell                                                   | No compartment map is loaded by the simulator. Expanding the CNS to detailed cells is the expansion the no-go forbids.                                                      |

The looming silence failure is not a reason to add a giant-fiber gap junction. Silencing
`DNp01` removes that cell's output, chemical and electrical together. `TTMn_R` still
reaches 3 spikes, so some other partner still drives it. A synapse that starts at `DNp01`
cannot put those spikes back. Which partner is not named in this decision: naming it
would have been a new measurement. Issue #20 recorded that limit and did not run. The
scan that later named DNp02 and DNp06 is
[behavior](result/behavior.md#residual-partner-scan).

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
LIF turns into a self-sustaining loop ([benchmarks](result/benchmarks.md)). Nothing is retuned.
Outputs: `results/mb-plasticity/v1/`.

## Kenyon cell sparseness (diagnostic, 2026-10-13)

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

**Result of version 1 (2026-10-13): not_recurrence.** Run from `b096b4a` on `main`, 11 min.

| Arm                           | KCs responding, odor 1 / 2 | Shared, of odor 1 / 2 |
| ----------------------------- | -------------------------- | --------------------- |
| A default                     | 25.5% / 25.1%              | 95% / 96%             |
| B KC → KC without fast effect | 17.4% / 17.3%              | 95% / 96%             |
| C APL → KC removed            | 99% / 100%                 | 100% / 99%            |
| D both                        | 79% / 79%                  | 99% / 99%             |

Removing the fast KC → KC excitation cuts the recruited Kenyon cells by a third, to just
above the 17% bound, but the two odors still share 95% of them. The recurrence makes the code
denser; it does not make two odors look alike. The overlap comes from upstream: two ORN
types already reach the same Kenyon cells. The APL control moves as Lin et al. 2014 predict.
Outputs: `results/kc-sparseness/v1/`.

**Version 2 (fixed 2026-10-13, after the v1 verdict, before its run).** An exploratory run
after v1 (seed 0) found one ORN type driving 414 of 577 PN-like neurons, 121 PN types, 120 of
them shared between the two odors: the overlap is made in the antennal lobe. There, the
excitatory local neurons couple to projection neurons electrically (abolished in `shakB²`,
insensitive to Cd²⁺ and mecamylamine; Yaksi & Wilson 2010), while the model, with no gap
junctions, turns the 137 cholinergic local neurons' chemical contacts onto PNs into fast
excitation. Version 2 keeps the bounds and odors, moves to seeds 70–72, and runs four arms:
default, KC → KC without fast effect, cholinergic local neuron → PN removed, and both. Its
verdict lists the arms within the measured bounds. Named caveat: Huang et al. 2010 report a
chemical component as well, and the lateral local neurons' transmitter is a prediction.

**Result of version 2 (2026-10-13): within E, F — but by undershoot.** Run from `374309e`.

| Arm                                     | KCs responding, odor 1 / 2 | Shared | PNs spiking |
| --------------------------------------- | -------------------------- | ------ | ----------- |
| A default                               | 25.2% / 25.4%              | 95%    | 73–74%      |
| B KC → KC without fast effect           | 17.5% / 17.2%              | 95%    | 73%         |
| E cholinergic local neuron → PN removed | 0.2% / 0%                  | 0      | 4.4–4.7%    |
| F both                                  | 0.3% / 0%                  | 0      | 4.4–4.8%    |

The antennal-lobe spread is found: without the cholinergic local neurons' chemical contacts
onto projection neurons, which are electrical in the fly, one ORN type drives 4.5% of the PNs
instead of 73%. The verdict lists E and F because they meet the upper bounds, but they do so
by almost silencing the Kenyon cells (0.2% against the measured 6 ± 5%): the lock had no
lower bound, a weakness stated here. Read together: the overlap came from the antennal lobe,
and once it is gone a single ORN type at 100 Hz no longer drives Kenyon cells, which in the
fly integrate about ten PNs (Turner et al. 2008). Real odors activate many receptor types;
[#96](https://github.com/gianlucamazza/flymsg/issues/96) (odors as measured receptor vectors)
is the test that can tell. The default model is unchanged. Outputs:
`results/kc-sparseness/v2/`.

**Version 3 (fixed 2026-10-13, after the v2 run, before its own).** The two odors of Hige et
al. 2015, 3-octanol and 4-methylcyclohexanol, as DoOR receptor vectors (31 and 22 ORN types),
with a rate of 100 Hz for a response of 1 (the flymsg stimulus rate; a named compensation),
on seeds 80–82, the same four arms, and the lower bound v2 lacked: between 1% (Turner et al.
2008, 6% minus one SD) and 17% of Kenyon cells per odor, at most 64.6% shared. Reported next to
the verdict: the share of shared responders against the 30% (OCT) and 33% (MCH) that Hige et
al. 2015 measured for exactly these odors.

**Result of version 3 (2026-10-13): none.** Run from `c1cf896`.

| Arm                                     | KCs responding, OCT / MCH | Shared, of OCT / MCH | PNs spiking |
| --------------------------------------- | ------------------------- | -------------------- | ----------- |
| A default                               | 36% / 30%                 | 82% / 99%            | 75–79%      |
| B KC → KC without fast effect           | 22.5% / 19.6%             | 84% / 97%            | 75–79%      |
| E cholinergic local neuron → PN removed | 0.2% / 0.2%               | 0                    | 8–12%       |
| F both                                  | 0.2% / 0.2%               | 0                    | 8–12%       |

With real odors the model has two regimes and the fly's lies between them: with the
lateral excitation of the antennal lobe as fast chemical synapses, Kenyon cells respond
densely and the two odors share 82–99% of them (Hige et al.: 30–33%); without it, projection
neurons still respond but no longer recruit Kenyon cells. One global synaptic weight with no
gap junctions cannot produce the sparse code, and tuning it is not allowed. What would: the
measured electrical coupling of excitatory local neurons to projection neurons, the evidence
[#85](https://github.com/gianlucamazza/flymsg/issues/85) already asks for. The default model
is unchanged. Outputs: `results/kc-sparseness/v3/`.

**Version 4 (lock, 2026-10-13, #85).** Arms E and F remove the chemical contacts; version 4
puts them back as [electrical synapses](#electrical-synapses-optional-2026-10-13). Each
cholinergic local neuron and PN joined by chemical synapses gets a junction proportional to
their synapse count, scaled so that the median PN's total coupling equals a grid value of
0, 0.01, 0.03, 0.1, 0.3 or 1 (junction over leak conductance; unmeasured). Same-type PNs on
one side are coupled at the coefficient Kazama & Wilson 2009 measured between homotypic PNs
(0.013, Fig. 7d). The 12 coupled arms run with fresh seeds (83–85) beside A, E and F under
v3's bounds; the smallest coupling whose arm is within is reported as the model's prediction
of the coupling the fly would need. It is a calibration of a free parameter against
sparseness, not a test: what would test it is a measured eLN → PN coupling.

**Result of version 4 (2026-10-13): none.** Run from `b1116af` (coupling as an explicit
first-order step, a compensation named in the lock). No scanned coupled arm meets the locked bounds: E and F stay silent (0.2% of Kenyon cells) and coupling makes them
quieter, down to 0% at 1, while the share of spiking PNs falls from 11% / 8% to 5% / 1%.
Symmetric subthreshold coupling ties active PNs to local neurons at rest and drains them.
In the fly the eLN → PN lateral excitation is driven by eLN spikes, which cross the junction
as spikelets (Yaksi & Wilson 2010). This run's junctions pass only subthreshold potentials:
the lock sets no spike term, and a LIF reset draws none. The missing waveform is a candidate explanation, not a cause isolated by this finite
grid and its explicit first-order integrator. v4 did not test the later implementations. Outputs:
`results/kc-sparseness/v4/`. Figure: [v1–v5, dense or silent](img/kc-sparseness.svg).

**Version 5 (lock, 2026-10-13, #85).** The coupling is no longer scanned: Yaksi & Wilson
2010 (Fig. 4C/4F, 37 pairs) give eLN → PN 0.0021 and PN → eLN 0.0039 for hyperpolarizing
steps, which pass the electrical component only, and Kazama & Wilson 2009 give 0.013
between sister PNs; each side of a junction couples at c / (1 − c) of the coefficient
towards it. The depolarizing coupling the fly shows (0.0083) comes with eLN spikes of about
40 mV, which now cross the junction as spikelets ([electrical synapses](#electrical-synapses-optional-2026-10-13)); their duration is not measured,
so arms E and F run with 0, 0.5, 1 and 2 ms (8 coupled arms, seeds 86–88) under v3's bounds.

**Result of version 5 (2026-10-13): none.** Run from `00aff9c`, the lock commit, with
boundary-only refractory reset as registered; interrupted once and resumed from its saved
arms (the manifest lists them). No coupled arm is within: all eight stay silent, 0.22–0.30%
of Kenyon cells (9–12 cells) against the 1% floor, as E and F without coupling (0.22–0.27%).
Spiking PNs fall slightly, from 11% / 8% in E to 10% / 6–7% coupled. The spikelet duration
does not change the answer: 0 ms and 2 ms differ by one or two Kenyon cells. The default
arm A stays dense (37% / 30%). At the measured coefficients the junctions are too weak to
carry lateral excitation, with or without spikelets of up to 2 ms, so the eLN → PN coupling
as modelled here is not the missing excitation. Untested: rectifying junctions, a larger
coupling at the junction than at the soma, and the chemical cholinergic component (Huang et
al. 2010) that arm E removes. Outputs: `results/kc-sparseness/v5/`. Figure:
[v1–v5, dense or silent](img/kc-sparseness.svg).

**Version 6 (locked 2026-10-13, interrupted).** v5 treated all 137 cholinergic ALLNs as eLNs, and
removing their 216,510 synapses onto PNs takes Kenyon cells from 30–37% (arm A) to 0.2–0.3%.
Eckstein et al. 2024 liken only lLN2T_abc (13 MaleCNS neurons, 39,108 synapses onto PNs) to
the cholinergic krasavietz eLNs, by soma position and morphology. v6 treats only them as
electrical partners of PNs (with lLN1_bc, 30 neighbouring neurons, as a variant set), keeps
every other cholinergic local neuron chemical, and runs E, F and the eight coupled arms once per set (16 in all)
with the current continuous clamp, seeds 89–91, under v3's bounds. Its run was stopped after
the five uncoupled arms, saved and never read; that step store was then deleted
with the run's worktree, so those arms are lost. The coupling joins 688 cells (726 with lLN1_bc) in
one component, and the continuous clamp builds a dense exponential of about 2,100 × 2,100 for
each new refractory mask, 1.1–1.6 s each with no cache hit, so one coupled simulation takes
hours (#155).

**Version 7 (lock, 2026-10-13).** Version 6 with the boundary reset of v5 and seeds
92–94. Before the lock, `scripts/qualify_boundary_reset.py` ran arm E/lLN2T on 3-octanol for
50 ms (seed 0, spikelets 0 and 1 ms) under both modes: every neuron's spike count and first
spike agree (9,798 and 9,634 spikes), in 2–5 s against 671–696 s
(`docs/evidence/kc-boundary-qualification-2026-10-13.json`). That qualifies 50 ms of one
odor and seed, which the lock names as a compensation.

**Result of version 7 (2026-10-13): within, only with the variant set.** Run from
`45c0641`, the lock commit, in one attempt. With the variant set lLN2T+lLN1_bc (43
neurons), 9 of its 10 arms are within: 2.0–2.2% of Kenyon cells respond to 3-octanol and
1.5–1.7% to 4-methylcyclohexanol (82–90 and 61–70 of 4,064 cells), and 43–47% / 59–65% of
each odor's responders are shared. The tenth, E/lLN2T+lLN1_bc+spike0ms, misses by overlap:
65.1% of the second odor's responders are shared against the 64.6% bound. With lLN2T alone,
the set Eckstein et al. 2024 liken to the eLNs, no arm is within: 16–23% / 14–19% of Kenyon
cells respond and 79–82% / 91–96% are shared, dense and overlapping like arm A (37% / 30%).
The coupling does not make the difference: every coupled arm stays within 17 cells of its
uncoupled base (E/lLN2T 928 responders, coupled 921–942; E/lLN2T+lLN1_bc 87, coupled 88–90),
whatever the spikelet duration. What separates the sets is the chemical cholinergic input
arm E removes: without lLN1_bc's contacts onto PNs as well, 41–43% / 37–38% of PNs spike
instead of 72–73% / 68–69%, and Kenyon cells come down to the low end of the measured range
(Turner et al. 2008: 6 ± 5%). Against v5, which removed all 137 cholinergic ALLNs (0.2–0.3%
of Kenyon cells, 6–11% of PNs), the variant set lands between dense and silent. The shared
share stays above Hige et al. 2015's 30% / 33%, though under the similar-odor bound. So the
sparse arms rest on a set that is a morphological neighbour of the match, not the match, and
on removing chemical synapses rather than on electrical coupling; the result does not say
the eLNs are electrical, and the default model is unchanged. Outputs:
`results/kc-sparseness/v7.executions/f8549bf7414656b26cf37dcf99811142bb3b1b3a7743b79d5ebeda941457c3a5/output/`.

**Version 8 (locked 2026-10-14).** Version 7 under the continuous clamp, integrated by
the Taylor action (`flymsg.gap/continuous-clamp-taylor-v1`, #155), with fresh seeds 95–97.
Version 7's boundary reset was qualified on 50 ms of one odor and seed; the Taylor action is
exact to rounding by its truncation bound, and on 50 ms of arm E of each eLN set (seed 0) it
reproduced the dense continuous clamp spike for spike
(`docs/evidence/gap-taylor-qualification-2026-10-14.json`) at about the boundary reset's cost,
so the whole run can use the exact integrator. Arms, bounds and decision are version 7's; the
version 7 result was read before this lock, so version 8 tests whether it survives the exact
integrator and new seeds, not a new hypothesis.

**Result of version 8 (2026-10-14): within, only with the variant set; v7 replicates.** Run
from `ad7b71e`, the lock commit, in one attempt (35 min). With lLN2T+lLN1_bc, 8 of 10 arms are
within: 2.0–2.3% of Kenyon cells respond to 3-octanol and 1.4–1.7% to 4-methylcyclohexanol, and
43–48% / 56–66% of each odor's responders are shared. The two arms out, E/lLN2T+lLN1_bc and
E/lLN2T+lLN1_bc+spike1ms, miss by overlap (66.2% and 65.1% of the second odor's responders
shared against the 64.6% bound). Version 7's tenth arm missed the same way; the arms of base E
sit at 61–66%, across the bound, so which of them pass depends on the seeds. With lLN2T alone
no arm is within (16–23% / 14–20%, 80–82% / 92–96% shared). Every coupled arm stays within 21
cells of its uncoupled base, and every arm within 19 cells of its version 7 count for each
odor. The exact continuous clamp and fresh seeds therefore leave version 7's answer unchanged:
the variant set is sparse by removing chemical cholinergic input onto PNs (41–43% / 37–39% of
PNs spike), and electrical coupling barely changes recruitment: it moves no arm by more than
21 cells, though near the overlap bound that can flip an arm (E/lLN2T+lLN1_bc is out, three of
its four coupled arms are in). Outputs:
`results/kc-sparseness/v8.executions/c714d0a3035c6d0842295f3e8057367fe9adbebb6e12fee4ac09eed6b31aee24/output/`.

## Electrical synapses (optional, 2026-10-13)

`sim.Gap` (#85) couples pairs of neurons through their potentials. A coupled neuron follows
τ_m dv_i/dt = v_rest − v_i + g_i + Σ_j c_ij (v_j + s_j − v_i), where c_ij is the junction's
conductance over i's leak conductance; a coupling coefficient c measured from j to i gives
c / (1 − c), and the two sides of a junction may differ (cells of different input
resistance). s_j is the spike a LIF reset does not draw: with `spike_mv` and `spike_ms`, a
spike of j adds a rectangular `spike_mv` (one value, or one per neuron; 0 for neurons whose
spikes do not cross) to the potential its partners see for `spike_ms`, so spikes cross the
junction as spikelets. Junctions do not rectify.

Between step boundaries the equation is linear, so each connected group is integrated
exactly: the matrix exponential of the group's membrane, synaptic and spike terms (Van
Loan's block form) is computed once per run for the all-free group (the dense solver adds one
reduced exponential per new refractory mask; the Taylor solver builds none), and each step applies it in float64. As
everywhere in the model, discrete events act at step boundaries: spikes, resets,
deliveries, kicks, the start and end of a spike term, and the refractory hold. Refractory membranes are continuously clamped at rest, with frozen
chemical conductance; free partners retain the sink from their contacts. The accepted
[electrical ADR](adr-gap-refractory.md) and [run integrity](reference/run-integrity.md) document the
reduced operators and execution identity. The dense solver builds one reduced exponential
per new refractory mask, which on a component of hundreds of cells costs about a second per
mask (#155). `Gap(solver="taylor")` (`flymsg.gap/continuous-clamp-taylor-v1`) applies the
same exponential to the state as a truncated Taylor series, with as many terms as bound the
remainder by the float64 unit roundoff for the component's step norm; on the Kenyon cell
couplings it gives the dense solver's spikes neuron for neuron in about 1/400 of the time
([qualification](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/gap-taylor-qualification-2026-10-14.json)).

EM does not show gap junctions and few are measured (#85), so no electrical synapse is in
the default model. Without them the engine is unchanged, bit for bit; with them `sim.run`,
the NumPy reference and `CpuRuntime` agree exactly (`tests/test_gap.py`), two coupled cells
relax as the exact solution and reproduce c / (1 + c), the native C++ executor retains its explicitly named boundary-reset and all-free
electrical paths; dynamic
continuous clamps require a separately qualified native implementation and are refused.
The GPU lane runs the boundary-reset and all-free paths too (#215), bit for bit on a Series S (#39); it refuses the dynamic continuous clamp, as the C++ executor does.
Until 2026-10-13 (`b1116af`, Kenyon cell v4) the coupling was an explicit first-order step
added to the membrane update.

## Graded (non-spiking) neurons (optional, 2026-10-13)

Photoreceptors, the lamina monopolar cells L1–L3 and other fly neurons do not spike; they
release transmitter in proportion to their membrane potential. `sim.Graded` (#97) makes a
chosen set of neurons non-spiking. A graded neuron integrates its inputs like every other
neuron but has no threshold, reset or refractory period. At every step it releases
f = clip((v − v_lo) / span, 0, 1) times `rate_hz · dt` of one spike's weight on each of its
synapses, delivered after the synaptic delay. At saturation it acts on its targets like a
neuron firing at `rate_hz`; with v_lo below rest it releases tonically.

No value has a default. No release curve (presynaptic voltage to release, or to the
postsynaptic voltage) is measured in Drosophila: the audit of 2026-10-13 found the operating
ranges only (photoreceptors depolarize 40–65 mV to light, LMCs hyperpolarize 20–45 mV;
Juusola et al. 2016, Zheng et al. 2006); the one measured R → LMC curve is from Calliphora.
So a lock that uses graded neurons states its curve as a compensation and scans it over the
measured ranges instead of choosing a value (`validation/t4t5.yaml` versions 2 and 3).

Without graded neurons the engine is unchanged, bit for bit. With them, `sim.run`, the NumPy
reference (`tests/reference_sim.py`) and `CpuRuntime` (chunks, checkpoints) give identical
spikes and potentials (`tests/test_graded.py`); `Result.graded_v` holds the mean potential of
the graded neurons per bin. The native C++ executor runs them from fixture version 2 and
matches the CPU runtime bit for bit; so does the GPU lane (#215) on a Series S
(#39).

## Per-neuron membranes (optional, 2026-10-13)

`sim.Membrane` gives listed neurons their own membrane time constant, synaptic time
constant, rest (also the reset) and threshold; every other neuron keeps `Params`. No value
has a default: a lock states each one and its source, as for `Graded`. The refractory
period, the delay and the weights stay global. Each neuron's step constants are computed in
float64 and rounded as the scalar ones are, so without a `Membrane` the kernel reads the same
float32 values and its spikes are unchanged bit for bit (tested, and 11,091 spikes equal on
the whole CNS with LC4_R input); the uniform case keeps scalar loops and costs about 5% more
time per step in a measured whole-CNS run (0.99 s against 1.05 s for 300 ms). The kernel, the
NumPy oracle and `CpuRuntime` agree exactly with random per-neuron membranes; a runtime with
a `Membrane` names it in its checkpoint identity. A `Membrane` on an electrically coupled
neuron is refused (`sim.Gap` integrates with the `Params` membrane), and the native executor
refuses any `Membrane` until it is qualified. Sources that could fill it are in
[leads](leads.md); the only lock using one is T4/T5 v4 (τ_syn of Mi1 and Tm1 from Behnia et al.
2014's delays, [eye](reference/eye.md)). With a `Membrane` on a minority of neurons the kernel keeps its
scalar loops and recomputes only those neurons, with bit-identical results (#182).

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
