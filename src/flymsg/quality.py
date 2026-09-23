"""Reconstruction completeness: left/right asymmetry of bilateral cell types.

A bilateral pair whose two sides differ by an order of magnitude in synapse count is far more
likely an incompletely reconstructed neuron than biology. For each cell type with neurons on
both sides, `pair_asymmetry` compares the median input synapses of the right and left
neurons and scores the log ratio against all types (robust z: median and MAD), so that
outliers stand out from the ordinary spread of left/right differences.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from flymsg import data

Z_FLAG = 3.0  # |robust z| above this flags a pair
_SIDE = re.compile(r"_([LR])$")


def side_of(instance) -> str | None:
    """L or R from an instance name such as 'MN9_L' or 'DNp01(GF)_R'; sensory and many VNC
    neurons have no somaSide, but their instance carries the side."""
    m = _SIDE.search(instance) if isinstance(instance, str) else None
    return m.group(1) if m else None


def synapse_totals(neurons: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    """Input and output synapses per neuron, among traced neurons."""
    n = len(neurons)
    return pd.DataFrame(
        {
            "in": np.bincount(edges["post"], weights=edges["weight"], minlength=n),
            "out": np.bincount(edges["pre"], weights=edges["weight"], minlength=n),
        }
    )


def pair_asymmetry(neurons: pd.DataFrame, totals: pd.DataFrame) -> pd.DataFrame:
    """One row per cell type with neurons on both sides: counts, median input synapses per
    side, log2((R + 1) / (L + 1)), robust z over all such types, and the flag."""
    df = pd.DataFrame(
        {
            "type": neurons["type"].to_numpy(),
            "side": [side_of(i) for i in neurons["instance"]],
            "in": totals["in"].to_numpy(),
            "out": totals["out"].to_numpy(),
        }
    ).dropna(subset=["type", "side"])
    g = df.groupby(["type", "side"])
    per = g["in"].median().unstack()
    per_out = g["out"].median().unstack()
    count = g.size().unstack()
    if not {"L", "R"} <= set(per.columns):
        raise ValueError(
            "no neuron has a left or a right instance, so no pair to compare"
        )
    both = per.dropna().index
    if both.empty:
        raise ValueError("no cell type has neurons on both sides")
    out = pd.DataFrame(
        {
            "n_L": count.loc[both, "L"].astype(int),
            "n_R": count.loc[both, "R"].astype(int),
            "in_L": per.loc[both, "L"],
            "in_R": per.loc[both, "R"],
            "out_L": per_out.loc[both, "L"],
            "out_R": per_out.loc[both, "R"],
        }
    )
    out["log2_RL"] = np.log2((out["in_R"] + 1) / (out["in_L"] + 1))
    med = out["log2_RL"].median()
    mad = 1.4826 * (out["log2_RL"] - med).abs().median()
    if not mad:  # every pair equally asymmetric: no spread to score against
        raise ValueError("the log2(R/L) spread is zero, so no z-score can be computed")
    out["z"] = (out["log2_RL"] - med) / mad
    out["flag"] = out["z"].abs() > Z_FLAG
    return out


def traced_input_share(data_dir: Path, neurons: pd.DataFrame, idx) -> pd.Series:
    """For the given neurons, the share of all their input synapses (untraced fragments
    included) that comes from traced neurons; a truncated neuron often receives much of its
    input on orphan fragments. Reads the raw weights table (`flymsg fetch`)."""
    ids = neurons["bodyId"].to_numpy()[np.asarray(idx)]
    traced = neurons["bodyId"].to_numpy()
    w = ds.dataset(data_dir / "raw" / data.RAW["weights"], format="feather").to_table(
        filter=ds.field("body_post").isin(ids)
    )
    t = pd.DataFrame(
        {
            "post": w["body_post"].to_numpy(),
            "weight": w["weight"].to_numpy(),
            "traced": np.isin(w["body_pre"].to_numpy(), traced),
        }
    )
    total = t.groupby("post")["weight"].sum()
    from_traced = t[t["traced"]].groupby("post")["weight"].sum()
    share = (from_traced / total).reindex(ids)
    share.index = np.asarray(idx)
    return share
