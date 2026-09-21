"""Graph queries: strongest paths and aggregated partners."""

from itertools import pairwise

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import dijkstra


def input_fraction(edges: pd.DataFrame, n: int) -> np.ndarray:
    """Share of the postsynaptic neuron's total input carried by each edge."""
    total_in = np.bincount(edges["post"], weights=edges["weight"], minlength=n)
    return edges["weight"].to_numpy() / total_in[edges["post"].to_numpy()]


def strongest_path(
    edges: pd.DataFrame,
    n: int,
    sources: np.ndarray,
    targets: np.ndarray,
    min_weight: int = 5,
) -> list[int]:
    """Path from any source to any target maximising the product of input fractions.

    Edge cost is -log(input fraction), so the shortest path is the chain along which
    each hop drives the largest share of the next neuron's input. Edges below
    `min_weight` synapses are not traversed but still count in the input totals.
    """
    # Fractions use each neuron's full input; filtering first would inflate them.
    keep = edges["weight"].to_numpy() >= min_weight
    cost = (
        -np.log(input_fraction(edges, n)[keep]) + 1e-9
    )  # zero cost would drop the edge
    e = edges[keep]
    g = sparse.csr_matrix((cost, (e["pre"], e["post"])), shape=(n, n))
    dist, pred, src = dijkstra(
        g, indices=sources, min_only=True, return_predecessors=True
    )
    best = targets[np.argmin(dist[targets])]
    if not np.isfinite(dist[best]):
        return []
    path = [int(best)]
    while path[-1] != src[best] and pred[path[-1]] >= 0:
        path.append(int(pred[path[-1]]))
    return path[::-1]


def partners(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    idx: np.ndarray,
    upstream: bool,
    top: int = 15,
):
    """Synapse counts to/from `idx`, aggregated by partner cell type."""
    here, there = ("post", "pre") if upstream else ("pre", "post")
    e = edges[np.isin(edges[here], idx)]
    t = neurons["type"].fillna("untyped").to_numpy()[e[there].to_numpy()]
    out = (
        pd.DataFrame({"type": t, "weight": e["weight"].to_numpy()})
        .groupby("type")["weight"]
        .agg(["sum", "size"])
    )
    return out.rename(columns={"sum": "synapses", "size": "connections"}).nlargest(
        top, "synapses"
    )


def edge_weights(edges: pd.DataFrame, path: list[int]) -> list[int]:
    """Synapse count of each hop along `path`."""
    pre, post, w = (edges[c].to_numpy() for c in ("pre", "post", "weight"))
    return [int(w[(pre == a) & (post == b)][0]) for a, b in pairwise(path)]
