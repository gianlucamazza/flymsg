"""Post-verdict exploratory paths for DN-arena v2 (docs/result/dn-arena.md); not scored.

Usage: uv run python scripts/dn_arena_v2_paths.py DATA_DIR OUT_DIR

Anatomical expectation only, with no simulation. A linear signed walk ignores
thresholds, graded dynamics and delays. setup.W is the matrix from sim.network
via sim.weight_matrix: scipy CSC, rows postsynaptic, columns presynaptic, so
one hop is v = W @ v. Starting from an indicator on the left-eye or right-eye
input photoreceptors, each hop is divided by its L1 norm; the reported value is
that normalised component (the sum over a class, which can cancel). Hops are
1..6. The shortest hop is the first at which any watched neuron is nonzero.
The two eyes are normalised separately, so a difference of yaw proxies is a
sign check, not the walk of a combined perturbation. The lock's yaw proxy is
(DNa01 L - DNa01 R) + (DNa02 L - DNa02 R), positive for a left turn. A left
sphere is expected to turn ipsilateral (positive): kicks are gain * (1 -
coverage), so the sphere drives the right eye harder, and the sign check is yaw
of the right-eye walk minus yaw of the left-eye walk.
"""

import json
import sys
from pathlib import Path

import numpy as np

from flymsg import data, dn_arena

DECODERS = (
    "DNa01 L",
    "DNa01 R",
    "DNa02 L",
    "DNa02 R",
    "oDN1 L",
    "oDN1 R",
)


def _names(setup) -> dict[str, tuple[int, int]]:
    info = dn_arena.neurons(setup.doc)
    named = {}
    pairs = zip(setup.traced_ids, setup.traced_rows, strict=True)
    for body, row in pairs:
        kind, side = info[int(body)]
        named[f"{kind} {side}"] = (int(body), int(row))
    if set(named) != set(DECODERS):
        raise SystemExit("decoder neurons are not the six lock names")
    return named


def _eyes(setup) -> tuple[np.ndarray, np.ndarray]:
    side = np.asarray(setup.sides, dtype=str)[setup.column_of_input]
    rows = np.asarray(setup.input_rows, dtype=np.int64)
    return rows[side == "L"], rows[side == "R"]


def _aggregates(setup) -> dict[str, np.ndarray]:
    types = setup.neurons["type"].fillna("").astype(str)
    return {
        "LC / LPLC": np.flatnonzero(types.str.startswith(("LC", "LPLC")).to_numpy()),
        "DN*": np.flatnonzero(types.str.startswith(("DN",)).to_numpy()),
    }


def _walk(W, seed, watch: dict[str, np.ndarray]):
    """Per hop, the L1-normalised signed mass, and the first hop that reaches anyone."""
    v = np.zeros(W.shape[0], dtype=np.float64)
    v[np.asarray(seed, dtype=np.int64)] = 1.0
    hops: list[dict[str, float]] = []
    reached = dict.fromkeys(watch)
    for hop in range(1, 7):
        v = np.asarray(W @ v, dtype=np.float64).ravel()
        scale = float(np.abs(v).sum())
        if scale > 0.0:
            v /= scale
        row = {}
        for name, idx in watch.items():
            piece = v[idx]
            row[name] = float(piece.sum()) + 0.0
            if reached[name] is None and bool(np.any(piece != 0.0)):
                reached[name] = hop
        hops.append(row)
    return hops, reached


def _columns(left, right, reached_l, reached_r, name: str) -> dict:
    lv = [hop[name] for hop in left]
    rv = [hop[name] for hop in right]
    diff = [float(a - b) + 0.0 for a, b in zip(lv, rv, strict=True)]
    return {
        "left": lv,
        "right": rv,
        "left_minus_right": diff,
        "shortest_hop": {"left": reached_l[name], "right": reached_r[name]},
    }


def _yaw(hop: dict[str, float]) -> float:
    dna01 = hop["DNa01 L"] - hop["DNa01 R"]
    dna02 = hop["DNa02 L"] - hop["DNa02 R"]
    return float(dna01 + dna02) + 0.0


def _sign_check(left, right) -> dict:
    hops = []
    for i, (lh, rh) in enumerate(zip(left, right, strict=True), 1):
        yl, yr = _yaw(lh), _yaw(rh)
        proxy = float(yr - yl) + 0.0
        if proxy == 0.0:
            match = None
        else:
            match = proxy > 0.0
        hops.append(
            {
                "hop": i,
                "left": yl,
                "right": yr,
                "right_minus_left": proxy,
                "matches_ipsilateral": match,
            }
        )
    return {
        "rule": "(DNa01 L - DNa01 R) + (DNa02 L - DNa02 R)",
        "positive": "left turn",
        "expected_for_left_sphere": "positive (ipsilateral)",
        "compared": "right_minus_left; left sphere darkens the left eye",
        "hops": hops,
    }


def main(data_dir: Path, out: Path) -> dict:
    doc = dn_arena.assert_matches_code()
    neurons, edges = data.load(data_dir)
    setup = dn_arena.build(doc, neurons, edges, data_dir, out, "exploratory")
    named = _names(setup)
    groups = _aggregates(setup)
    watch: dict[str, np.ndarray] = {}
    for name in DECODERS:
        watch[name] = np.asarray([named[name][1]], dtype=np.int64)
    watch.update(groups)
    left_rows, right_rows = _eyes(setup)
    if left_rows.size == 0 or right_rows.size == 0:
        raise SystemExit("an eye has no input photoreceptors")
    left, reach_l = _walk(setup.W, left_rows, watch)
    right, reach_r = _walk(setup.W, right_rows, watch)
    decoders = {}
    for name in DECODERS:
        body, _row = named[name]
        decoders[name] = {
            "bodyId": body,
            **_columns(left, right, reach_l, reach_r, name),
        }
    classes = {}
    for name, idx in groups.items():
        classes[name] = {
            "neurons": int(idx.size),
            **_columns(left, right, reach_l, reach_r, name),
        }
    return {
        "hops": "1..6",
        "weight_matrix": "rows=post, cols=pre (sim.weight_matrix); v = W @ v / L1",
        "decoders": decoders,
        "classes": classes,
        "yaw_proxy": _sign_check(left, right),
    }


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2])), indent=1))
