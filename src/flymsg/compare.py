"""Male (MaleCNS) vs female (FlyWire FAFB v783) comparisons.

Cell types are matched through MaleCNS `flywireType`, which names the FAFB type of each
male neuron. The FAFB neuron sets below are those of the Shiu et al. (2024) model
(github.com/philshiu/Drosophila_brain_model, figures.ipynb); the paper used FlyWire v630, so
a few IDs no longer exist in v783 and are skipped.
"""

import numpy as np
import pandas as pd

# labellar GRNs of one side, as stimulated by Shiu et al.; all are FAFB type LB3 (sugar,
# water) or LB1 (bitter)
SHIU_SUGAR = [
    720575940624963786, 720575940630233916, 720575940637568838, 720575940638202345,
    720575940617000768, 720575940630797113, 720575940632889389, 720575940621754367,
    720575940621502051, 720575940640649691, 720575940639332736, 720575940616885538,
    720575940639198653, 720575940620900446, 720575940617937543, 720575940632425919,
    720575940633143833, 720575940612670570, 720575940628853239, 720575940629176663,
    720575940611875570,
]  # fmt: skip
SHIU_WATER = [
    720575940612950568, 720575940631898285, 720575940606002609, 720575940612579053,
    720575940622902535, 720575940616177458, 720575940660292225, 720575940622486922,
    720575940613786774, 720575940629852866, 720575940625861168, 720575940613996959,
    720575940617857694, 720575940644965399, 720575940625203504, 720575940630553415,
    720575940635172191, 720575940634796536,
]  # fmt: skip
SHIU_BITTER = [
    720575940621778381, 720575940602353632, 720575940617094208, 720575940619197093,
    720575940626287336, 720575940618600651, 720575940627692048, 720575940630195909,
    720575940646212996, 720575940610483162, 720575940645743412, 720575940627578156,
    720575940622298631, 720575940621008895, 720575940629146711, 720575940610259370,
    720575940610481370, 720575940619028208, 720575940614281266, 720575940613061118,
    720575940604027168,
]  # fmt: skip
SHIU_MN9 = 720575940660219265  # FAFB CB0701_R; MaleCNS MN9 has flywireType CB0701


def ids_to_idx(neurons: pd.DataFrame, ids) -> np.ndarray:
    """Row indices of the given bodyIds that exist in `neurons` (missing ones skipped)."""
    return np.flatnonzero(np.isin(neurons["bodyId"].to_numpy(), ids))


def output_profile(neurons: pd.DataFrame, edges: pd.DataFrame, idx) -> pd.Series:
    """Share of the synapses from `idx` onto each partner FAFB type (flywireType)."""
    e = edges[np.isin(edges["pre"], idx)]
    s = pd.Series(
        e["weight"].to_numpy(), index=neurons["flywireType"].to_numpy()[e["post"]]
    )
    s = s[s.index.notna()].groupby(level=0).sum()
    return s / s.sum()


def cosine(a: pd.Series, b: pd.Series) -> float:
    a, b = a.align(b, fill_value=0.0)
    return float(a @ b / np.sqrt((a @ a) * (b @ b)))


def fingerprint(
    male: tuple[pd.DataFrame, pd.DataFrame],
    female: tuple[pd.DataFrame, pd.DataFrame],
    male_types: list[str],
    references: dict[str, list[int]],
) -> pd.DataFrame:
    """Cosine similarity between the output profile of each male type and of each FAFB
    reference set, over partner types named in the shared FAFB vocabulary. Rows: male types;
    columns: references, plus `nearest`."""
    mn, me = male
    fn, fe = female
    refs = {k: output_profile(fn, fe, ids_to_idx(fn, v)) for k, v in references.items()}
    types = mn["type"].to_numpy()
    rows = {}
    for t in male_types:
        p = output_profile(mn, me, np.flatnonzero(types == t))
        rows[t] = {k: cosine(p, r) for k, r in refs.items()}
    out = pd.DataFrame(rows).T
    out["nearest"] = out.idxmax(axis=1)
    return out


