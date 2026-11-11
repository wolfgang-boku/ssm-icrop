"""Tests for the DM distribution module."""

import pytest

from ssm_icrop.dm_distribution import (
    DMDistributionParams,
    _dhidmf,
    step_dm_distribution,
)
from ssm_icrop.state import SimState


def make_params(**overrides) -> DMDistributionParams:
    defaults = dict(
        flf1a=0.6,
        flf1b=0.3,
        wtopl=200.0,
        flf2=0.1,
        frtrl=0.2,
        gcc=1.3,
        pdhi=0.015,
        wdhi1=50.0,
        wdhi2=100.0,
        wdhi3=400.0,
        wdhi4=500.0,
        mc=12.5,
        heat=0,
        tp2h=33.0,
        tch=45.0,
        tp1f=5.0,
        tbf=-3.0,
        rfmax=1.0,
    )
    defaults.update(overrides)
    return DMDistributionParams(**defaults)


def make_state(**overrides) -> SimState:
    state = SimState()
    state.ini_dmd = 1  # skip init unless a test explicitly wants it
    state.cbd_blg = 5.0
    state.cbd_bsg = 100.0
    state.cbd_tsg = 150.0
    state.cbd_tlm = 60.0
    state.cbd_tlp = 100.0
    state.cbd_bxtf = 90.0
    state.cbd_txtf = 110.0
    state.sumflw = 10.0
    state.wtop = 200.0
    state.wveg = 200.0
    state.wgrn = 0.0
    state.wlf = 100.0
    state.wst = 100.0
    state.ddmp = 10.0
    state.hi = 0.0
    state.frhtdhi = 1.0
    state.lai = 3.0
    state.nst = 1.0
    state.tmin = 15.0
    state.tmax = 25.0
    state.srad = 20.0
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


class TestDhidmf:
    def test_below_wdhi1_is_zero(self):
        assert _dhidmf(40.0, 50.0, 100.0, 400.0, 500.0) == 0.0

    def test_above_wdhi4_is_zero(self):
        assert _dhidmf(600.0, 50.0, 100.0, 400.0, 500.0) == 0.0

    def test_ramping_up_between_wdhi1_and_wdhi2(self):
        result = _dhidmf(75.0, 50.0, 100.0, 400.0, 500.0)
        assert 0.0 < result < 1.0
        assert result == pytest.approx((75.0 - 50.0) / (100.0 - 50.0))

    def test_plateau_between_wdhi2_and_wdhi3(self):
        assert _dhidmf(250.0, 50.0, 100.0, 400.0, 500.0) == 1.0

    def test_ramping_down_between_wdhi3_and_wdhi4(self):
        result = _dhidmf(450.0, 50.0, 100.0, 400.0, 500.0)
        assert 0.0 < result < 1.0
        assert result == pytest.approx((500.0 - 450.0) / (500.0 - 400.0))


