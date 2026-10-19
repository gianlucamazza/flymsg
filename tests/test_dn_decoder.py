"""Engineered DN decoder: windowed rates to (yaw, forward) (DN-arena ADR)."""

import json

import pytest

from flymsg.embodiment import Clock, ContractError, SpikeEvent

# docs/dn-arena-inventory.md (MaleCNS v1.0); not a gain
DNA01_L, DNA01_R = 10442, 10760
DNA02_L, DNA02_R = 523769, 10360
ODN1_L, ODN1_R = 13805, 230783
MDN_L = 11288
NEURONS = {
    DNA01_L: ("DNa01", "L"),
    DNA01_R: ("DNa01", "R"),
    DNA02_L: ("DNa02", "L"),
    DNA02_R: ("DNa02", "R"),
    ODN1_L: ("oDN1", "L"),
    ODN1_R: ("oDN1", "R"),
}
WINDOW = (0, 1_000_000)  # 1 s
GAINS = {"DNa01": 0.5, "DNa02": 0.25, "oDN1": 0.1}
# one control period per second, so a count reads directly as spikes/s
CLOCK = Clock(neural_us=100, body_us=500_000, control_us=1_000_000)


def arena():
    from flymsg.arena import Arena

    return Arena(z_m=1e-3, roll_rad=0.0, pitch_rad=0.0, source="test kinematic")


def decoder(gains=None, window=WINDOW, actuators=None, clock=CLOCK, neurons=None):
    from flymsg.dn_decoder import Decoder

    return Decoder(
        gains=dict(GAINS if gains is None else gains),
        window=window,
        actuators=actuators if actuators is not None else arena().actuators,
        clock=clock,
        neurons=dict(NEURONS) if neurons is None else neurons,
    )


def values(commands):
    return {actuator.name: value for actuator, value in commands}


def spikes(*pairs):
    return tuple(SpikeEvent(neuron_id, time_us) for neuron_id, time_us in pairs)


def test_zero_rates_give_zero_command():
    commands = decoder()(spikes())
    assert values(commands) == {"yaw": 0.0, "forward": 0.0}
    commands = decoder()(spikes((DNA01_L, -1), (ODN1_R, 1_000_000)))
    assert values(commands) == {"yaw": 0.0, "forward": 0.0}


def test_left_minus_right_sets_the_yaw_sign():
    left = values(decoder()(spikes((DNA01_L, 0))))
    right = values(decoder()(spikes((DNA01_R, 0))))
    assert left["yaw"] == 0.5 and right["yaw"] == -0.5
    assert left["forward"] == 0.0 and right["forward"] == 0.0
    both = values(decoder()(spikes((DNA02_L, 0), (DNA02_R, 0))))
    assert both["yaw"] == 0.0
    only_l = values(decoder()(spikes((DNA02_L, 0))))
    assert only_l["yaw"] == 0.25


def test_forward_scales_linearly_with_odn1_rate():
    one = values(decoder()(spikes((ODN1_L, 0))))
    two = values(decoder()(spikes((ODN1_L, 0), (ODN1_R, 100))))
    assert one["forward"] == 0.1 and two["forward"] == 0.2
    assert one["yaw"] == 0.0
    doubled = values(decoder()(spikes((ODN1_L, 0), (ODN1_L, 10))))
    assert doubled["forward"] == 0.2


def test_window_is_half_open_on_the_edges():
    start = values(decoder()(spikes((DNA01_L, 0))))
    end = values(decoder()(spikes((DNA01_L, 1_000_000))))
    last = values(decoder()(spikes((DNA01_L, 999_999))))
    assert start["yaw"] == 0.5
    assert end["yaw"] == 0.0
    assert last["yaw"] == 0.5


def test_missing_nonfinite_or_unknown_types_refuse():
    with pytest.raises(ContractError, match="gain"):
        decoder(gains={"DNa01": 0.5, "DNa02": 0.25})
    with pytest.raises(ContractError, match="gain"):
        decoder(gains={**GAINS, "MDN": 1.0})
    with pytest.raises(ContractError, match="finite"):
        decoder(gains={**GAINS, "oDN1": float("nan")})
    with pytest.raises(ContractError, match="window"):
        decoder(window=(1000, 1000))
    with pytest.raises(ContractError, match="unknown"):
        decoder()(spikes((MDN_L, 0)))
    with pytest.raises(ContractError, match="unknown"):
        decoder()(spikes((1, 0)))


def test_existing_synthetic_closedloop_replay_is_unchanged():
    from test_closedloop import test_a_replay_reproduces_the_recorded_spikes_exactly

    test_a_replay_reproduces_the_recorded_spikes_exactly()


def test_a_rate_is_the_call_count_over_one_control_period():
    # closedloop.run delivers one control period per call, whatever the window
    clock = Clock(neural_us=100, body_us=500, control_us=1000)
    one_ms = values(decoder(clock=clock)(spikes((ODN1_L, 5000))))
    assert one_ms["forward"] == GAINS["oDN1"] * 1000.0


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        ("missing", "six"),
        ("extra", "six"),
        ("duplicate", "duplicate"),
        ("type", "unknown descending type"),
        ("side", "side must be"),
        ("zero", "bodyId"),
    ],
)
def test_a_neuron_map_that_is_not_the_six_rows_refuses(mutate, match):
    neurons = dict(NEURONS)
    if mutate == "missing":
        del neurons[DNA01_R]
    elif mutate == "extra":
        neurons[1] = ("oDN1", "R")
    elif mutate == "duplicate":
        del neurons[DNA01_R]
        neurons[1] = ("DNa01", "L")
    elif mutate == "type":
        neurons[DNA01_L] = ("MDN", "L")
    elif mutate == "side":
        neurons[DNA01_L] = ("DNa01", "M")
    else:
        neurons = {0 if k == DNA01_L else k: v for k, v in neurons.items()}
    with pytest.raises(ContractError, match=match):
        decoder(neurons=neurons)


def test_body_ids_are_sorted_and_describe_is_canonical():
    neurons = {
        ODN1_R: ("oDN1", "R"),
        DNA02_L: ("DNa02", "L"),
        DNA01_R: ("DNa01", "R"),
        ODN1_L: ("oDN1", "L"),
        DNA02_R: ("DNa02", "R"),
        DNA01_L: ("DNa01", "L"),
    }
    dec = decoder(neurons=neurons)
    ordered = (DNA02_R, DNA01_L, DNA01_R, ODN1_L, ODN1_R, DNA02_L)
    assert dec.body_ids == ordered
    neurons[1] = ("DNa01", "L")
    assert dec.body_ids == ordered
    described = dec.describe()
    assert described == {
        "schema": "flymsg.dn_decoder/v1",
        "gains": {"DNa01": 0.5, "DNa02": 0.25, "oDN1": 0.1},
        "window_us": [0, 1_000_000],
        "control_us": CLOCK.control_us,
        "neurons": [
            {"body_id": DNA01_L, "type": "DNa01", "side": "L"},
            {"body_id": DNA01_R, "type": "DNa01", "side": "R"},
            {"body_id": DNA02_L, "type": "DNa02", "side": "L"},
            {"body_id": DNA02_R, "type": "DNa02", "side": "R"},
            {"body_id": ODN1_L, "type": "oDN1", "side": "L"},
            {"body_id": ODN1_R, "type": "oDN1", "side": "R"},
        ],
        "actuators": {"yaw": "rad/s", "forward": "m/s"},
    }
    assert list(described["gains"]) == ["DNa01", "DNa02", "oDN1"]
    assert list(described["actuators"]) == ["yaw", "forward"]
    assert json.loads(json.dumps(described)) == described
