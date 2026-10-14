import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flymsg import sim, viz

ROOT = Path(__file__).parent.parent


def result(counts, stim_ms=100.0):
    counts = np.asarray(counts, np.uint16)
    return sim.Result(counts, np.full(counts.shape[1], np.nan), 10.0, stim_ms)


def test_select_keeps_stim_first_then_every_responder_by_rate():
    counts = np.zeros((10, 6))
    counts[:, 0] = 3  # stimulated
    counts[:, 2] = 1
    counts[:, 4] = 2
    counts[0, 5] = 1  # one spike: 10 Hz over 100 ms
    r = result(counts)
    assert viz.select_from_result(r, np.array([0]), 0.0).tolist() == [0, 4, 2, 5]
    assert viz.select_from_result(r, np.array([0]), 50.0).tolist() == [
        0,
        4,
        2,
    ]  # 200, 100 Hz
    assert (
        viz.select_from_result(r, np.array([0, 0]), 0.0).tolist()[0] == 0
    )  # duplicates folded
    # a kept neuron is appended once even if silent; one already listed is not repeated
    assert viz.select_from_result(
        r, np.array([0]), 0.0, np.array([3, 4, 3])
    ).tolist() == [
        0,
        4,
        2,
        5,
        3,
    ]


NEURONS = pd.DataFrame(
    {
        "bodyId": [10, 20],
        "type": ["A", None],
        "instance": ["A_R", None],
        "nt": ["gaba", None],
        "superclass": ["x", "y"],
        "dimorphism": ["male-specific", None],
        "fruDsx": ["fru_high", None],
    }
)


def test_export_replay_bundle(tmp_path):
    counts = np.array([[1, 0], [0, 300]])
    viz.export(
        tmp_path, NEURONS, np.array([1, 0]), ["g1", "g2"], result(counts, stim_ms=10.0)
    )
    scene = json.loads((tmp_path / "scene.json").read_text())
    assert [n["bodyId"] for n in scene["neurons"]] == [20, 10]
    assert (
        scene["neurons"][0]["type"] == "untyped"
        and scene["neurons"][0]["nt"] == "unknown"
    )
    assert scene["neurons"][1]["rate"] == 100.0  # 1 spike in the 10 ms stimulus window
    assert scene["neurons"][1]["dimorphism"] == "male-specific"
    assert scene["neurons"][0]["fruDsx"] == ""
    assert scene["activity"] == {"bins": 2, "bin_ms": 10.0, "stim_ms": 10.0}
    act = np.fromfile(tmp_path / "activity.bin", np.uint8).reshape(2, 2)
    assert act.tolist() == [
        [0, 1],
        [255, 0],
    ]  # columns follow idx order, clipped to uint8
    # every module beside the page is exported, or the page would fail to load
    assert all((tmp_path / f.name).exists() for f in viz.page_files())
    assert {f.name for f in viz.page_files()} >= {
        f.name for f in (viz.STATIC).glob("*.js")
    }
    assert (tmp_path / "vendor/three/build/three.module.min.js").exists()


def test_export_graded_potentials_as_signed_steps_of_their_scale(tmp_path):
    counts = np.zeros((2, 2), dtype=np.uint16)
    graded = {
        "rows": np.array([0]),
        "mv": np.array([[10.0], [-40.0]]),
        "scale_mv": np.array([20.0]),
        "reference": "rest",
    }
    scene = viz.export(
        tmp_path, NEURONS, np.array([1, 0]), ["g1", "g2"], result(counts), graded=graded
    )
    assert scene["graded"] == {"k": [1], "scale_mv": [20.0], "reference": "rest"}
    steps = np.fromfile(tmp_path / "graded.bin", np.int8).reshape(2, 1)
    assert steps[:, 0].tolist() == [64, -127]  # half the scale, then clipped at -1
    # a later export without potentials removes the stale file
    viz.export(tmp_path, NEURONS, np.array([1, 0]), ["g1", "g2"], result(counts))
    assert not (tmp_path / "graded.bin").exists()
    with pytest.raises(ValueError, match="one scale per row"):
        viz.export(
            tmp_path,
            NEURONS,
            np.array([1, 0]),
            ["g1", "g2"],
            result(counts),
            graded={**graded, "scale_mv": np.array([1.0, 2.0])},
        )


