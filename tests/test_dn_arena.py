"""The DN arena lock, its jobs and the yaw metric. No connectome and no FlyGym."""

import copy
from pathlib import Path

import numpy as np
import pytest
import test_closedloop
from test_dn_decoder import DNA01_L, GAINS, NEURONS

from flymsg import closedloop, dn_arena, sim, visual_pathway
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
    elif name == "window":
        doc["score"]["window_us"] = [0, doc["model"]["duration_us"] + 1]
    elif name == "decoder_window":
        doc["decoder"]["window_us"] = [0, doc["model"]["duration_us"] + 1]
    elif name == "neuron":
        doc["decoder"]["neurons"][0] = "1 DNa01 L"
    elif name == "scored":
        doc["claim"]["scored"] = True
    elif name == "defaults":
        doc["defaults_changed"] = True
    elif name == "t4t5_sha256":
        doc["pathway"]["t4t5_sha256"] = "0" * 64
    elif name == "pathway":
        doc["pathway"]["photoreceptor_response_mv"] = 40.0
    elif name == "encoding":
        doc["model"]["input_encoding"] = "counts"
    elif name == "configuration":
        doc["pathway"]["lmc_rate_hz"] = 100.0
    elif name == "smoke":
        doc["smoke"] = ""
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
    seed0 = doc["controls"]["wiring_null"]["seed0"]
    rows = []
    for job in dn_arena.jobs(doc):
        if job["kind"] == "script":
            rows.append({"key": job["key"], "yaw_change": float(script_yaw)})
            continue
        index = job["configuration"]["index"]
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
        rows.append(
            {
                "key": job["key"],
                "replay_parity": True,
                "pathway_sha256": "b" * 64,
                "arms": per_arm,
            }
        )
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
    [
        "seeds",
        "arms",
        "window",
        "decoder_window",
        "neuron",
        "scored",
        "defaults",
        "t4t5_sha256",
        "pathway",
        "encoding",
        "configuration",
        "smoke",
    ],
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


def test_configurations_and_jobs():
    doc = dn_arena.load()
    configs = dn_arena.configurations(doc)
    path = doc["pathway"]
    assert configs == [
        {
            "index": i,
            "photoreceptor_mv": path["photoreceptor_response_mv"],
            "lmc_mv": path["lmc_hyperpolarisation_mv"],
            "lmc_rate_hz": path["lmc_rate_hz"],
            "medulla_rate_hz": path["medulla_rate_hz"],
            "lamina_medulla_gain": gain,
        }
        for i, gain in enumerate(path["lamina_medulla_gain"])
    ]
    assert [cfg["lamina_medulla_gain"] for cfg in configs] == [1.0, 4.0, 16.0]
    assert len(configs) == 3
    wn = doc["controls"]["wiring_null"]
    assert (wn["seed0"], wn["seeds"]) == (7300, 39)
    jobs = dn_arena.jobs(doc)
    assert jobs == dn_arena.jobs(doc)
    assert len(jobs) == 121
    assert len(jobs) == 3 + 3 * 39 + 1
    assert len({job["key"] for job in jobs}) == len(jobs)
    seeds = list(range(wn["seed0"], wn["seed0"] + wn["seeds"]))
    cursor = 0
    for cfg in configs:
        arms = jobs[cursor]
        assert arms["kind"] == "arms" and arms["configuration"] == cfg
        assert arms["key"] == f"arms/{cfg['index']}"
        assert arms["arms"] == list(ARM_ORDER)
        assert arms["arms"].index("replay") > arms["arms"].index("intact")
        cursor += 1
        found = []
        for _seed in seeds:
            null = jobs[cursor]
            assert null["kind"] == "wiring-null" and null["configuration"] == cfg
            assert null["key"] == f"wiring-null/{cfg['index']}/{null['seed']}"
            found.append(null["seed"])
            cursor += 1
        assert found == seeds
    assert jobs[cursor] == {"key": "script", "kind": "script"}
    assert cursor == len(jobs) - 1
    assert jobs[0]["key"] == "arms/0"
    assert any(job["key"] == "wiring-null/0/7300" for job in jobs)


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
        input_encoding="counts",
        pathway_sha256=None,
    )
    heading = dn_arena.heading_rad(record, clock)
    assert np.array_equal(heading, body.logged)
    assert not np.all(heading == 0.0)
    assert dn_arena.yaw_change(heading, clock, (0, 4_000)) == float(heading[-1])
    with pytest.raises(dn_arena.DNArenaError):
        dn_arena.yaw_change(heading, clock, (100, 500))


