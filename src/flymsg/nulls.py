"""Multi-draw wiring nulls: several shuffle families and a locked score.

N1 (`wiring.shuffle_targets`, one seed, full criterion v4) stays as it is. This
module is a separate protocol: four families, many seeded draws, signed pathway
weights, empirical p and z for every pre-registered pathway. Methods follow the
configuration model and signed/weighted randomization used for networks
(Maslov & Sneppen 2002; Newman 2003; Rubinov & Sporns 2010).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from flymsg import prereg, validate, wiring

FAMILIES = (
    "degree_preserving",
    "cell_type_preserving",
    "weight_within_type",
    "sign",
)


def cell_types(neurons: pd.DataFrame) -> np.ndarray:
    return neurons["type"].fillna("untyped").astype(str).to_numpy()


def shuffle_degree_preserving(edges: pd.DataFrame, seed: int) -> pd.DataFrame:
    """N1's permutation of `post` (configuration model)."""
    shuffled, _ = wiring.shuffle_targets(edges, seed)
    return shuffled


def shuffle_cell_type_preserving(
    edges: pd.DataFrame, neurons: pd.DataFrame, seed: int
) -> pd.DataFrame:
    """Permute `post` within each postsynaptic cell type.

    Type-to-type synapse counts and each neuron's in-degree stay. Which neuron
    of that type receives each edge is randomized (Newman 2003, configuration
    model inside groups).
    """
    out = edges.copy()
    post = out["post"].to_numpy().copy()
    types = cell_types(neurons)[post]
    rng = np.random.default_rng(seed)
    for label in np.unique(types):
        idx = np.flatnonzero(types == label)
        if idx.size > 1:
            post[idx] = rng.permutation(post[idx])
    out["post"] = post
    return out


def shuffle_weight_within_type(
    edges: pd.DataFrame, neurons: pd.DataFrame, seed: int
) -> pd.DataFrame:
    """Keep topology; permute weights among outgoing edges of the same pre type.

    Rubinov & Sporns 2010 describe weight-preserving randomization; applying it
    inside a cell type keeps that type's weight multiset.
    """
    out = edges.copy()
    weight = out["weight"].to_numpy().copy()
    types = cell_types(neurons)[out["pre"].to_numpy()]
    rng = np.random.default_rng(seed)
    for label in np.unique(types):
        idx = np.flatnonzero(types == label)
        if idx.size > 1:
            weight[idx] = rng.permutation(weight[idx])
    out["weight"] = weight
    return out


