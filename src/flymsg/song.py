"""Pulse vs sine song across neuropils: a held-out benchmark (Pacheco et al. 2021, #36, M4).

The YAML file is the lock. Johnston's organ song neurons (JO-A, JO-B, JO-D, both sides) get
the same input in three conditions that differ only in time: pulse (16 ms on, 20 ms off, the
paper's stimulus), sine (constant) and an aperiodic pulse train (the same pulses at random,
non-overlapping onsets). Kicks pass a dead time of one refractory period and are then
subsampled per neuron to the same count in every condition, so each JO neuron fires the
same number of spikes: any pulse/sine difference downstream comes from the connectome's
timing, not from more input. Carrier frequency is absent by construction (the LIF model has
no band-pass mechanoreception), so the claim is the envelope-driven part of selectivity.

Per neuropil the model's activity is the sum of spike counts weighted by each neuron's
synaptic connections in that region (MaleCNS `primary_post`, left and right pooled because
the data has no hemisphere); the preference index is (pulse - sine) / (pulse + sine). The
data's sign per neuropil follows the paper's response magnitude (Methods, "Response type
kinetics and tuning") per male ROI, median per fly, sign shared by enough flies.

The model runs and its no-go check finish before the data file is opened.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import io, sparse

from flymsg import draws, locks, nulls, parallel, sim

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "song.yaml"
SYN_PARTNERS = "syn-partners-male-cns-v1.0-minconf-0.5-significant-only.feather"
PACHECO = "median_auditory_responses_wildtype.mat"
YAMAKOSHI = "Figure3_S7_Table6_Table7.zip"
KINDS = ("pulse", "sine", "aperiodic")

VERSION_HASHES: dict[int, str] = {
    1: "ad2065e6031e1c24cb8b1cf4d9a88741d67913ee6178108422ec2efbbeee54c6",
}


class SongError(ValueError):
    """The song protocol drifted from its lock, or its inputs from their hashes."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return locks.prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, SongError, "song protocol")


