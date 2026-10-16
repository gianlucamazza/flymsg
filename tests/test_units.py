"""The SF2 dimensional check reads the live step and the evidence registry."""

import numpy as np
import pytest

from flymsg import evidence, sim, units
from flymsg.units import UnitError


def test_the_live_step_and_the_registry_agree(monkeypatch):
    records = evidence.load()
    params = sim.Params()
    seen = {}
    real_constants = sim._constants
    real_graded = sim.graded_arrays

    def watch_constants(p):
        seen["constants"] = real_constants(p)
        return seen["constants"]

    def watch_graded(*args, **kwargs):
        seen["graded"] = real_graded(*args, **kwargs)
        return seen["graded"]

    monkeypatch.setattr(sim, "_constants", watch_constants)
    monkeypatch.setattr(sim, "graded_arrays", watch_graded)
    text = units.report(records, params)
    em, es, gv, decay, rest, th, kick = seen["constants"]
    scale = seen["graded"][3]
    for piece in (
        f"em={float(em)}",
        f"es={float(es)}",
        f"gv={float(gv)}",
        f"decay={float(decay)}",
        f"kick={float(kick)}",
        f"v_rest={float(rest)}",
        f"v_th={float(th)}",
        f"scale={float(scale[0])}",
    ):
        assert piece in text
    assert "uncertainty propagation: blocked, no distribution" in text
    parsed = dict(units.registry(records))
    assert set(parsed) == set(records)
    assert parsed["eln_spike_amplitude"] == units.VOLTAGE
    assert parsed["eln_pn_coupling"] == units.DIMENSIONLESS
    assert units.PARAM_DIM["w_syn"] == units.PARAM_DIM["v_rest"] == units.VOLTAGE
    assert units.PARAM_DIM["dt"] == units.PARAM_DIM["tau_m"] == units.TIME


def test_shared_time_labels_are_not_a_voltage(monkeypatch):
    for name in ("v_rest", "v_th", "w_syn", "th_jump"):
        monkeypatch.setitem(units.PARAM_DIM, name, units.TIME)
    with pytest.raises(UnitError, match="voltage"):
        units.check_params(sim.Params())


def test_a_live_kick_that_disagrees_is_refused(monkeypatch):
    real = sim._constants

    def wrong(p):
        values = list(real(p))
        values[6] = np.float32(np.float64(values[6]) + 1.0)
        return tuple(values)

    monkeypatch.setattr(sim, "_constants", wrong)
    with pytest.raises(UnitError, match="disagree"):
        units.check_params(sim.Params())


def test_a_live_graded_scale_that_disagrees_is_refused(monkeypatch):
    real = sim.graded_arrays

    def wrong(*args, **kwargs):
        idx, lo, span, scale, mask = real(*args, **kwargs)
        scale = scale.copy()
        scale[0] = np.float32(np.float64(scale[0]) + 1.0)
        return idx, lo, span, scale, mask

    monkeypatch.setattr(sim, "graded_arrays", wrong)
    with pytest.raises(UnitError, match="disagree"):
        units.check_params(sim.Params())


def test_graded_release_matches_the_kernel_count():
    graded = sim.Graded(
        idx=np.array([0]),
        v_lo=np.array([-60.0]),
        span=np.array([20.0]),
        rate_hz=np.array([1000.0]),
    )
    _idx, _lo, _span, scale, _mask = sim.graded_arrays(graded, 1, 1.0)
    assert float(scale[0]) == pytest.approx(units.per_step_release(1000.0, 1.0))


def test_an_unknown_unit_is_refused():
    with pytest.raises(UnitError, match="unrecognized"):
        units.parse_unit("furlongs")


def test_a_param_without_its_dimension_is_refused(monkeypatch):
    monkeypatch.delitem(units.PARAM_DIM, "dt")
    with pytest.raises(UnitError, match="drifted"):
        units.check_params(sim.Params())


def test_a_time_marked_as_voltage_is_refused(monkeypatch):
    monkeypatch.setitem(units.PARAM_DIM, "dt", units.VOLTAGE)
    with pytest.raises(UnitError, match="dimensionless"):
        units.check_params(sim.Params())


def test_prose_uncertainty_is_not_a_distribution_and_a_number_map_is():
    records = evidence.load()
    assert units.propagation_blocked(records)
    assert not units.is_distribution(records["eln_spike_amplitude"]["uncertainty"])
    copied = {"only": {"uncertainty": {"sd": 1.5}}}
    assert units.is_distribution(copied["only"]["uncertainty"])
    assert not units.propagation_blocked(copied)
    with pytest.raises(UnitError, match="does not propagate"):
        units.report(copied)
