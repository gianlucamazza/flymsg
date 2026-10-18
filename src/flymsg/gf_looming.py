"""Looming -> giant fiber timing against whole-cell recordings (#34, gate G3).

The YAML file is the lock. A dark disc expands from 10 to 63 degrees at four r/v (Jang et
al. 2023's protocol, which Dombrovski et al. 2025 cite for their giant-fiber recordings).
LC4 is driven in proportion to the disc's angular velocity and LPLC2 to its angular size,
both sides, with gains scanned over an engineered grid: LC4 and LPLC2 spike rates to looming
are not measured. Each of the model's giant fibers (DNp01 R and L) is read at every neural
step; a cell is scored only where both stay graded, as the recordings are. The peak time
before the virtual collision is fitted as alpha * r/v - delta per cell. The recordings give
the same fit per fly; the score asks whether the model's slope alpha, which fixes the
angular size the response follows, lies in the flies' interval. If that interval holds the
slope a peak locked to the stimulus would give whatever the circuit (at the expansion's end
or onset), the run is uninformative. Amplitudes are never compared.

Version 1 found the LIF giant fiber firing to every drive of the grid, while the recordings
are graded; from version 2 the two giant fibers are passive (a threshold out of reach), so
their potential integrates the drive.

The model runs and its no-go check finish before any data file is opened.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import io, signal

from flymsg import draws, eye, locks, parallel, sim, stimulus
from flymsg.runtime import CpuRuntime

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "gf_looming.yaml"
GF = ("DNp01(GF)_R", "DNp01(GF)_L")
REACH = 0.95  # a peak's time: the first sample at 95% of the window maximum
NEAR_END_MS = 20.0  # a peak this soon after the expansion stops follows the stimulus

VERSION_HASHES: dict[int, str] = {
    # version 1 ran uninformative: the LIF giant fiber fired in every cell
    1: "c868e4ec8a84cc375492f4a26b3e3f7a47ced35966d4ad575a328a285c65f0c4",
    2: "dea19e71409fefdc62d2db657e76322e4f4144d3c7dbe318162326170dcc29f1",  # passive giant fibers
}


class LoomingError(ValueError):
    """The giant-fiber protocol drifted from its lock, or its inputs from their hashes."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(
        doc, VERSION_HASHES, LoomingError, "giant-fiber looming protocol"
    )


def assert_matches_code(doc: dict | None = None) -> dict:
    doc = assert_locked() if doc is None else doc
    s, d, m = doc["stimulus"], doc["drive"], doc["model"]
    if (s["start_deg"], s["end_deg"]) != (10.0, 63.0):
        raise LoomingError("the disc is not Jang et al.'s 10 to 63 degrees")
    if s["rv_ms"] != doc["inputs"]["columns_rv_ms"]:
        raise LoomingError("the model's r/v are not the data's columns")
    if 0.0 not in d["g4_hz_per_rad_s"] or 0.0 not in d["g2_hz_per_rad"]:
        raise LoomingError("the grid covers each population alone")
    if (doc["version"] >= 2) != passive_gf(doc):
        raise LoomingError(
            "versions from 2 on, and only they, make the giant fibers passive"
        )
    if passive_gf(doc) and not m["passive_v_th_mv"] > 1000.0:
        raise LoomingError("a passive giant fiber's threshold must be out of reach")
    if (m["reach"], m["near_end_ms"]) != (REACH, NEAR_END_MS):
        raise LoomingError("the peak rule differs from the code's")
    if doc["claim"]["scored"] is not True or doc.get("defaults_changed") is not False:
        raise LoomingError("a held-out benchmark is scored and changes no default")
    if len(doc["inputs"]["control_md5"]) != 20:
        raise LoomingError("the lock names the ten control flies' twenty files")
    return doc


def cells(doc: dict) -> list[tuple[float, float]]:
    d = doc["drive"]
    return [
        (g4, g2)
        for g4 in d["g4_hz_per_rad_s"]
        for g2 in d["g2_hz_per_rad"]
        if (g4, g2) != (0.0, 0.0)
    ]


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    m = doc["model"]
    return (
        f"gf_looming v{doc['version']} (issue #{doc['issue']}): LC4 ~ dtheta/dt, "
        f"LPLC2 ~ theta, {len(cells(doc))} gain cells, r/v {doc['stimulus']['rv_ms']} ms, "
        f"seeds {m['seed0']}-{m['seed0'] + m['seeds'] - 1}; timing of DNp01 against "
        f"Dombrovski et al. 2025"
    )


