# Male vs female

flymsg runs the same model on the male CNS (MaleCNS v1.0) and the female brain (FlyWire FAFB
v783, `--dataset fafb`, see [data](data.md#female-brain-flywire-fafb-v783---dataset-fafb)).
Cell types are matched through MaleCNS `flywireType`. Code: `src/flymsg/compare.py`.

## Engine check

Before comparing sexes, the simulator is checked against the model it claims to reproduce.
The published brian2 code of Shiu et al. (repository commit `91bdd1e`, brian2 2.10.1) and
flymsg ran on the same connectome (FAFB v783 with the model's own signs, `shiu_sign`), the
same 20 sugar GRNs (their list, one ID missing in v783), no adaptive threshold, 10 runs of
1 s per input rate.

| Sugar input | Pearson r, all active neurons | MN9 (CB0701_R), brian2 | MN9, flymsg | Downstream neurons > 10 Hz, median flymsg / brian2 |
|---|---|---|---|---|
| 50 Hz | 0.998 | 11.0 Hz | 12.5 Hz | 0.99 (42 neurons) |
| 100 Hz | 0.999 | 61.9 Hz | 60.5 Hz | 0.95 (205) |
| 200 Hz | 1.000 | 90.7 Hz | 88.0 Hz | 0.98 (273) |

MN9 varies by about ±4 Hz between brian2 runs at 200 Hz, so the two engines agree within
noise. The check found six places where flymsg had departed from the published model; the
last two (synaptic input reaching a refractory neuron is lost; refractory length) were only
visible at high rates and were isolated on a two-neuron network, which is now a regression
test (`tests/test_core.py`). Details in the [findings log](validation.md#findings-log).

Reproduce: `scripts/shiu_reference.py` runs the brian2 reference (needs a separate
environment with brian2, see the script); `compare.shiu_rates` gives the flymsg side.

## Synapse counts are not on the same scale

Across 7,327 cell types matched through `flywireType`, a male neuron has a median **1.81×**
the input synapses of its female counterpart (interquartile range of the per-type ratio about
1.4–2.4; output synapses the same). A factor this uniform across types is methodological —
MaleCNS was imaged by FIB-SEM at 8 nm isotropic and FAFB by serial-section TEM, with
different synapse detectors — not biological. With one `w_syn` for both, the male network is
driven about 1.8× harder, so raw comparisons between the datasets are confounded.
`compare.synapse_density_ratio` measures the factor; the comparison below multiplies the
female `w_syn` by it, so that the same biological connection weighs the same in both.

This also bears on the male model itself: `w_syn` 0.275 was tuned by Shiu et al. on FAFB, and
in MaleCNS it acts like a ~1.8× stronger synapse. That may be why the male model needs the
adaptive threshold (an exploratory test is in the [findings log](validation.md#findings-log)).

## Male vs female (`runs/sex-comparison-normalized.csv`)

Same model and defaults (`th_jump` 2) on both, female `w_syn` × 1.81, 3 seeds × 300 ms per
input rate. Only cases whose stimulus and target exist in both datasets can run: P1, pIP10
and dPR1 have no FAFB counterpart (male-specific or unmatched) and TTMn lies in the VNC,
which FAFB lacks.

| Case (target) | Input | Male target | Female target | Shared types responding, male / female | Jaccard |
|---|---|---|---|---|---|
| sugar GRNs → MN9 (CB0701) | 50 Hz | 7.8 Hz | 36.7 Hz | 485 / 348 | 0.30 |
| | 100 Hz | 23.3 Hz | 53.3 Hz | 745 / 613 | 0.31 |
| | 200 Hz | 24.4 Hz | 68.9 Hz | 417 / 624 | 0.38 |
| LC4_R → DNp01 | 50 Hz | 127.8 Hz | 44.4 Hz | 493 / 572 | 0.34 |
| | 100 Hz | 158.9 Hz | 75.6 Hz | 862 / 530 | 0.34 |
| | 200 Hz | 190.0 Hz | 111.1 Hz | 972 / 573 | 0.34 |

Stimuli: male LB3b_L + LB3c_L (17) vs the Shiu et al. sugar set (20, FlyWire `left`, all FAFB
type LB3); male LC4_R (55) vs female LC4_R (50). Without the density correction the female
responded with 3–6× fewer shared types (Jaccard 0.13–0.18, `runs/sex-comparison.csv`).

- About a third of the responding cell types are shared, in both cases. The rest differ in
  which downstream types the same stimulus reaches.
- The target responses differ in opposite directions: MN9 fires 2–3× more in the female,
  DNp01 1.7–2.9× more in the male. The male GF has 3.9× the input synapses of the female GF,
  well beyond the 1.8× density factor.
- **These are not yet dimorphism results.** Each dataset is one animal; individual variability,
  reconstruction differences (proofreading, synapse detection beyond a global factor) and
  real sex differences cannot be separated with one fly per sex. The sugar stimuli also
  differ: the male set excludes LB3d, while FAFB types all these neurons as LB3.
