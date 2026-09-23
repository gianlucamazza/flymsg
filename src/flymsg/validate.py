"""Validation battery: stimulate known circuits and check the expected outcome.

positive   reliable: the best neuron of each target type fires >= MIN_SPIKES during the
           stimulus in at least MIN_SEED_SHARE of the seeds
specific   its rate beats the control by SPECIFICITY x + MARGIN_HZ; the control stimulates
           the same number of random neurons from the same superclasses (the same classes
           for a sensory stimulus, criterion v4), excluding direct inputs of the targets, so
           the response must need the specific wiring
stability  at most MAX_PERSISTENT neurons still fire from 100 ms after the stimulus ends
order      (criterion v3) along a chain of targets, first spikes come in chain order in at
           least MIN_SEED_SHARE of the seeds where both neurons fire
dose       (criterion v3) the target's rate does not fall as the input rate rises through
           DOSE_RATES_HZ, within one spike per window, and is higher at the top than at
           the bottom
negative   (criterion v4) a stimulus known to suppress a response drives the target to less
           than 1/SPECIFICITY of the rate its positive counterpart reaches

Positive checks count spikes rather than requiring a rate: the adaptive threshold caps
steady rates (about (drive - 7 mV) / (th_jump * tau_th)), so an absolute rate threshold
would penalise adaptation itself instead of testing the wiring.

`calibrate` grid-searches w_syn x th_jump and ranks parameter sets by checks passed.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise, product

import numpy as np
import pandas as pd

from flymsg import data, parallel, sim

MIN_SPIKES = 3  # in the 300 ms stimulus window
MIN_SEED_SHARE = 2 / 3
SPECIFICITY, MARGIN_HZ = 3.0, 2.0
MAX_PERSISTENT = 100
RATE_HZ, STIM_MS, DURATION_MS = 100.0, 300.0, 600.0
DOSE_RATES_HZ = (25.0, 50.0, 100.0, 200.0)
DOSE_TOL_HZ = 1000.0 / STIM_MS  # one spike in the stimulus window


def p1(neurons: pd.DataFrame) -> np.ndarray:
    """P1 courtship neurons: the pC1 subtypes matching pMP4/pMP-e (Yu 2010, Cachero 2010)."""
    is_pc1 = neurons["type"].fillna("").str.startswith("pC1")
    return np.flatnonzero(is_pc1 & neurons["synonyms"].fillna("").str.contains("pMP4"))


def sugar_grns(neurons: pd.DataFrame) -> np.ndarray:
    """Right labellar sugar GRNs: LB3b and LB3c, the subtypes on which two independent lines
    agree (docs/validation.md): morphology matched to Gr64f-GAL4 in the gustatory connectome,
    and connectivity closest to the Shiu et al. sugar set in FAFB (compare.fingerprint)."""
    return np.flatnonzero(neurons["instance"].isin(["LB3b_R", "LB3c_R"]).to_numpy())


def bitter_grns(neurons: pd.DataFrame) -> np.ndarray:
    """Right labellar bitter GRNs: LB1a-d, matched to Gr33a-GAL4 in the gustatory connectome
    and nearest the Shiu et al. bitter set in FAFB (docs/validation.md). LB1e (Ir94e) is not
    included."""
    types = [f"LB1{s}_R" for s in "abcd"]
    return np.flatnonzero(neurons["instance"].isin(types).to_numpy())


@dataclass
class Case:
    name: str
    stim: str | Callable[[pd.DataFrame], np.ndarray]
    targets: list[str]
    reference: str
    chain: bool = False  # targets are successive stages: check their latency order

    def stim_idx(self, neurons: pd.DataFrame) -> np.ndarray:
        return (
            data.resolve(neurons, self.stim)
            if isinstance(self.stim, str)
            else self.stim(neurons)
        )

    def target_idx(self, neurons: pd.DataFrame) -> np.ndarray:
        return np.concatenate([data.resolve(neurons, t) for t in self.targets])


CASES = [
    Case(
        "looming escape", "LC4_R", ["DNp01", "TTMn"], "von Reyn 2014, Ache 2019", True
    ),
    # GF -> PSI -> DLMn is not tested: it runs mostly through gap junctions, which the
    # connectome does not contain (the chemical GF -> PSI link has only ~23 synapses).
    Case("giant fiber output", "DNp01", ["TTMn"], "King & Wyman 1980"),
    Case("P1 courtship drive", p1, ["pIP10", "dPR1"], "von Philipsborn 2011", True),
    Case("pIP10 song pathway", "pIP10", ["dPR1"], "von Philipsborn 2011"),
    Case("sugar feeding", sugar_grns, ["MN9"], "Shiu 2024; Gordon & Scott 2009"),
]

# (name, stimulus, target, positive case whose response must not be matched)
NEGATIVES = [("bitter feeding", bitter_grns, "MN9", "sugar feeding")]


def control_idx(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    stim: np.ndarray,
    targets: np.ndarray,
    rng,
) -> np.ndarray:
    """Random neurons matching the stimulus' superclass mix, minus targets and their inputs.
    For a sensory stimulus the match is by class (gustatory, olfactory, …) instead: a taste
    stimulus is compared with other taste neurons, not with any sense entering nearby."""
    strong = edges[(edges["weight"] >= 5) & np.isin(edges["post"], targets)]
    excluded = np.zeros(len(neurons), dtype=bool)
    excluded[np.concatenate([stim, targets, strong["pre"].to_numpy()])] = True
    sc = neurons["superclass"].fillna("none").to_numpy()
    if all(str(c).endswith("sensory") for c in sc[stim]):
        sc = neurons["class"].fillna("none").to_numpy()
    picks = []
    for cls, k in zip(*np.unique(sc[stim], return_counts=True), strict=True):
        pool = np.flatnonzero((sc == cls) & ~excluded)
        picks.append(rng.choice(pool, size=min(k, pool.size), replace=False))
    return np.concatenate(picks)


def case_by_name(name: str) -> "Case":
    """The validation case with this name; a KeyError listing the names if there is none."""
    for c in CASES:
        if c.name == name:
            return c
    raise KeyError(f"unknown case {name!r}; cases: {', '.join(c.name for c in CASES)}")


def respond(
    W,
    neurons,
    stim,
    targets,
    p,
    seeds,
    rate_hz=RATE_HZ,
    silence=None,
    seed0=0,
    duration_ms=DURATION_MS,
) -> tuple[dict[str, dict], float]:
    """Per target type, its best neuron (highest mean rate over seeds): rate, reliable seeds,
    first-spike latency per seed and its median. Also the mean number of self-sustained
    neurons. With `duration_ms` = STIM_MS the run stops at the end of the stimulus: rates
    are identical (the input is drawn for the stimulus only and the dynamics are causal),
    at about half the cost, but latencies miss spikes after the stimulus and the
    self-sustained count is NaN."""
    results = [
        sim.run(W, stim, rate_hz, duration_ms, STIM_MS, p, seed, silence=silence)
        for seed in range(seed0, seed0 + seeds)
    ]
    stim_bins = round(STIM_MS / results[0].bin_ms)
    spikes = np.stack([r.counts[:stim_bins].sum(axis=0) for r in results])  # seeds x n
    rates = spikes.mean(axis=0) / (STIM_MS / 1000.0)
    latency = np.stack([r.first_spike_ms for r in results])
    types = neurons["type"].to_numpy()
    out = {}
    for t in targets:
        idx = np.flatnonzero(types == t)
        if not idx.size:
            raise KeyError(f"target type {t!r} is not in this dataset")
        best = idx[np.argmax(rates[idx])]
        lat = latency[:, best]
        out[t] = {
            "rate": float(rates[best]),
            "reliable": int((spikes[:, best] >= MIN_SPIKES).sum()),
            "latencies": lat,
            "seed_rates": spikes[:, best] / (STIM_MS / 1000.0),
            "latency": float(np.median(lat[np.isfinite(lat)]))
            if np.isfinite(lat).any()
            else np.nan,
        }
    if duration_ms <= STIM_MS + 100.0:  # too short to see self-sustained activity
        return out, float("nan")
    return out, float(np.mean([r.persistent().size for r in results]))


def bootstrap_ci(values, n: int = 2000, level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap interval of the mean (fixed generator, reproducible)."""
    v = np.asarray(values, dtype=float)
    means = np.random.default_rng(0).choice(v, size=(n, v.size)).mean(axis=1)
    lo, hi = np.percentile(means, [50 * (1 - level), 50 * (1 + level)])
    return float(lo), float(hi)