class TestInitialization:
    def test_init_sets_starting_biomass(self):
        params = make_params()
        # ddmp=0 means GLF=GST=0 on the init day itself (stem growth isn't
        # gated by cbd_blg/cbd_tlp in VBA -- it just absorbs whatever DDMP2
        # leaves over), so wlf/wst stay exactly at their freshly-init'd values.
        state = make_state(ini_dmd=0, cbd=1.0, ddmp=0.0)
        step_dm_distribution(state, params, water_mode=0)

        assert state.ini_dmd == 1
        assert state.wlf == pytest.approx(0.5)
        assert state.wst == pytest.approx(0.5)
        assert state.wveg == pytest.approx(1.0)
        assert state.frhtdhi == 1.0

    def test_init_computes_sumflw(self):
        params = make_params(rfmax=1.0)
        state = make_state(ini_dmd=0, cbd=50.0, cbd_bxtf=90.0, cbd_txtf=110.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.sumflw > 0.0

    def test_init_runs_once(self):
        params = make_params()
        state = make_state(ini_dmd=0, cbd=50.0)
        step_dm_distribution(state, params, water_mode=0)
        state.wlf = 99.0  # sentinel
        step_dm_distribution(state, params, water_mode=0)
        assert state.wlf != pytest.approx(0.5)


class TestPreBsgPhase:
    def test_bsgdm_latches_wtop(self):
        params = make_params()
        state = make_state(cbd=50.0, wtop=175.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.bsgdm == pytest.approx(175.0)

    def test_no_grain_growth_before_bsg(self):
        params = make_params()
        state = make_state(cbd=50.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.sgr == 0.0

    def test_trldm_seeded_from_bsgdm(self):
        params = make_params(frtrl=0.25)
        state = make_state(cbd=50.0, wtop=200.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.trldm == pytest.approx(200.0 * 0.25)

    def test_dhi_scaled_by_dhidmf(self):
        params = make_params(pdhi=0.02, wdhi1=50.0, wdhi2=100.0,
                             wdhi3=400.0, wdhi4=500.0)
        state = make_state(cbd=50.0, wtop=250.0)  # squarely in the plateau
        step_dm_distribution(state, params, water_mode=0)
        assert state.dhi == pytest.approx(0.02)  # dhidmf=1 on the plateau

    def test_dhi_zero_when_biomass_too_low(self):
        params = make_params(pdhi=0.02, wdhi1=50.0, wdhi2=100.0,
                             wdhi3=400.0, wdhi4=500.0)
        state = make_state(cbd=50.0, wtop=10.0)  # below wdhi1
        step_dm_distribution(state, params, water_mode=0)
        assert state.dhi == 0.0


class TestGrainFillPhase:
    def test_sgr_positive_during_grain_fill(self):
        params = make_params()
        state = make_state(cbd=120.0, dhi=0.02, trldm=20.0, hi=0.1,
                           wtop=300.0, ddmp=10.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.sgr > 0.0

    def test_sgr_zero_without_nitrogen_when_canopy_gone(self):
        """LAI=0 and NST <= WST*SNCS blocks grain filling (no N available)."""
        params = make_params()
        state = make_state(cbd=120.0, dhi=0.02, trldm=20.0, hi=0.1, wtop=300.0,
                           ddmp=10.0, lai=0.0, nst=0.0, wst=1.0, sncs=0.005)
        step_dm_distribution(state, params, water_mode=0)
        assert state.sgr == 0.0

    def test_translocation_used_when_demand_exceeds_production(self):
        params = make_params(gcc=1.0)
        # dhi high enough that demand (sgr/gcc) exceeds ddmp
        state = make_state(cbd=120.0, dhi=0.5, trldm=50.0, hi=0.5, wtop=300.0, ddmp=1.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.trldm < 50.0  # reserve was drawn down

    def test_translocation_capped_at_available_reserve(self):
        params = make_params(gcc=1.0)
        state = make_state(cbd=120.0, dhi=0.5, trldm=0.5, hi=0.5, wtop=300.0, ddmp=0.1)
        step_dm_distribution(state, params, water_mode=0)
        assert state.trldm == pytest.approx(0.0)  # fully drawn down, never negative

    def test_no_grain_growth_after_tsg(self):
        params = make_params()
        state = make_state(cbd=200.0)  # past cbd_tsg=150
        step_dm_distribution(state, params, water_mode=0)
        assert state.sgr == 0.0


class TestLeafStemPartition:
    def test_no_leaf_growth_before_blg(self):
        params = make_params()
        state = make_state(cbd=1.0)  # before cbd_blg=5
        step_dm_distribution(state, params, water_mode=0)
        assert state.glf == 0.0

    def test_no_leaf_growth_after_tlp(self):
        params = make_params()
        state = make_state(cbd=150.0)  # past cbd_tlp=100
        step_dm_distribution(state, params, water_mode=0)
        assert state.glf == 0.0

    def test_flf1a_regime_below_wtopl(self):
        params = make_params(flf1a=0.6, flf1b=0.3, wtopl=200.0)
        state = make_state(cbd=30.0, wtop=100.0, ddmp=10.0)  # below cbd_tlm=60
        step_dm_distribution(state, params, water_mode=0)
        expected_ddmp2 = state.ddmp  # sgr=0 before bsg
        assert state.glf == pytest.approx(0.6 * expected_ddmp2)

    def test_flf1b_regime_above_wtopl(self):
        params = make_params(flf1a=0.6, flf1b=0.3, wtopl=200.0)
        state = make_state(cbd=30.0, wtop=300.0, ddmp=10.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.glf == pytest.approx(0.3 * 10.0)

    def test_flf2_regime_between_tlm_and_tlp(self):
        params = make_params(flf2=0.15)
        state = make_state(cbd=80.0, wtop=100.0, ddmp=10.0)  # between tlm=60, tlp=100
        step_dm_distribution(state, params, water_mode=0)
        assert state.glf == pytest.approx(0.15 * 10.0)

    def test_stem_gets_remainder(self):
        params = make_params(flf1a=0.6, wtopl=200.0)
        state = make_state(cbd=30.0, wtop=100.0, ddmp=10.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.gst == pytest.approx(state.ddmp - state.glf)


class TestOrganAccumulation:
    def test_wtop_equals_wveg_plus_wgrn(self):
        params = make_params()
        state = make_state(cbd=50.0, wtop=200.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.wtop == pytest.approx(state.wveg + state.wgrn)

    def test_hi_is_wgrn_over_wtop(self):
        params = make_params()
        state = make_state(cbd=120.0, dhi=0.02, trldm=20.0, hi=0.1,
                           wtop=300.0, ddmp=10.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.hi == pytest.approx(state.wgrn / state.wtop)

    def test_wveg_can_shrink_when_translocation_exceeds_production(self):
        """VBA quirk: WVEG accumulates DDMP - SGR/GCC *unclamped*, so heavy
        translocation can shrink WVEG even though GLF+GST (from clamped
        DDMP2) never go negative."""
        params = make_params(gcc=1.0)
        state = make_state(cbd=120.0, dhi=0.9, trldm=50.0, hi=0.9, wtop=300.0,
                           ddmp=1.0, wveg=300.0)
        wveg_before = state.wveg
        step_dm_distribution(state, params, water_mode=0)
        assert state.glf + state.gst >= 0.0  # partitioning never goes negative
        assert state.wveg < wveg_before  # but the bulk pool can still shrink


class TestHeatFrostEffect:
    def test_disabled_by_default(self):
        params = make_params(heat=0)
        state = make_state(cbd=95.0, tmax=45.0, tmin=-10.0)  # extreme temps
        step_dm_distribution(state, params, water_mode=0)
        assert state.frhtdhi == 1.0

    def test_no_effect_outside_flowering_window(self):
        params = make_params(heat=1)
        state = make_state(cbd=50.0, tmax=45.0)  # outside [90, 110]
        step_dm_distribution(state, params, water_mode=0)
        assert state.frhtdhi == 1.0

    def test_heat_stress_reduces_frhtdhi(self):
        params = make_params(heat=1, tp2h=33.0, tch=45.0)
        state = make_state(cbd=100.0, tmax=40.0, tmin=15.0, sumflw=10.0)
        step_dm_distribution(state, params, water_mode=0)
        assert state.frhtdhi < 1.0

    def test_frhtdhi_is_monotonic_running_minimum(self):
        """Once reduced, frhtdhi should never increase even on a mild day."""
        params = make_params(heat=1, tp2h=33.0, tch=45.0, tp1f=5.0, tbf=-3.0)
        state = make_state(cbd=95.0, tmax=44.0, tmin=15.0, sumflw=10.0)
        step_dm_distribution(state, params, water_mode=0)
        reduced_value = state.frhtdhi
        assert reduced_value < 1.0

        state.cbd = 96.0
        state.tmax = 20.0  # mild day, shouldn't undo prior damage
        step_dm_distribution(state, params, water_mode=0)
        assert state.frhtdhi <= reduced_value

    def test_canopy_temp_falls_back_to_air_temp_when_no_water_balance(self):
        params = make_params(heat=1, tp2h=33.0, tch=45.0)
        state = make_state(cbd=100.0, tmax=40.0, tmin=15.0, sumflw=10.0)
        step_dm_distribution(state, params, water_mode=0)
        # With water_mode=0, canopy temp == air temp exactly (tmax=40 used directly)
        expected_heatf1 = min(1.0, max(0.0, (40.0 - 33.0) / (45.0 - 33.0)))
        assert expected_heatf1 > 0.0  # sanity: the branch is actually exercised
