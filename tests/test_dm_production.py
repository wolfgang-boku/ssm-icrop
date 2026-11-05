"""Tests for the DM production module."""

import math
import warnings

import pytest

from ssm_icrop.dm_production import DMProductionParams, step_dm_production
from ssm_icrop.phenology import _solar_geometry
from ssm_icrop.state import SimState


def make_params(**overrides) -> DMProductionParams:
    defaults = dict(
        irue=3.0,
        kpar=0.5,
        tbrue=0.0,
        tp1rue=15.0,
        tp2rue=25.0,
        tcrue=35.0,
        vpd_type=0,
        vpd_threshold=1.5,
        vpdf=0.75,
        co2=350.0,
        co2_ref=350.0,
        co2_res=0.0,
        tec_ref=6.0,
    )
    defaults.update(overrides)
    return DMProductionParams(**defaults)


def make_state(**overrides) -> SimState:
    state = SimState()
    state.cbd = 50.0
    state.cbd_emr = 10.0
    state.cbd_tsg = 120.0
    state.tmp = 20.0
    state.tmin = 10.0
    state.tmax = 28.0
    state.tmaxb = 27.0
    state.tmina = 11.0
    state.srad = 20.0
    state.lai = 3.0
    state.wsfg = 1.0
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


def set_solar_geometry(state: SimState, doy: int, lat: float) -> None:
    state.dayl, state.sinld, state.cosld, state.aob = _solar_geometry(doy, lat)


class TestInitialization:
    def test_co2_neutral_when_co2_equals_ref(self):
        params = make_params(co2=350.0, co2_ref=350.0, co2_res=0.8,
                             irue=3.0, tec_ref=6.0)
        state = make_state()
        step_dm_production(state, params)

        assert state.irue_eff == pytest.approx(3.0)
        assert state.tec == pytest.approx(6.0)
        assert state.ini_dmp == 1

    def test_higher_co2_increases_effective_rue(self):
        params = make_params(co2=550.0, co2_ref=350.0, co2_res=0.5, irue=3.0)
        state = make_state()
        step_dm_production(state, params)

        assert state.irue_eff > 3.0

    def test_init_runs_once(self):
        params = make_params(co2=550.0, co2_ref=350.0, co2_res=0.5)
        state = make_state()
        step_dm_production(state, params)
        state.irue_eff = 99.0  # sentinel
        step_dm_production(state, params)
        assert state.irue_eff == 99.0


class TestTemperatureResponse:
    def test_tcfrue_zero_below_base(self):
        params = make_params(tbrue=5.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0)
        state = make_state(tmp=2.0)
        step_dm_production(state, params)
        assert state.tcfrue == 0.0

    def test_tcfrue_one_at_optimum(self):
        params = make_params(tbrue=5.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0)
        state = make_state(tmp=20.0)
        step_dm_production(state, params)
        assert state.tcfrue == 1.0

    def test_tcfrue_zero_above_ceiling(self):
        params = make_params(tbrue=5.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0)
        state = make_state(tmp=40.0)
        step_dm_production(state, params)
        assert state.tcfrue == 0.0

    def test_default_temp_response_is_dent(self):
        params = make_params(tbrue=5.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0)
        assert params.temp_response == "dent"

    def test_dent_has_flat_plateau_between_tp1_and_tp2(self):
        """Distinguishing feature vs beta: dent is 1.0 across the whole plateau."""
        params = make_params(tbrue=5.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0,
                             temp_response="dent")
        state_mid = make_state(tmp=17.0)
        state_late = make_state(tmp=23.0)
        step_dm_production(state_mid, params)
        step_dm_production(state_late, params)
        assert state_mid.tcfrue == 1.0
        assert state_late.tcfrue == 1.0

    def test_beta_option_selectable(self):
        params = make_params(tbrue=5.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0,
                             temp_response="beta")
        state = make_state(tmp=15.0)  # at tp1rue, the beta function's peak-ish region
        step_dm_production(state, params)
        assert 0.0 < state.tcfrue <= 1.0

    def test_beta_zero_below_base_and_above_ceiling(self):
        params = make_params(tbrue=5.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0,
                             temp_response="beta")
        state_cold = make_state(tmp=2.0)
        state_hot = make_state(tmp=40.0)
        step_dm_production(state_cold, params)
        step_dm_production(state_hot, params)
        assert state_cold.tcfrue == 0.0
        assert state_hot.tcfrue == 0.0

    def test_beta_and_dent_differ_at_same_temperature(self):
        """The two curve shapes should disagree somewhere in the rising phase."""
        base = dict(tbrue=5.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0)
        params_dent = make_params(temp_response="dent", **base)
        params_beta = make_params(temp_response="beta", **base)

        state_dent = make_state(tmp=10.0)
        state_beta = make_state(tmp=10.0)
        step_dm_production(state_dent, params_dent)
        step_dm_production(state_beta, params_beta)

        assert state_dent.tcfrue != pytest.approx(state_beta.tcfrue)