def _ci(values) -> str:
    lo, hi = bootstrap_ci(values)
    return f"[{lo:.1f}, {hi:.1f}]"


def in_order(
    earlier: np.ndarray, later: np.ndarray, need_share: float
) -> tuple[bool, str]:
    """Per seed, does `earlier` fire first? Only seeds where both fired count."""
    both = np.isfinite(earlier) & np.isfinite(later)
    ok = int((earlier[both] < later[both]).sum())
    n = int(both.sum())
    return n > 0 and ok >= np.ceil(need_share * n), f"{ok}/{n} seeds in order"


def dose_ok(rates: list[float]) -> bool:
    """Non-decreasing within DOSE_TOL_HZ per step, and higher at the top than the bottom."""
    steps_ok = all(b >= a - DOSE_TOL_HZ for a, b in pairwise(rates))
    return steps_ok and rates[-1] > rates[0]


def run(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    p: sim.Params,
    seeds: int = 3,
    seed0: int = 0,
    control_seed: int = 0,
) -> pd.DataFrame:
    """One row per check: case, kind, subject, value, note, latency_ms, passed.
    Simulations use seeds seed0 .. seed0+seeds-1; control draws use `control_seed`."""
    W = sim.weight_matrix(edges, neurons["sign"].to_numpy(), len(neurons), p.w_syn)
    rng = np.random.default_rng(control_seed)
    need = int(np.ceil(MIN_SEED_SHARE * seeds))
    rows = []
    positive_rate = {}  # (case, target) -> rate, for the negative checks
    for case in CASES:
        stim = case.stim_idx(neurons)
        target_idx = np.concatenate([data.resolve(neurons, t) for t in case.targets])
        pos, persistent = respond(W, neurons, stim, case.targets, p, seeds, seed0=seed0)
        ctrl, _ = respond(
            W,
            neurons,
            control_idx(neurons, edges, stim, target_idx, rng),
            case.targets,
            p,
            seeds,
            seed0=seed0,
        )
        for t in case.targets:
            r, c = pos[t], ctrl[t]
            positive_rate[case.name, t] = r["rate"]
            rows.append(
                (
                    case.name,
                    "positive",
                    t,
                    r["rate"],
                    f"{r['reliable']}/{seeds} seeds >= {MIN_SPIKES} spikes",
                    r["latency"],
                    r["reliable"] >= need,
                )
            )
            rows.append(
                (
                    case.name,
                    "specific",
                    t,
                    c["rate"],
                    (
                        f"control {_ci(c['seed_rates'])}, target {_ci(r['seed_rates'])};"
                        f" needs <= {(r['rate'] - MARGIN_HZ) / SPECIFICITY:.1f} Hz"
                    ),
                    np.nan,
                    r["rate"] >= SPECIFICITY * c["rate"] + MARGIN_HZ,
                )
            )
        if case.chain:
            for a, b in pairwise(case.targets):
                ok, note = in_order(
                    pos[a]["latencies"], pos[b]["latencies"], MIN_SEED_SHARE
                )
                rows.append(
                    (case.name, "order", f"{a} before {b}", np.nan, note, np.nan, ok)
                )
        sweep = {
            r: pos
            if r == RATE_HZ
            else respond(W, neurons, stim, case.targets, p, seeds, r, seed0=seed0)[0]
            for r in DOSE_RATES_HZ
        }
        for t in case.targets:
            curve = [sweep[r][t]["rate"] for r in DOSE_RATES_HZ]
            # share of the peak reached at the standard rate (Shiu et al. tuned w_syn so
            # that 100 Hz sugar input gives ~80 % of maximal MN9 firing): descriptive only
            at_std = curve[DOSE_RATES_HZ.index(RATE_HZ)]
            top = (
                f", {100 * at_std / max(curve):.0f}% of peak at {RATE_HZ:.0f} Hz"
                if max(curve)
                else ""
            )
            rows.append(
                (
                    case.name,
                    "dose",
                    t,
                    curve[-1],
                    " / ".join(f"{c:.0f}" for c in curve)
                    + f" Hz at {'/'.join(f'{r:.0f}' for r in DOSE_RATES_HZ)} Hz{top}",
                    np.nan,
                    dose_ok(curve),
                )
            )
        rows.append(
            (
                case.name,
                "stability",
                "self-sustained neurons",
                persistent,
                f"<= {MAX_PERSISTENT}",
                np.nan,
                persistent <= MAX_PERSISTENT,
            )
        )
    for name, stim_fn, target, against in NEGATIVES:
        neg, _ = respond(W, neurons, stim_fn(neurons), [target], p, seeds, seed0=seed0)
        ref = positive_rate[against, target]
        rows.append(
            (
                name,
                "negative",
                target,
                neg[target]["rate"],
                (
                    f"{_ci(neg[target]['seed_rates'])}; must stay < {ref / SPECIFICITY:.1f}"
                    f" Hz (1/{SPECIFICITY:.0f} of {against})"
                ),
                np.nan,
                neg[target]["rate"] < ref / SPECIFICITY,
            )
        )
    return pd.DataFrame(
        rows,
        columns=["case", "kind", "subject", "value", "note", "latency_ms", "passed"],
    )