def assert_matches_code(doc: dict | None = None) -> dict:
    doc = assert_locked() if doc is None else doc
    s = doc["stimulus"]
    if (s["pulse_ms"], s["pause_ms"], s["train_ms"]) != (16.0, 20.0, 10000.0):
        raise SongError("the stimulus is not Pacheco et al.'s pulse train")
    if doc["claim"]["scored"] is not True or doc.get("defaults_changed") is not False:
        raise SongError("a held-out benchmark is scored and changes no default")
    labels = [row["label"] for row in doc["neuropils"]]
    if len(labels) != 41 or len(set(labels)) != 41:
        raise SongError("the map lists the 41 neuropils of the data")
    for row in doc["neuropils"]:
        if row["relation"] not in ("exact", "merged", "absent"):
            raise SongError(f"{row['label']}: unknown relation")
        if (row["relation"] == "absent") != (not row["malecns"]):
            raise SongError(f"{row['label']}: an absent neuropil has no MaleCNS region")
    if not set(doc["score"]["excluded"]) <= set(labels):
        raise SongError("an excluded neuropil is not in the map")
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    g = doc["grid"]
    return (
        f"song v{doc['version']} (issue #{doc['issue']}): JO {'/'.join(doc['drive']['types'])}, "
        f"pulse {doc['stimulus']['pulse_ms']:g}/{doc['stimulus']['pause_ms']:g} ms vs sine, "
        f"rates {g['rates_hz']} Hz, seeds {g['seed0']}-{g['seed0'] + g['seeds'] - 1}, "
        f"{g['shuffles']} degree-preserving shuffles; held-out against Pacheco et al. 2021"
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_input(path: Path, expected: str) -> Path:
    if not path.is_file():
        raise SongError(f"missing {path}")
    if sha256(path) != expected:
        raise SongError(f"{path.name} does not match its locked sha256")
    return path


# --- regions ------------------------------------------------------------------------------


def region_counts(path: Path) -> pd.DataFrame:
    """Synaptic connections per (bodyId, primary region), each connection counted for its
    presynaptic and its postsynaptic neuron; read batch by batch from the feather file."""
    from pyarrow import ipc

    reader = ipc.open_file(path)
    parts = []
    for i in range(reader.num_record_batches):
        b = reader.get_batch(i).select(["body_pre", "body_post", "primary_post"])
        roi = b.column("primary_post")
        codes = roi.indices.to_numpy(zero_copy_only=False)
        names = np.asarray(roi.dictionary.to_pylist(), dtype=object)
        for col in ("body_pre", "body_post"):
            df = pd.DataFrame({"bodyId": b.column(col).to_numpy(), "roi": names[codes]})
            parts.append(df.value_counts().rename("synapses").reset_index())
        if len(parts) > 64:
            parts = [pd.concat(parts).groupby(["bodyId", "roi"], as_index=False).sum()]
    out = pd.concat(parts).groupby(["bodyId", "roi"], as_index=False)["synapses"].sum()
    return out.sort_values(["bodyId", "roi"]).reset_index(drop=True)


def region_table(data_dir: Path, doc: dict) -> pd.DataFrame:
    """Cached `region_counts` of the locked synapse table (data/roi/neuron_roi.parquet)."""
    src = check_input(
        data_dir / "raw" / "roi" / SYN_PARTNERS, doc["inputs"]["syn_partners_sha256"]
    )
    out = data_dir / "roi" / "neuron_roi.parquet"
    meta = out.with_suffix(".json")
    sha = doc["inputs"]["syn_partners_sha256"]
    if (
        out.exists()
        and meta.exists()
        and json.loads(meta.read_text()).get("source_sha256") == sha
    ):
        return pd.read_parquet(out)
    table = region_counts(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out, index=False)
    meta.write_text(
        json.dumps(
            {
                "source": SYN_PARTNERS,
                "source_sha256": doc["inputs"]["syn_partners_sha256"],
            }
        )
    )
    return table


def base_region(name: str) -> str:
    """MaleCNS `AVLP(R)` -> `AVLP`; the data pools both hemispheres."""
    return name[:-3] if name.endswith(("(L)", "(R)")) else name


def label_weights(
    regions: pd.DataFrame, neurons: pd.DataFrame, doc: dict
) -> tuple[sparse.csr_matrix, list[str]]:
    """(neurons x scorable labels) synapse weights; rows follow `neurons`."""
    to_label = {}
    for row in doc["neuropils"]:
        if row["label"] in doc["score"]["excluded"]:
            continue  # AMMC and SAD share MaleCNS's SAD
        for r in row["malecns"]:
            if r in to_label and to_label[r] != row["label"]:
                raise SongError(f"MaleCNS region {r} maps to two labels")
            to_label[r] = row["label"]
    labels = [
        row["label"]
        for row in doc["neuropils"]
        if row["malecns"] and row["label"] not in doc["score"]["excluded"]
    ]
    col = {lab: i for i, lab in enumerate(labels)}
    r = regions.assign(label=regions["roi"].map(base_region).map(to_label))
    r = r[r["label"].isin(col)]
    index = pd.Series(np.arange(len(neurons)), index=neurons["bodyId"].to_numpy())
    rows = index.reindex(r["bodyId"].to_numpy())
    keep = rows.notna().to_numpy()
    W = sparse.csr_matrix(
        (
            r["synapses"].to_numpy(float)[keep],
            (
                rows.to_numpy()[keep].astype(np.int64),
                r["label"].map(col).to_numpy()[keep],
            ),
        ),
        shape=(len(neurons), len(labels)),
    )
    return W, labels


# --- drive --------------------------------------------------------------------------------


def stimulated(neurons: pd.DataFrame, doc: dict) -> np.ndarray:
    pattern = doc["drive"]["type_regex"]
    hit = neurons["type"].fillna("").str.match(pattern).to_numpy()
    return np.flatnonzero(hit)


def envelope(kind: str, steps: int, dt: float, doc: dict, rng) -> np.ndarray:
    """Boolean per step: is the stimulus on. Aperiodic pulses keep the pulse count and
    duration and draw onsets uniformly among placements that keep pulses apart."""
    s = doc["stimulus"]
    on = round(s["pulse_ms"] / dt)
    period = on + round(s["pause_ms"] / dt)
    t = np.arange(steps)
    if kind == "sine":
        return np.ones(steps, bool)
    pulse = (t % period) < on
    if kind == "pulse":
        return pulse
    if kind != "aperiodic":
        raise SongError(f"unknown condition {kind}")
    n = int(np.count_nonzero(np.diff(np.r_[0, pulse.astype(int)]) == 1))
    # at least one step between pulses, so no two merge into a longer one
    slack = steps - n * on - (n - 1)
    gaps = np.sort(rng.integers(0, slack + 1, n))
    starts = gaps + np.arange(n) * (on + 1)
    out = np.zeros(steps, bool)
    for a in starts:
        out[a : a + on] = True
    return out


def dead_time(k: np.ndarray, gap: int) -> np.ndarray:
    """At most one kick per step and none within `gap` steps of the previous kept one."""
    out = np.zeros(k.shape, np.int8)
    for j in range(k.shape[1]):
        last = -gap
        for t in np.flatnonzero(k[:, j]):
            if t - last >= gap:
                out[t, j] = 1
                last = t
    return out


def matched_kicks(
    n_stim: int, rate_hz: float, seed: int, doc: dict, p: sim.Params
) -> dict[str, np.ndarray]:
    """Kicks per condition with the same per-neuron count in every condition."""
    s = doc["stimulus"]
    steps = round(s["train_ms"] / p.dt)
    gap = round(p.t_ref / p.dt)
    duty = s["pulse_ms"] / (s["pulse_ms"] + s["pause_ms"])
    rng = np.random.default_rng(seed)
    raw = {}
    for kind in KINDS:
        env = envelope(kind, steps, p.dt, doc, rng)
        rate_on = rate_hz if kind == "sine" else rate_hz / duty  # equal mean rate
        lam = np.where(env, rate_on * p.dt / 1000.0, 0.0)[:, None]
        raw[kind] = dead_time(rng.poisson(np.broadcast_to(lam, (steps, n_stim))), gap)
    target = np.min([k.sum(0) for k in raw.values()], axis=0)
    out = {}
    for kind, k in raw.items():
        m = np.zeros_like(k)
        for j in range(n_stim):
            idx = np.flatnonzero(k[:, j])
            m[rng.choice(idx, target[j], replace=False), j] = 1
        out[kind] = m
    return out


# --- secondary weights (Yamakoshi et al. 2025) ---------------------------------------------


def _peak(raw: np.ndarray, y: dict) -> float:
    """Their pipeline (Methods; reproduces data_afterfitting_all.csv): dF/F per trial on the
    mean of frames 1-19, a linear bleaching fit on frames 1-19 and 61-100 subtracted, the
    mean over trials, a centred three-frame moving average; the peak over the stimulus."""
    frames = np.arange(1, raw.shape[0] + 1)
    base = raw[: y["baseline_frames"][1]].mean(axis=0)
    dff = (raw - base) / base
    fit = np.r_[
        np.arange(y["baseline_frames"][1]),
        np.arange(y["fit_after_frame"] - 1, raw.shape[0]),
    ]
    out = []
    for j in range(dff.shape[1]):
        slope, intercept = np.polyfit(frames[fit], dff[fit, j], 1)
        out.append(dff[:, j] - (slope * frames + intercept))
    mean = np.mean(out, axis=0)
    smooth = np.convolve(mean, np.ones(3) / 3, mode="same")
    a, b = y["stimulus_frames"]
    return float(smooth[a - 1 : b].max())


def yamakoshi_ratios(path: Path, doc: dict) -> dict:
    """Per condition, the median over control flies of JO-A peak / JO-B peak (same fly,
    same stimulus, two ROIs on the JO axon bundle): pulse <- the 35 ms IPI pulse song, sine
    <- the 100 Hz tone."""
    import zipfile

    y = doc["secondary"]
    check_input(path, doc["inputs"]["yamakoshi_sha256"])
    root = "Figure3_S7_Table6_Table7/Figure_3_S7_Table_6_7_FGal4iavGal4_Dop1R2"
    out = {}
    with zipfile.ZipFile(path) as z:
        for kind, column in (("pulse", y["pulse_column"]), ("sine", y["sine_column"])):
            ratios = []
            for fly in range(1, y["control_flies"] + 1):
                peaks = {}
                for g in ("JOA", "JOB"):
                    name = f"{root}/{g}/control/fly{fly}_control_{g}.csv"
                    t = pd.read_csv(z.open(name), index_col=0)
                    cols = [c for c in t.columns if c.startswith(column + "_")]
                    peaks[g] = _peak(t[cols].to_numpy(float), y)
                ratios.append(peaks["JOA"] / peaks["JOB"])
            out[kind] = float(np.median(ratios))
    return out


# --- runs ---------------------------------------------------------------------------------


def _respond(
    W, stim, weights, kicks: dict, doc: dict, p: sim.Params, seed: int, kinds
) -> list[dict]:
    g = doc["grid"]
    rows = []
    for kind in kinds:
        r = sim.run(
            W,
            stim,
            duration_ms=g["duration_ms"],
            stim_ms=doc["stimulus"]["train_ms"],
            p=p,
            seed=seed,
            bin_ms=g["bin_ms"],
            kicks=kicks[kind],
        )
        counts = np.asarray(r.counts.sum(axis=0), float)
        jo = counts[stim]
        counts[stim] = 0.0  # the driven neurons' counts are set by the design
        activity = weights.T @ counts
        rows.append(
            {
                "kind": kind,
                "activity": [float(x) for x in activity],
                "jo_spikes": int(jo.sum()),
                "jo_kicks": int(kicks[kind].sum()),
                "active": int(np.count_nonzero(counts)),
            }
        )
    return rows


def weighted_kicks(
    kicks: dict, subgroup: np.ndarray, ratios: dict, seed: int
) -> dict[str, np.ndarray]:
    """Secondary drive: in each condition thin the weaker of JO-A and JO-B so that their
    kick ratio is the measured response ratio A/B (JO-D untouched)."""
    rng = np.random.default_rng(seed + 1_000_003)
    out = {}
    for kind, rho in (("pulse", ratios["pulse"]), ("sine", ratios["sine"])):
        k = kicks[kind].copy()
        weak, keep = ("A", rho) if rho < 1 else ("B", 1 / rho)
        cols = np.flatnonzero(subgroup == weak)
        k[:, cols] *= (rng.random((k.shape[0], cols.size)) < keep).astype(k.dtype)
        out[f"{kind}_w"] = k
    return out


def _job(job: tuple) -> list[dict]:
    (neurons, edges, weights, doc, ratios), _checkpoint, _meta = parallel.context()
    family, rate, shuffle, seed = job
    p = sim.Params()
    e = edges if family == "real" else nulls.shuffle_degree_preserving(edges, shuffle)
    W = sim.network(neurons, e, p)
    stim = stimulated(neurons, doc)
    kicks = matched_kicks(stim.size, rate, seed, doc, p)
    kinds = KINDS if family == "real" else ("pulse", "sine")
    if family == "real" and rate == doc["grid"]["decision_rate_hz"]:
        sub = np.array([t[3] for t in neurons["type"].to_numpy()[stim]])
        kicks |= weighted_kicks(kicks, sub, ratios, seed)
        kinds = (*kinds, "pulse_w", "sine_w")
    rows = _respond(W, stim, weights, kicks, doc, p, seed, kinds)
    for row in rows:
        row.update(family=family, rate_hz=rate, shuffle=shuffle, seed=seed)
    return rows


def jobs(doc: dict) -> list[tuple]:
    g = doc["grid"]
    seeds = range(g["seed0"], g["seed0"] + g["seeds"])
    real = [("real", r, -1, s) for r in g["rates_hz"] for s in seeds]
    shuf = [
        ("shuffle", g["decision_rate_hz"], g["shuffle_seed0"] + k, s)
        for k in range(g["shuffles"])
        for s in seeds
    ]
    return real + shuf


def run(
    neurons,
    edges,
    regions: pd.DataFrame,
    ratios: dict,
    workers: int = 1,
    checkpoint: Path | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    doc = assert_matches_code()
    weights, labels = label_weights(regions, neurons, doc)
    meta = {"version": doc["version"], "sha256": doc["content_sha256"]}
    rows = draws.map_jobs(
        _job,
        jobs(doc),
        workers,
        (neurons, edges, weights, doc, ratios),
        checkpoint,
        meta,
    )
    return pd.DataFrame(rows), labels


# --- model judgement ------------------------------------------------------------------------


def index(pulse: np.ndarray, other: np.ndarray) -> np.ndarray:
    """(pulse - other) / (pulse + other); NaN where both are silent."""
    total = pulse + other
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(total > 0, (pulse - other) / total, np.nan)


def model_indices(
    cells: pd.DataFrame,
    labels: list[str],
    family: str,
    rate: float,
    other: str = "sine",
    shuffle: int = -1,
) -> pd.DataFrame:
    """Per seed and label: the preference index of pulse against `other`."""
    c = cells[
        (cells.family == family) & (cells.rate_hz == rate) & (cells.shuffle == shuffle)
    ]
    out = []
    for seed, g in c.groupby("seed"):
        by = {row.kind: np.asarray(row.activity, float) for row in g.itertuples()}
        for lab, d in zip(labels, index(by["pulse"], by[other]), strict=True):
            out.append({"seed": seed, "label": lab, "index": d})
    return pd.DataFrame(out)


def model_signs(idx: pd.DataFrame) -> pd.DataFrame:
    """Per label: seed-median index, and resolved when every seed has the same nonzero sign."""
    rows = []
    for lab, g in idx.groupby("label", sort=False):
        s = np.sign(g["index"].to_numpy())
        rows.append(
            {
                "label": lab,
                "index_median": float(g["index"].median()),
                "resolved": bool(
                    np.all(s == s[0]) and s[0] != 0 and not np.isnan(s).any()
                ),
                "sign": int(s[0]) if np.all(s == s[0]) and not np.isnan(s).any() else 0,
            }
        )
    return pd.DataFrame(rows)


def no_go(signs: pd.DataFrame, doc: dict) -> tuple[bool, str]:
    """Model only, before the data are read: informative when enough labels resolve."""
    share = float(signs["resolved"].mean()) if len(signs) else 0.0
    need = doc["no_go"]["min_resolved_share"]
    ok = share >= need - 1e-12
    return (
        ok,
        f"{int(signs['resolved'].sum())} of {len(signs)} neuropils resolved ({share:.2f}, need {need})",
    )


# --- data targets (read only after the model and its no-go) --------------------------------


def magnitude(trace: np.ndarray, t: np.ndarray, rule: dict) -> np.ndarray:
    """The paper's response magnitude per ROI: baseline-subtracted signal from stimulus onset
    to 2 s after offset, its 80th or 20th percentile, whichever is larger in absolute value
    (absolute value returned). Baseline: mean from -4 to -0.5 s."""
    base = trace[:, (t >= rule["baseline_s"][0]) & (t <= rule["baseline_s"][1])].mean(
        axis=1
    )
    win = (
        trace[:, (t >= rule["window_s"][0]) & (t <= rule["window_s"][1])]
        - base[:, None]
    )
    hi = np.percentile(win, rule["high_percentile"], axis=1)
    lo = np.percentile(win, rule["low_percentile"], axis=1)
    return np.maximum(np.abs(hi), np.abs(lo))


def data_targets(path: Path, doc: dict) -> pd.DataFrame:
    """Per neuropil label: male flies, the median over flies of each fly's median ROI index,
    and a sign when at least `min_flies` flies and `min_fly_share` of them agree."""
    d = io.loadmat(path, simplify_cells=True)["dataset"]
    rule = doc["data_rule"]
    t_all = np.asarray(d["timestamps"], float)
    stim_idx = np.asarray(d["stimuli_index_vector"], int)
    names = list(d["stimuli_name_string"])
    signal = np.asarray(d[rule["signal"]], float)
    sexes = list(d["sex_full_name_string"])
    male = np.asarray(d["sex_index_per_roi"], int) == sexes.index(rule["sex"]) + 1
    neuropil = np.asarray(d["neuropil_index_per_roi"], int)  # 1-based, 0 = none
    labels = list(d["neuropil_full_names"])
    fly = np.asarray(d["fly_index_per_roi"], int)
    mags = {}
    for stim in ("Pulse", "Sine"):
        k = names.index(stim) + 1
        on = np.flatnonzero(stim_idx == k)
        block = np.arange(
            on[0] - rule["block_before"],
            on[0] - rule["block_before"] + rule["block_len"],
        )
        t = t_all[block]
        mags[stim] = magnitude(signal[:, block], t, rule)
    roi_index = index(mags["Pulse"], mags["Sine"])
    df = pd.DataFrame({"fly": fly, "neuropil": neuropil, "index": roi_index})[
        male & (neuropil > 0)
    ]
    df["label"] = [labels[i - 1] for i in df["neuropil"]]
    per_fly = df.groupby(["label", "fly"])["index"].median().reset_index()
    rows = []
    for lab, g in per_fly.groupby("label"):
        s = np.sign(g["index"].to_numpy())
        pos, neg = int((s > 0).sum()), int((s < 0).sum())
        n = len(g)
        share = max(pos, neg) / n
        need = rule["min_fly_share_num"] / rule["min_fly_share_den"]
        decided = n >= rule["min_flies"] and share >= need - 1e-12
        rows.append(
            {
                "label": lab,
                "flies": n,
                "index_median": float(g["index"].median()),
                "fly_share": share,
                "sign": (1 if pos > neg else -1) if decided else 0,
            }
        )
    return pd.DataFrame(rows)


# --- score ----------------------------------------------------------------------------------


def balanced_accuracy(pred: np.ndarray, truth: np.ndarray) -> float:
    """Mean recall over the two data classes; a missing or zero prediction is wrong."""
    recalls = [
        float(np.mean(pred[truth == c] == c)) for c in (1, -1) if np.any(truth == c)
    ]
    return float(np.mean(recalls))


def judge(
    cells: pd.DataFrame, labels: list[str], targets: pd.DataFrame, doc: dict
) -> dict:
    g = doc["grid"]
    s = doc["score"]
    rate = g["decision_rate_hz"]
    real = model_signs(model_indices(cells, labels, "real", rate))
    t = targets[targets["label"].isin(labels) & (targets["sign"] != 0)]
    scored = t.merge(real[real["resolved"]], on="label", suffixes=("_data", "_model"))
    out = {"scored": len(scored), "labels": scored["label"].tolist()}
    truth = scored["sign_data"].to_numpy()
    if len(scored) < s["min_scored"] or len(set(truth)) < 2:
        out["verdict"] = "uninformative: too few scored neuropils or one data class"
        return out
    pred = scored["sign_model"].to_numpy()
    acc = balanced_accuracy(pred, truth)
    rng = np.random.default_rng(s["permutation_seed"])
    perm = np.array(
        [
            balanced_accuracy(rng.permutation(pred), truth)
            for _ in range(s["permutations"])
        ]
    )
    p_perm = (1 + int(np.sum(perm >= acc - 1e-12))) / (1 + s["permutations"])
    shuf = []
    for k in sorted(cells.loc[cells.family == "shuffle", "shuffle"].unique()):
        sg = model_signs(
            model_indices(cells, labels, "shuffle", rate, shuffle=k)
        ).set_index("label")
        shuf.append(
            balanced_accuracy(
                sg.reindex(scored["label"])["sign"].fillna(0).to_numpy(), truth
            )
        )
    shuf = np.asarray(shuf)
    p_shuf = (1 + int(np.sum(shuf >= acc - 1e-12))) / (1 + len(shuf))
    acc_aper = balanced_accuracy(_aperiodic_pred(cells, labels, rate, scored), truth)
    out.update(
        balanced_accuracy=acc,
        p_permutation=p_perm,
        p_shuffle=p_shuf,
        shuffle_accuracies=shuf.tolist(),
        aperiodic_accuracy=acc_aper,
    )
    alpha = s["alpha"]
    if p_perm <= alpha and p_shuf <= alpha and acc > acc_aper:
        out["verdict"] = "pass"
    elif p_perm <= alpha and p_shuf <= alpha:
        out["verdict"] = "pass_burst_only"
    else:
        out["verdict"] = "fail"
    return out


def _aperiodic_pred(cells, labels, rate, scored) -> np.ndarray:
    """Signs of the aperiodic train against sine: a model with pulses but no period."""
    c = cells[(cells.family == "real") & (cells.rate_hz == rate)]
    out = []
    for seed, g in c.groupby("seed"):
        by = {row.kind: np.asarray(row.activity, float) for row in g.itertuples()}
        for lab, d in zip(labels, index(by["aperiodic"], by["sine"]), strict=True):
            out.append({"seed": seed, "label": lab, "index": d})
    sg = model_signs(pd.DataFrame(out)).set_index("label")
    return sg.reindex(scored["label"])["sign"].fillna(0).to_numpy()


def reported(
    cells: pd.DataFrame, labels: list[str], targets: pd.DataFrame, doc: dict
) -> dict:
    """What does not decide: the other rates, the secondary drive, pulse against the
    aperiodic train, and whether JO spikes matched across conditions."""
    t = targets[targets["label"].isin(labels) & (targets["sign"] != 0)].set_index(
        "label"
    )
    truth = t["sign"].to_numpy()

    def acc(signs: pd.DataFrame) -> float | None:
        pred = signs.set_index("label").reindex(t.index)["sign"].fillna(0).to_numpy()
        return balanced_accuracy(pred, truth) if len(set(truth)) == 2 else None

    out = {}
    for rate in doc["grid"]["rates_hz"]:
        out[f"accuracy_at_{rate:g}_hz"] = acc(
            model_signs(model_indices(cells, labels, "real", rate))
        )
    rate = doc["grid"]["decision_rate_hz"]
    c = cells[(cells.family == "real") & (cells.rate_hz == rate)]
    rows = []
    for seed, g in c.groupby("seed"):
        by = {row.kind: np.asarray(row.activity, float) for row in g.itertuples()}
        for lab, d in zip(labels, index(by["pulse_w"], by["sine_w"]), strict=True):
            rows.append({"seed": seed, "label": lab, "index": d})
    out["secondary_accuracy"] = acc(model_signs(pd.DataFrame(rows)))
    period = model_signs(model_indices(cells, labels, "real", rate, other="aperiodic"))
    out["pulse_vs_aperiodic_resolved"] = int(period["resolved"].sum())
    real = cells[(cells.family == "real") & cells.kind.isin(KINDS)]
    spread = real.groupby(["rate_hz", "seed"])["jo_spikes"].agg(
        lambda x: int(x.max() - x.min())
    )
    out["jo_spike_spread_max"] = int(spread.max())
    return out
