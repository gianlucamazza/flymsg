"""N1: one degree-preserving shuffle of the traced graph.

Fixed in docs/reference/related.md on 2026-10-10, before any confirmatory run. The permutation
is numpy's Generator.permutation with seed 0 (PCG64). A later numpy that changes that
permutation changes N1; tests/test_wiring.py locks the image of a five-element column.
"""

import numpy as np
import pandas as pd

SHUFFLE_SEED = 0
N1_SEEDS = 3  # criterion v4, seeds 0, 1, 2


def shuffle_targets(
    edges: pd.DataFrame, seed: int = SHUFFLE_SEED
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Permute `post`. Each presynaptic neuron keeps its outgoing weights, the multiset of
    in-degrees is unchanged, and self-loops and duplicate pairs are kept.

    `sim.weight_matrix` sums duplicate (post, pre) entries, so a duplicate pair reaches
    the simulator as one weight, the sum of its synapse counts. The census below counts
    the pairs in the table, before that sum."""
    out = edges.copy()
    post = out["post"].to_numpy()
    permuted = np.random.default_rng(seed).permutation(post)
    out["post"] = permuted
    stats = census(out["pre"].to_numpy(), out["post"].to_numpy())
    return out, stats


def census(pre: np.ndarray, post: np.ndarray) -> dict[str, int]:
    """Self-loops, (pre, post) pairs that occur more than once, and the extra edges in them."""
    n = int(pre.size)
    if n == 0:
        return {
            "n_edges": 0,
            "n_self_loops": 0,
            "n_duplicate_pairs": 0,
            "n_extra_edges": 0,
        }
    order = np.lexsort((post, pre))
    pre_s, post_s = pre[order], post[order]
    new = np.empty(n, dtype=bool)
    new[0] = True
    new[1:] = (pre_s[1:] != pre_s[:-1]) | (post_s[1:] != post_s[:-1])
    lengths = np.diff(np.append(np.flatnonzero(new), n))
    repeated = lengths[lengths > 1]
    return {
        "n_edges": n,
        "n_self_loops": int(np.count_nonzero(pre == post)),
        "n_duplicate_pairs": int(repeated.size),
        "n_extra_edges": int((repeated - 1).sum()) if repeated.size else 0,
    }


def confirmatory(real: pd.DataFrame, shuffled: pd.DataFrame) -> pd.DataFrame:
    """One row per `specific` check. The rule applies where the real graph passes, and holds
    where that check then fails on the shuffle. Other kinds are not scored."""
    keys = ["case", "kind", "subject"]
    left = real.loc[real["kind"] == "specific", [*keys, "passed"]]
    right = shuffled.loc[shuffled["kind"] == "specific", [*keys, "passed"]]
    left_keys = set(map(tuple, left[keys].to_numpy()))
    right_keys = set(map(tuple, right[keys].to_numpy()))
    if left_keys != right_keys:
        raise ValueError(
            "real and shuffle reports list different specific checks: "
            f"only real {sorted(left_keys - right_keys)}, "
            f"only shuffle {sorted(right_keys - left_keys)}"
        )
    # how="left" keeps the real report's order. pandas 3 reorders an outer merge.
    merged = left.merge(
        right, on=keys, how="left", suffixes=("_real", "_shuffle"), sort=False
    )
    applies = merged["passed_real"].astype(bool)
    return pd.DataFrame(
        {
            "case": merged["case"],
            "subject": merged["subject"],
            "passed_real": applies,
            "passed_shuffle": merged["passed_shuffle"].astype(bool),
            "applies": applies,
            "held": ~applies | ~merged["passed_shuffle"].astype(bool),
        }
    ).reset_index(drop=True)


def verdict(table: pd.DataFrame) -> str:
    """The confirmatory count, then one line per specific check that still passes."""
    ruled = table[table["applies"]]
    if ruled.empty:
        return (
            "N1: no specific check passes on the real graph, so the rule does not apply"
        )
    held = int(ruled["held"].sum())
    lines = [
        (
            f"N1: {held}/{len(ruled)} specific checks that pass on the real graph"
            " fail on the shuffle"
        )
    ]
    for row in ruled[~ruled["held"]].itertuples(index=False):
        lines.append(f"finding: {row.case} / {row.subject} still passes on the shuffle")
    return "\n".join(lines)
