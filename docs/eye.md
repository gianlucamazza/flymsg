# Eye

MaleCNS optic-lobe columns, their measured viewing directions, and the T4/T5 locks that
use them. The fetch, the licence and the files are in
[data](data.md#eye-map-flymsg-eye). The body and the jump are in
[embodiment](embodiment.md).

## Eye geometry (#84)

`flymsg eye` joins the MaleCNS optic-lobe columns to measured viewing directions. Each
column has hex coordinates (`assignedOlHex1/2`, Nern et al. 2025, doi:10.1038/s41586-025-08746-0);
with p = hex2 − 19 and q = hex1 − 18 they are the (p, q) of the eye map of Zhao et al. 2025
(doi:10.1038/s41586-025-09276-5), whose lens directions come from a micro-CT of one female
head. Mi1 columns and lenses share (p, q) in all 778 of Zhao's pairs, so the registration is
the identity on the hex grid; nothing is fitted. The map is fetched from
`reiserlab/eyemap_T4` at `99d2a43` (GPL-3.0) into `data/raw/eyemap/` and never committed;
`data/eye/columns.parquet` and `photoreceptors.parquet` stay local.

|                               |      Left |     Right |
| ----------------------------- | --------: | --------: |
| Columns (one L1 each)         |       875 |       892 |
| With a viewing direction      |       835 |       843 |
| R1–R6 assigned to a cartridge |       498 |       888 |
| R7 / R8 assigned to a column  | 541 / 624 | 687 / 698 |

Photoreceptors carry no hex label; each takes the column that receives most of its
synapses among column-assigned neurons. Many R1–R6 bodies are out-of-scope fragments,
more on the left. **Check, independent of the map:** the dorsal-rim photoreceptors (R7d,
R8d) land on columns with a median elevation of 67.7°, the other R7/R8 at 3.7°. Named
assumptions: the left eye is the right eye mirrored; a male optic lobe is read through a
female eye; columns without a lens (mostly the anterior edge) get no direction. Expected
error is about one column (≈ 5°) inside the eye, worse at its margins.

**A looming stimulus per column.** `eye.looming_radius_deg` gives the angular radius of an
object approaching at constant speed (tan θ/2 = l/(v·t), the stimulus of von Reyn et al.
2014), and `eye.disk_coverage` the share of each column's acceptance profile the dark disk
covers: a circular Gaussian of a given full width at half maximum around the column's
direction, exact in the small-angle limit (Rice CDF). The acceptance angle is an argument,
not a default; the value and its source go into the lock of the first run. With 5°, a disk
centred at 90° to the right covers more than half the profile of 5 right-eye columns at a
radius of 5°, 138 at 30° and 462 at 60°, and no left-eye column.

`eye.photoreceptor_kicks` turns the coverage into graded input for each photoreceptor of a
column: `gain` times the light left (1 − coverage), in units of the Poisson kick; the gain has
no measured value and is stated by the lock. That lock is the T4/T5 test below.
The giant fiber's size/velocity split (Ache et al. 2019) is a separate test on the
[roadmap](roadmap.md) and is not part of this lock.

## T4/T5 direction selectivity through the eye (lock, 2026-10-13)

`eye.edge_coverage` moves a straight edge across each eye's measured columns (direction per
eye, so front-to-back points away from the midline on both sides).
[`validation/t4t5.yaml`](../validation/t4t5.yaml), locked before its run, drives the 640
photoreceptors of the 336 columns within 30° of each eye's centre with ON and OFF edges in
the four cardinal directions at 30°/s (Haag et al. 2017), acceptance 8.23° (Gonzalez-Bellido
et al. 2011), and a gain equal to the mean input of every flymsg protocol (a named
compensation). It decides on two levels: **polarity** (every T4 subtype fires more to ON than
to OFF edges, every T5 subtype the reverse; Maisak et al. 2013), which signs alone predict,
and **direction** (the vector sum of at least 6 of the 8 subtypes within 45° of the measured
preferred direction: a front-to-back, b back-to-front, c up, d down). The prior is stated in
the lock: Lappalainen et al. 2024 found untrained connectome models get polarity right and
direction wrong. DSI is reported next to the 0.8 measured in calcium.

