"""T4/T5 direction selectivity through the eye (issue #84). The YAML file is the lock.

Moving ON and OFF edges are drawn on each eye's measured column directions
(`eye.edge_coverage`), turned into graded photoreceptor input (`eye.photoreceptor_kicks`),
and the spikes of each T4/T5 subtype are summed per direction and polarity. Nothing is
tuned; the default model is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data, eye, locks, prereg, sim

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "validation" / "t4t5.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
VERSION_HASHES = {
    1: "bf56cc800341402e0c520ad3e320d8a490e25542abcad108336bc4501def2cd8",  # ON/OFF edges, 4 directions, 30 deg/s, acceptance 8.23 deg, seeds 90-92
}
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
    if p["gain"] != 100.0 * sim.Params.dt / 1000.0:
        raise T4T5Error("the gain is not the protocols' mean Poisson input")
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
        f"deg, gain {p['gain']:g}; seeds {', '.join(map(str, p['seeds']))}"
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
    """Photoreceptors in the window and their graded input per step."""
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
    kicks = eye.photoreceptor_kicks(1.0 - lit, rec_cols, proto["gain"])
    return rec["neuron"].to_numpy(), kicks.astype(np.float32), steps


def preferred_angle(responses: dict) -> float:
    """Direction of the vector sum of responses over the four directions, in degrees."""
    x = sum(r * np.cos(np.radians(ANGLE[d])) for d, r in responses.items())
    y = sum(r * np.sin(np.radians(ANGLE[d])) for d, r in responses.items())
    return float(np.degrees(np.arctan2(y, x)) % 360.0) if (x or y) else float("nan")


def angle_error(a: float, b: float) -> float:
    return float(abs((a - b + 180.0) % 360.0 - 180.0))


def decide(table: pd.DataFrame, preferred: dict) -> dict:
    """`table` has subtype, direction, polarity, spikes. Returns the verdict and per-subtype
    metrics."""
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
    dir_pass = direction_ok >= 6
    verdict = {
        (True, True): "both",
        (True, False): "polarity only",
        (False, True): "direction only",
        (False, False): "neither",
    }[(pol_pass, dir_pass)]
    return {"metrics": pd.DataFrame(rows), "verdict": verdict}


def protocol(W, neurons: pd.DataFrame, cols, receptors, doc: dict) -> dict:
    proto = doc["protocol"]
    p = sim.Params()
    win = window(cols, proto["window_deg"])
    types = neurons["type"].to_numpy()
    groups = {s: np.flatnonzero(types == s) for s in proto["subtypes"]}
    rows = []
    for direction in proto["directions"]:
        for polarity in proto["polarities"]:
            stim, kicks, steps = drive(win, receptors, proto, direction, polarity, p.dt)
            for seed in proto["seeds"]:
                r = sim.run(
                    W, stim, duration_ms=steps * p.dt, p=p, seed=seed, kicks=kicks
                )
                total = r.counts.sum(axis=0)
                for sub, idx in groups.items():
                    rows.append(
                        {
                            "subtype": sub,
                            "direction": direction,
                            "polarity": polarity,
                            "seed": seed,
                            "spikes": int(total[idx].sum()),
                        }
                    )
    table = pd.DataFrame(rows)
    out = decide(table, proto["preferred"])
    out["table"] = table
    out["window_columns"] = len(win)
    return out


def run(neurons: pd.DataFrame, edges: pd.DataFrame, data_dir: Path) -> dict:
    doc = assert_matches_code()
    eye.fetch(data_dir)
    ann = pd.read_feather(
        data_dir / "raw" / data.RAW["annotations"],
        columns=["bodyId", "type", "instance", "assignedOlHex1", "assignedOlHex2"],
    )
    cols = eye.columns(ann, eye.lenses(data_dir))
    receptors = eye.photoreceptors(neurons, edges, ann)
    return protocol(
        sim.network(neurons, edges, sim.Params()), neurons, cols, receptors, doc
    )