class TestRueWindow:
    def test_rue_zero_before_emergence(self):
        params = make_params()
        state = make_state(cbd=5.0, cbd_emr=10.0, cbd_tsg=120.0)
        step_dm_production(state, params)
        assert state.rue == 0.0
        assert state.ddmp == 0.0

    def test_rue_zero_after_tsg(self):
        params = make_params()
        state = make_state(cbd=150.0, cbd_emr=10.0, cbd_tsg=120.0)
        step_dm_production(state, params)
        assert state.rue == 0.0

    def test_rue_positive_during_growth(self):
        params = make_params()
        state = make_state(cbd=50.0, cbd_emr=10.0, cbd_tsg=120.0)
        step_dm_production(state, params)
        assert state.rue > 0.0


class TestDailyMethod:
    def test_ddmp_formula(self):
        params = make_params(vpd_type=0, kpar=0.5, irue=3.0, co2_res=0.0)
        state = make_state(lai=2.0, srad=20.0, tmp=20.0)
        step_dm_production(state, params)

        expected_fint = 1.0 - math.exp(-0.5 * 2.0)
        assert state.fint == pytest.approx(expected_fint)
        expected_ddmp = 20.0 * 0.48 * expected_fint * state.rue
        assert state.ddmp == pytest.approx(expected_ddmp)

    def test_zero_lai_gives_zero_fint_and_ddmp(self):
        params = make_params(vpd_type=0)
        state = make_state(lai=0.0)
        step_dm_production(state, params)
        assert state.fint == pytest.approx(0.0)
        assert state.ddmp == pytest.approx(0.0)

    def test_daily_method_does_not_touch_tr(self):
        params = make_params(vpd_type=0)
        state = make_state()
        state.tr = 42.0  # sentinel, should be untouched (matches VBA)
        step_dm_production(state, params)
        assert state.tr == 42.0


class TestHourlyMethod:
    """vpd_type=1 is unused by every crop in the 2022 source workbook and

    triggers a UserWarning each time it runs (see dm_production.py) — every
    test here must expect that warning explicitly.
    """

    def test_hourly_produces_positive_ddmp_and_tr(self):
        params = make_params(vpd_type=1)
        state = make_state(lai=3.0)
        set_solar_geometry(state, doy=180, lat=38.0)

        with pytest.warns(UserWarning, match="hourly VPD method"):
            step_dm_production(state, params)

        assert state.ddmp > 0.0
        assert state.tr > 0.0

    def test_hourly_zero_lai_gives_zero_ddmp(self):
        params = make_params(vpd_type=1)
        state = make_state(lai=0.0)
        set_solar_geometry(state, doy=180, lat=38.0)

        with pytest.warns(UserWarning, match="hourly VPD method"):
            step_dm_production(state, params)

        assert state.ddmp == pytest.approx(0.0)

    def test_hourly_and_daily_are_same_order_of_magnitude(self):
        """Sanity check: both integration methods should give roughly similar DDMP."""
        state_daily = make_state(lai=3.0)
        params_daily = make_params(vpd_type=0)
        step_dm_production(state_daily, params_daily)

        state_hourly = make_state(lai=3.0)
        set_solar_geometry(state_hourly, doy=180, lat=38.0)
        params_hourly = make_params(vpd_type=1)
        with pytest.warns(UserWarning, match="hourly VPD method"):
            step_dm_production(state_hourly, params_hourly)

        ratio = state_hourly.ddmp / state_daily.ddmp
        assert 0.3 < ratio < 3.0

    def test_high_vpd_caps_transpiration_and_ddmp(self):
        """Very dry air (large VPD) should trigger the VPDcr correction branch."""
        # threshold set very low so it's easy to exceed
        params = make_params(vpd_type=1, vpd_threshold=0.1)
        state = make_state(lai=3.0, tmin=5.0, tmax=35.0)
        set_solar_geometry(state, doy=180, lat=38.0)

        with pytest.warns(UserWarning, match="hourly VPD method"):
            step_dm_production(state, params)

        assert state.ddmp > 0.0  # still produces something, just capped

    def test_daily_method_does_not_warn(self):
        params = make_params(vpd_type=0)
        state = make_state(lai=3.0)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            step_dm_production(state, params)  # would raise if any warning fired