def test_anatomy_export_drops_stale_replay(tmp_path):
    (tmp_path / "activity.bin").write_bytes(b"old")
    scene = viz.export(tmp_path, NEURONS, np.array([0]), ["path"])
    assert "activity" not in scene and not (tmp_path / "activity.bin").exists()
    assert scene["neurons"][0]["rate"] is None


def run_node_tests(network: bool) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "FLYMSG_NETWORK"}
    if network:
        env["FLYMSG_NETWORK"] = "1"
    # explicit files: Node < 23 does not accept a directory argument to --test
    files = sorted(
        str(f.relative_to(ROOT)) for f in (ROOT / "tests" / "js").glob("*.test.mjs")
    )
    return subprocess.run(
        ["node", "--test", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_modules():
    """Runs the browser modules' unit tests (tests/js) with node's test runner."""
    run = run_node_tests(network=False)
    assert run.returncode == 0, run.stdout + run.stderr


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_modules_against_gcs():
    """Same, including the live read of the Giant Fiber manifest from GCS."""
    run = run_node_tests(network=True)
    assert run.returncode == 0, run.stdout + run.stderr


def _partner_graph():
    # 0..5 typed or untyped; two types tie on synapses onto neuron 0
    neurons = pd.DataFrame(
        {
            "bodyId": [100, 101, 102, 103, 104, 105],
            "type": ["T0", "B", "A", None, "A", "C"],
        }
    )
    neurons["type"] = neurons["type"].astype("string")
    edges = pd.DataFrame(
        {
            "pre": [1, 2, 3, 4, 0, 0, 0, 5],
            "post": [0, 0, 0, 0, 1, 5, 2, 1],
            "weight": [6, 4, 9, 2, 7, 7, 1, 3],
        }
    )
    return neurons, edges


@pytest.mark.parametrize("top", [1, 2, 10])
def test_partner_table_matches_flymsg_info(top):
    from flymsg import graph

    neurons, edges = _partner_graph()
    idx = np.array([0, 1, 5])
    table = graph.partner_table(neurons, edges, idx, top)
    for i in idx:
        entry = table[int(neurons["bodyId"][i])]
        for up, key in ((True, "upstream"), (False, "downstream")):
            ref = graph.partners(neurons, edges, np.array([i]), upstream=up, top=top)
            got = entry[key]
            assert got["types"] == [
                [t, int(r.synapses), int(r.connections)] for t, r in ref.iterrows()
            ]
            full = graph.partners(neurons, edges, np.array([i]), upstream=up, top=99)
            assert got["total_types"] == len(full)
            assert got["total_synapses"] == int(full["synapses"].sum())
    # neuron 0: untyped first (9), then A (2 neurons, 6) tied with B (6), A first as in info
    assert (
        table[100]["upstream"]["types"]
        == [["untyped", 9, 1], ["A", 6, 2], ["B", 6, 1]][:top]
    )
    assert table[100]["upstream"]["total_types"] == 3
    # partners inside the scene, as rows of idx, strongest first
    assert table[100]["upstream"]["in_scene"] == [[1, 6]]
    assert table[100]["downstream"]["in_scene"] == [[1, 7], [2, 7]]
    assert table[105]["upstream"]["in_scene"] == [[0, 7]]


def test_export_writes_partners_and_drops_a_stale_table(tmp_path):
    neurons, edges = _partner_graph()
    neurons = neurons.assign(
        instance=pd.NA, nt=pd.NA, superclass=pd.NA, dimorphism=pd.NA, fruDsx=pd.NA
    )
    viz.export(tmp_path, neurons, np.array([0, 1]), ["a", "b"], edges=edges)
    table = json.loads((tmp_path / "partners.json").read_text())
    assert table["top"] == 10 and set(table["neurons"]) == {"100", "101"}
    viz.export(tmp_path, neurons, np.array([0]), ["a"])
    assert not (tmp_path / "partners.json").exists()


def _export(path, idx, counts, seed=0, files=None, silence=()):
    """A replay export with a minimal manifest, as flymsg viz writes it."""
    neurons, edges = _partner_graph()
    neurons = neurons.assign(
        instance=pd.NA, nt=pd.NA, superclass="x", dimorphism=pd.NA, fruDsx=pd.NA
    )
    counts = np.zeros((4, len(neurons)), np.uint16) if counts is None else counts
    viz.export(
        path, neurons, np.array(idx), ["g"] * len(idx), result(counts, 20.0), edges
    )
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "flymsg.run_manifest/v1",
                "command": "viz",
                "config": {"sim": ["S"], "silence": list(silence)},
                "seeds": {"seed": seed},
                "git": {"commit": "abc", "dirty": False},
                "dataset": {
                    "name": "malecns",
                    "release": "v1.0",
                    "files": files or {"e": 1},
                },
            }
        )
    )
    return path


