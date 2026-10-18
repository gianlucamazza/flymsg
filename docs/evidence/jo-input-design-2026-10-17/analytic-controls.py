"""Independent finite mathematical counterexamples; no JO physiology or model run."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def correlation(a: list[int], b: list[int]) -> float:
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cross = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    energy_a = sum((x - ma) ** 2 for x in a)
    energy_b = sum((y - mb) ** 2 for y in b)
    return cross / math.sqrt(energy_a * energy_b)


def main() -> None:
    cases = []
    times = [k / 10000 for k in range(100)]
    waves = [[math.cos(2 * math.pi * f * t) for t in times] for f in (100, 200)]
    envelopes = [[1] * len(times), [1] * len(times)]
    assert envelopes[0] == envelopes[1]
    assert any(abs(a - b) > TOLERANCE for a, b in zip(*waves, strict=True))
    cases.append(
        {"case": "envelope_non_identifiability", "assertions": 2, "pass": True}
    )

    times = [k / 10 for k in range(10)]
    waves = [[math.cos(2 * math.pi * f * t) for t in times] for f in (101, 111)]
    alias_error = max(abs(a - b) for a, b in zip(*waves, strict=True))
    assert alias_error < TOLERANCE
    cases.append(
        {
            "case": "abstract_sampling_alias",
            "assertions": 1,
            "pass": True,
            "max_error": alias_error,
            "sample_hz": 10,
            "carrier_hz": [101, 111],
        }
    )

    peak = 2.0
    peak_to_peak = 2 * peak
    rms = peak / math.sqrt(2)
    assert peak_to_peak == 4
    assert abs(rms - math.sqrt(2)) < TOLERANCE
    assert peak_to_peak / 2 == peak and abs(rms * math.sqrt(2) - peak) < TOLERANCE
    assert peak_to_peak / peak == 2
    velocities = [peak / impedance for impedance in (2, 4)]
    assert velocities == [1, 0.5]
    cases.append(
        {
            "case": "amplitude_and_impedance",
            "assertions": 5,
            "pass": True,
            "peak": peak,
            "peak_to_peak": peak_to_peak,
            "rms": rms,
            "velocity_for_distinct_impedances": velocities,
        }
    )

    events_us = [0, 99, 100, 299, 300]
    counts = [sum(i * 100 <= t < (i + 1) * 100 for t in events_us) for i in range(3)]
    assert counts == [2, 1, 1]
    assert sum(counts) == 4
    assert sum(bool(x) for x in counts) == 3
    onset_us = 150
    ceil_us = ((onset_us + 99) // 100) * 100
    floor_us = (onset_us // 100) * 100
    assert ceil_us == 200 and ceil_us - onset_us == 50
    assert floor_us == 100 and onset_us - floor_us == 50
    cases.append(
        {
            "case": "half_open_collision_and_alignment",
            "assertions": 5,
            "pass": True,
            "counts": counts,
            "excluded_end_us": 300,
            "onset_us": onset_us,
            "ceiling_us": ceil_us,
            "floor_us": floor_us,
        }
    )

    a = [1, 1, 1, 1, 0, 0, 0, 0]
    complement = [1 - x for x in a]
    assert sum(a) == sum(complement) == 4
    assert correlation(a, a) == 1
    assert correlation(a, complement) == -1
    cases.append(
        {
            "case": "marginals_do_not_identify_correlation",
            "assertions": 3,
            "pass": True,
            "mean_per_bin": 0.5,
            "clone_correlation": 1,
            "complement_correlation": -1,
        }
    )

    shape = [0.25, 1.0, 0.5]
    low = [20 * x for x in shape]
    high = [80 * x for x in shape]
    assert low != high
    assert all(b / a == 4 for a, b in zip(low, high, strict=True))
    assert [x / max(low) for x in low] == [x / max(high) for x in high] == shape
    cases.append(
        {
            "case": "normalized_tuning_unknown_gain",
            "assertions": 3,
            "pass": True,
            "normalized_shape": shape,
            "absolute_traces": [low, high],
        }
    )

    result = {
        "schema": "flymsg.jo-design-math-controls/v1",
        "scope": "Synthetic mathematical controls; DO NOT qualify JO physiology.",
        "exclusions": [
            "no measured data",
            "no neural model runs",
            "no JO adapter",
            "no gain or filter selection",
            "no source-trace acquisition",
            "no downstream held-out outcomes",
        ],
        "protocol_sha256": sha256(ROOT / "analytic-protocol.md"),
        "script_sha256": sha256(Path(__file__).resolve()),
        "floating_tolerance": TOLERANCE,
        "cases": cases,
        "case_count": len(cases),
        "assertion_count": sum(case["assertions"] for case in cases),
        "all_pass": all(case["pass"] for case in cases),
    }
    (ROOT / "analytic-results.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
