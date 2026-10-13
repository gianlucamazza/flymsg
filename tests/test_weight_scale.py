"""A postsynaptic weight scale: absent, the weights are count x sign x w_syn as before;
present, every weight onto a neuron is multiplied by its value (e.g. synapse density)."""

import numpy as np
import pandas as pd
import pytest

from flymsg import sim

EDGES = pd.DataFrame(
    {"pre": [0, 0, 1, 2], "post": [1, 2, 2, 0], "weight": [10, 4, 7, 3]}
)
SIGN = np.array([1, -1, 1], dtype=np.int8)


def test_no_scale_and_unit_scale_give_the_count_rule():
    plain = sim.weight_matrix(EDGES, SIGN, 3, 0.192)
    ones = sim.weight_matrix(EDGES, SIGN, 3, 0.192, post_scale=np.ones(3))
    assert (plain != ones).nnz == 0
    assert plain.dtype == ones.dtype == np.float32
    assert plain[1, 0] == np.float32(10 * 0.192)


def test_scale_multiplies_the_weights_onto_each_neuron():
    W = sim.weight_matrix(EDGES, SIGN, 3, 0.192, post_scale=np.array([1.0, 2.0, 0.5]))
    plain = sim.weight_matrix(EDGES, SIGN, 3, 0.192)
    assert W[1, 0] == np.float32(10 * 0.192 * 2.0)
    assert W[2, 0] == np.float32(4 * 0.192 * 0.5)
    assert W[2, 1] == np.float32(-7 * 0.192 * 0.5)
    assert W[0, 2] == plain[0, 2]


def test_density_scale_is_reference_area_over_area():
    np.testing.assert_allclose(
        sim.density_scale(np.array([1000.0, 4000.0]), 2000.0), [2.0, 0.5]
    )
    with pytest.raises(ValueError):
        sim.density_scale(np.array([0.0]), 1.0)
    with pytest.raises(ValueError):
        sim.weight_matrix(EDGES, SIGN, 3, 0.192, post_scale=np.array([1.0, -1.0, 1.0]))
    with pytest.raises(ValueError):
        sim.weight_matrix(EDGES, SIGN, 3, 0.192, post_scale=np.ones(2))