def _counts():
    c = np.zeros((4, 6), np.uint16)
    c[0, 0], c[1, 1], c[2, 5] = 2, 1, 3
    return c


def test_identical_runs_compare_to_zero_delta(tmp_path):
    a = _export(tmp_path / "a", [0, 1, 5], _counts())
    scene = viz.compare_bundles(a, a, tmp_path / "c", ("A", "A"), ("exploratory",) * 2)
    out = tmp_path / "c"
    sa = np.fromfile(out / "activity.bin", np.uint8)
    sb = np.fromfile(out / "activity_b.bin", np.uint8)
    assert np.array_equal(sa, sb) and sa.any()
    assert scene["comparison"]["differences"] == []
    assert all(n["in"] == [True, True] for n in scene["neurons"])


def test_comparison_keeps_missing_neurons_apart_and_lists_differences(tmp_path):
    a = _export(tmp_path / "a", [0, 1], _counts())
    b = _export(tmp_path / "b", [0, 5], _counts(), seed=0, silence=("DNp01",))
    scene = viz.compare_bundles(
        a, b, tmp_path / "c", ("baseline", "silenced"), ("exploratory", "failed")
    )
    assert [n["bodyId"] for n in scene["neurons"]] == [100, 101, 105]
    assert [n["in"] for n in scene["neurons"]] == [
        [True, True],
        [True, False],
        [False, True],
    ]
    assert scene["neurons"][1]["rate_b"] is None  # not exported in b, not "silent"
    assert scene["comparison"]["differences"] == [
        {"key": "config.silence", "a": [], "b": ["DNp01"]}
    ]
    assert scene["comparison"]["runs"][1]["status"] == "failed"
    table = json.loads((tmp_path / "c" / "partners.json").read_text())
    # 100 -> 101 is a row of a, 100 -> 105 a row of b; both are renumbered to the union
    assert table["neurons"]["100"]["downstream"]["in_scene"] == [[1, 7], [2, 7]]


def test_incomparable_runs_are_refused(tmp_path):
    a = _export(tmp_path / "a", [0, 1], _counts())
    other = _export(tmp_path / "b", [0, 1], _counts(), files={"e": 2})
    with pytest.raises(ValueError, match="datasets differ"):
        viz.compare_bundles(a, other, tmp_path / "c", ("A", "B"), ("exploratory",) * 2)
    longer = _export(tmp_path / "d", [0, 1], np.zeros((6, 6), np.uint16))
    with pytest.raises(ValueError, match="time bases differ"):
        viz.compare_bundles(a, longer, tmp_path / "c", ("A", "B"), ("exploratory",) * 2)
    with pytest.raises(ValueError, match="status"):
        viz.compare_bundles(a, a, tmp_path / "c", ("A", "B"), ("validated", "wrong"))


def test_viz_keep_exports_a_silenced_neuron_as_kept(
    monkeypatch, capsys, data_dir, tmp_path
):
    from test_cli import run

    out = tmp_path / "scene"
    run(
        monkeypatch,
        capsys,
        "--data",
        str(data_dir),
        "viz",
        "--sim",
        "A_R",
        "--silence",
        "B",
        "--keep",
        "C",
        "--duration",
        "100",
        "--stim-ms",
        "100",
        "--out",
        str(out),
    )
    scene = json.loads((out / "scene.json").read_text())
    groups = {n["type"]: n["group"] for n in scene["neurons"]}
    assert groups["A"] == "stimulus" and groups["C"] == "kept" and "B" not in groups
    config = json.loads((out / "manifest.json").read_text())["config"]
    assert config["keep"] == ["C"]
