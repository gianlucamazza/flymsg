"""The DN arena lock, its jobs and the yaw metric. No connectome and no FlyGym."""

import copy
from pathlib import Path

import numpy as np
import pytest
import test_closedloop
from test_dn_decoder import DNA01_L, GAINS, NEURONS

from flymsg import closedloop, dn_arena
from flymsg.arena import Arena
from flymsg.dn_decoder import Decoder
from flymsg.embodiment import ContractError

ARM_ORDER = ("intact", "disconnected", "shuffled", "silenced", "replay")
OTHER_YAW = {"disconnected": 1.0, "shuffled": 2.0, "silenced": 3.0, "replay": 4.0}


def _edit(name: str) -> dict:
    doc = copy.deepcopy(dn_arena.load())
    if name == "seeds":
        doc["controls"]["wiring_null"]["seeds"] = 38
    elif name == "arms":
        doc["arms"] = list(reversed(doc["arms"]))
    elif name == "gap":
        doc["model"]["input_gap_steps"] += 1
    elif name == "window":
        doc["score"]["window_us"] = [0, doc["model"]["duration_us"] + 1]
    elif name == "neuron":
        doc["decoder"]["neurons"][0] = "1 DNa01 L"
    elif name == "scored":
        doc["claim"]["scored"] = True
    elif name == "defaults":
        doc["defaults_changed"] = True
    return doc


def _mapped_rows() -> dict[int, tuple[str, str]]:
    path = Path(__file__).resolve().parents[1] / "docs" / "dn-arena-inventory.md"
    rows: dict[int, tuple[str, str]] = {}
    header = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "Type":
            header = cells
            continue
        if header is None or set(cells[0]) <= set("-: "):
            continue
        kind, status, male, side = cells[0], cells[2], cells[3], cells[5]
        if status != "mapped":
            continue
        assert kind in {"DNa01", "DNa02", "oDN1"}
        if kind == "oDN1":
            assert male == "DNg97"
        else:
            assert male == kind
        rows[int(cells[4])] = (kind, side)
    return rows


def _spikes(ids: list[str], fired: bool) -> dict[str, int]:
    counts = {body: 0 for body in ids}
    if fired:
        counts[ids[0]] = 1
    return counts


def _at(value, index):
    return value[index] if isinstance(value, list) else value


def _rows(intact, spikes, script_yaw=5.0):
    doc = dn_arena.load()
    ids = [str(body) for body in sorted(dn_arena.neurons(doc))]
    cells = dn_arena.cells(doc)
    seed0 = doc["controls"]["wiring_null"]["seed0"]
    rows = []
    for job in dn_arena.jobs(doc):
        if job["kind"] == "script":
            rows.append({"key": job["key"], "yaw_change": float(script_yaw)})
            continue
        index = cells.index(job["cell"])
        if job["kind"] == "wiring-null":
            rows.append(
                {
                    "key": job["key"],
                    "yaw_change": float(job["seed"] - seed0),
                    "spikes": _spikes(ids, True),
                }
            )
            continue
        fired = _at(spikes, index)
        per_arm = {}
        for arm in job["arms"]:
            if arm == "intact":
                yaw, counts = float(_at(intact, index)), _spikes(ids, fired)
            else:
                yaw, counts = OTHER_YAW[arm], _spikes(ids, True)
            per_arm[arm] = {
                "yaw_change": yaw,
                "spikes": counts,
                "record_sha256": "a" * 64,
            }
        rows.append({"key": job["key"], "replay_parity": True, "arms": per_arm})
    return rows, doc, ids


class _LoggingArena(Arena):
    def __init__(self):
        super().__init__(z_m=0.0, roll_rad=0.0, pitch_rad=0.0, source="test kinematic")
        self.logged = []

    def step(self, commands, dt_us):
        state, contacts = super().step(commands, dt_us)
        self.logged.append(self.yaw_rad)
        return state, contacts


def test_the_lock_matches_the_code():
    doc = dn_arena.assert_locked()
    assert dn_arena.assert_matches_code() == doc
    assert dn_arena.assert_matches_code(doc) == doc


@pytest.mark.parametrize(
    "name",
    ["seeds", "arms", "gap", "window", "neuron", "scored", "defaults"],
)
def test_a_drifted_lock_is_refused(name):
    with pytest.raises(dn_arena.DNArenaError):
        dn_arena.assert_matches_code(_edit(name))


def test_decoder_neurons_are_the_mapped_inventory():
    rows = _mapped_rows()
    assert dn_arena.neurons(dn_arena.load()) == rows
    assert set(rows.values()) == {
        ("DNa01", "L"),
        ("DNa01", "R"),
        ("DNa02", "L"),
        ("DNa02", "R"),
        ("oDN1", "L"),
        ("oDN1", "R"),
    }


def test_cells_and_jobs():
    doc = dn_arena.load()
    cells = dn_arena.cells(doc)
    dec = doc["decoder"]
    assert cells == [
        {"yaw_gain_deg_s_per_hz": yaw, "forward_gain_mm_s_per_hz": forward}
        for yaw in dec["yaw_gain_deg_s_per_hz"]
        for forward in dec["forward_gain_mm_s_per_hz"]
    ]
    assert len(cells) == 6
    wn = doc["controls"]["wiring_null"]
    assert (wn["seed0"], wn["seeds"]) == (7100, 39)
    jobs = dn_arena.jobs(doc)
    assert jobs == dn_arena.jobs(doc)
    assert len(jobs) == 6 + 6 * 39 + 1
    assert len({job["key"] for job in jobs}) == len(jobs)
    seeds = list(range(wn["seed0"], wn["seed0"] + wn["seeds"]))
    cursor = 0
    for cell in cells:
        arms = jobs[cursor]
        assert arms["kind"] == "arms" and arms["cell"] == cell
        assert arms["arms"] == list(ARM_ORDER)
        assert arms["arms"].index("replay") > arms["arms"].index("intact")
        cursor += 1
        found = []
        for _seed in seeds:
            null = jobs[cursor]
            assert null["kind"] == "wiring-null" and null["cell"] == cell
            found.append(null["seed"])
            cursor += 1
        assert found == seeds
    assert jobs[cursor] == {"key": "script", "kind": "script", "cell": None}
    assert cursor == len(jobs) - 1


