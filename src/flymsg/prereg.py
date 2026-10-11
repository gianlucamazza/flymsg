"""Versioned pre-registration: hypotheses, metrics, thresholds and null comparisons.

`validation/preregistration.yaml` is the lock file. A confirmatory run whose config
differs from it fails unless the file version is bumped and VERSION_HASHES is updated.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from flymsg import sim, validate, wiring

ROOT = Path(__file__).resolve().parents[2]
PREREG_PATH = ROOT / "validation" / "preregistration.yaml"

# sha256 of the canonical JSON of every field except version and content_sha256.
# A change to the locked fields without a new version fails the test suite.
VERSION_HASHES = {
    1: "fe54f4512b024a37d3c8602c1fe9944f89f500675c1bbc01aa456bda657cafa8",
}

SKIP_HASH_KEYS = frozenset({"version", "content_sha256"})


class PreregistrationError(ValueError):
    """A confirmatory run or the live code drifted from the locked file."""


def _parse_scalar(text: str):
    text = text.strip()
    if text in ("true", "True"):
        return True
    if text in ("false", "False"):
        return False
    if text in ("null", "None", "~"):
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in _split_top(inner, ",")]
    try:
        if any(ch in text for ch in ".eE"):
            return float(text)
        return int(text)
    except ValueError:
        return text


def _split_top(text: str, sep: str) -> list[str]:
    parts, buf, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch in "[":
            depth += 1
        elif ch in "]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf or parts:
        parts.append("".join(buf))
    return parts


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def load_yaml(text: str) -> dict:
    """Load the restricted YAML subset used by the preregistration file."""
    lines = []
    for raw in text.splitlines():
        cut = raw.split(" #", 1)[0].rstrip()
        if not cut.strip() or cut.lstrip().startswith("#"):
            continue
        lines.append(cut)

    def parse_block(index: int, indent: int):
        mapping, sequence = {}, []
        kind = None
        while index < len(lines):
            line = lines[index]
            level = _indent(line)
            if level < indent:
                break
            if level > indent:
                raise PreregistrationError(f"unexpected indent: {line!r}")
            body = line[level:]
            if body.startswith("- "):
                if kind == "map":
                    raise PreregistrationError("mixed map and list")
                kind = "list"
                item = body[2:].strip()
                index += 1
                if item and ":" in item and not item.startswith("["):
                    key, _, rest = item.partition(":")
                    nested, index = parse_block(index, indent + 2)
                    nested = {key.strip(): _parse_scalar(rest), **nested}
                    sequence.append(nested)
                elif item:
                    sequence.append(_parse_scalar(item))
                else:
                    value, index = parse_block(index, indent + 2)
                    sequence.append(value)
                continue
            if kind == "list":
                break
            kind = "map"
            key, _, rest = body.partition(":")
            rest = rest.strip()
            index += 1
            if rest:
                mapping[key] = _parse_scalar(rest)
            else:
                mapping[key], index = parse_block(index, indent + 2)
        if kind == "list":
            return sequence, index
        return mapping, index

    doc, end = parse_block(0, 0)
    if end != len(lines):
        raise PreregistrationError("unparsed preregistration lines")
    if not isinstance(doc, dict):
        raise PreregistrationError("preregistration root must be a mapping")
    return doc


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_payload(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in SKIP_HASH_KEYS}


def content_hash(doc: dict) -> str:
    return hashlib.sha256(canonical(content_payload(doc)).encode()).hexdigest()


def load(path: Path = PREREG_PATH) -> dict:
    return load_yaml(path.read_text(encoding="utf-8"))


def live_fields() -> dict:
    """The locked values as they stand in the running code."""
    return {
        "criterion": {
            "name": "v4",
            "min_spikes": validate.MIN_SPIKES,
            "min_seed_share_num": 2,
            "min_seed_share_den": 3,
            "specificity": float(validate.SPECIFICITY),
            "margin_hz": float(validate.MARGIN_HZ),
            "max_persistent": validate.MAX_PERSISTENT,
            "rate_hz": float(validate.RATE_HZ),
            "stim_ms": float(validate.STIM_MS),
            "duration_ms": float(validate.DURATION_MS),
            "dose_rates_hz": [float(r) for r in validate.DOSE_RATES_HZ],
            "control_min_weight": 5,
            "shiu_w_syn": float(sim.SHIU_W_SYN),
            "density_divisor": 1.43,
            "th_jump": float(sim.Params.th_jump),
            "seeds": 3,
            "seed0": 0,
            "control_seed": 0,
        },
        "n1": {
            "family": "degree_preserving",
            "shuffle_seed": wiring.SHUFFLE_SEED,
            "seeds": wiring.N1_SEEDS,
            "metric": "criterion_v4_specific",
        },
        "pathways": [
            {"case": c.name, "target": t, "kind": "specific", "tail": "upper"}
            for c in validate.CASES
            for t in c.targets
        ]
        + [
            {
                "case": name,
                "target": target,
                "kind": "negative",
                "tail": "lower",
            }
            for name, _, target, _ in validate.NEGATIVES
        ],
        "null_family_ids": [
            "degree_preserving",
            "cell_type_preserving",
            "weight_within_type",
            "sign",
        ],
        "w_syn": float(sim.Params.w_syn),
        "min_seed_share": validate.MIN_SEED_SHARE,
        "dose_tol_hz": validate.DOSE_TOL_HZ,
    }


def _neq(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) > 1e-12
    return a != b


def mismatches(doc: dict | None = None) -> list[str]:
    """Human-readable ways the live code disagrees with the lock file."""
    doc = doc if doc is not None else load()
    live = live_fields()
    found = []
    crit, live_c = doc["criterion"], live["criterion"]
    for key, want in live_c.items():
        got = crit.get(key)
        if _neq(got, want):
            found.append(f"criterion.{key}: file={got!r} code={want!r}")
    if abs(live["w_syn"] - crit["shiu_w_syn"] / crit["density_divisor"]) > 1e-12:
        found.append(
            f"w_syn: code={live['w_syn']!r} "
            f"file={crit['shiu_w_syn']!r}/{crit['density_divisor']!r}"
        )
    if _neq(
        live["min_seed_share"], crit["min_seed_share_num"] / crit["min_seed_share_den"]
    ):
        found.append("min_seed_share does not match min_seed_share_num/den")
    if _neq(live["dose_tol_hz"], 1000.0 / crit["stim_ms"]):
        found.append("dose_tol_hz does not match 1000/stim_ms")
    n1 = {k: doc["n1"][k] for k in ("family", "shuffle_seed", "seeds", "metric")}
    for key, want in live["n1"].items():
        if n1.get(key) != want:
            found.append(f"n1.{key}: file={n1.get(key)!r} code={want!r}")
    file_paths = [
        {k: row[k] for k in ("case", "target", "kind", "tail")}
        for row in doc["pathways"]
    ]
    if file_paths != live["pathways"]:
        found.append("pathways do not match validate.CASES / NEGATIVES")
    ids = [row["id"] for row in doc["nulls"]["families"]]
    if ids != live["null_family_ids"]:
        found.append(f"null families: file={ids} code={live['null_family_ids']}")
    return found


def assert_file_matches_code(doc: dict | None = None) -> dict:
    doc = doc if doc is not None else load()
    found = mismatches(doc)
    if found:
        raise PreregistrationError(
            "live code drifted from validation/preregistration.yaml; "
            "bump version and update the file: " + "; ".join(found)
        )
    return doc


def assert_version_locked(doc: dict | None = None) -> dict:
    """Fail if the locked fields changed without a version bump."""
    doc = doc if doc is not None else load()
    version = doc["version"]
    digest = content_hash(doc)
    if doc.get("content_sha256") != digest:
        raise PreregistrationError(
            "content_sha256 does not match the locked fields; "
            "bump version and recompute the hash"
        )
    expected = VERSION_HASHES.get(version)
    if expected is None:
        raise PreregistrationError(
            f"preregistration version {version} is not in VERSION_HASHES; "
            "add the new hash after bumping"
        )
    if expected != digest:
        raise PreregistrationError(
            f"preregistration version {version} changed without a bump "
            f"(file {digest}, lock {expected})"
        )
    return doc


def run_config(
    w_syn: float,
    th_jump: float,
    seeds: int | None = None,
    seed0: int = 0,
    control_seed: int = 0,
    draws: int | None = None,
) -> dict:
    return {
        "w_syn": float(w_syn),
        "th_jump": float(th_jump),
        "seeds": seeds,
        "seed0": seed0,
        "control_seed": control_seed,
        "draws": draws,
    }


def assert_run_matches(config: dict, *, exploratory: bool = False) -> dict:
    """Fail if a confirmatory run's config is not the locked one.

    `exploratory=True` skips the check (calibrate, ad-hoc `--w-syn`, …).
    """
    doc = assert_file_matches_code()
    assert_version_locked(doc)
    if exploratory:
        return doc
    crit = doc["criterion"]
    want_w = crit["shiu_w_syn"] / crit["density_divisor"]
    diffs = []
    if abs(config["w_syn"] - want_w) > 1e-12:
        diffs.append(f"w_syn {config['w_syn']} != {want_w}")
    if abs(config["th_jump"] - crit["th_jump"]) > 1e-12:
        diffs.append(f"th_jump {config['th_jump']} != {crit['th_jump']}")
    if config.get("seed0", 0) != crit["seed0"]:
        diffs.append(f"seed0 {config.get('seed0')} != {crit['seed0']}")
    if config.get("control_seed", 0) != crit["control_seed"]:
        diffs.append(
            f"control_seed {config.get('control_seed')} != {crit['control_seed']}"
        )
    seeds = config.get("seeds")
    if seeds is not None and seeds != crit["seeds"]:
        diffs.append(f"seeds {seeds} != {crit['seeds']}")
    draws = config.get("draws")
    if draws is not None and draws not in (
        doc["nulls"]["draws_ci"],
        doc["nulls"]["draws_full"],
    ):
        diffs.append(
            f"draws {draws} is not the CI ({doc['nulls']['draws_ci']}) "
            f"or full ({doc['nulls']['draws_full']}) count"
        )
    if diffs:
        raise PreregistrationError(
            "run config differs from preregistration v"
            f"{doc['version']} without a version bump: " + "; ".join(diffs)
        )
    return doc
