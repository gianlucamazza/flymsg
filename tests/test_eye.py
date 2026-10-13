"""The eye geometry joins the MaleCNS column grid to the lens map; no data are loaded."""

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from flymsg import eye, sim


def test_hex_to_pq_uses_the_published_origin():
    p, q = eye.pq([18, 19], [19, 21])
    assert p.tolist() == [0, 2] and q.tolist() == [0, 1]


def test_lens_table_orders_by_match_and_drops_the_left_eye():
    # four micro-CT rows: matched lens order 3, 1, 2, 4; the third sorted row is left-eye
    i_match = [3, 1, 2, 4]
    ucl = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0], [0, -1, 0]], dtype=float)
    left = [False, False, True, False]  # applies after the sort, as in proc_eyemap.R
    lens_ixy = [[1, 0, 0], [2, 1, 0], [3, 0, 1]]
    t = eye.lens_table(lens_ixy, i_match, ucl, left)
    # sorted rows: lens1 (1,0,0), lens2 (0,1,0), lens3 (0,0,1) dropped as left, lens4
    assert t[["x", "y", "z"]].to_numpy().tolist() == [
        [1, 0, 0],
        [0, 1, 0],
        [0, -1, 0],
    ]
    assert t[["p", "q"]].to_numpy().tolist() == [[0, 0], [1, 0], [0, 1]]


def _annotations():
    return pd.DataFrame(
        {
            "bodyId": [1, 2, 3, 4],
            "type": ["L1", "L1", "L1", "Mi1"],
            "instance": ["L1_R", "L1_L", "L1_R", "Mi1_R"],
            "assignedOlHex1": [18, 18, 30, 18],
            "assignedOlHex2": [19, 19, 30, 19],
        }
    )


def test_columns_mirror_the_left_eye_and_keep_columns_without_a_lens():
    # one lens at p = q = 0, looking 30 deg to the fly's left and 10 deg up (map frame)
    az, el = np.radians(30), np.radians(10)
    lens = pd.DataFrame(
        {
            "p": [0],
            "q": [0],
            "x": [np.cos(el) * np.cos(az)],
            "y": [np.cos(el) * np.sin(az)],
            "z": [np.sin(el)],
        }
    )
    cols = eye.columns(_annotations(), lens)
    right = cols[(cols.side == "R") & (cols.hex1 == 18)].iloc[0]
    left = cols[cols.side == "L"].iloc[0]
    assert right["azimuth_deg"] == pytest.approx(-30)  # toward the fly's left
    assert left["azimuth_deg"] == pytest.approx(30)  # mirrored
    assert right["elevation_deg"] == pytest.approx(10)
    assert cols[(cols.side == "R") & (cols.hex1 == 30)]["azimuth_deg"].isna().all()
    assert len(cols) == 3  # one row per L1 column, Mi1 not counted


def test_photoreceptors_take_the_column_of_their_strongest_output():
    neurons = pd.DataFrame(
        {
            "bodyId": [1, 2, 3, 10, 11],
            "type": ["L1", "L1", "L1", "R7d", "R1-R6"],
            "instance": ["L1_R", "L1_L", "L1_R", "R7d_R", "R1-R6_R"],
        }
    )
    ann = _annotations().iloc[:3]
    edges = pd.DataFrame({"pre": [3, 3, 4], "post": [0, 2, 2], "weight": [5, 9, 7]})
    r = eye.photoreceptors(neurons, edges, ann).set_index("neuron")
    assert (r.loc[3, "hex1"], r.loc[3, "kind"], r.loc[3, "synapses"]) == (30, "R7", 9)
    assert (r.loc[4, "hex1"], r.loc[4, "kind"]) == (30, "R1-R6")


