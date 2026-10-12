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


def build_dataset(path, types, superclass, edges):
    """A traced dataset under `path` through the real `data.build`."""
    raw = path / "raw"
    raw.mkdir(parents=True)
    n = len(types)
    ann = pd.DataFrame({c: [None] * n for c in data.ANN_COLS})
    ann["bodyId"] = [10 * (i + 1) for i in range(n)]
    ann["type"] = types
    ann["status"] = ["Traced"] * n
    ann["superclass"] = superclass
    ann.to_feather(raw / data.RAW["annotations"])
    pd.DataFrame(
        {"body": ann["bodyId"], "consensus_nt": ["acetylcholine"] * n}
    ).to_feather(raw / data.RAW["nt"])
    pre, post, w = zip(*edges, strict=True)
    pd.DataFrame(
        {
            "body_pre": [10 * (i + 1) for i in pre],
            "body_post": [10 * (i + 1) for i in post],
            "weight": list(w),
        }
    ).to_feather(raw / data.RAW["weights"])
    data.build(path)
    return path


@pytest.fixture
def twin_dir(tmp_path):
    """Two C neurons, each driven by its own stimulated A: which one fires more depends on
    the seed, so a best neuron picked per seed changes and one picked over seeds does not."""
    return build_dataset(
        tmp_path,
        ["A", "A", "C", "C"],
        ["sensory", "sensory", "y", "y"],
        [(0, 2, 90), (1, 3, 90)],  # each C has its own Poisson-driven A
    )