def select_model(passed: dict[str, int], eligible: list[str], tie_break: str) -> str:
    """Pre-registered rule: most checks passed among the eligible models; ties go to
    `tie_break` (the model with fewer compensations) if it is among the best."""
    best = max(passed[m] for m in eligible)
    top = [m for m in eligible if passed[m] == best]
    return tie_break if tie_break in top else top[0]


def _run_model(item: tuple[str, sim.Params]) -> tuple[str, pd.DataFrame]:
    neurons, edges, seeds, seed0, control_seed = parallel.context()
    name, p = item
    t = time.monotonic()
    report = run(neurons, edges, p, seeds, seed0, control_seed)
    print(
        f"  {name} (w_syn={p.w_syn:.3f} th_jump={p.th_jump}):"
        f" {int(report['passed'].sum())}/{len(report)} ({time.monotonic() - t:.0f} s)",
        flush=True,
    )
    return name, report


def compare_models(
    neurons,
    edges,
    models: dict[str, sim.Params],
    seeds: int = 10,
    workers: int = 4,
    seed0: int = 0,
    control_seed: int = 0,
) -> dict[str, pd.DataFrame]:
    """The full battery for each model, in parallel processes. Returns name -> report."""
    ctx = (neurons, edges, seeds, seed0, control_seed)
    items = list(models.items())
    done = dict(r for _, r in parallel.imap(_run_model, items, workers, ctx))
    return {name: done[name] for name in models}


