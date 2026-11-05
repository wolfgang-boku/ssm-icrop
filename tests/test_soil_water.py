"""Tests for the soil water module.

The rainfed path is verified day by day against the reference output in
test_verification.py. These tests cover the branches that scenario never takes:
irrigation modes, waterlogging, drought survival, and the season carry-over.
"""

import math
from pathlib import Path

import pytest

from ssm_icrop.inputs import (
    IrrigationEvent,
    IrrigationSchedule,
    ManagementConfig,
    SoilConfig,
    SoilLayer,
)
from ssm_icrop.soil_water import SoilWaterParams, step_soil_water
from ssm_icrop.state import SimState

REPO_ROOT = Path(__file__).parent.parent


def make_params(**overrides) -> SoilWaterParams:
    defaults = dict(
        deport=200.0, meed=1000.0, grtdp=30.0,
        tec_ref=5.8, co2_res=0.8, co2_ref=385.0,
        wssg=0.3, wssl=0.4, wssd=0.5, wssn=0.0,
        fldkil=99.0, vpd_type=0, surviv=0, epcond=0.0, ltlrwc=0.0,
        vpdf=0.63, co2=385.0,
    )
    defaults.update(overrides)
    return SoilWaterParams(**defaults)


def make_soil(n_layers: int = 3, init_water: float = 0.3, **overrides) -> SoilConfig:
    layer = dict(depth_mm=200.0, sat=0.5, dul=0.35, cll=0.15, adry=0.05,
                 init_water=init_water, drainf=0.4)
    defaults = dict(name="test", n_layers=n_layers, ldrain=n_layers, salb=0.13, cn=73.0,
                    layers=[SoilLayer(**layer) for _ in range(n_layers)])
    defaults.update(overrides)
    return SoilConfig(**defaults)


def make_management(water: int = 2, **overrides) -> ManagementConfig:
    defaults = dict(
        name="test", plant_year=2000, sim_years=1, fix_find=0, sim_doy=1, pdoy=5,
        lpdoy=365, stop_doy=400, sow_tmp=5.0, sow_wat=0.5, plant_density=300.0,
        water=water, nitrogen=0, irg_level=0.5,
    )
    defaults.update(overrides)
    return ManagementConfig(**defaults)


def make_state(**overrides) -> SimState:
    state = SimState()
    state.tmax, state.tmin, state.tmp, state.srad = 20.0, 8.0, 14.0, 15.0
    state.cbd_emr, state.cbd_bsg, state.cbd_tsg = 4.0, 40.0, 60.0
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


def run_day(state, params=None, soil=None, management=None, sla=0.02):
    step_soil_water(state, params or make_params(), soil or make_soil(),
                    management or make_management(), sla)


class TestInitialization:
    """iCrop.vba:1117-1184"""

    def test_layer_water_from_soil_sheet(self):
        state = make_state()
        params = make_params()
        # zero fluxes on day 1 so only the initial state is visible
        state.srad = 0.0
        run_day(state, params=params, soil=make_soil(init_water=0.3))
        assert state.ini_sw == 1
        assert state.wl[0] == pytest.approx(0.3 * 200.0)
        assert state.ttsw[0] == pytest.approx((0.35 - 0.15) * 200.0)
        assert state.isolwat == pytest.approx(3 * (0.3 - 0.15) * 200.0)
        assert state.soldep == 600.0
        assert state.deport == params.deport

    def test_tec_is_co2_adjusted(self):
        state = make_state()
        run_day(state, params=make_params(co2=550.0, co2_ref=385.0, co2_res=0.8))
        ratio = (1 + 0.8 * math.log10(550 / 330)) / (1 + 0.8 * math.log10(385 / 330))
        assert state.tec == pytest.approx(5.8 * ratio)

    def test_layers_past_nlyer_are_ignored(self):
        state = make_state()
        soil = make_soil(n_layers=3)
        soil.layers.append(SoilLayer(depth_mm=300.0, sat=0.5, dul=0.4, cll=0.2,
                                     adry=0.1, init_water=0.4, drainf=0.4))
        run_day(state, soil=soil)
        assert state.soldep == 600.0
        assert state.wl[3] == 0.0


