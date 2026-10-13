"""T4/T5 direction selectivity through the eye (issues #84, #97). The YAML file is the lock.

Moving ON and OFF edges are drawn on each eye's measured column directions
(`eye.edge_coverage`), turned into graded photoreceptor input (`eye.photoreceptor_kicks`),
and the spikes of each T4/T5 subtype are summed per direction and polarity. Version 2 makes
photoreceptors and L1-L3 graded (`sim.Graded`) and runs every configuration of the locked
envelope of release parameters; nothing is tuned and the default model is unchanged.
Version 3 (issue #140) also makes T4's medulla inputs graded over the voltages Groschner et al.
2022 measured (`flymsg.medulla`), scans their release rate and decides on T4 only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

from flymsg import data, eye, locks, medulla, prereg, progress, sim

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "t4t5.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "bf56cc800341402e0c520ad3e320d8a490e25542abcad108336bc4501def2cd8",  # ON/OFF edges, 4 directions, 30 deg/s, acceptance 8.23 deg, seeds 90-92
    2: "d25bcbd7ecd6e01f383c00703995164d29cc57fc11192be15234b19314b0e390",  # graded photoreceptors and L1-L3, 17-configuration envelope, settle 200 ms, seed 93
    3: "e7a3bf42657983d910547530b9123a75bf60e13b663ce666d03bcaff15271793",  # T4's medulla inputs graded over Groschner et al.'s voltages, 25 configurations, seed 94
}
SPENT_SEEDS = (90, 91, 92, 93)
# measured Drosophila ranges and their midpoints (Juusola et al. 2016), and the unmeasured
# LMC release rate scanned in doublings around the 100 Hz protocol input
PHOTORECEPTOR_MV = (40.0, 52.5, 65.0)
LMC_MV = (20.0, 32.5, 45.0)
LMC_RATE_HZ = (25.0, 50.0, 100.0, 200.0, 400.0)
MEDULLA_RATE_HZ = LMC_RATE_HZ
PATHWAY = ("Mi1", "Tm3", "Mi4", "Mi9", "Tm1", "Tm2", "Tm4", "Tm9")
ANGLE = {
    "front_to_back": 0.0,
    "upward": 90.0,
    "back_to_front": 180.0,
    "downward": 270.0,
}


class T4T5Error(ValueError):
    """The T4/T5 protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def content_hash(doc: dict) -> str:
    return prereg.content_hash(doc)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    locks.check(doc, VERSION_HASHES, T4T5Error, "T4/T5 protocol")
    return doc


def assert_matches_code(doc: dict | None = None) -> dict:
    doc = assert_locked() if doc is None else doc
    p = doc["protocol"]
    if p["acceptance_deg"] != 8.23 or p["speed_deg_s"] != 30.0:
        raise T4T5Error("optics or speed are not the sourced values")
    if set(p["directions"]) != set(ANGLE) or p["polarities"] != ["on", "off"]:
        raise T4T5Error("the stimulus set changed")
    env = p["envelope"]
    if (
        tuple(env["photoreceptor_response_mv"]) != PHOTORECEPTOR_MV
        or tuple(env["lmc_hyperpolarisation_mv"]) != LMC_MV
        or tuple(env["lmc_rate_hz"]) != LMC_RATE_HZ
    ):
        raise T4T5Error("the envelope is not the sourced ranges")
    if p["graded_lmc"] != ["L1", "L2", "L3"] or p["settle_ms"] != 200.0:
        raise T4T5Error("the graded types or the settle period changed")
    if "graded_medulla" in p:
        if p["graded_medulla"] != list(medulla.FILES) or list(p["medulla_mv"]) != list(
            medulla.FILES
        ):
            raise T4T5Error("the graded medulla types are not the measured ones")
        if doc["decides"].get("subtypes") != ["T4a", "T4b", "T4c", "T4d"]:
            raise T4T5Error("version 3 decides on the T4 subtypes")
        if tuple(env["medulla_rate_hz"]) != MEDULLA_RATE_HZ:
            raise T4T5Error("the medulla rate scan changed")
        for name, r in p["medulla_mv"].items():
            if not r["lowest"] <= r["dark"] <= r["highest"]:
                raise T4T5Error(f"{name}: the dark potential is outside its range")
    if p["seed"] in SPENT_SEEDS:
        raise T4T5Error("the seed was spent by an earlier version")
    for name, row in doc["reported"].items():
        if row["decides"] is not False:
            raise T4T5Error(f"reported row {name} must not decide")
    if doc["defaults_changed"] is not False:
        raise T4T5Error("the test never changes the defaults")
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    p = doc["protocol"]
    return (
        f"t4t5 v{doc['version']} (issue #{doc['issue']}): ON/OFF edges, 4 directions, "
        f"{p['speed_deg_s']:g} deg/s over {p['travel_deg']:g} deg within "
        f"{p['window_deg']:g} deg of each eye's centre, acceptance {p['acceptance_deg']:g} "
        f"deg; graded photoreceptors and {'/'.join(p['graded_lmc'])}"
        + (
            f", graded {'/'.join(p['graded_medulla'])} over measured voltages"
            if "graded_medulla" in p
            else ""
        )
        + f", {len(configurations(doc))} release configurations; seed {p['seed']}"
        + (
            f"; decides on {'/'.join(doc['decides']['subtypes'])}"
            if "subtypes" in doc["decides"]
            else ""
        )
    )


