import json
import struct

import numpy as np
import pandas as pd

from flymsg import sim, viz


def skeleton_bytes(verts, edges):
    verts, edges = np.asarray(verts, "<f4"), np.asarray(edges, "<u4")
    return (
        struct.pack("<II", len(verts), len(edges)) + verts.tobytes() + edges.tobytes()
    )


def test_parse_skeleton_roundtrip():
    v, e = viz.parse_skeleton(
        skeleton_bytes([[0, 0, 0], [1, 2, 3], [4, 5, 6]], [[0, 1], [1, 2]])
    )
    assert v.shape == (3, 3) and v[2].tolist() == [4, 5, 6]
    assert e.tolist() == [[0, 1], [1, 2]]


def test_parse_ngmesh():
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], "<f4")
    buf = struct.pack("<I", 3) + verts.tobytes() + np.array([0, 1, 2], "<u4").tobytes()
    v, t = viz.parse_ngmesh(buf)
    assert v.tolist() == verts.tolist() and t.tolist() == [[0, 1, 2]]


def test_simplify_reduces_and_keeps_bounds():
    # fine triangulated 10 x 10 grid of the unit square
    xs = np.linspace(0, 1, 11)
    verts = np.array([[x, y, 0] for y in xs for x in xs], dtype=np.float32)
    tris = []
    for r in range(10):
        for c in range(10):
            a = r * 11 + c
            tris += [[a, a + 1, a + 12], [a, a + 12, a + 11]]
    v, t = viz.simplify(verts, np.array(tris, np.uint32), cell=0.3)
    assert 0 < len(t) < len(tris) and len(v) < len(verts)
    assert t.max() < len(v)
    assert np.all(v.min(0) >= -1e-6) and np.all(v.max(0) <= 1 + 1e-6)


def test_simplify_skeleton_merges_nearby_nodes():
    # a 10-node straight line with 1 unit spacing, plus a far branch node
    verts = np.array([[i, 0, 0] for i in range(10)] + [[5, 50, 0]], np.float32)
    edges = np.array([[i, i + 1] for i in range(9)] + [[5, 10]], np.uint32)
    v, e = viz.simplify_skeleton(verts, edges, cell=3.0)
    assert len(v) == 5  # 4 cells along the line + the branch tip
    assert len(e) == 4 and e.max() < len(v)
    assert (e[:, 0] != e[:, 1]).all()


def test_select_from_result_keeps_stim_and_ranks():
    counts = np.zeros((10, 6), np.uint16)
    counts[:, 0] = 3  # stimulated
    counts[:, 2] = 1
    counts[:, 4] = 2
    r = sim.Result(counts, np.full(6, np.nan), 10.0, 100.0)
    assert viz.select_from_result(r, np.array([0]), 3).tolist() == [0, 4, 2]
    assert viz.select_from_result(r, np.array([0]), 2).tolist() == [0, 4]


def test_export_bundle_layout(tmp_path):
    cache = tmp_path / "cache"
    (cache / "skeletons").mkdir(parents=True)
    c = viz.CENTER_NM
    (cache / "skeletons" / "10").write_bytes(skeleton_bytes([c, c + 1000], [[0, 1]]))
    (cache / "skeletons" / "20").write_bytes(
        skeleton_bytes([c, c + 2000, c + 4000], [[0, 1], [1, 2]])
    )
    neurons = pd.DataFrame(
        {
            "bodyId": [10, 20],
            "type": ["A", None],
            "instance": ["A_R", None],
            "nt": ["gaba", None],
            "superclass": ["x", "y"],
        }
    )
    counts = np.array([[1, 0], [0, 300]], np.uint16)
    result = sim.Result(counts, np.full(2, np.nan), 10.0, 10.0)
    out = tmp_path / "out"
    viz.export(
        out,
        neurons,
        np.array([0, 1]),
        ["g1", "g2"],
        cache,
        result,
        neuropils=False,
        skeleton_nm=1.0,
    )

    scene = json.loads((out / "scene.json").read_text())
    assert (
        [n["v0"] for n in scene["neurons"]] == [0, 2]
        and scene["vertices"] == 5
        and scene["edges"] == 3
    )
    assert scene["neurons"][1]["type"] == "untyped"
    raw = (out / "skeletons.bin").read_bytes()
    verts = np.frombuffer(raw, "<f4", 15).reshape(5, 3)
    edges = np.frombuffer(raw, "<u4", 6, 60).reshape(3, 2)
    assert np.allclose(
        verts[[0, 1, 4]], [[0, 0, 0], [1, 1, 1], [4, 4, 4]]
    )  # um, centred
    assert edges.tolist() == [[0, 1], [2, 3], [3, 4]]  # second neuron re-based
    act = np.fromfile(out / "activity.bin", np.uint8).reshape(2, 2)
    assert act.tolist() == [[1, 0], [0, 255]]  # clipped to uint8
    assert (out / "index.html").exists() and (out / "main.js").exists()
