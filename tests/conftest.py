"""Shared fixtures."""

import pandas as pd
import pytest

from flymsg import data


@pytest.fixture
def data_dir(tmp_path):
    """Three traced neurons, A -> B -> C, built through the real `data.build`."""
    raw = tmp_path / "raw"
    raw.mkdir()
    ann = pd.DataFrame({c: [None] * 3 for c in data.ANN_COLS})
    ann["bodyId"] = [10, 20, 30]
    ann["type"] = ["A", "B", "C"]
    ann["instance"] = ["A_R", "B_R", "C_R"]
    ann["status"] = ["Traced"] * 3
    ann["superclass"] = ["sensory"] * 3
    ann.to_feather(raw / data.RAW["annotations"])
    pd.DataFrame(
        {"body": [10, 20, 30], "consensus_nt": ["acetylcholine"] * 3}
    ).to_feather(raw / data.RAW["nt"])
    pd.DataFrame(
        {"body_pre": [10, 20], "body_post": [20, 30], "weight": [200, 200]}
    ).to_feather(raw / data.RAW["weights"])
    data.build(tmp_path)
    return tmp_path