# --- stimulus ---------------------------------------------------------------------------


def expansion(rv_ms: float, doc: dict, dt_ms: float) -> dict:
    """Times (ms from the run's start) and the disc's full angle (rad) and its rate (rad/s)
    at every step; onset, end of expansion and virtual collision in ms."""
    s, m = doc["stimulus"], doc["model"]
    to_start = rv_ms / math.tan(math.radians(s["start_deg"] / 2))
    to_end = rv_ms / math.tan(math.radians(s["end_deg"] / 2))
    onset = m["pre_ms"]
    collision = onset + to_start
    end = collision - to_end
    # one filter frame past the window, so the filter's edge stays outside it
    duration = end + m["post_ms"] + (end - onset) / 10
    t = np.arange(round(duration / dt_ms)) * dt_ms
    half = np.radians(eye.looming_radius_deg(np.minimum(t, end), collision, rv_ms))
    theta = np.where(t < onset, 0.0, 2 * half)
    to_go = collision - t
    rate = np.where(
        (t >= onset) & (t < end), 2 * rv_ms / (to_go**2 + rv_ms**2) * 1000.0, 0.0
    )
    return {
        "t": t,
        "theta": theta,
        "dtheta": rate,
        "onset": onset,
        "end": end,
        "collision": collision,
    }


def rates(stim: dict, g4: float, g2: float, p: sim.Params) -> tuple[np.ndarray, ...]:
    cap = 1000.0 / p.t_ref
    return np.minimum(g4 * stim["dtheta"], cap), np.minimum(g2 * stim["theta"], cap)


