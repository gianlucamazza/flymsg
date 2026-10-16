"""The SF2 dimensional check reads the live step and the evidence registry."""

import numpy as np
import pytest

from flymsg import evidence, sim, units
from flymsg.units import UnitError


def test_the_live_step_and_the_registry_agree():
    records = evidence.load()
    text = units.report(records)
    assert "dimensionless" in text
    assert "uncertainty propagation: blocked, no distribution" in text
    parsed = dict(units.registry(records))
    assert set(parsed) == set(records)
    assert parsed["eln_spike_amplitude"] == units.VOLTAGE
    assert parsed["eln_pn_coupling"] == units.DIMENSIONLESS
    lines = units.check_params(sim.Params())
    assert any("dimensionless" in line for line in lines)
    assert units.PARAM_DIM["w_syn"] == units.PARAM_DIM["v_rest"] == units.VOLTAGE
    assert units.PARAM_DIM["dt"] == units.PARAM_DIM["tau_m"] == units.TIME


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