def configurations(doc: dict) -> list[dict]:
    """The locked grid. Version 2: every LMC range x rate at the middle photoreceptor range,
    plus the two outer photoreceptor ranges at the middle LMC range and 100 Hz. Version 3:
    every LMC rate x medulla rate at the middle photoreceptor and LMC ranges."""
    mid_r, mid_l = PHOTORECEPTOR_MV[1], LMC_MV[1]
    if "graded_medulla" in doc["protocol"]:
        grid = [
            {
                "photoreceptor_mv": mid_r,
                "lmc_mv": mid_l,
                "lmc_rate_hz": r,
                "medulla_rate_hz": m,
            }
            for r in LMC_RATE_HZ
            for m in MEDULLA_RATE_HZ
        ]
        return [{"config": i, **c} for i, c in enumerate(grid)]
    grid = [
        {"photoreceptor_mv": mid_r, "lmc_mv": h, "lmc_rate_hz": r}
        for h in LMC_MV
        for r in LMC_RATE_HZ
    ]
    grid += [
        {"photoreceptor_mv": a, "lmc_mv": mid_l, "lmc_rate_hz": 100.0}
        for a in (PHOTORECEPTOR_MV[0], PHOTORECEPTOR_MV[2])
    ]
    return [{"config": i, **c} for i, c in enumerate(grid)]


def steady_gain(p: sim.Params) -> float:
    """Steady-state potential change (mV) per unit of conductance delivered every step:
    g = c / (1 - es), v - v_rest = g * gv / (1 - em)."""
    em, es = np.exp(-p.dt / p.tau_m), np.exp(-p.dt / p.tau_syn)
    gv = p.tau_syn / (p.tau_syn - p.tau_m) * (es - em)
    return float(gv / ((1.0 - es) * (1.0 - em)))


def photoreceptor_gain(response_mv: float, p: sim.Params) -> float:
    """Kicks per step at full light that hold a photoreceptor `response_mv` above rest."""
    return response_mv * (1.0 - np.exp(-p.dt / p.tau_m)) / (p.poisson_scale * p.w_syn)


def photoreceptor_rate(
    W: sparse.csc_matrix,
    lit: np.ndarray,
    lmc: np.ndarray,
    hyper_mv: float,
    p: sim.Params,
) -> tuple[float, np.ndarray]:
    """Saturated photoreceptor release rate (Hz) at which full light on `lit` lowers the
    median LMC receiving their synapses by `hyper_mv` at steady state, photoreceptor input
    only. Also returns those LMCs."""
    total = np.asarray(W[:, lit].sum(axis=1)).ravel()[lmc]
    receiving = lmc[total < 0]
    if receiving.size == 0:
        raise T4T5Error("no LMC receives synapses from the lit photoreceptors")
    per_step = hyper_mv / (steady_gain(p) * float(np.median(-total[total < 0])))
    return per_step * 1000.0 / p.dt, receiving


def graded_spec(
    receptors_all: np.ndarray,
    lmc: np.ndarray,
    cfg: dict,
    rate_r: float,
    p: sim.Params,
    medulla_cells: dict | None = None,
    medulla_mv: dict | None = None,
) -> sim.Graded:
    """Photoreceptors: no release at rest, saturated `photoreceptor_mv` above. LMCs: half
    release at rest, none `lmc_mv` below, saturated `lmc_mv` above. Medulla types (version
    3): rest stands for the measured dark potential; no release at the lowest measured
    potential, saturated at the highest."""
    a, h = cfg["photoreceptor_mv"], cfg["lmc_mv"]
    nr, nl = receptors_all.size, lmc.size
    idx = [receptors_all, lmc]
    v_lo = [np.full(nr, p.v_rest), np.full(nl, p.v_rest - h)]
    span = [np.full(nr, a), np.full(nl, 2.0 * h)]
    rate = [np.full(nr, rate_r), np.full(nl, cfg["lmc_rate_hz"])]
    for name, cells in (medulla_cells or {}).items():
        r = medulla_mv[name]
        idx.append(cells)
        v_lo.append(np.full(cells.size, p.v_rest - (r["dark"] - r["lowest"])))
        span.append(np.full(cells.size, r["highest"] - r["lowest"]))
        rate.append(np.full(cells.size, cfg["medulla_rate_hz"]))
    return sim.Graded(
        idx=np.concatenate(idx),
        v_lo=np.concatenate(v_lo),
        span=np.concatenate(span),
        rate_hz=np.concatenate(rate),
    )


