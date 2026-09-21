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


def _path_costs(edges: pd.DataFrame, n: int, min_weight: int):
    """(pre, post, cost) of the traversable edges; cost = -log(input fraction)."""
    # Fractions use each neuron's full input; filtering first would inflate them.
    keep = edges["weight"].to_numpy() >= min_weight
    cost = (
        -np.log(input_fraction(edges, n)[keep]) + 1e-9
    )  # zero cost would drop the edge
    return edges["pre"].to_numpy()[keep], edges["post"].to_numpy()[keep], cost


def _shortest(pre, post, cost, n, sources, targets, blocked=None) -> list[int]:
    if blocked is not None:
        ok = ~(blocked[pre] | blocked[post])
        pre, post, cost = pre[ok], post[ok], cost[ok]
    g = sparse.csr_matrix((cost, (pre, post)), shape=(n, n))
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
    return _shortest(*_path_costs(edges, n, min_weight), n, sources, targets)


def alternative_paths(
    edges: pd.DataFrame,
    n: int,
    sources: np.ndarray,
    targets: np.ndarray,
    groups: np.ndarray,
    k: int,
    min_weight: int = 5,
) -> list[list[int]]:
    """Up to `k` strongest paths, each avoiding the intermediate groups of the previous ones.

    `groups` labels every neuron (e.g. its cell type): once a path passes through a group,
    later paths may not use any neuron of it as an intermediate, so the list shows distinct
    routes rather than the same route through sibling cells. Sources and targets stay open.
    """
    costs = _path_costs(edges, n, min_weight)
    ends = np.zeros(n, dtype=bool)
    ends[sources] = ends[targets] = True
    banned: set = set()
    paths = []
    for _ in range(k):
        blocked = np.isin(groups, list(banned)) & ~ends if banned else None
        path = _shortest(*costs, n, sources, targets, blocked)
        if not path:
            break
        paths.append(path)
        banned |= {groups[i] for i in path[1:-1]}
        if not path[1:-1]:
            break  # a direct connection: nothing left to route around
    return paths


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
