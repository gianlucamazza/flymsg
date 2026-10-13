"""The eye geometry joins the MaleCNS column grid to the lens map; no data are loaded."""

import numpy as np
import pandas as pd
import pytest

from flymsg import eye


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