def window(cols: pd.DataFrame, radius_deg: float) -> pd.DataFrame:
    """Columns within `radius_deg` of their eye's median viewing direction."""
    keep = []
    for side in ("L", "R"):
        c = cols[(cols["side"] == side) & cols["azimuth_deg"].notna()]
        d = eye.angular_distance_deg(
            c["azimuth_deg"],
            c["elevation_deg"],
            c["azimuth_deg"].median(),
            c["elevation_deg"].median(),
        )
        keep.append(c[d <= radius_deg])
    return pd.concat(keep).reset_index(drop=True)


def light(coverage: np.ndarray, polarity: str) -> np.ndarray:
    """Light per column: an OFF edge darkens what it has crossed, an ON edge lights it."""
    return 1.0 - coverage if polarity == "off" else coverage


def drive(cols, receptors, proto: dict, direction: str, polarity: str, dt: float):
    """Photoreceptors in the window and their light per step, 0 to 1: the edge's first
    frame held for `settle_ms`, then the motion. Returns neurons, light, total steps and the
    first moving step."""
    settle = round(proto["settle_ms"] / dt)
    steps = round(proto["travel_deg"] / proto["speed_deg_s"] * 1000.0 / dt)
    key = list(zip(cols["side"], cols["hex1"], cols["hex2"], strict=True))
    col_of = {k: i for i, k in enumerate(key)}
    rec = receptors[
        [
            k in col_of
            for k in zip(
                receptors["side"], receptors["hex1"], receptors["hex2"], strict=True
            )
        ]
    ]
    rec_cols = np.array(
        [col_of[k] for k in zip(rec["side"], rec["hex1"], rec["hex2"], strict=True)]
    )
    t_deg = np.arange(steps) * dt / 1000.0 * proto["speed_deg_s"]
    cov = np.stack(
        [eye.edge_coverage(cols, direction, x, proto["acceptance_deg"]) for x in t_deg]
    )
    lit = light(cov, polarity)
    lit = np.concatenate([np.repeat(lit[:1], settle, axis=0), lit])
    light_per_receptor = eye.photoreceptor_kicks(1.0 - lit, rec_cols, 1.0)
    return (
        rec["neuron"].to_numpy(),
        light_per_receptor.astype(np.float32),
        settle + steps,
        settle,
    )


def preferred_angle(responses: dict) -> float:
    """Direction of the vector sum of responses over the four directions, in degrees."""
    x = sum(r * np.cos(np.radians(ANGLE[d])) for d, r in responses.items())
    y = sum(r * np.sin(np.radians(ANGLE[d])) for d, r in responses.items())
    return float(np.degrees(np.arctan2(y, x)) % 360.0) if (x or y) else float("nan")


def angle_error(a: float, b: float) -> float:
    return float(abs((a - b + 180.0) % 360.0 - 180.0))