def test_heading_matches_the_arena_after_every_tick():
    clock = test_closedloop.CLOCK
    body = _LoggingArena()
    record = closedloop.run(
        test_closedloop.runtime(4_000),
        body,
        input_ids=test_closedloop.INPUT_IDS,
        traced_ids=(DNA01_L,),
        stimulus=lambda _time, _state: (0.0,),
        transducer=lambda _coverage: np.array([1_000_000.0]),
        decoder=Decoder(
            gains=dict(GAINS),
            window=(0, 4_000),
            actuators=body.actuators,
            clock=clock,
            neurons=dict(NEURONS),
        ),
        compiled=body.compiled,
        clock=clock,
        duration_us=4_000,
        arm="intact",
        mode="synthetic",
        evidence=dict(test_closedloop.SYNTHETIC),
        provenance=test_closedloop.PROVENANCE,
        optics_config_sha256="c" * 64,
        run_identity_sha256="b" * 64,
        input_gap_steps=0,
    )
    heading = dn_arena.heading_rad(record, clock)
    assert np.array_equal(heading, body.logged)
    assert not np.all(heading == 0.0)
    assert dn_arena.yaw_change(heading, clock, (0, 4_000)) == float(heading[-1])
    with pytest.raises(dn_arena.DNArenaError):
        dn_arena.yaw_change(heading, clock, (100, 500))


def test_rates_follow_full_light_and_nonfinite_coverage_is_refused():
    rate = dn_arena.load()["transducer"]["rate_full_light_hz"]
    coverage = (0.0, 0.5, 1.0)
    column = [2, 0, 1, 2]
    got = dn_arena.rates(coverage, column, rate)
    assert got.tolist() == [rate * (1.0 - coverage[i]) for i in column]
    assert not np.isfinite(dn_arena.rates((float("nan"),), [0], rate)).all()
    with pytest.raises(ContractError):
        test_closedloop.run(stimulus=lambda _time, _state: (float("nan"),))


def test_verdict_uses_the_inclusive_null_and_the_no_go():
    n = 6
    rows, doc, ids = _rows(0.0, True)
    found = dn_arena.verdict(rows, doc)
    assert found["envelope"] == "robust: null"
    cell = found["cells"][0]
    assert cell["verdict"] == "null"
    assert cell["intact"] == 0.0
    assert cell["disconnected"] == 1.0
    assert cell["shuffled"] == 2.0
    assert cell["replay"] == 4.0
    assert cell["silenced"] == 3.0
    assert cell["script"] == 5.0
    assert cell["intact_minus_script"] == -5.0
    assert cell["wiring_null_minimum"] == 0.0
    assert cell["wiring_null_median"] == 19.0
    assert cell["wiring_null_maximum"] == 38.0
    assert cell["replay_parity"] is True
    assert set(cell["spikes"]) == set(ARM_ORDER)
    assert cell["spikes"]["intact"] == _spikes(ids, True)
    assert [row["verdict"] for row in found["cells"]] == ["null"] * n

    at_max, doc, _ids = _rows(38.0, True)
    assert dn_arena.verdict(at_max, doc)["envelope"] == "robust: null"

    below, doc, _ids = _rows(-1e-6, True)
    above, doc, _ids = _rows(38.0 + 1e-6, True)
    assert dn_arena.verdict(below, doc)["envelope"] == "robust: difference"
    assert dn_arena.verdict(above, doc)["envelope"] == "robust: difference"

    mixed_yaw = [0.0, -1e-6] + [0.0] * (n - 2)
    mixed, doc, _ids = _rows(mixed_yaw, True)
    judged = dn_arena.verdict(mixed, doc)
    assert judged["envelope"] == "depends"
    assert [row["verdict"] for row in judged["cells"]] == [
        "null",
        "difference",
        *["null"] * (n - 2),
    ]

    dark, doc, _ids = _rows(100.0, False)
    blind = dn_arena.verdict(dark, doc)
    assert blind["envelope"] == "uninformative"
    assert blind["cells"][0]["verdict"] == "uninformative"
    assert blind["cells"][0]["intact"] == 100.0
    assert blind["cells"][0]["wiring_null_maximum"] == 38.0
    assert sum(blind["cells"][0]["spikes"]["intact"].values()) == 0

    partial_spikes = [False] + [True] * (n - 1)
    partial_yaw = [100.0] + [0.0] * (n - 1)
    partial, doc, _ids = _rows(partial_yaw, partial_spikes)
    split = dn_arena.verdict(partial, doc)
    assert split["envelope"] == "depends"
    assert split["cells"][0]["verdict"] == "uninformative"
    assert split["cells"][1]["verdict"] == "null"

    other, doc, _ids = _rows(0.0, True, script_yaw=9.0)
    shifted = dn_arena.verdict(other, doc)
    assert shifted["envelope"] == found["envelope"]
    assert [row["verdict"] for row in shifted["cells"]] == ["null"] * n
    assert shifted["cells"][0]["script"] == 9.0
    assert shifted["cells"][0]["intact_minus_script"] == -9.0