def shuffle_signs(neurons: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Permute non-zero transmitter signs; modulators stay at 0.

    Signed-network randomization that keeps the counts of +1 and -1
    (Rubinov & Sporns 2010).
    """
    out = neurons.copy()
    sign = out["sign"].to_numpy().copy()
    fast = np.flatnonzero(sign != 0)
    if fast.size > 1:
        sign[fast] = np.random.default_rng(seed).permutation(sign[fast])
    out["sign"] = sign
    return out


def apply_family(
    family: str,
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if family == "degree_preserving":
        return neurons, shuffle_degree_preserving(edges, seed)
    if family == "cell_type_preserving":
        return neurons, shuffle_cell_type_preserving(edges, neurons, seed)
    if family == "weight_within_type":
        return neurons, shuffle_weight_within_type(edges, neurons, seed)
    if family == "sign":
        return shuffle_signs(neurons, seed), edges
    raise KeyError(f"unknown null family {family!r}; families: {', '.join(FAMILIES)}")


def pathway_rows(neurons: pd.DataFrame) -> list[dict]:
    """Resolve stim indices for each locked pathway."""
    by_name = {c.name: c for c in validate.CASES}
    rows = []
    for spec in prereg.load()["pathways"]:
        if spec["kind"] == "specific":
            stim = by_name[spec["case"]].stim_idx(neurons)
        else:
            stim_fn = next(
                fn for name, fn, _, _ in validate.NEGATIVES if name == spec["case"]
            )
            stim = stim_fn(neurons)
        rows.append({**spec, "stim": np.asarray(stim)})
    return rows


def pathway_scores(
    neurons: pd.DataFrame, edges: pd.DataFrame, pathways: list[dict] | None = None
) -> pd.DataFrame:
    """Signed stim → target-type weight: sum over the type and max onto one neuron."""
    pathways = pathways if pathways is not None else pathway_rows(neurons)
    pre = edges["pre"].to_numpy()
    post = edges["post"].to_numpy()
    weight = edges["weight"].to_numpy().astype(np.float64)
    sign = neurons["sign"].to_numpy().astype(np.float64)
    types = cell_types(neurons)
    signed = weight * sign[pre]
    rows = []
    for spec in pathways:
        stim = spec["stim"]
        from_stim = np.isin(pre, stim)
        to_type = types[post] == spec["target"]
        hit = from_stim & to_type
        per_post: dict[int, float] = {}
        if hit.any():
            for p, w in zip(post[hit], signed[hit], strict=True):
                per_post[int(p)] = per_post.get(int(p), 0.0) + float(w)
        values = np.array(list(per_post.values()), dtype=np.float64)
        rows.append(
            {
                "case": spec["case"],
                "target": spec["target"],
                "kind": spec["kind"],
                "tail": spec["tail"],
                "sum": float(values.sum()) if values.size else 0.0,
                "max": float(values.max()) if values.size else 0.0,
            }
        )
    return pd.DataFrame(rows)


def empirical_p(real: float, nulls: np.ndarray, tail: str) -> float:
    """+1 smoothing, as in dimorphism. Smallest p is 1/(1+n)."""
    n = np.asarray(nulls, dtype=float)
    if tail == "upper":
        extreme = int(np.sum(n >= real))
    elif tail == "lower":
        extreme = int(np.sum(n <= real))
    else:
        raise ValueError(f"tail must be upper or lower, not {tail!r}")
    return (1 + extreme) / (1 + n.size)


def z_score(real: float, nulls: np.ndarray) -> float | None:
    n = np.asarray(nulls, dtype=float)
    if n.size < 2:
        return None
    sd = float(n.std(ddof=1))
    mu = float(n.mean())
    if sd == 0.0:
        return 0.0 if real == mu else None
    return (real - mu) / sd


def headline(scores: pd.DataFrame, metric: str = "max") -> dict[str, float]:
    """Locked family-level scalars: sum of `metric` on specific rows, bitter `sum`."""
    specific = scores[scores["kind"] == "specific"]
    bitter = scores[scores["kind"] == "negative"]
    out = {"specific_max_sum": float(specific[metric].sum())}
    if len(bitter):
        out["bitter_sum"] = float(bitter["sum"].iloc[0])
    return out


def compare_to_nulls(
    real: pd.DataFrame, draws: list[pd.DataFrame], metric: str
) -> pd.DataFrame:
    """One row per pathway: real, null mean/sd, empirical p, z."""
    rows = []
    for i, row in real.iterrows():
        values = np.array([d.loc[i, metric] for d in draws], dtype=float)
        z = z_score(row[metric], values)
        rows.append(
            {
                "case": row["case"],
                "target": row["target"],
                "kind": row["kind"],
                "tail": row["tail"],
                "metric": metric,
                "real": float(row[metric]),
                "null_mean": float(values.mean()),
                "null_sd": float(values.std(ddof=1)) if values.size > 1 else 0.0,
                "p": empirical_p(float(row[metric]), values, row["tail"]),
                "z": z,
                "n_draws": int(values.size),
            }
        )
    return pd.DataFrame(rows)


def run_family(
    family: str,
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    draws: int,
    seed0: int = 0,
    pathways: list[dict] | None = None,
) -> dict:
    """Real scores plus `draws` seeded nulls for one family."""
    pathways = pathways if pathways is not None else pathway_rows(neurons)
    real = pathway_scores(neurons, edges, pathways)
    null_tables = []
    for i in range(draws):
        n, e = apply_family(family, neurons, edges, seed0 + i)
        null_tables.append(pathway_scores(n, e, pathways))
    reports = {m: compare_to_nulls(real, null_tables, m) for m in ("sum", "max")}
    real_h = headline(real)
    null_h = [headline(t) for t in null_tables]
    family_rows = []
    for key, tail in ("specific_max_sum", "upper"), ("bitter_sum", "lower"):
        if key not in real_h:
            continue
        values = np.array([h[key] for h in null_h], dtype=float)
        z = z_score(real_h[key], values)
        family_rows.append(
            {
                "family": family,
                "statistic": key,
                "tail": tail,
                "real": real_h[key],
                "null_mean": float(values.mean()),
                "null_sd": float(values.std(ddof=1)) if values.size > 1 else 0.0,
                "p": empirical_p(real_h[key], values, tail),
                "z": z,
                "n_draws": int(values.size),
            }
        )
    return {
        "family": family,
        "real": real,
        "nulls": null_tables,
        "by_metric": reports,
        "headline": pd.DataFrame(family_rows),
    }


def run_all(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    draws: int,
    families: tuple[str, ...] = FAMILIES,
    seed0: int = 0,
) -> dict[str, dict]:
    pathways = pathway_rows(neurons)
    return {
        family: run_family(family, neurons, edges, draws, seed0, pathways)
        for family in families
    }


def format_report(results: dict[str, dict]) -> str:
    """Plain-text table of every family headline and every pathway. No omissions."""
    lines = []
    for family, got in results.items():
        lines.append(f"## {family} ({int(got['headline']['n_draws'].iloc[0])} draws)")
        lines.append(got["headline"].to_string(index=False))
        lines.append("sum:")
        lines.append(got["by_metric"]["sum"].to_string(index=False))
        lines.append("max:")
        lines.append(got["by_metric"]["max"].to_string(index=False))
        lines.append("")
    return "\n".join(lines)