class TestBalanceResetAtSowing:
    """iCrop.vba:1187-1198"""

    def test_dap1_moves_totals_to_pre_sowing_baselines(self):
        state = make_state()
        run_day(state)
        ce_before = state.ce
        state.dap = 1
        run_day(state)
        assert state.ce0 == ce_before
        assert state.ce == pytest.approx(state.sevp)  # restarted, then today's


class TestIrrigation:
    """iCrop.vba:1201-1248"""

    def test_auto_refills_root_zone_once_crop_is_up(self):
        state = make_state()
        mgmt = make_management(water=1, irg_level=0.99)
        run_day(state, management=mgmt)          # CBD=0: no irrigation yet
        assert state.irgw == 0.0
        state.cbd = 10.0
        run_day(state, management=mgmt)
        assert state.irgw > 0.0
        assert state.irgno == 1

    def test_auto_amount_is_negative_above_dul(self):
        """No lower bound on the water=1 amount (:1203), unlike water=3 (:1240)."""
        state = make_state()
        mgmt = make_management(water=1, irg_level=99.0)
        run_day(state, soil=make_soil(init_water=0.45), management=mgmt)
        state.cbd = 10.0
        run_day(state, soil=make_soil(init_water=0.45), management=mgmt)
        assert state.irgw < 0.0

    def test_rainfed_never_irrigates(self):
        state = make_state(cbd=10.0)
        run_day(state, management=make_management(water=2))
        assert state.irgw == 0.0

    def _scheduled(self, basis, events):
        return make_management(
            water=3,
            irrigation=IrrigationSchedule(
                timing_basis=basis,
                events=[IrrigationEvent(time=t, amount_mm=a) for t, a in events],
            ),
        )

    def test_dap_based(self):
        state = make_state()
        mgmt = self._scheduled(1, [(2, 40.0)])
        state.dap = 2
        run_day(state, management=mgmt)
        assert state.irgw == 40.0

    def test_doy_based(self):
        state = make_state(doy=100)
        run_day(state, management=self._scheduled(3, [(100, 25.0)]))
        assert state.irgw == 25.0

    def test_cbd_based_fires_once(self):
        state = make_state()
        mgmt = self._scheduled(2, [(10, 30.0)])
        run_day(state, management=mgmt)          # iniSW zeroes CBD (:1150)
        state.cbd = 12.0
        run_day(state, management=mgmt)
        assert state.irgw == 30.0
        run_day(state, management=mgmt)
        assert state.irgw == 0.0
        assert state.irgno == 1

    def test_cbd_based_automatic_amount_is_clipped_at_zero(self):
        state = make_state()
        soil, mgmt = make_soil(init_water=0.45), self._scheduled(4, [(10, 999.0)])
        run_day(state, soil=soil, management=mgmt)
        state.cbd = 12.0
        run_day(state, soil=soil, management=mgmt)
        assert state.irgw == 0.0
        assert state.irgno == 1

    def test_cbd_based_automatic_amount_refills_root_zone(self):
        state = make_state()
        soil, mgmt = make_soil(init_water=0.2), self._scheduled(4, [(10, 999.0)])
        run_day(state, soil=soil, management=mgmt)
        deficit = state.ttswrz - state.atswrz
        state.cbd = 12.0
        run_day(state, soil=soil, management=mgmt)
        assert state.irgw == pytest.approx(deficit)

    def test_same_day_events_last_amount_wins_each_counts(self):
        state = make_state(doy=100)
        run_day(state, management=self._scheduled(3, [(100, 25.0), (100, 10.0)]))
        assert state.irgw == 10.0
        assert state.irgno == 2


class TestDrainage:
    def test_drain_is_yesterdays_outflow_of_ldrain(self):
        """DRAIN reads FLOUT(LDRAIN) before today's update (:1251)."""
        state = make_state()
        soil = make_soil(init_water=0.45)
        run_day(state, soil=soil)
        yesterday = state.flout[soil.n_layers - 1]
        assert yesterday > 0.0
        run_day(state, soil=soil)
        assert state.drain == yesterday