def drive(
    neurons: pd.DataFrame, doc: dict
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    d = doc["drive"]
    lc4 = np.flatnonzero(neurons["type"].to_numpy() == d["lc4_type"])
    lplc2 = np.flatnonzero(neurons["type"].to_numpy() == d["lplc2_type"])
    if (lc4.size, lplc2.size) != (d["lc4_neurons"], d["lplc2_neurons"]):
        raise LoomingError("the LC4 or LPLC2 count differs from the lock's")
    hits = [np.flatnonzero(neurons["instance"].to_numpy() == g) for g in GF]
    if any(h.size != 1 for h in hits):
        raise LoomingError("each giant fiber instance must name one neuron")
    return lc4, lplc2, np.array([h[0] for h in hits])


# --- model ------------------------------------------------------------------------------


def respond(W, lc4, lplc2, gf, rv_ms, g4, g2, seed, doc, p) -> dict:
    """One run: each giant fiber's potential every step and the readout."""
    stim = expansion(rv_ms, doc, p.dt)
    r4, r2 = rates(stim, g4, g2, p)
    inputs = np.concatenate([lc4, lplc2])
    order = np.argsort(inputs)  # CpuRuntime keeps its inputs sorted
    lam = np.concatenate(
        [np.repeat(r4[:, None], lc4.size, 1), np.repeat(r2[:, None], lplc2.size, 1)],
        axis=1,
    )[:, order] * (p.dt / 1000.0)
    # stimulated neurons are never refractory in the kernel: kicks keep one refractory
    # period apart, as in song
    raw = np.random.default_rng(seed).poisson(lam)
    kicks = stimulus.dead_time(raw, round(p.t_ref / p.dt)).astype(np.int64)
    steps = kicks.shape[0]
    rt = CpuRuntime(
        W,
        inputs[order],
        steps=steps,
        kicks=kicks,
        p=p,
        per_bin=steps,  # one count bin: the readout is the traced potential, not counts
        trace=gf,
        membrane=passive(gf, doc, p),
    )
    v = np.empty((steps, gf.size))
    for k in range(steps):
        rt.advance_to(k + 1)
        v[k] = rt.read(gf)["v"]
    fired = rt.traced_spikes(0, steps).astype(bool)
    if passive_gf(doc) and fired.any():  # anywhere in the run
        raise LoomingError("a passive giant fiber reached its threshold")
    return {"v": v, **readout(v, fired, stim, p.dt, doc)}


def passive_gf(doc: dict) -> bool:
    """Whether the lock makes the giant fibers passive (version 2 on)."""
    return "passive_v_th_mv" in doc["model"]


def passive(gf: np.ndarray, doc: dict, p: sim.Params) -> sim.Membrane | None:
    """From version 2: the giant fibers keep every default but a threshold out of reach,
    so their potential integrates the drive as a recorded potential below threshold."""
    if not passive_gf(doc):
        return None
    v_th = doc["model"]["passive_v_th_mv"]
    n = gf.size
    return sim.Membrane(
        gf,
        np.full(n, p.tau_m),
        np.full(n, p.tau_syn),
        np.full(n, p.v_rest),
        np.full(n, float(v_th)),
    )


def peak_time(x: np.ndarray, t: np.ndarray, window: np.ndarray, base: float) -> tuple:
    """The first time the trace reaches REACH of its window maximum above baseline, the
    rise, and whether that is the window's last sample (an edge peak)."""
    idx = np.flatnonzero(window)
    top = float(x[idx].max())
    i = idx[np.flatnonzero(x[idx] >= base + REACH * (top - base))[0]]
    return float(t[i]), top - base, bool(i == idx[-1])


def smooth(x: np.ndarray, stim: dict, dt_ms: float) -> np.ndarray:
    """Jang et al. 2023's Savitzky-Golay filter: order 4, a frame of a tenth of the
    expansion, odd; the same in ms for model and data, since the distortion it gives an
    asymmetric peak grows with r/v."""
    frame = math.ceil((stim["end"] - stim["onset"]) / 10 / dt_ms) // 2 * 2 + 1
    return signal.savgol_filter(x, frame, 4)


def readout(v, fired, stim, dt_ms, doc) -> dict:
    """Per giant fiber its peak time on the filtered trace; the run's is their mean. A
    sample read after a step stands at the end of that step."""
    t = stim["t"] + dt_ms
    window = (t > stim["onset"]) & (t <= stim["end"] + doc["model"]["post_ms"])
    before = t <= stim["onset"]
    times, rises, edge = [], [], False
    for j in range(v.shape[1]):
        x = smooth(v[:, j], stim, dt_ms)
        when, rise, at_edge = peak_time(x, t, window, float(x[before].mean()))
        times.append(when)
        rises.append(rise)
        edge |= at_edge
    when = float(np.mean(times))
    return {
        "depolarization_mv": float(min(rises)),
        "peak_ms": when,
        "before_collision_ms": float(stim["collision"] - when),
        "spiked": bool(fired[window].any()),
        "edge": edge,
        "near_end": bool(stim["end"] <= when <= stim["end"] + NEAR_END_MS),
    }


def _job(job: tuple) -> list[dict]:
    (W, lc4, lplc2, gf, doc), _checkpoint, _meta = parallel.context()
    g4, g2, seed = job
    p = sim.Params()
    rows = []
    for rv in doc["stimulus"]["rv_ms"]:
        r = respond(W, lc4, lplc2, gf, rv, g4, g2, seed, doc, p)
        r.pop("v")
        rows.append({"g4": g4, "g2": g2, "seed": seed, "rv_ms": rv, **r})
    return rows


def jobs(doc: dict) -> list[tuple]:
    m = doc["model"]
    seeds = range(m["seed0"], m["seed0"] + m["seeds"])
    return [(g4, g2, s) for g4, g2 in cells(doc) for s in seeds]


def run(neurons, edges, workers: int = 1, checkpoint: Path | None = None):
    doc = assert_matches_code()
    p = sim.Params()
    lc4, lplc2, gf = drive(neurons, doc)
    W = sim.network(neurons, edges, p)
    meta = {"version": doc["version"], "sha256": doc["content_sha256"]}
    rows = draws.map_jobs(
        _job, jobs(doc), workers, (W, lc4, lplc2, gf, doc), checkpoint, meta
    )
    return pd.DataFrame(rows)


def fit(rv: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Ordinary least squares y = alpha * rv - delta."""
    slope, intercept = np.polyfit(np.asarray(rv, float), np.asarray(y, float), 1)
    return float(slope), float(-intercept)


def threshold_deg(alpha: float) -> float:
    return math.degrees(2 * math.atan(1 / alpha)) if alpha > 0 else float("nan")


def model_fits(rows: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Per cell: whether it responds and stays graded, and the fit over seed medians."""
    w = sim.Params.w_syn
    out = []
    for (g4, g2), c in rows.groupby(["g4", "g2"]):
        responds = bool((c.depolarization_mv >= w).all())
        graded = not bool(c.spiked.any())
        med = c.groupby("rv_ms")["before_collision_ms"].median().sort_index()
        alpha, delta = fit(med.index.to_numpy(), med.to_numpy())
        out.append(
            {
                "g4": g4,
                "g2": g2,
                "responds": responds,
                "graded": graded,
                "scored": responds and graded,
                "alpha": alpha,
                "delta_ms": delta,
                "theta_thr_deg": threshold_deg(alpha),
                "increasing": bool(np.all(np.diff(med.to_numpy()) > 0)),
                "near_end_share": float(c.near_end.mean()),
                "edge_peaks": int(c.edge.sum()),
            }
        )
    return pd.DataFrame(out)


def no_go(fits: pd.DataFrame, doc: dict) -> tuple[bool, str]:
    n = int(fits["scored"].sum())
    return n >= doc["no_go"]["min_scored_cells"], (
        f"{n} of {len(fits)} cells scored (responding and graded); "
        f"{int(fits['responds'].sum())} respond, {int(fits['graded'].sum())} stay graded"
    )


def lowpass(x: np.ndarray, tau_ms: float, dt_ms: float) -> np.ndarray:
    """First-order low-pass, exact for piecewise-constant input."""
    if tau_ms == 0:
        return x
    a = math.exp(-dt_ms / tau_ms)
    out = np.empty_like(x)
    acc = 0.0
    for k, v in enumerate(x):
        acc = a * acc + (1 - a) * v
        out[k] = acc
    return out


def follower_slopes(doc: dict, dt_ms: float) -> dict[str, float]:
    """The slope alpha the locked readout gives a trace that only follows the stimulus:
    theta or dtheta/dt, raw or through tau_syn and tau_m (sim.Params), at this dt."""
    p = sim.Params()
    filters = {
        "raw": (),
        "tau_syn": (p.tau_syn,),
        "tau_m": (p.tau_m,),
        "tau_syn+tau_m": (p.tau_syn, p.tau_m),
    }
    out = {}
    for name in ("theta", "dtheta"):
        for label, taus in filters.items():
            ys = []
            for rv in doc["stimulus"]["rv_ms"]:
                stim = expansion(rv, doc, dt_ms)
                x = stim[name]
                for tau in taus:
                    x = lowpass(x, tau, dt_ms)
                y = readout(x[:, None], np.zeros((x.size, 1), bool), stim, dt_ms, doc)
                ys.append(y["before_collision_ms"])
            out[f"{name}/{label}"] = fit(np.asarray(doc["stimulus"]["rv_ms"]), ys)[0]
    return out


def stimulus_locked(doc: dict) -> dict:
    """The band of slopes stimulus followers give at the model's and the data's dt, and
    the slope of a peak at onset; whatever the circuit, a slope there is the stimulus's."""
    s = doc["stimulus"]
    slopes = {
        **follower_slopes(doc, sim.Params.dt),
        **{
            f"{k}@data": v
            for k, v in follower_slopes(
                doc, 1000.0 / doc["inputs"]["sample_rate_hz"]
            ).items()
        },
    }
    return {
        "band": [min(slopes.values()), max(slopes.values())],
        "onset": 1 / math.tan(math.radians(s["start_deg"] / 2)),
        "followers": slopes,
    }


# --- data -------------------------------------------------------------------------------


def md5(path: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def inputs_present(data_dir: Path, doc: dict) -> Path:
    """Before the model runs: every locked file exists (none is opened here)."""
    directory = data_dir / Path(doc["inputs"]["directory"]).relative_to("data")
    missing = [n for n in doc["inputs"]["control_md5"] if not (directory / n).is_file()]
    if missing:
        raise LoomingError(f"{len(missing)} control files missing in {directory}")
    return directory


def read_trace(path: Path, doc: dict) -> np.ndarray:
    i = doc["inputs"]
    shape = (round(i["sample_rate_hz"] * i["trace_s"]), len(i["columns_rv_ms"]))
    arrays = [
        v
        for k, v in io.loadmat(path).items()
        if not k.startswith("__") and getattr(v, "shape", None) == shape
    ]
    if len(arrays) != 1:
        raise LoomingError(f"{path.name} does not hold one {shape} trace array")
    return np.asarray(arrays[0], dtype=float)


def data_fits(directory: Path, doc: dict) -> pd.DataFrame:
    """Per control fly: the peak time before collision per r/v and the fit."""
    i, rule = doc["inputs"], doc["data_rule"]
    fs = i["sample_rate_hz"]
    flies: dict[str, list[np.ndarray]] = {}
    for name, digest in sorted(i["control_md5"].items()):
        path = directory / name
        if not path.is_file():
            raise LoomingError(f"{name} is missing")
        if md5(path) != digest:
            raise LoomingError(f"{name} does not match its locked md5")
        flies.setdefault(name.rsplit("_trial", 1)[0], []).append(read_trace(path, doc))
    rows = []
    for fly, traces in sorted(flies.items()):
        if len(traces) != 2:
            raise LoomingError(f"{fly} does not have its two trials")
        mean = np.mean(traces, axis=0)
        t = (np.arange(mean.shape[0]) / fs - i["onset_s"]) * 1000.0  # ms from onset
        ys, edges, near = [], 0, 0
        for col, rv in enumerate(i["columns_rv_ms"]):
            stim = expansion(rv, doc, 1000.0 / fs)
            length = stim["end"] - stim["onset"]
            x = smooth(mean[:, col], stim, 1000.0 / fs)
            base = float(x[(t >= -rule["baseline_s"] * 1000.0) & (t < 0)].mean())
            window = (t > 0) & (t <= length + doc["model"]["post_ms"])
            when, _, at_edge = peak_time(x, t, window, base)
            edges += at_edge
            near += length <= when <= length + NEAR_END_MS
            ys.append(stim["collision"] - stim["onset"] - when)
        alpha, delta = fit(np.asarray(i["columns_rv_ms"]), np.asarray(ys))
        rows.append(
            {
                "fly": fly,
                "alpha": alpha,
                "delta_ms": delta,
                "edge_peaks": edges,
                "near_end": near,
                **{
                    f"y_{rv:g}": y for rv, y in zip(i["columns_rv_ms"], ys, strict=True)
                },
            }
        )
    return pd.DataFrame(rows)


def interval(values: np.ndarray, doc: dict) -> tuple[float, float]:
    rule = doc["data_rule"]
    rng = np.random.default_rng(rule["bootstrap_seed"])
    v = np.asarray(values, float)
    boot = np.median(rng.choice(v, (rule["bootstrap"], v.size)), axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(lo), float(hi)


def judge(fits: pd.DataFrame, flies: pd.DataFrame, doc: dict) -> dict:
    lo, hi = interval(flies["alpha"].to_numpy(), doc)
    d_lo, d_hi = interval(flies["delta_ms"].to_numpy(), doc)
    locked = stimulus_locked(doc)
    band_lo, band_hi = locked["band"]
    out = {
        "alpha_interval": [lo, hi],
        "theta_thr_interval_deg": [threshold_deg(hi), threshold_deg(lo)],
        "delta_interval_ms": [d_lo, d_hi],
        "stimulus_locked": locked,
        "flies": len(flies),
        "fly_edge_peaks": int(flies.edge_peaks.sum()),
        "fly_near_end_peaks": int(flies.near_end.sum()),
    }
    hits = [
        name
        for name, overlaps in (
            ("followers", lo <= band_hi and band_lo <= hi),
            ("onset", lo <= locked["onset"] <= hi),
        )
        if overlaps
    ]
    if hits:
        out["verdict"] = (
            "uninformative: the flies' slope does not separate the circuit from a "
            f"stimulus-locked peak ({' and '.join(hits)})"
        )
        return out
    live = fits[fits.scored]
    if live.empty:
        out["verdict"] = "uninformative: no scored cell"
        return out
    inside = int(((live.alpha >= lo) & (live.alpha <= hi)).sum())
    out["inside"] = f"{inside} of {len(live)} scored cells"
    # the part of a cell's slope that is the circuit's: its distance from the band
    out["cell_distance_from_band"] = [
        float(max(band_lo - a, a - band_hi, 0.0)) for a in live.alpha
    ]
    out["verdict"] = "pass" if inside == len(live) else "partial" if inside else "fail"
    return out


def evaluate(rows: pd.DataFrame, data_dir: Path, doc: dict) -> dict:
    """The no-go on the model alone; only if it passes are the data files opened."""
    fits = model_fits(rows, doc)
    informative, note = no_go(fits, doc)
    out = {"model": fits, "no_go": note, "verdict": "uninformative: no-go"}
    if not informative:
        return out
    flies = data_fits(inputs_present(data_dir, doc), doc)
    out.update(judge(fits, flies, doc))
    out["flies_table"] = flies
    return out