def _run_point(point: tuple[float, float]) -> dict:
    neurons, edges, seeds = parallel.context()
    w_syn, th_jump = point
    t = time.monotonic()
    report = run(neurons, edges, sim.Params(w_syn=w_syn, th_jump=th_jump), seeds)
    failed = report[~report["passed"]]
    print(
        f"  w_syn={w_syn} th_jump={th_jump}: {int(report['passed'].sum())}/{len(report)} "
        f"({time.monotonic() - t:.0f} s)",
        flush=True,
    )
    return {
        "w_syn": w_syn,
        "th_jump": th_jump,
        "passed": int(report["passed"].sum()),
        "total": len(report),
        "failed": "; ".join(
            f"{r.case}/{r.kind}/{r.subject}={r.value:.0f}" for r in failed.itertuples()
        ),
    }


def calibrate(
    neurons, edges, w_syns, th_jumps, seeds: int = 3, workers: int = 4
) -> pd.DataFrame:
    """Run the battery on every (w_syn, th_jump); best first.

    Ties on checks passed go to the set closest to the published Shiu model
    (w_syn nearest 0.275, then the smallest th_jump).
    """
    grid = list(product(w_syns, th_jumps))
    done = dict(parallel.imap(_run_point, grid, workers, (neurons, edges, seeds)))
    out = pd.DataFrame([done[g] for g in grid])
    out["shiu_dist"] = (out["w_syn"] - sim.SHIU_W_SYN).abs()
    return out.sort_values(
        ["passed", "shiu_dist", "th_jump"], ascending=[False, True, True]
    ).drop(columns="shiu_dist")