**Result of version 1 (2026-10-13): neither.** Run from `0c574f5`. No T4 or T5 neuron spikes
for any edge, direction or polarity, so neither level passes. An exploratory count after the
verdict (seed 0, one sweep each polarity) shows where the signal stops: the 640
photoreceptors fire about 370,000 spikes per sweep, and L1, L2, L3, Mi1, Tm3, Mi4, Mi9, Tm1,
Tm2 and Tm9 fire none. Photoreceptor synapses are histaminergic, inhibitory; in the fly the
lamina monopolar cells are graded neurons with a resting tone that light hyperpolarises and
darkness depolarises, which is where ON and OFF begin. A spiking point neuron at rest that
receives only inhibition stays silent in light and in darkness, so contrast cannot cross the
first synapse. The eye and its geometry work; the model's neurons do not, at this stage. This
is the case for graded, tonically active neurons
([#97](https://github.com/gianlucamazza/flymsg/issues/97)), now with a concrete failure.
Outputs: `results/t4t5/v1/`.

## T4/T5 version 2: graded photoreceptors and lamina (lock, 2026-10-13, #84, #97)

Version 2 of [`validation/t4t5.yaml`](../validation/t4t5.yaml), locked after the v1 run and
before any v2 run, makes photoreceptors and L1–L3 graded ([model](model.md#graded-non-spiking-neurons-optional-2026-10-13)).
Photoreceptors release nothing at rest and saturate at their light response; L1–L3 release
half their maximum at rest, nothing at the measured maximal hyperpolarization and saturate
as far above rest. The light gain holds a fully lit photoreceptor at its response, and the
photoreceptor release rate makes full light hyperpolarize the median receiving LMC by the
LMC range, both from the steady state of the membrane equation. Because no release curve is
measured in Drosophila, the test runs an envelope of 17 configurations: LMC ranges 20, 32.5
and 45 mV times LMC release rates 25–400 Hz (unmeasured, four doublings) at a 52.5 mV
photoreceptor response, plus 40 and 65 mV. The edge's first frame is held 200 ms before it
moves and spikes count only during motion; the input is deterministic, so one run per
stimulus and configuration. The decision per configuration is v1's; the test reports
`robust: <verdict>` only if all 17 agree, and otherwise `depends` with the counts. The
pathway's spikes per type (Mi1 to Tm9) and the LMC potentials are reported next to the
measured ranges.

**Result of version 2 (2026-10-13): robust: neither.** Run from `17173c2`, the lock commit,
seed 93, 136 simulations; interrupted once after 8 configurations and resumed from saved ones
(the manifest lists them). All 17 configurations give `neither`: no T4 or T5 neuron spikes
for any edge, direction or polarity. Contrast now crosses the lamina: under light the graded
L1–L3 receiving window photoreceptors hyperpolarize by 14–33 mV at their lowest (the measured
range is 20–45 mV; the 20 mV configurations stay below it). It stops in the medulla. The ON
inputs of T4 (Mi1, Tm3, Mi4) fire in no configuration. The OFF inputs (Tm1, Tm2, Tm4, Mi9)
fire only when the LMC release rate is 200 or 400 Hz, with 7 to about 560,000 spikes per type
over the eight stimuli; at 25–100 Hz the whole medulla stage is silent. In the fly Mi1 and Tm3
are graded and the medulla inputs differ in timing (Behnia et al. 2014; [leads](leads.md));
here they are spiking point neurons at rest, which disinhibition from the lamina does not
lift, the outcome the lock's prior names. Outputs: `results/t4t5/v2/`.

**Version 3 (locked 2026-10-13; #140).** T4's medulla inputs Mi1, Tm3, Mi4, Mi9 and
C3 become graded over the potentials Groschner et al. 2022 recorded in vivo to the same
30°/s edges (Edmond doi:10.17617/3.8G, CC BY 4.0; `flymsg.medulla` fetches the five files by
sha256 and the run recomputes the ranges). Per type, the mean dark potential stands at the
model's rest, release is 0 at the lowest mean potential and saturates at the highest: Mi1
−69.2 to −41.3 mV around a dark level of −65.2, Tm3 −69.4 to −42.5 (−64.4), Mi4 −66.7 to
−52.3 (−65.1), Mi9 −62.5 to −50.4 (−58.0, an OFF cell releasing in darkness), C3 −74.0 to
−46.9 (−66.8). The release rate of the medulla and of L1–L3 is not measured: both are scanned
over 25–400 Hz (25 configurations, seed 94) at the middle photoreceptor and LMC ranges. T5's
inputs Tm1, Tm2, Tm4 and Tm9 have no voltage in mV in any source found (Behnia et al. 2014,
Kohn et al. 2021, Yang et al. 2016), so they stay spiking and v3 decides on the four T4
subtypes; T5 is reported. Per-type timing (Mi1 71 ms against Tm3 53 ms, Behnia et al. 2014)
is not set: the model has one membrane time constant. Graded types never spike, so the
pathway table counts 0 for Mi1, Tm3, Mi4 and Mi9; their potentials are in `medulla.csv`,
next to the measured range.

**Result of version 3 (2026-10-14): robust: neither.** Run from `406f622`, the lock commit,
seed 94, 200 simulations in one attempt (11.3 h). No T4 neuron spikes in any configuration, for
any edge, direction or polarity, and T5 is `neither` in all 25. The LMCs still carry contrast
(−20.6 to −25.4 mV at their lowest under light). The graded medulla receives it with the
measured sign only for Tm3 and C3 (ON, up to +1.4 and +0.8 mV) and Mi9 (OFF, ±0.6 mV); Mi1 and
Mi4 move by at most 0.5 mV, without a consistent sign (mostly the OFF one at LMC rates of
100 Hz and above). The measured ranges span 12–28 mV, so the evoked swings are at most about 5% of
the measured ones. Before the edge, tonic lamina release holds Mi1, Tm3, Mi4 and C3 below the
measured dark level (Mi9, an OFF cell, above it), the more so the higher the LMC rate (Mi1 −1.0
to −16.8 mV, Tm3 to −16.7 mV). Below its lowest measured potential a graded type releases
nothing: Mi1 and Mi4 from an LMC rate of 100 Hz, Tm3 from 200 Hz and C3 at 400 Hz. T5's spiking
inputs fire only at LMC rates of 200–400 Hz (Tm1 up to about 381,000 spikes over the eight
stimuli). Making the medulla graded therefore does not carry the edge to T4: at low LMC rates
the lamina → medulla step is too small, and at high rates tonic release pushes the medulla
below release. Outputs: `results/t4t5/v3.executions/d85c3913…/output/`.
