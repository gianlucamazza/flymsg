"""Dimensional check of the live LIF step and the evidence-registry units (SF2, #148).

The dimensions are the ones already written on ``sim.Params`` and in
``validation/evidence.yaml``. A text uncertainty stays text. This module does not
build an interval.
"""

from __future__ import annotations

from dataclasses import fields

import numpy as np

from flymsg import sim

TIME = "time"
VOLTAGE = "voltage"
DIMENSIONLESS = "dimensionless"
LABEL = "label"
BUNDLE = "bundle"

# Comments on sim.Params. A synapse count is dimensionless, so w_syn is a voltage.
PARAM_DIM = {
    "v_rest": VOLTAGE,
    "v_th": VOLTAGE,
    "tau_m": TIME,
    "tau_syn": TIME,
    "t_ref": TIME,
    "delay": TIME,
    "w_syn": VOLTAGE,
    "poisson_scale": DIMENSIONLESS,
    "th_jump": VOLTAGE,
    "tau_th": TIME,
    "dt": TIME,
}

# Spellings already stored on evidence records. A new spelling is refused until
# its dimension is written here.
UNIT_DIM = {
    "mV": VOLTAGE,
    "ms": TIME,
    "dimensionless": DIMENSIONLESS,
    "dimensionless (voltage ratio)": DIMENSIONLESS,
    "fraction of Kenyon cells": DIMENSIONLESS,
    "fraction of responders": DIMENSIONLESS,
    "standard deviations of dF/F": DIMENSIONLESS,
    "region name per connection": LABEL,
    (
        "p values (two-way ANOVA with Tukey; Brown-Forsythe and Welch ANOVA), flies"
    ): DIMENSIONLESS,
    "ms, Hz, mm/s": BUNDLE,
    "deg (full angular size), s, ms, Hz": BUNDLE,
}


class UnitError(ValueError):
    """A unit or a LIF combination is not the one the step uses."""


def parse_unit(unit: str) -> str:
    """The dimension of one evidence-registry unit string."""
    if unit not in UNIT_DIM:
        raise UnitError(f"unrecognized unit {unit!r}")
    return UNIT_DIM[unit]


def registry(records: dict) -> list[tuple[str, str]]:
    """``(id, dimension)`` for every record. An unknown unit is an error."""
    return [(rid, parse_unit(record["unit"])) for rid, record in records.items()]


def is_distribution(value) -> bool:
    """A distribution is a non-empty map of numbers. Prose is not one."""
    return (
        isinstance(value, dict)
        and bool(value)
        and all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in value.values()
        )
    )


def propagation_blocked(records: dict) -> bool:
    """True when no record stores a distribution in ``uncertainty``."""
    return not any(
        is_distribution(record.get("uncertainty")) for record in records.values()
    )


def per_step_release(rate_hz: float, dt_ms: float) -> float:
    """Saturated graded release in spike-equivalents per step.

    ``sim.graded_arrays`` multiplies hertz by milliseconds and divides by 1000,
    the number of milliseconds in a second. The result is a count.
    """
    return float(rate_hz) * float(dt_ms) / 1000.0


def _step_combination(params: sim.Params) -> tuple:
    """Float32 terms the LIF update multiplies, in ``sim._constants`` order.

    Decays are ``exp(-dt/tau)``. ``gv`` is the dimensionless factor in ``g*gv``.
    The last term is the kick ``poisson_scale * w_syn`` added to ``v``.
    """
    em = np.exp(-params.dt / params.tau_m)
    es = np.exp(-params.dt / params.tau_syn)
    gv = params.tau_syn / (params.tau_syn - params.tau_m) * (es - em)
    return tuple(
        np.float32(item)
        for item in (
            em,
            es,
            gv,
            np.exp(-params.dt / params.tau_th),
            params.v_rest,
            params.v_th,
            params.poisson_scale * params.w_syn,
        )
    )


def check_params(params: sim.Params | None = None) -> list[str]:
    """Read the live LIF constants and report those combinations.

    ``v_rest``, ``v_th``, ``w_syn`` and ``th_jump`` must each be a voltage.
    Time fields must be times, so the decays and ``gv`` stay dimensionless.
    ``poisson_scale`` must be dimensionless. The sentences quote ``sim._constants``
    and a 1000 Hz ``sim.graded_arrays`` probe at this ``dt``. A live return that
    is not the combination the step uses is an error.
    """
    params = sim.Params() if params is None else params
    names = {item.name for item in fields(params)}
    missing = sorted(names - set(PARAM_DIM))
    extra = sorted(set(PARAM_DIM) - names)
    if missing or extra:
        raise UnitError(f"Params dimensions drifted: missing {missing} extra {extra}")
    times = ("tau_m", "tau_syn", "tau_th", "t_ref", "delay", "dt")
    if any(PARAM_DIM[name] != TIME for name in times):
        raise UnitError("a time ratio stopped being dimensionless")
    voltages = ("v_rest", "v_th", "w_syn", "th_jump")
    if any(PARAM_DIM[name] != VOLTAGE for name in voltages):
        raise UnitError("v_rest, v_th, w_syn and th_jump must be a voltage")
    if PARAM_DIM["poisson_scale"] != DIMENSIONLESS:
        raise UnitError("poisson_scale * w_syn would leave voltage")
    for name in times:
        value = getattr(params, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise UnitError(f"{name} must be a positive time")
    live = sim._constants(params)
    expected = _step_combination(params)
    if len(live) != len(expected) or any(
        np.float32(got) != np.float32(want)
        for got, want in zip(live, expected, strict=True)
    ):
        raise UnitError("live LIF constants disagree with the step")
    em, es, gv, decay, rest, threshold, kick = live
    span = float(params.v_th) - float(params.v_rest)
    if not (span > 0):
        raise UnitError("graded span must be a positive voltage")
    graded = sim.Graded(
        idx=np.array([0], dtype=np.int64),
        v_lo=np.array([params.v_rest], dtype=np.float64),
        span=np.array([span], dtype=np.float64),
        rate_hz=np.array([1000.0], dtype=np.float64),
    )
    _idx, _lo, _span, scale, _mask = sim.graded_arrays(graded, 1, float(params.dt))
    want_scale = np.float32(per_step_release(1000.0, params.dt))
    if scale.shape != (1,) or np.float32(scale[0]) != want_scale:
        raise UnitError("graded release disagrees with the kernel count")
    return [
        (
            "dt/tau decays from _constants are dimensionless: "
            f"em={float(em)} es={float(es)} decay={float(decay)}"
        ),
        (
            "gv from _constants is dimensionless, so g*gv stays a voltage: "
            f"gv={float(gv)}"
        ),
        (
            "kick from _constants is poisson_scale*w_syn, a voltage added to v: "
            f"kick={float(kick)}"
        ),
        (
            "rest and threshold from _constants are voltages: "
            f"v_rest={float(rest)} v_th={float(threshold)}"
        ),
        f"graded_arrays scale is a count: scale={float(scale[0])}",
    ]


def report(records: dict, params: sim.Params | None = None) -> str:
    """The dimensional report. A distribution is refused, not propagated."""
    if not propagation_blocked(records):
        raise UnitError(
            "a record carries a distribution; this check does not propagate it"
        )
    rows = registry(records)
    lines = check_params(params)
    lines.append(f"registry units parsed: {len(rows)}")
    lines.append("uncertainty propagation: blocked, no distribution")
    return "\n".join(lines)
