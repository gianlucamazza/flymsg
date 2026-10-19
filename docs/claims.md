# CLAIMS: measured, engineered, not claimed

Status: current, 2026-10-19. This page labels each part of flymsg's closed loop.
It invents no number and no citation. Every sentence restates a page, an ADR, a
lock, an example or a README row already in this repository. It is not a scored
result.

The scheduler is `flymsg.closedloop`. Each of its four components — registration,
transducer, motor map and body — carries one of `measured` / `engineered` /
`unmapped` / `synthetic`
([body-wiring ADR](adr-body-wiring.md), [DN-arena ADR](adr-dn-arena.md)). A
biological run refuses unless every component is `measured`. A synthetic run is
allowed, records those statuses and supports no claim about the fly.

## What runs today

The executable fixture is synthetic. `closedloop_experiment` and
`examples/closedloop-nmf.yaml` run a two-neuron toy circuit, a test-only
registration, an engineered looming transducer and a synthetic torque decoder.
That is infrastructure, not a world→sensory or muscle→actuator map
([DN-arena ADR](adr-dn-arena.md), [embodiment](embodiment.md#g5-groundwork-closed-loop-schedule-and-record-180)).

The accepted [DN-arena ADR](adr-dn-arena.md) names a later kinematic planar body
and an engineered descending-neuron decoder. Acceptance authorizes `arena-1`
through `arena-6`, one reviewed PR at a time. It does not implement them, write
a lock or authorize a counted run.

Earlier one-axis fixtures stay as recorded and are not this loop: the one-bit
looming cut ([behavior](behavior.md)), M1 `flymsg jump` and M2 `flymsg loop`
([embodiment](embodiment.md)).

## Measured

Taken from published data already cited in this repository.

| Part              | What is measured                                                                                                                                                   | Source in this repo                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| MaleCNS wiring    | The traced graph: 165,122 neurons and the connections among them. `flymsg build` keeps `status == "Traced"`. Not a claim that a decoder uses that graph correctly. | [data](data.md); Berg et al., _Cell_ 189, 5504–5526 (2026), doi:10.1016/j.cell.2026.08.015. README and the DN-arena ADR use the same citation. |
| Column geometry   | Optic-lobe column directions on MaleCNS. `flymsg.optics` projects dark spheres onto those columns. Nothing here is a photoreceptor response.                       | [eye](eye.md); Zhao et al. 2025, _Nature_, doi:10.1038/s41586-025-09276-5. Hex coordinates: Nern et al. 2025, doi:10.1038/s41586-025-08746-0.  |
| MANC muscle names | MANC names a muscle for 406 of 708 `vnc_motor` neurons. That table is not a motor map.                                                                             | [embodiment](embodiment.md#muscles-from-manc-phase-c); Cheong et al. 2024, _eLife_, doi:10.7554/eLife.96084.                                   |

The default LIF time constants and delay are Shiu et al.'s published values
([model](model.md#parameters); Shiu et al. 2024, _Nature_,
doi:10.1038/s41586-024-07763-9). The engine is still an engineered model of
those numbers, not a measurement of this fly. Battery 29/29 at `w_syn` 0.192 is
a model check, not closed-loop behaviour
([validation](validation.md), [DN-arena ADR](adr-dn-arena.md)).

## Engineered

Chosen in this repository. A gain or decoder is not a connectome-derived
controller ([#31](https://github.com/gianlucamazza/flymsg/issues/31)).

| Part                       | What was chosen                                                                                                                                                                                                                                                                                                                                                   | Source in this repo                                                              |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| LIF / `CpuRuntime`         | Point leaky integrate-and-fire on the traced graph, bit-identical to `sim.run`. Optional gap, graded and plasticity stay off unless a lock names them.                                                                                                                                                                                                            | [model](model.md), [runtime](runtime.md), [approximations](approximations.md)    |
| Clock and order            | Integer-microsecond `embodiment.Clock`. Causal order command → sample → stimulus → input → neural → physics. One scheduler; no renderer enters the loop.                                                                                                                                                                                                          | [body-wiring ADR](adr-body-wiring.md)                                            |
| Visual transducer          | Coverage → Poisson rates. Not a photoreceptor. The existing fixture's coverage-to-rate function is fixed in fixture source; those numbers are not biological calibrations.                                                                                                                                                                                        | [DN-arena ADR](adr-dn-arena.md), [VEE qualification](vee-qualification.md)       |
| Existing body adapter      | `flymsg.flygym_body.FlyGymBody` reports `engineered`: posture gain and torque-driven hinges are chosen. NeuroMechFly (FlyGym 2.1.0; Wang-Chen et al. 2024, _Nat Methods_, doi:10.1038/s41592-024-02497-y) sits behind the adapter.                                                                                                                                | [embodiment](embodiment.md#g5-groundwork-closed-loop-schedule-and-record-180)    |
| Synthetic closed-loop mode | `mode: synthetic` in `examples/closedloop-nmf.yaml`. Five arms: intact, disconnected, shuffled, replay, silenced. Record `flymsg.closedloop/v1`.                                                                                                                                                                                                                  | [VEE qualification](vee-qualification.md), [body-wiring ADR](adr-body-wiring.md) |
| DN decoder and its gains   | Accepted design only. Windowed spike rates of named descending types map to `(yaw, forward)` of the kinematic body: DNa01 / DNa02 for steering, oDN1 for forward speed. Gains are declared per run in the experiment lock and the run record, with no defaults in code or in docs. They do not enter `validation/evidence.yaml`. Not implemented until `arena-3`. | [DN-arena ADR](adr-dn-arena.md)                                                  |
| Kinematic arena body       | Accepted design only. Planar integrator of yaw rate (`rad/s`) and forward speed (`m/s`) behind `closedloop.Body`. _z_, roll and pitch stay at lock constants. No MuJoCo in that loop. Not free flight. Not implemented until `arena-2`.                                                                                                                           | [DN-arena ADR](adr-dn-arena.md)                                                  |

M1 `engineered_decoder` and M2's looming transducer are the same kind of choice
on the earlier one-axis bodies: stated gains, not a motor map
([embodiment](embodiment.md#m1-jump-body-v0834-33)).

## Unmapped

No published source in this repository fills these rows. They stay `unmapped`
or refuse. They are not renamed to look measured.

| Part                       | What is missing                                                                                                                                                                | Source in this repo                                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Eyemap → body registration | No sourced `pose.Registration`. The rotation between the Zhao et al. 2025 micro-CT head and NeuroMechFly's head is not measured. Tests may use a declared identity.            | [eye](eye.md), [#179](https://github.com/gianlucamazza/flymsg/issues/179), [g2-capsule-rotation](g2-capsule-rotation.md) |
| Muscle → actuator          | `validation/motor_map.yaml` has every actuator row `unmapped`. `motor_map.command` and `pose.command` refuse every command. MANC names a muscle; it does not name an actuator. | [embodiment](embodiment.md), README results row "Motor map"                                                              |
| DN identity (bodyId, side) | Unmapped until `arena-1` inventories DNa01, DNa02 and oDN1. Ambiguous or missing stays unmapped and stops that milestone. No gain is chosen here.                              | [DN-arena ADR](adr-dn-arena.md)                                                                                          |

`closedloop.require` therefore refuses a biological run
([DN-arena ADR](adr-dn-arena.md)).

## Not claimed

flymsg does not claim that:

- the fly perceives, steers, walks, flies or escapes;
- MaleCNS, T4/T5, LC cells or descending neurons implement that behaviour
  (T4/T5 v1 is neither and v2–v4 are robust neither, [eye](eye.md));
- the decoder, its gains or the kinematic body are biological;
- world→sensory or muscle→actuator maps exist;
- VEE-0, VEE-1 or VEE-2 of the [sensorimotor plan](sensorimotor-environment-plan.md)
  is done, including that plan's take-off task (G2 registration, G3
  transduction and G4 motor map remain open);
- a yaw change outside a wiring-null seed range is a biological or
  connectome-derived mechanism (the accepted ADR would call that a synthetic
  difference);
- the point LIF on the traced graph is a whole-brain emulation
  ([approximations](approximations.md), README Limits);
- this loop is free flight ([DN-arena ADR](adr-dn-arena.md);
  [sensorimotor plan](sensorimotor-environment-plan.md): free flight, walking
  and real-time whole-CNS execution are out of scope);
- a learned policy is reproduced or endorsed
  ([#31](https://github.com/gianlucamazza/flymsg/issues/31)).

A synthetic run supports no claim about the fly
([body-wiring ADR](adr-body-wiring.md)). Equal closed and disconnected results
are reported as observed; they are not a pass. Words such as "upload" or
"living fly" are out of scope.

The [replication claims audit](replication.md#claims-audit) classifies scored
results. None is a discovery. This page is the closed-loop label list, not that
audit.

## Reproduce the existing synthetic closed loop

Bit-identical replay of the fixture that already runs. Commands below are the
ones [VEE qualification](vee-qualification.md#run-the-headless-engineering-fixture)
already documents. From clean committed source, with Python 3.13 and the locked
dependencies:

```bash
uv sync --locked
uv run flymsg closedloop examples/closedloop-nmf.yaml --check
uv run flymsg closedloop examples/closedloop-nmf.yaml --out runs/closedloop
```

`--check` loads neither the connectome nor a physical body. The config selects
`nmf-optics-chain/v1`, names the clock, duration, seed, checkpoint period and
all five arms, and sets `mode: synthetic`. A biological config refuses before
constructing the body.

The replay arm must reproduce the intact spikes exactly
([body-wiring ADR](adr-body-wiring.md): anything else is a failure, not a
tolerance). Repeat the identical `--out` command to resume checkpoints or
verify completed output. A changed source, config, asset or environment selects
another execution.

The [cold-clone record](https://github.com/gianlucamazza/flymsg/blob/main/docs/evidence/vee-synthetic-2026-10-15.json)
verifies that all five scientific traces are byte-identical across the original
run and a fresh clone at source `1223551`; timing differs as expected
([VEE qualification](vee-qualification.md#gate-ledger)).

The unit path already named on [embodiment](embodiment.md#g5-groundwork-closed-loop-schedule-and-record-180)
is:

```bash
uv run pytest tests/test_closedloop.py tests/test_flygym_body.py
```

`replay_parity` refuses any count or spike difference. Those tests use a
two-neuron chain, a one-axis toy body and NeuroMechFly with a test-only eye
registration, a looming sphere and a synthetic torque decoder: no claim about
the fly.

Rendering on or off changes no number. Full-connectome closed-loop performance
is not measured yet.