def test_check_reports_coverage_and_the_dorsal_rim():
    cols = pd.DataFrame(
        {
            "side": ["R", "R"],
            "hex1": [1, 2],
            "hex2": [1, 2],
            "azimuth_deg": [10.0, np.nan],
            "elevation_deg": [70.0, np.nan],
        }
    )
    receptors = pd.DataFrame(
        {
            "neuron": [0],
            "kind": ["R7"],
            "type": ["R7d"],
            "side": ["R"],
            "hex1": [1],
            "hex2": [1],
            "synapses": [3],
        }
    )
    c = eye.check(cols, receptors)
    assert c["columns"]["R"] == 2 and c["with_direction"]["R"] == 1
    assert c["dorsal_rim_elevation_deg"] == 70.0


def _cols(az, el):
    return pd.DataFrame({"azimuth_deg": az, "elevation_deg": el})


def test_angular_distance():
    assert eye.angular_distance_deg(0, 0, 90, 0) == pytest.approx(90)
    assert eye.angular_distance_deg(10, 89.999, 190, 89.999) == pytest.approx(
        0, abs=1e-2
    )


def test_disk_coverage_runs_from_none_to_all():
    cols = _cols([0.0, 0.0, 40.0, np.nan], [0.0, 0.0, 0.0, 0.0])
    big = eye.disk_coverage(cols, 0, 0, 30, 5)
    assert big[0] == pytest.approx(1, abs=1e-5) and big[2] == pytest.approx(0, abs=1e-5)
    assert np.isnan(big[3])
    edge = eye.disk_coverage(_cols([10.0], [0.0]), 0, 0, 10, 5)
    assert 0.4 < edge[0] < 0.6  # a column on the rim sees about half its profile
    assert eye.disk_coverage(cols, 0, 0, 0, 5)[0] == 0


def test_looming_radius_grows_to_collision():
    r = eye.looming_radius_deg(
        [0, 400, 490, 500, 600], collision_ms=500, l_over_v_ms=40
    )
    assert r[0] < r[1] < r[2] < 90
    assert r[0] == pytest.approx(np.degrees(np.arctan(40 / 500)))
    assert r[3] == r[4] == 90


def test_photoreceptor_kicks_follow_the_light_left():
    coverage = np.array([[0.0, 0.5], [1.0, np.nan]])
    k = eye.photoreceptor_kicks(coverage, np.array([0, 1, -1]), 0.2)
    np.testing.assert_allclose(k, [[0.2, 0.1, 0.0], [0.0, 0.0, 0.0]])


def test_real_kicks_reproduce_integer_kicks_and_integrate_fractions():
    W = sparse.csc_matrix((2, 2), dtype=np.float32)
    ints = sim.poisson_kicks(0, 500.0, 0.1, 200, 1)
    a = sim.run(W, np.array([0]), duration_ms=20.0, kicks=ints, bin_ms=10.0)
    b = sim.run(
        W, np.array([0]), duration_ms=20.0, kicks=ints.astype(float), bin_ms=10.0
    )
    assert np.array_equal(a.counts, b.counts)
    # one Poisson kick is far above threshold; a tenth per step must sum up before a spike
    tenth = np.full((200, 1), 0.01)
    r = sim.run(W, np.array([0]), duration_ms=20.0, kicks=tenth, bin_ms=10.0)
    assert 0 < r.counts[:, 0].sum() < 200


def test_edge_crosses_columns_in_order_and_mirrors_between_eyes():
    cols = pd.DataFrame(
        {
            "side": ["R", "R", "L", "L"],
            "azimuth_deg": [10.0, 40.0, -10.0, -40.0],
            "elevation_deg": [0.0, 0.0, 0.0, 0.0],
        }
    )
    c = eye.edge_coverage(cols, "front_to_back", 15.0, 5.0)
    # 15 deg after starting at the frontmost column of each eye: the 10 deg columns are
    # crossed, the 40 deg ones not yet, on both sides
    assert c[0] > 0.99 and c[1] < 0.01 and c[2] > 0.99 and c[3] < 0.01
    back = eye.edge_coverage(cols, "back_to_front", 15.0, 5.0)
    assert back[1] > 0.99 and back[0] < 0.01
