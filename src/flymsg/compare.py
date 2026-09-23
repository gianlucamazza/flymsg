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
SHIU_IR94E = [
    720575940614211295, 720575940638218173, 720575940628832256,
    720575940626016017, 720575940621375231, 720575940612920386,
    720575940614273292, 720575940628198503, 720575940626241636,
    720575940619387814, 720575940624604560, 720575940615274425,
    720575940610683315, 720575940627265265, 720575940624079544,
    720575940629211607, 720575940615089369, 720575940631082124,
]  # fmt: skip
SHIU_MN9 = 720575940660219265  # FAFB CB0701_R; MaleCNS MN9 has flywireType CB0701
SHIU_MN9_PAIR = (720575940660219265, 720575940645521262)  # their `ids_mn9`, both sides

# The four lists above are `neu_sugar`, `neu_water`, `neu_bitter` and `neu_ir94e` of
# figures.ipynb at the pinned commit 91bdd1e, checked against it id by id.
REFERENCE_SETS = {
    "sugar": SHIU_SUGAR,
    "water": SHIU_WATER,
    "bitter": SHIU_BITTER,
    "Ir94e": SHIU_IR94E,
}


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

    p = sim.Params(w_syn=sim.SHIU_W_SYN, th_jump=0.0)
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


def nearest_male_type(
    male: tuple[pd.DataFrame, pd.DataFrame],
    female: tuple[pd.DataFrame, pd.DataFrame],
    female_idx: np.ndarray,
    male_types: list[str],
) -> pd.DataFrame:
    """For each female neuron, the male type whose output profile (over partner types in the
    shared FAFB vocabulary) is most similar by cosine: the per-neuron counterpart of
    `fingerprint`, used to split a FAFB type that MaleCNS divides into subtypes."""
    mn, me = male
    fn, fe = female
    types = mn["type"].to_numpy()
    refs = {t: output_profile(mn, me, np.flatnonzero(types == t)) for t in male_types}
    rows = []
    for i in female_idx:
        prof = output_profile(fn, fe, np.array([i]))
        sims = {t: cosine(prof, r) for t, r in refs.items()}
        best = max(sims, key=sims.get)
        rows.append(
            {"idx": int(i), "bodyId": int(fn["bodyId"].iat[i]), **sims, "nearest": best}
        )
    return pd.DataFrame(rows)


LB3_SUBTYPES = ["LB3a", "LB3b", "LB3c", "LB3d"]


def sex_cases(
    male: tuple[pd.DataFrame, pd.DataFrame], female: tuple[pd.DataFrame, pd.DataFrame]
) -> dict[str, tuple[np.ndarray, np.ndarray, str]]:
    """The cases of `sex_comparison` that both datasets can run: sugar GRNs → MN9 and
    LC4_R → DNp01. The male sugar set is the validated one (LB3b_R + LB3c_R) and the female
    one is Shiu et al.'s; both read the contralateral pathway, the one they scored (see
    docs/comparison.md)."""
    from flymsg import data, validate

    mn, fn = male[0], female[0]
    return {
        "sugar GRNs -> MN9": (
            validate.sugar_grns(mn),
            ids_to_idx(fn, SHIU_SUGAR),
            "CB0701",
        ),
        "LC4_R -> DNp01": (
            data.resolve(mn, "LC4_R"),
            data.resolve(fn, "LC4_R"),
            "DNp01",
        ),
    }


def lb3_split(
    male: tuple[pd.DataFrame, pd.DataFrame], female: tuple[pd.DataFrame, pd.DataFrame]
) -> pd.DataFrame:
    """Every FAFB LB3 neuron assigned to the male subtype with the most similar output
    profile, with the Shiu et al. set it belongs to (sugar, water, bitter, Ir94e or none).
    MaleCNS splits FAFB's single LB3 into LB3a (water), LB3b/c (sugar) and LB3d (high salt),
    so this says what their sugar set is made of."""
    fn = female[0]
    idx = np.flatnonzero(fn["type"].to_numpy() == "LB3")
    out = nearest_male_type(male, female, idx, LB3_SUBTYPES)
    in_set = {i: k for k, v in REFERENCE_SETS.items() for i in v}
    out["shiu_set"] = [in_set.get(b, "none") for b in out["bodyId"]]
    return out


def lb3_mn9_rates(
    female: tuple[pd.DataFrame, pd.DataFrame],
    split: pd.DataFrame,
    rates_hz=(100.0, 200.0),
    seeds: int = 10,
    draws: int = 3,
    seed: int = 0,
) -> pd.DataFrame:
    """MN9's rate in the published model when the parts of Shiu et al.'s sugar set are
    stimulated separately: all of it, the sugar-like (LB3b/c) part, the LB3d-like part, and
    `draws` random subsets of sugar-like neurons as large as the LB3d-like part, which say
    whether the difference is just the number of neurons."""
    fn, fe = female
    mn9 = ids_to_idx(fn, [SHIU_MN9])
    sug = split[split["shiu_set"] == "sugar"]
    parts = {
        "all (their set)": sug["idx"].to_numpy(),
        "LB3b/c-like": sug[sug["nearest"].isin(["LB3b", "LB3c"])]["idx"].to_numpy(),
        "LB3d-like": sug[sug["nearest"] == "LB3d"]["idx"].to_numpy(),
    }
    rng = np.random.default_rng(seed)
    n_d = parts["LB3d-like"].size
    for d in range(draws):
        parts[f"{n_d} random LB3b/c-like ({d + 1})"] = rng.choice(
            parts["LB3b/c-like"],
            size=min(n_d, parts["LB3b/c-like"].size),
            replace=False,
        )
    rows = []
    for name, stim in parts.items():
        row = {"stimulus": name, "n": int(stim.size)}
        for rate in rates_hz:
            r = shiu_rates(fn, fe, stim, rate, seeds=seeds)
            row[f"MN9 at {rate:.0f} Hz"] = float(r[mn9].max()) if mn9.size else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