def test_drive_matches_the_locked_rule_bit_for_bit():
    gain = 0.137
    coverage = (0.0, 0.25, 1.0, -0.5, 1.5)
    column = [2, 0, 4, 1]
    steps = 4
    got = dn_arena.drive(coverage, column, gain, steps)
    lit = 1.0 - np.asarray(coverage, dtype=np.float64)[np.asarray(column)]
    row = (gain * lit).astype(np.float32)
    expect = np.broadcast_to(row, (steps, row.shape[0])).copy()
    assert got.dtype == np.float32
    assert got.shape == (steps, len(column))
    assert got.flags.c_contiguous
    assert got.tobytes() == expect.tobytes()
    assert np.isfinite(got).all()
    nan = dn_arena.drive((float("nan"),), [0], gain, 2)
    assert nan.shape == (2, 1) and nan.dtype == np.float32
    assert not np.isfinite(nan).all()


def test_a_toy_graded_loop_records_the_pathway_hash():
    from scipy import sparse
    from test_visual_pathway import LIT, _neurons, _protocol, _weights

    neurons = _neurons()
    weights = _weights()
    proto, cfg = _protocol("v4")
    proto = {**proto, "settle_ms": 20.0, "dark_anchor_passes": 2, "seed": 98}
    p = sim.Params()
    static, built = dn_arena.pathway(weights, neurons, cfg, LIT, proto, p)
    digest = visual_pathway.config_hash(static, built)
    bare = sparse.csc_matrix(weights.shape, dtype=np.float32)
    with pytest.raises(dn_arena.DNArenaError):
        dn_arena.pathway(bare, neurons, cfg, LIT, proto, p)
    doubled = weights.copy()
    doubled.data = (doubled.data * np.float32(2)).astype(np.float32)
    static_n, null = dn_arena.pathway(
        doubled,
        neurons,
        cfg,
        LIT,
        proto,
        p,
        rate=(built.rate_hz, built.receiving),
    )
    assert built.rate_hz > 0.0
    assert null.rate_hz == built.rate_hz
    assert np.array_equal(null.receiving, built.receiving)
    assert null.gain == built.gain
    assert set(null.anchor) == set(built.anchor)
    moved = False
    for name in built.anchor:
        assert np.isfinite(built.anchor[name]).all()
        assert np.isfinite(null.anchor[name]).all()
        moved = moved or not np.array_equal(null.anchor[name], built.anchor[name])
    assert moved
    assert visual_pathway.config_hash(static_n, null) != digest

    clock = test_closedloop.CLOCK
    duration = 2_000
    per = clock.body_us // clock.neural_us
    column = np.array([0, 1])
    coverage = (0.25, 0.75)

    def transducer(_stim):
        return dn_arena.drive(coverage, column, built.gain, per)

    def runtime():
        return dn_arena.cpu_runtime(
            built,
            LIT,
            steps=duration // clock.neural_us,
            p=p,
            per_bin=clock.control_us // clock.neural_us,
            trace=np.array([13]),
            silence=False,
        )

    def run(body_runtime, **kw):
        return closedloop.run(
            body_runtime,
            test_closedloop.ToyBody(),
            input_ids=(10, 11),
            traced_ids=(13,),
            stimulus=lambda _t, _s: coverage,
            transducer=transducer,
            decoder=test_closedloop.decoder,
            compiled=test_closedloop.COMPILED,
            clock=clock,
            duration_us=duration,
            arm=kw.pop("arm", "intact"),
            mode="synthetic",
            evidence=dict(test_closedloop.SYNTHETIC),
            provenance=test_closedloop.PROVENANCE,
            optics_config_sha256="c" * 64,
            run_identity_sha256="e" * 64,
            input_gap_steps=0,
            input_encoding="kick_equivalent",
            pathway_sha256=digest,
            **kw,
        )

    record = run(runtime())
    assert type(record) is closedloop.RecordV2
    assert record.input_encoding == "kick_equivalent"
    assert record.pathway_sha256 == digest
    expected = dn_arena.drive(coverage, column, built.gain, per)
    stored = np.asarray(record.ticks[0].input_drive, dtype=np.float64)
    assert np.array_equal(stored, expected.astype(np.float64))
    replayed = run(runtime(), arm="replay", replay=record)
    closedloop.replay_parity(record, replayed)

    def nonfinite(_stim):
        return dn_arena.drive((float("nan"), 0.0), [0, 1], built.gain, per)

    with pytest.raises(ContractError):
        closedloop.run(
            runtime(),
            test_closedloop.ToyBody(),
            input_ids=(10, 11),
            traced_ids=(13,),
            stimulus=lambda _t, _s: (float("nan"), 0.0),
            transducer=nonfinite,
            decoder=test_closedloop.decoder,
            compiled=test_closedloop.COMPILED,
            clock=clock,
            duration_us=duration,
            arm="intact",
            mode="synthetic",
            evidence=dict(test_closedloop.SYNTHETIC),
            provenance=test_closedloop.PROVENANCE,
            optics_config_sha256="c" * 64,
            run_identity_sha256="e" * 64,
            input_gap_steps=0,
            input_encoding="kick_equivalent",
            pathway_sha256=digest,
        )