def decide(
    table: pd.DataFrame,
    preferred: dict,
    subtypes: list[str] | None = None,
    direction_min: int = 6,
) -> dict:
    """`table` has subtype, direction, polarity, spikes. Returns the verdict over `subtypes`
    (default: all in the table) and per-subtype metrics."""
    if subtypes is not None:
        table = table[table["subtype"].isin(subtypes)]
    rows, polarity_ok, direction_ok = [], 0, 0
    for sub in sorted(table["subtype"].unique()):
        t = table[table["subtype"] == sub]
        pref_pol = "on" if sub.startswith("T4") else "off"
        other = "off" if pref_pol == "on" else "on"
        on_pref = t.loc[t["polarity"] == pref_pol, "spikes"].sum()
        on_other = t.loc[t["polarity"] == other, "spikes"].sum()
        resp = (
            t[t["polarity"] == pref_pol].groupby("direction")["spikes"].sum().to_dict()
        )
        pd_dir = preferred[sub[-1]]
        nd_dir = {
            "front_to_back": "back_to_front",
            "back_to_front": "front_to_back",
            "upward": "downward",
            "downward": "upward",
        }[pd_dir]
        r_pd, r_nd = resp.get(pd_dir, 0), resp.get(nd_dir, 0)
        angle = preferred_angle(resp)
        err = angle_error(angle, ANGLE[pd_dir]) if np.isfinite(angle) else float("nan")
        pol = bool(on_pref > on_other)
        dirn = bool(np.isfinite(err) and err <= 45.0)
        polarity_ok += pol
        direction_ok += dirn
        rows.append(
            {
                "subtype": sub,
                "preferred_polarity_spikes": int(on_pref),
                "other_polarity_spikes": int(on_other),
                "polarity_ok": pol,
                "vector_angle_deg": angle,
                "measured_angle_deg": ANGLE[pd_dir],
                "angle_error_deg": err,
                "direction_ok": dirn,
                "dsi": (r_pd - r_nd) / (r_pd + r_nd) if (r_pd + r_nd) else float("nan"),
            }
        )
    pol_pass = polarity_ok == len(rows)
    dir_pass = direction_ok >= direction_min
    verdict = {
        (True, True): "both",
        (True, False): "polarity only",
        (False, True): "direction only",
        (False, False): "neither",
    }[(pol_pass, dir_pass)]
    return {"metrics": pd.DataFrame(rows), "verdict": verdict}


def protocol(
    W,
    neurons: pd.DataFrame,
    cols,
    receptors,
    doc: dict,
    steps: progress.Steps | None = None,
    report: progress.Progress | None = None,
) -> dict:
    """Every configuration of the envelope; `steps` stores each finished configuration so
    an interrupted run resumes, `report` counts simulations."""
    proto = doc["protocol"]
    p = sim.Params()
    steps = steps or progress.Steps(None, doc["content_sha256"])
    win = window(cols, proto["window_deg"])
    types = neurons["type"].fillna("").to_numpy()
    pattern = "|".join(f"(?:{x})" for x in eye.RECEPTORS.values())
    receptors_all = np.flatnonzero(
        neurons["type"].fillna("").str.contains(pattern).to_numpy()
    )
    lmc = np.flatnonzero(np.isin(types, proto["graded_lmc"]))
    medulla_cells = {
        t: np.flatnonzero(types == t) for t in proto.get("graded_medulla", [])
    }
    groups = {s: np.flatnonzero(types == s) for s in proto["subtypes"]}
    path_groups = {t: np.flatnonzero(types == t) for t in PATHWAY}
    stimuli = {
        (direction, polarity): drive(win, receptors, proto, direction, polarity, p.dt)
        for direction in proto["directions"]
        for polarity in proto["polarities"]
    }
    lit_neurons = np.unique(np.concatenate([v[0] for v in stimuli.values()]))

    def configuration(cfg: dict) -> dict[str, pd.DataFrame]:
        rate_r, receiving = photoreceptor_rate(W, lit_neurons, lmc, cfg["lmc_mv"], p)
        graded = graded_spec(
            receptors_all, lmc, cfg, rate_r, p, medulla_cells, proto.get("medulla_mv")
        )
        order = np.sort(graded.idx)
        watch = np.searchsorted(order, receiving)
        watch_medulla = {t: np.searchsorted(order, c) for t, c in medulla_cells.items()}
        medulla_rows = []
        gain = photoreceptor_gain(cfg["photoreceptor_mv"], p)
        spikes, path_rows, lmc_rows = [], [], []
        for (direction, polarity), (stim, lit, n_steps, settle) in stimuli.items():
            r = sim.run(
                W,
                stim,
                duration_ms=n_steps * p.dt,
                p=p,
                seed=proto["seed"],
                kicks=(gain * lit).astype(np.float32),
                graded=graded,
            )
            first_bin = round(settle * p.dt / r.bin_ms)
            total = r.counts[first_bin:].sum(axis=0)
            key = {
                "config": cfg["config"],
                "direction": direction,
                "polarity": polarity,
            }
            for sub, idx in groups.items():
                spikes.append({**key, "subtype": sub, "spikes": int(total[idx].sum())})
            path_rows.append(
                {**key, **{t: int(total[i].sum()) for t, i in path_groups.items()}}
            )
            v = r.graded_v[:, watch] - p.v_rest
            moving = np.median(v[first_bin:], axis=1)
            lmc_rows.append(
                {
                    **key,
                    "settled_mv": float(np.median(v[first_bin - 1])),
                    "lowest_mv": float(moving.min()),
                    "highest_mv": float(moving.max()),
                }
            )
            for t, cols_t in watch_medulla.items():
                type_median = np.median(r.graded_v[:, cols_t] - p.v_rest, axis=1)
                medulla_rows.append(
                    {
                        **key,
                        "type": t,
                        "settled_mv": float(type_median[first_bin - 1]),
                        "lowest_mv": float(type_median[first_bin:].min()),
                        "highest_mv": float(type_median[first_bin:].max()),
                    }
                )
            if report is not None:
                report.step(note=f"config {cfg['config']} {direction} {polarity}")
        out = {
            "spikes": pd.DataFrame(spikes),
            "pathway": pd.DataFrame(path_rows),
            "lmc": pd.DataFrame(lmc_rows),
            "rate": pd.DataFrame([{"photoreceptor_rate_hz": rate_r}]),
        }
        if medulla_rows:
            out["medulla"] = pd.DataFrame(medulla_rows)
        return out

    rows, path_rows, lmc_rows, metrics, verdicts = [], [], [], [], []
    medulla_rows, t5_rows = [], []
    dec = doc["decides"]
    decided = dec.get("subtypes")
    direction_min = 3 if decided else 6
    for cfg in configurations(doc):
        got, fresh = steps.get(
            f"config{cfg['config']:02d}", lambda c=cfg: configuration(c)
        )
        if not fresh and report is not None:
            report.step(
                len(stimuli), note=f"config {cfg['config']} resumed", resumed=True
            )
        out = decide(got["spikes"], proto["preferred"], decided, direction_min)
        metrics.append(out["metrics"].assign(config=cfg["config"]))
        if decided:
            t5 = sorted(set(proto["subtypes"]) - set(decided))
            t5_out = decide(got["spikes"], proto["preferred"], t5, 3)
            t5_rows.append({"config": cfg["config"], "t5_verdict": t5_out["verdict"]})
            metrics.append(t5_out["metrics"].assign(config=cfg["config"]))
        if "medulla" in got:
            medulla_rows.append(got["medulla"])
        rate_r = float(got["rate"]["photoreceptor_rate_hz"].iloc[0])
        verdicts.append(
            {**cfg, "photoreceptor_rate_hz": rate_r, "verdict": out["verdict"]}
        )
        rows.append(got["spikes"])
        path_rows.append(got["pathway"])
        lmc_rows.append(got["lmc"])
    verdict_table = pd.DataFrame(verdicts)
    return {
        "table": pd.concat(rows, ignore_index=True),
        "metrics": pd.concat(metrics, ignore_index=True),
        "pathway": pd.concat(path_rows, ignore_index=True),
        "lmc": pd.concat(lmc_rows, ignore_index=True),
        "configurations": verdict_table,
        "verdict": envelope_verdict(verdict_table["verdict"]),
        "window_columns": len(win),
        **(
            {
                "medulla": pd.concat(medulla_rows, ignore_index=True),
                "t5": pd.DataFrame(t5_rows),
            }
            if medulla_rows
            else {}
        ),
    }


