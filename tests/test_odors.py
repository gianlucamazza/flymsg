"""Odors from DoOR tables, read as R writes them; no download, no connectome."""

import numpy as np
import pandas as pd
import pytest

from flymsg import odors, sim


def _write(tmp_path):
    raw = odors.raw_dir(tmp_path)
    raw.mkdir(parents=True)
    (raw / "door_response_matrix.csv").write_text(
        '"Or1a";"ab4B";"Or33a";"Or9z"\n"SFR";0.1;0.1;0.1;0.1\n"KEY-A";0.5;0.3;0.8;NA\n'
    )
    (raw / "door_mappings.csv").write_text(
        '"receptor";"glomerulus"\n'
        '"1";"Or1a";"VA1"\n'
        '"2";"ab4B";"DA2"\n'
        '"3";"Or33a";"DA2"\n'
        '"4";"Or9z";"ZZ"\n'
    )
    (raw / "odor.csv").write_text('"Name";"InChIKey"\n"1";"odor a";"KEY-A"\n')
    return odors.tables(tmp_path)


def test_r_tables_are_read_with_their_row_names(tmp_path):
    responses, mappings, table = _write(tmp_path)
    assert responses.loc["KEY-A", "Or33a"] == 0.8
    assert np.isnan(responses.loc["KEY-A", "Or9z"])
    assert mappings.set_index("receptor").loc["ab4B", "glomerulus"] == "DA2"
    assert odors.inchikey(table, "Odor A") == "KEY-A"
    with pytest.raises(KeyError):
        odors.inchikey(table, "missing")


def test_vector_keeps_measured_receptors_with_a_type_in_the_volume(tmp_path):
    responses, mappings, table = _write(tmp_path)
    v = odors.vector(responses, mappings, table, "odor a", {"ORN_VA1", "ORN_DA2"})
    assert sorted(v["receptor"]) == ["Or1a", "Or33a", "ab4B"]
    c = odors.coverage(responses, table, "odor a", v)
    assert c == {"receptors": 4, "measured": 3, "in_volume": 3}


def test_per_type_prefers_the_neuron_recording():
    v = pd.DataFrame(
        {
            "receptor": ["ab4B", "Or33a", "Or1a", "Or2a"],
            "type": ["ORN_DA2", "ORN_DA2", "ORN_VA1", "ORN_VA1"],
            "response": [0.3, 0.8, 0.5, 0.2],
        }
    )
    pt = odors.per_type(v)
    assert pt["ORN_DA2"] == 0.3  # in vivo ab4B, not the larger Or33a
    assert pt["ORN_VA1"] == 0.5  # no neuron recording: the larger receptor


def test_stimulus_rates_scale_the_response():
    neurons = pd.DataFrame({"type": ["ORN_A", "x", "ORN_B", "ORN_A"]})
    idx, rates = odors.stimulus(neurons, pd.Series({"ORN_A": 0.5, "ORN_B": 1.0}), 100.0)
    assert idx.tolist() == [0, 2, 3] and rates.tolist() == [50.0, 100.0, 50.0]


def test_equal_rates_reproduce_the_engine_draw():
    a = odors.kicks(np.full(3, 150.0), 7, 0.1, 500)
    assert np.array_equal(a, sim.poisson_kicks(7, 150.0, 0.1, 500, 3))
