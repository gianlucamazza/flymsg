"""The DN arena lock, its jobs and the yaw metric. No connectome and no FlyGym."""

import copy
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import test_closedloop
import test_optics
from test_dn_decoder import DNA01_L, GAINS, NEURONS

from flymsg import closedloop, dn_arena, optics, pose, sim, visual_pathway
from flymsg.arena import Arena
from flymsg.dn_decoder import Decoder
from flymsg.embodiment import ContractError
from flymsg.pose import IDENTITY, EyeMount

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


def _side_fired(spikes, index, side):
    item = _at(spikes, index)
    if isinstance(item, dict):
        return bool(item[side])
    return bool(item)


def _rows(
    intact,
    spikes,
    script_yaw=None,
    paired_intact=None,
    paired_spikes=None,
    nulls=None,
):
    """Synthetic results. `intact` is the mirrored contrast, shared by a configuration.

    Left yaw is twice that contrast and mirror yaw is 0, so the score reads it back.
    `nulls`, when given, replaces the contrasts 0 .. 38. The paired set defaults to
    the same contrasts and spikes as `all`.
    """
    doc = dn_arena.load()
    ids = [str(body) for body in sorted(dn_arena.neurons(doc))]
    seed0 = doc["controls"]["wiring_null"]["seed0"]
    if script_yaw is None:
        script_yaw = {"left": 5.0, "mirror": 6.0}
    chosen = {
        "all": (intact, spikes),
        "paired": (
            intact if paired_intact is None else paired_intact,
            spikes if paired_spikes is None else paired_spikes,
        ),
    }
    rows = []
    for job in dn_arena.jobs(doc):
        if job["kind"] == "script":
            rows.append(
                {"key": job["key"], "yaw_change": float(script_yaw[job["side"]])}
            )
            continue
        index = job["configuration"]["index"]
        if job["kind"] == "wiring-null":
            i = job["seed"] - seed0
            contrast_i = float(i if nulls is None else nulls[i])
            rows.append(
                {
                    "key": job["key"],
                    "yaw_change": {"left": 2.0 * contrast_i, "mirror": 0.0},
                }
            )
            continue
        value = float(_at(chosen[job["input_set"]][0], index))
        fired = _side_fired(chosen[job["input_set"]][1], index, job["side"])
        per_arm = {}
        for arm in job["arms"]:
            if arm == "intact":
                yaw = 2.0 * value if job["side"] == "left" else 0.0
                counts = _spikes(ids, fired)
            else:
                yaw = OTHER_YAW[arm] + (10.0 if job["side"] == "mirror" else 0.0)
                counts = _spikes(ids, True)
            per_arm[arm] = {
                "yaw_change": yaw,
                "spikes": counts,
                "record_sha256": "a" * 64,
            }
        digest = "b" * 64 if job["input_set"] == "all" else "c" * 64
        rows.append(
            {
                "key": job["key"],
                "replay_parity": True,
                "pathway_sha256": digest,
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
    assert doc["version"] == 3
    assert dn_arena.content_hash(doc) == dn_arena.VERSION_HASHES[3]
    assert dn_arena.VERSION_HASHES == {
        1: "9ba9a69c8397fae5c6aa9ee60cd48147d4898110c2dbb22a2d461254b4583aa3",
        2: "1426386c66041510812bdcd6b3bfebb91d05a0811c5bfe33f9c191f3cd9a3ac7",
        3: "7ed0e04de84b9a584080021da2c5d4748d062e5af92327deab049b15ffbbea1c",
    }
    assert doc["content_sha256"] == dn_arena.VERSION_HASHES[3]
    assert dn_arena.summary() == (
        "dn_arena v3 (issue #263): 2 input sets, 2 configurations, 2 sides, "
        "5 arms, 39 nulls, seeds 7400-7438, duration 1000000 us, kick_equivalent"
    )


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
    assert [cfg["lamina_medulla_gain"] for cfg in configs] == [4.0, 16.0]
    assert len(configs) == 2
    wn = doc["controls"]["wiring_null"]
    assert (wn["seed0"], wn["seeds"]) == (7400, 39)
    jobs = dn_arena.jobs(doc)
    assert jobs == dn_arena.jobs(doc)
    sets = doc["pathway"]["input_sets"]
    sides = doc["stimulus"]["sides"]
    assert sets == ["all", "paired"]
    assert sides == ["left", "mirror"]
    # per input set and configuration: one arms job per side, then 39 nulls;
    # the script is one job per side and does not depend on the set
    assert len(jobs) == len(sets) * len(configs) * (len(sides) + wn["seeds"]) + len(
        sides
    )
    assert len(jobs) == 166
    assert len({job["key"] for job in jobs}) == len(jobs)
    seeds = list(range(wn["seed0"], wn["seed0"] + wn["seeds"]))
    cursor = 0
    for name in sets:
        for cfg in configs:
            for side in sides:
                arms = jobs[cursor]
                assert arms["kind"] == "arms" and arms["configuration"] == cfg
                assert arms["input_set"] == name and arms["side"] == side
                assert arms["key"] == f"arms/{name}/{cfg['index']}/{side}"
                assert arms["arms"] == list(ARM_ORDER)
                assert arms["arms"].index("replay") > arms["arms"].index("intact")
                cursor += 1
            found = []
            for _seed in seeds:
                null = jobs[cursor]
                assert null["kind"] == "wiring-null" and null["configuration"] == cfg
                assert null["input_set"] == name and "side" not in null
                assert (
                    null["key"] == f"wiring-null/{name}/{cfg['index']}/{null['seed']}"
                )
                found.append(null["seed"])
                cursor += 1
            assert found == seeds
    for side in sides:
        assert jobs[cursor] == {"key": f"script/{side}", "kind": "script", "side": side}
        cursor += 1
    assert cursor == len(jobs)
    assert jobs[0]["key"] == "arms/all/0/left"
    assert any(job["key"] == "wiring-null/all/0/7400" for job in jobs)
    assert [job["key"] for job in jobs[-2:]] == ["script/left", "script/mirror"]


def test_paired_inputs_require_a_directed_mirror_column():
    # (1, 1) is paired. (2, 2) loses its mirror to a missing azimuth. (3, 3) is
    # directed on both sides but only the left has an input. (4, 4) has no mirror
    # column. (5, 5) and (5, 6) are both directed and are not mirrors.
    columns = pd.DataFrame(
        {
            "side": ["L", "R", "L", "R", "L", "R", "L", "R", "L"],
            "hex1": [1, 1, 2, 2, 3, 3, 4, 5, 5],
            "hex2": [1, 1, 2, 2, 3, 3, 4, 5, 6],
            "azimuth_deg": [
                -10.0,
                10.0,
                -20.0,
                np.nan,
                -30.0,
                30.0,
                -40.0,
                50.0,
                -55.0,
            ],
            "elevation_deg": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
    )
    receptors = pd.DataFrame(
        {
            "side": ["L", "R", "L", "L", "R", "L", "L", "R", "L"],
            "hex1": [1, 1, 1, 2, 2, 3, 4, 5, 5],
            "hex2": [1, 1, 1, 2, 2, 3, 4, 5, 6],
            "neuron": [11, 12, 10, 20, 21, 30, 40, 50, 51],
        }
    )
    directed = dn_arena.directed_inputs(columns, receptors)
    assert directed["neuron"].tolist() == [10, 11, 12, 20, 30, 40, 50, 51]
    assert directed["rank"].tolist() == [0, 0, 1, 2, 3, 5, 6, 7]
    paired = dn_arena.paired_inputs(directed)
    assert paired["neuron"].tolist() == [10, 11, 12]
    assert paired["rank"].tolist() == [0, 0, 1]
    assert list(zip(paired["side"], paired["hex1"], paired["hex2"], strict=True)) == [
        ("L", 1, 1),
        ("L", 1, 1),
        ("R", 1, 1),
    ]
    assert dn_arena.paired_inputs(directed[directed["hex1"] == 4]).empty
    bad = directed.copy()
    bad.loc[bad.index[0], "side"] = "left"
    with pytest.raises(dn_arena.DNArenaError, match="L or R"):
        dn_arena.paired_inputs(bad)


def _on_axis(time_us, body_pose):
    return pose.BodyState(time_us, body_pose, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def test_the_bar_covers_the_aimed_eye_and_sweeps_toward_the_midline():
    # Eyes on the cylinder axis, so a column's body azimuth of the bar centre is
    # the centre itself. Left body azimuth -56.25 is world azimuth +56.25.
    doc = dn_arena.load()
    reset = dn_arena._body(doc).reset()
    mounts = (
        EyeMount("L", pose.Pose("body", "eye/L", (0.0, 0.0, 0.0), IDENTITY), "on axis"),
        EyeMount("R", pose.Pose("body", "eye/R", (0.0, 0.0, 0.0), IDENTITY), "on axis"),
    )
    made = dn_arena.bars(doc, reset, mounts)
    half = float(doc["stimulus"]["screen_radius_m"]) * math.tan(
        math.radians(float(doc["stimulus"]["height_deg"]) / 2.0)
    )
    assert made["left"].angular_velocity_deg_s == -25.0
    assert made["mirror"].angular_velocity_deg_s == 25.0
    assert made["left"].azimuth0_deg == 56.25
    assert made["mirror"].azimuth0_deg == -56.25
    assert made["left"].screen_radius_m == 0.1
    assert made["left"].axis_xy_m == (0.0, 0.0)
    assert made["left"].visible_us == (100_000, 1_000_000)
    assert made["left"].z_bottom_m == pytest.approx(-half)
    assert made["left"].z_top_m == pytest.approx(half)
    assert made["mirror"].z_bottom_m == made["left"].z_bottom_m
    cols = test_optics.table(
        [
            ("L", -56.25, 0.0),
            ("L", -54.0, 0.0),
            ("R", 56.25, 0.0),
            ("R", 54.0, 0.0),
            ("L", -33.75, 0.0),
            ("R", 33.75, 0.0),
        ]
    )
    quad = tuple(doc["stimulus"]["quadrature"])
    acceptance = float(doc["eye"]["acceptance_deg"])

    def sample(side, time_us):
        return optics.bar_coverage(
            cols,
            test_optics.REG,
            mounts,
            _on_axis(time_us, reset.pose),
            (made[side],),
            acceptance,
            quad,
        )

    start, end = 100_000, 999_999
    opened = sample("left", start)
    assert np.allclose(opened.azimuth_deg[0], -56.25)
    assert opened.coverage[0, 0] > 0.5 and opened.coverage[0, 1] > 0.5
    assert np.all(opened.coverage[0, 2:] == 0.0)
    mirrored = sample("mirror", start)
    assert np.allclose(mirrored.azimuth_deg[0], 56.25)
    assert mirrored.coverage[0, 2] > 0.5 and mirrored.coverage[0, 3] > 0.5
    assert mirrored.coverage[0, 0] == 0.0 and mirrored.coverage[0, 1] == 0.0
    assert mirrored.coverage[0, 4] == 0.0 and mirrored.coverage[0, 5] == 0.0
    late = sample("left", end)
    body = -made["left"].centre_azimuth_deg(end)
    assert np.allclose(late.azimuth_deg[0], body)
    assert abs(body - (-33.75)) < 1e-3 and body < -33.75
    assert late.coverage[0, 4] > 0.5
    assert late.coverage[0, 0] == 0.0 and np.all(late.coverage[0, [2, 3, 5]] == 0.0)
    late_m = sample("mirror", end)
    body_m = -made["mirror"].centre_azimuth_deg(end)
    assert np.allclose(late_m.azimuth_deg[0], body_m)
    assert abs(body_m - 33.75) < 1e-3 and body_m > 33.75
    assert late_m.coverage[0, 5] > 0.5
    assert np.all(late_m.coverage[0, :5] == 0.0)
    # half-open window: the microsecond before the sweep and the end instant are dark
    assert np.all(sample("left", start - 1).coverage == 0.0)
    assert np.all(sample("left", 1_000_000).coverage == 0.0)


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


def test_verdict_scores_the_contrast_and_keeps_the_paired_set_outside():
    rows, doc, ids = _rows(0.0, True)
    found = dn_arena.verdict(rows, doc)
    assert found["envelope"] == "robust: null"
    assert [item["verdict"] for item in found["configurations"]] == ["null", "null"]
    assert [item["verdict"] for item in found["sensitivity"]] == ["null", "null"]
    assert [item["index"] for item in found["configurations"]] == [0, 1]
    assert [item["lamina_medulla_gain"] for item in found["configurations"]] == [
        4.0,
        16.0,
    ]
    assert [item["input_set"] for item in found["configurations"]] == ["all", "all"]
    row = found["configurations"][0]
    assert row["verdict"] == "null"
    assert row["contrast"] == 0.0
    assert row["expected_sign"] == "positive"
    assert row["contrast_sign"] == "zero"
    assert row["expected_sign_met"] is False
    assert row["wiring_null_minimum"] == 0.0
    assert row["wiring_null_median"] == 19.0
    assert row["wiring_null_maximum"] == 38.0
    assert row["replay_parity"] is True
    assert row["pathway_sha256"] == "b" * 64
    assert "intact_minus_script" not in row
    left, mirror = row["sides"]["left"], row["sides"]["mirror"]
    assert left["intact"] == 0.0
    assert left["disconnected"] == 1.0
    assert left["shuffled"] == 2.0
    assert left["silenced"] == 3.0
    assert left["replay"] == 4.0
    assert left["script"] == 5.0
    assert set(left["spikes"]) == set(ARM_ORDER)
    assert left["spikes"]["intact"] == _spikes(ids, True)
    assert mirror["intact"] == 0.0
    assert mirror["disconnected"] == 11.0
    assert mirror["script"] == 6.0
    assert found["sensitivity"][0]["pathway_sha256"] == "c" * 64
    assert found["sensitivity"][0]["input_set"] == "paired"

    at_max, doc, _ids = _rows(38.0, True)
    assert dn_arena.verdict(at_max, doc)["envelope"] == "robust: null"

    above, doc, _ids = _rows(38.0 + 1e-6, True)
    high = dn_arena.verdict(above, doc)
    assert high["envelope"] == "robust: difference"
    assert high["configurations"][0]["verdict"] == "difference"
    assert high["configurations"][0]["contrast_sign"] == "positive"
    assert high["configurations"][0]["expected_sign_met"] is True

    below, doc, _ids = _rows(-1e-6, True)
    low = dn_arena.verdict(below, doc)
    assert low["envelope"] == "robust: difference (wrong sign)"
    assert low["configurations"][0]["verdict"] == "difference (wrong sign)"
    assert low["configurations"][0]["contrast_sign"] == "negative"
    assert low["configurations"][0]["expected_sign_met"] is False

    # a negative contrast inside the null range stays null
    inside, doc, _ids = _rows(-0.5, True, nulls=[-1.0, *range(38)])
    held = dn_arena.verdict(inside, doc)
    assert held["configurations"][0]["verdict"] == "null"
    assert held["configurations"][0]["contrast_sign"] == "negative"

    # zero outside the null range is a difference, not a wrong sign
    flat, doc, _ids = _rows(0.0, True, nulls=[1.0] * 39)
    zero = dn_arena.verdict(flat, doc)
    assert zero["envelope"] == "robust: difference"
    assert zero["configurations"][0]["verdict"] == "difference"
    assert zero["configurations"][0]["contrast_sign"] == "zero"

    mixed, doc, _ids = _rows([0.0, 38.0 + 1e-6], True)
    judged = dn_arena.verdict(mixed, doc)
    assert judged["envelope"] == "depends"
    assert [item["verdict"] for item in judged["configurations"]] == [
        "null",
        "difference",
    ]

    dark, doc, _ids = _rows(100.0, False)
    blind = dn_arena.verdict(dark, doc)
    assert blind["envelope"] == "uninformative"
    assert blind["configurations"][0]["verdict"] == "uninformative"
    assert blind["configurations"][0]["contrast"] == 100.0
    assert blind["configurations"][0]["wiring_null_maximum"] == 38.0
    assert (
        sum(blind["configurations"][0]["sides"]["left"]["spikes"]["intact"].values())
        == 0
    )
    assert (
        sum(blind["configurations"][0]["sides"]["mirror"]["spikes"]["intact"].values())
        == 0
    )

    # silence on one side is not the no-go
    one, doc, _ids = _rows(100.0, {"left": False, "mirror": True})
    heard = dn_arena.verdict(one, doc)
    assert heard["envelope"] == "robust: difference"
    assert heard["configurations"][0]["verdict"] == "difference"

    partial, doc, _ids = _rows([100.0, 0.0], [False, True])
    split = dn_arena.verdict(partial, doc)
    assert split["envelope"] == "depends"
    assert split["configurations"][0]["verdict"] == "uninformative"
    assert split["configurations"][1]["verdict"] == "null"

    # the paired set is reported and does not enter the envelope
    apart, doc, _ids = _rows(0.0, True, paired_intact=100.0, paired_spikes=False)
    outside = dn_arena.verdict(apart, doc)
    assert outside["envelope"] == "robust: null"
    assert [item["verdict"] for item in outside["sensitivity"]] == [
        "uninformative",
        "uninformative",
    ]
    moved, doc, _ids = _rows(0.0, True, paired_intact=100.0)
    sensitivity = dn_arena.verdict(moved, doc)
    assert sensitivity["envelope"] == "robust: null"
    assert [item["verdict"] for item in sensitivity["sensitivity"]] == [
        "difference",
        "difference",
    ]

    other, doc, _ids = _rows(0.0, True, script_yaw={"left": 9.0, "mirror": 8.0})
    shifted = dn_arena.verdict(other, doc)
    assert shifted["envelope"] == found["envelope"]
    assert [item["verdict"] for item in shifted["configurations"]] == ["null", "null"]
    assert shifted["configurations"][0]["sides"]["left"]["script"] == 9.0
    assert shifted["configurations"][0]["contrast"] == 0.0


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
    left = dn_arena._store(tmp_path, "wiring-null/all/1/7400__left", _Text("left"))
    mirror = dn_arena._store(
        tmp_path, "wiring-null/all/1/7400__mirror", _Text("mirror")
    )
    rows = [
        {"kind": "arms", "key": "arms/1/2", "arms": arms},
        {
            "kind": "wiring-null",
            "key": "wiring-null/all/1/7400",
            "record_sha256": {"left": left, "mirror": mirror},
        },
    ]
    with pytest.raises(dn_arena.DNArenaError, match="both sides"):
        dn_arena.record_names(
            {
                "kind": "wiring-null",
                "key": "wiring-null/all/1/7400",
                "record_sha256": left,
            }
        )
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
