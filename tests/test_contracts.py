"""The boundaries named in docs/architecture.md. One test per boundary; none loads MaleCNS.

A failure here means a contract between modules changed. Change the ADR with it, or put the
contract back.
"""

import inspect
import json
from pathlib import Path

import numpy as np
import pytest
from test_cli import data_dir  # noqa: F401  (fixture)

from flymsg import (
    behavior,
    benchmarks,
    data,
    embodiment,
    manifest,
    motor_map,
    prereg,
    silence_scan,
    sim,
    viz,
)

ROOT = Path(__file__).resolve().parents[1]


def test_b1_dataset_tables(data_dir):  # noqa: F811
    neurons, edges = data.load(data_dir)
    assert list(neurons.columns) == [*data.ANN_COLS, "nt", "sign"]
    assert neurons["bodyId"].is_monotonic_increasing
    assert neurons["sign"].dtype == np.int8
    assert list(edges.columns) == ["pre", "post", "weight"]
    assert all(edges[c].dtype == np.int32 for c in edges.columns)
    # pre/post are row positions in `neurons`, not bodyIds
    assert edges["pre"].max() < len(neurons) and edges["post"].max() < len(neurons)


def test_b2_engine_entry_point():
    params = list(inspect.signature(sim.run).parameters)
    assert params == [
        "W",
        "stim",
        "rate_hz",
        "duration_ms",
        "stim_ms",
        "p",
        "seed",
        "bin_ms",
        "silence",
        "kicks",
        "trace",
    ]
    fields = {f for f in sim.Result.__dataclass_fields__}
    assert fields == {"counts", "first_spike_ms", "bin_ms", "stim_ms", "traced"}
    assert sim.Params.dt == 0.1


def test_b2_runtime_runs_the_same_engine():
    from test_core import chain

    from flymsg.runtime import CpuRuntime

    edges, sign, n = chain([400, 400])
    p = sim.Params()
    W = sim.weight_matrix(edges, sign, n, p.w_syn)
    kicks = sim.poisson_kicks(3, 150.0, p.dt, 2000, 1)
    ref = sim.run(W, np.array([0]), 150.0, 200.0, None, p, 3, kicks=kicks)
    rt = CpuRuntime(W, np.array([0]), steps=2000, kicks=kicks, p=p, per_bin=100)
    rt.advance_to(777)
    rt.advance_to(2000)
    got = rt.result()
    assert np.array_equal(got.counts, ref.counts)
    assert np.array_equal(got.first_spike_ms, ref.first_spike_ms, equal_nan=True)
    assert ref.counts[:, 2].sum() > 0  # the signal crossed the chain
    assert rt._constants == sim._constants(p)
    assert (rt._d, rt._ref_steps) == sim._delays(p)


@pytest.mark.parametrize(
    ("module", "path"),
    [
        (behavior, behavior.PATH),
        (benchmarks, benchmarks.PATH),
        (motor_map, motor_map.PATH),
        (silence_scan, silence_scan.PATH),
    ],
)
def test_b3_protocol_locks(module, path):
    doc = module.load(path)
    assert module.content_hash(doc) == module.VERSION_HASHES[doc["version"]]
    assert doc["content_sha256"] == module.VERSION_HASHES[doc["version"]]
    module.assert_locked(doc)


def test_b3_preregistration_lock():
    doc = prereg.load()
    assert prereg.content_hash(doc) == prereg.VERSION_HASHES[doc["version"]]
    prereg.assert_file_matches_code(doc)


def test_b4_run_manifest_schema():
    assert manifest.SCHEMA == "flymsg.run_manifest/v1"
    for path in sorted(ROOT.glob("docs/live/*/manifest.json")):
        doc = json.loads(path.read_text())
        assert doc["schema"] == manifest.SCHEMA, path
        assert manifest.required_keys(doc) == [], path


NEURON_KEYS = {
    "bodyId",
    "type",
    "instance",
    "nt",
    "superclass",
    "dimorphism",
    "fruDsx",
    "group",
    "rate",
}


def test_b5_viewer_bundle():
    page = (viz.STATIC / "main.js").read_text() + (
        viz.STATIC / "partners.js"
    ).read_text()
    for name in ("scene.json", "activity.bin", "partners.json"):
        assert f'"{name}"' in page  # the files the page fetches
    assert f'SCENE_SCHEMA = "{viz.SCENE_SCHEMA}"' in page  # page and exporter agree
    for path in sorted(ROOT.glob("docs/live/*/scene.json")):
        scene = json.loads(path.read_text())
        assert scene["schema"] == viz.SCENE_SCHEMA, path
        keys = NEURON_KEYS | ({"in", "rate_b"} if "comparison" in scene else set())
        assert all(set(n) == keys for n in scene["neurons"]), path
        if "activity" in scene:
            act = scene["activity"]
            assert set(act) == {"bins", "bin_ms", "stim_ms"}
            size = (path.parent / "activity.bin").stat().st_size
            assert size == act["bins"] * len(scene["neurons"])  # uint8, bin-major
            if "comparison" in scene:
                size_b = (path.parent / "activity_b.bin").stat().st_size
                assert size_b == size
                assert {r["status"] for r in scene["comparison"]["runs"]} <= set(
                    viz.COMPARE_STATUSES
                )
        table = json.loads((path.parent / "partners.json").read_text())
        assert set(table) == {"source", "top", "neurons"}
        assert set(table["neurons"]) == {str(n["bodyId"]) for n in scene["neurons"]}


def test_b6_embodiment_contract():
    assert embodiment.SCHEMA == "flymsg.embodiment/v1"
    assert embodiment.CLOCK == "flymsg.clock/us-v1"
    assert embodiment.Clock().neural_us == round(sim.Params.dt * 1000)
    # the only path from a motor neuron to a body refuses every name while all rows are unmapped
    doc = motor_map.assert_locked()
    for row in [*doc["actuators"], *doc["neurons"]]:
        with pytest.raises(motor_map.MotorMapError):
            motor_map.command(row["name"], doc)


@pytest.mark.parametrize(
    ("module", "error"),
    [
        (behavior, behavior.BehaviorError),
        (benchmarks, benchmarks.BenchmarkError),
        (motor_map, motor_map.MotorMapError),
        (silence_scan, silence_scan.ScanError),
    ],
)
def test_b3_locks_share_one_check_and_keep_their_errors(module, error):
    doc = module.load()
    with pytest.raises(error, match="not in VERSION_HASHES"):
        module.assert_locked({**doc, "version": 999})
    with pytest.raises(error, match="does not match"):
        module.assert_locked({**doc, "content_sha256": "0" * 64})
