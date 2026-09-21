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


NEURONS = pd.DataFrame(
    {
        "bodyId": [10, 20],
        "type": ["A", None],
        "instance": ["A_R", None],
        "nt": ["gaba", None],
        "superclass": ["x", "y"],
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
    assert scene["activity"] == {"bins": 2, "bin_ms": 10.0, "stim_ms": 10.0}
    act = np.fromfile(tmp_path / "activity.bin", np.uint8).reshape(2, 2)
    assert act.tolist() == [
        [0, 1],
        [255, 0],
    ]  # columns follow idx order, clipped to uint8
    assert all((tmp_path / f).exists() for f in viz.PAGE)
    assert (tmp_path / "vendor/three/build/three.module.min.js").exists()


def test_anatomy_export_drops_stale_replay(tmp_path):
    (tmp_path / "activity.bin").write_bytes(b"old")
    scene = viz.export(tmp_path, NEURONS, np.array([0]), ["path"])
    assert "activity" not in scene and not (tmp_path / "activity.bin").exists()
    assert scene["neurons"][0]["rate"] is None


def run_node_tests(network: bool) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "FLYMSG_NETWORK"}
    if network:
        env["FLYMSG_NETWORK"] = "1"
    return subprocess.run(
        ["node", "--test", "tests/js/"],
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