class TestLdrain:
    def test_out_of_range_is_rejected(self):
        """VBA stops with "subscript out of range" (iCrop.vba:1251)."""
        with pytest.raises(ValueError, match="ldrain"):
            make_soil(ldrain=11)

    def test_zero_reads_empty_slot(self):
        state = make_state()
        soil = make_soil(init_water=0.45, ldrain=0)
        run_day(state, soil=soil)
        run_day(state, soil=soil)
        assert state.drain == 0.0


class TestRunoff:
    """iCrop.vba:1274-1297"""

    def test_only_rainfed_mode_has_runoff(self):
        for water, expect_runoff in ((2, True), (1, False)):
            state = make_state(rain=120.0)
            run_day(state, soil=make_soil(init_water=0.45),
                    management=make_management(water=water))
            assert (state.runof > 0) is expect_runoff

    def test_deep_first_layer_uses_layer_one_only(self):
        """Saturated 300 mm layer 1 over a dry layer 2: SWER = 0."""
        soil = make_soil(init_water=0.15)
        soil.layers[0] = SoilLayer(depth_mm=300.0, sat=0.5, dul=0.35, cll=0.15,
                                   adry=0.05, init_water=0.5, drainf=0.4)
        state = make_state(rain=30.0)
        run_day(state, soil=soil)
        s = 254 * (100 / 73 - 1)
        assert state.runof == pytest.approx(30.0 ** 2 / (30.0 + s))

    def test_shallow_first_layer_averages_layers_one_and_two(self):
        soil = make_soil(init_water=0.15)  # 200 mm layers, layer 2 dry
        soil.layers[0] = SoilLayer(depth_mm=200.0, sat=0.5, dul=0.35, cll=0.15,
                                   adry=0.05, init_water=0.5, drainf=0.4)
        state = make_state(rain=30.0)
        run_day(state, soil=soil)
        s = 254 * (100 / 73 - 1)
        swer = 0.15 * (0.0 * 0.5 + 1.0 * 0.5)
        assert state.runof == pytest.approx((30 - swer * s) ** 2 / (30 + (1 - swer) * s))


class TestSoilEvaporation:
    """iCrop.vba:1316-1324"""

    def test_first_day_is_stage_two_because_ftswrz_starts_at_zero(self):
        state = make_state()
        run_day(state)
        assert state.sevp == pytest.approx(state.pet * (math.sqrt(2) - 1))

    def test_large_rain_resets_to_stage_one(self):
        state = make_state()
        run_day(state)
        state.rain = 20.0
        run_day(state)
        assert state.sevp == pytest.approx(state.pet)  # FTSWRZ now >= 0.5

    def test_demand_left_by_layer_one_is_taken_from_deeper_layers(self):
        """Layer 1 can give at most (WL - WLAD) * DRAINF; a tiny DRAINF leaves
        nearly all the demand to layer 2 (:1355-1361)."""
        soil = make_soil(init_water=0.3)
        soil.layers[0] = SoilLayer(depth_mm=200.0, sat=0.5, dul=0.35, cll=0.15,
                                   adry=0.05, init_water=0.3, drainf=0.001)
        state = make_state(srad=30.0, tmax=30.0, tmin=15.0)
        run_day(state, soil=soil)
        assert state.sevp > 0.0
        assert state.wl[1] == pytest.approx(0.3 * 200.0 - (state.sevp - 0.05))


class TestTranspiration:
    def test_vpd_type_1_keeps_tr_from_dm_production(self):
        state = make_state(tr=1.7, ddmp=5.0)
        state.ini_sw = 0
        run_day(state, params=make_params(vpd_type=1))
        assert state.tr == 1.7

    def test_daily_tr_from_growth_and_vpd(self):
        state = make_state()
        run_day(state)            # initialise
        state.ddmp = 10.0
        run_day(state)
        assert state.tr == pytest.approx(10.0 * state.vpd / state.tec)