def test_verdict_uses_the_inclusive_null_and_the_no_go():
    rows, doc, ids = _rows(0.0, True)
    n = len(dn_arena.configurations(doc))
    found = dn_arena.verdict(rows, doc)
    assert found["envelope"] == "robust: null"
    row = found["configurations"][0]
    assert row["verdict"] == "null"
    assert row["index"] == 0
    assert row["lamina_medulla_gain"] == 1.0
    assert row["intact"] == 0.0
    assert row["disconnected"] == 1.0
    assert row["shuffled"] == 2.0
    assert row["replay"] == 4.0
    assert row["silenced"] == 3.0
    assert row["script"] == 5.0
    assert row["intact_minus_script"] == -5.0
    assert row["wiring_null_minimum"] == 0.0
    assert row["wiring_null_median"] == 19.0
    assert row["wiring_null_maximum"] == 38.0
    assert row["replay_parity"] is True
    assert row["pathway_sha256"] == "b" * 64
    assert set(row["spikes"]) == set(ARM_ORDER)
    assert row["spikes"]["intact"] == _spikes(ids, True)
    assert [item["verdict"] for item in found["configurations"]] == ["null"] * n
    assert [item["index"] for item in found["configurations"]] == [0, 1, 2]

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
    assert [item["verdict"] for item in judged["configurations"]] == [
        "null",
        "difference",
        *["null"] * (n - 2),
    ]

    dark, doc, _ids = _rows(100.0, False)
    blind = dn_arena.verdict(dark, doc)
    assert blind["envelope"] == "uninformative"
    assert blind["configurations"][0]["verdict"] == "uninformative"
    assert blind["configurations"][0]["intact"] == 100.0
    assert blind["configurations"][0]["wiring_null_maximum"] == 38.0
    assert sum(blind["configurations"][0]["spikes"]["intact"].values()) == 0

    partial_spikes = [False] + [True] * (n - 1)
    partial_yaw = [100.0] + [0.0] * (n - 1)
    partial, doc, _ids = _rows(partial_yaw, partial_spikes)
    split = dn_arena.verdict(partial, doc)
    assert split["envelope"] == "depends"
    assert split["configurations"][0]["verdict"] == "uninformative"
    assert split["configurations"][1]["verdict"] == "null"

    other, doc, _ids = _rows(0.0, True, script_yaw=9.0)
    shifted = dn_arena.verdict(other, doc)
    assert shifted["envelope"] == found["envelope"]
    assert [item["verdict"] for item in shifted["configurations"]] == ["null"] * n
    assert shifted["configurations"][0]["script"] == 9.0
    assert shifted["configurations"][0]["intact_minus_script"] == -9.0


class _Text:
    def __init__(self, text):
        self.text = text

    def to_json(self):
        return self.text


def test_stored_records_are_verified_and_damage_refuses(tmp_path):
    import gzip

    from flymsg import dn_arena

    (tmp_path / "records").mkdir()
    arms = {
        arm: {
            "record_sha256": dn_arena._store(tmp_path, f"arms/1/2__{arm}", _Text(arm))
        }
        for arm in ("intact", "replay")
    }
    null = dn_arena._store(tmp_path, "wiring-null/1/2/7100", _Text("null"))
    rows = [
        {"kind": "arms", "key": "arms/1/2", "arms": arms},
        {"kind": "wiring-null", "key": "wiring-null/1/2/7100", "record_sha256": null},
    ]
    dn_arena.verify_records(tmp_path, rows)
    stored = tmp_path / "records" / "arms__1__2__replay.json.gz"
    with gzip.open(stored, "wb") as stream:
        stream.write(b"tampered")
    with pytest.raises(dn_arena.DNArenaError, match="does not match"):
        dn_arena.verify_records(tmp_path, rows)
    stored.unlink()
    with pytest.raises(dn_arena.DNArenaError, match="missing"):
        dn_arena.verify_records(tmp_path, rows)


def test_stored_records_are_byte_stable(tmp_path):
    from flymsg import dn_arena

    (tmp_path / "records").mkdir()
    first = dn_arena._store(tmp_path, "script", _Text("same"))
    data = (tmp_path / "records" / "script.json.gz").read_bytes()
    assert dn_arena._store(tmp_path, "script", _Text("same")) == first
    assert (tmp_path / "records" / "script.json.gz").read_bytes() == data