def n_runs(doc: dict) -> int:
    """Simulations of the locked protocol: configurations x directions x polarities."""
    proto = doc["protocol"]
    return (
        len(configurations(doc)) * len(proto["directions"]) * len(proto["polarities"])
    )


def envelope_verdict(verdicts: pd.Series) -> str:
    """robust: <verdict> when every configuration agrees, otherwise depends with counts."""
    counts = verdicts.value_counts()
    if len(counts) == 1:
        return f"robust: {counts.index[0]}"
    return "depends: " + ", ".join(f"{v} {n}" for v, n in counts.items())


def run(
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    data_dir: Path,
    steps: progress.Steps | None = None,
    report: progress.Progress | None = None,
) -> dict:
    doc = assert_matches_code()
    if "medulla_mv" in doc["protocol"]:
        got = medulla.ranges(data_dir).set_index("type")
        for name, r in doc["protocol"]["medulla_mv"].items():
            row = got.loc[name]
            measured = (row["n"], row["dark_mv"], row["lowest_mv"], row["highest_mv"])
            if measured != (r["n"], r["dark"], r["lowest"], r["highest"]):
                raise T4T5Error(f"{name}: the deposited traces give {measured}")
    eye.fetch(data_dir)
    ann = pd.read_feather(
        data_dir / "raw" / data.RAW["annotations"],
        columns=["bodyId", "type", "instance", "assignedOlHex1", "assignedOlHex2"],
    )
    cols = eye.columns(ann, eye.lenses(data_dir))
    receptors = eye.photoreceptors(neurons, edges, ann)
    return protocol(
        sim.network(neurons, edges, sim.Params()),
        neurons,
        cols,
        receptors,
        doc,
        steps,
        report,
    )