def shiu_rates(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    stim: np.ndarray,
    rate_hz: float,
    seeds: int = 10,
    duration_ms: float = 1000.0,
) -> np.ndarray:
    """Mean rate (Hz) per neuron with the plain Shiu et al. model: their signs
    (`shiu_sign`, FAFB only), no adaptive threshold, stimulus over the whole run, as in
    their `run_exp` (their default is 30 runs of 1 s)."""
    from flymsg import sim  # scipy-heavy; keep `compare` importable on its own

    p = sim.Params(th_jump=0.0)
    W = sim.weight_matrix(edges, neurons["shiu_sign"].to_numpy(), len(neurons), p.w_syn)
    return np.mean(
        [
            sim.run(W, stim, rate_hz, duration_ms, p=p, seed=s).rate()
            for s in range(seeds)
        ],
        axis=0,
    )


def responding_types(neurons, rates: np.ndarray, stim: np.ndarray) -> set[str]:
    """FAFB-vocabulary types (flywireType) with at least one non-stimulated neuron firing."""
    fired = rates > 0
    fired[stim] = False
    return set(neurons["flywireType"][fired].dropna())


def sex_comparison(
    male: tuple[pd.DataFrame, pd.DataFrame],
    female: tuple[pd.DataFrame, pd.DataFrame],
    cases: dict[str, tuple[np.ndarray, np.ndarray, str]],
    rates_hz=(50.0, 100.0, 200.0),
    seeds: int = 3,
    duration_ms: float = 300.0,
    female_w_scale: float = 1.0,
) -> pd.DataFrame:
    """Same model and parameters on both sexes. `cases`: name -> (male stim idx, female stim
    idx, target flywireType). Per case and input rate: the best target neuron's rate in each
    sex, and the overlap (Jaccard) of the responding types, counted only over types that exist
    in both datasets (FAFB has no VNC). `female_w_scale` multiplies w_syn on the female side,
    to correct for a different synapse detection density (see synapse_density_ratio)."""
    from flymsg import sim

    p = sim.Params()
    shared = set(male[0]["flywireType"].dropna()) & set(
        female[0]["flywireType"].dropna()
    )
    Ws = {
        sex: sim.weight_matrix(e, n["sign"].to_numpy(), len(n), p.w_syn * scale)
        for sex, (n, e), scale in (
            ("male", male, 1.0),
            ("female", female, female_w_scale),
        )
    }
    rows = []
    for name, (m_stim, f_stim, target) in cases.items():
        for rate in rates_hz:
            row = {"case": name, "input_hz": rate}
            types = {}
            for sex, (n, _), stim in (
                ("male", male, m_stim),
                ("female", female, f_stim),
            ):
                r = np.mean(
                    [
                        sim.run(Ws[sex], stim, rate, duration_ms, p=p, seed=s).rate()
                        for s in range(seeds)
                    ],
                    axis=0,
                )
                tgt = np.flatnonzero(n["flywireType"].to_numpy() == target)
                row[f"{sex}_target_hz"] = float(r[tgt].max())
                types[sex] = responding_types(n, r, stim) & shared
                row[f"{sex}_types"] = len(types[sex])
            union = types["male"] | types["female"]
            row["jaccard"] = (
                len(types["male"] & types["female"]) / len(union) if union else np.nan
            )
            rows.append(row)
    return pd.DataFrame(rows)


def synapse_density_ratio(
    male: tuple[pd.DataFrame, pd.DataFrame], female: tuple[pd.DataFrame, pd.DataFrame]
) -> tuple[float, int]:
    """Median over matched types of (male / female) median input synapses per neuron, and
    the number of matched types. The datasets were imaged and segmented differently, so
    their synapse counts are not on the same scale."""
    per_type = []
    for (n, e), col in ((male, "flywireType"), (female, "type")):
        inp = np.bincount(e["post"], weights=e["weight"], minlength=len(n))
        per_type.append(
            pd.Series(inp, index=n[col].to_numpy()).groupby(level=0).median()
        )
    m, f = per_type
    j = pd.concat({"m": m, "f": f}, axis=1, join="inner")
    j = j[(j["f"] > 0) & (j["m"] > 0)]
    return float(np.median(j["m"] / j["f"])), len(j)