class TestDroughtSurvival:
    """iCrop.vba:1342-1349"""

    def _dry_day(self, params):
        state = make_state()
        soil = make_soil(init_water=0.16)
        run_day(state, params=params, soil=soil)
        state.lai, state.dayl, state.ddmp = 2.0, 12.0, 0.0
        run_day(state, params=params, soil=soil)
        return state

    def test_survival_transpiration_costs_leaf_area(self):
        state = self._dry_day(make_params(surviv=1, epcond=0.1, ltlrwc=0.55))
        vpd = state.vpd
        trsurv = 2.0 * 0.1 * vpd * 12.0 * 3600 * 0.0022 / (state.tmp + 273)
        assert state.tr == pytest.approx(trsurv)
        assert 0.0 < state.lai == pytest.approx(2.0 - trsurv / (9 * 0.45) * 0.02 * 1000)

    def test_vba_bug_vpd_type_1_survival_never_fires(self):
        """VPD is unassigned when vpd_type=1, so TRSURV is 0 (:1343)."""
        state = self._dry_day(make_params(surviv=1, epcond=5.0, ltlrwc=0.55, vpd_type=1))
        assert state.lai == 2.0


class TestStressFactors:
    """iCrop.vba:1400-1408"""

    def test_dry_root_zone_stresses_and_speeds_phenology(self):
        state = make_state()
        run_day(state, soil=make_soil(init_water=0.18))
        assert state.ftswrz < 0.3
        assert state.wsfg == pytest.approx(state.ftswrz / 0.3)
        assert state.wsfd == pytest.approx((1 - state.wsfg) * 0.5 + 1)

    def test_blank_wssn_gives_no_n_stress(self):
        state = make_state()
        run_day(state, params=make_params(wssn=0.0), soil=make_soil(init_water=0.18))
        assert state.wsfn == 1.0

    def test_waterlogging_kills_crop_after_fldkil_days(self):
        state = make_state(cbd=20.0)
        soil = make_soil(init_water=0.5)
        for layer in soil.layers:
            layer.drainf = 0.0
        params = make_params(fldkil=2.0)
        for _ in range(3):
            state.cbd = 20.0
            run_day(state, params=params, soil=soil)
        assert state.wsxf <= 0.02
        assert state.matyp == 5
        assert state.cbd == state.cbd_tsg


class TestRootGrowth:
    """iCrop.vba:1255-1271"""

    def test_roots_grow_only_while_crop_grows(self):
        state = make_state()
        run_day(state)
        state.cbd, state.bd, state.ddmp = 10.0, 1.0, 0.0
        run_day(state)
        assert state.deport == 200.0
        state.ddmp = 5.0
        run_day(state)
        assert state.deport == 230.0
        assert state.rtln == 2

    def test_roots_stop_at_meed(self):
        state = make_state()
        params = make_params(meed=210.0)
        run_day(state, params=params)
        state.cbd, state.bd, state.ddmp = 10.0, 1.0, 5.0
        for _ in range(3):
            run_day(state, params=params)
        assert state.deport == 230.0  # one step past 200, then DEPORT >= MEED

    def test_roots_stop_after_begin_seed_growth(self):
        state = make_state()
        run_day(state)
        state.cbd, state.bd, state.ddmp = 41.0, 1.0, 5.0  # cbd_bsg = 40
        run_day(state)
        assert state.deport == 200.0


class TestSeasonCarryOver:
    """Globals the VBA does not reset between seasons (SEASON_CARRY_FIELDS)."""

    def test_second_season_first_day_drains_last_seasons_outflow(self):
        from ssm_icrop.inputs import load_crop_params, load_scenario
        from ssm_icrop.model import _run_season, _soil_water_inputs, build_params
        from ssm_icrop.weather import load_weather

        sc = load_scenario(REPO_ROOT / "configs" / "example" / "gorgan_wheat_waterlim.yaml")
        params = build_params(load_crop_params(sc.crop_file), sc.location)
        previous = SimState()
        previous.flout[sc.soil.n_layers - 1] = 3.5   # LDRAIN = 5
        previous.ftswrz = 0.9                        # first day stage 1, not 2
        records, _ = _run_season(
            weather_df=load_weather(sc.location.weather_file), params=params,
            lat=sc.location.latitude, pyear=2005, simdoy=340, pdoy=348,
            pden=386.0, water=2, nitrogen=0,
            soil_water=_soil_water_inputs(params, sc.soil, sc.management),
            previous=previous,
        )
        assert records[0]["drain"] == 3.5
        assert records[0]["sevp"] == pytest.approx(records[0]["pet"])
