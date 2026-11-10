"""Tests for the soil N module.

The spin-up days of the two nitrogen=2 reference scenarios are verified
against the reference output in test_verification.py: initialisation,
mineralization, DOY-based fertilizer, leaching and available N. These tests
call step_soil_n on hand-set soil water state and cover what those days do
not run: the DAP 1 reset, denitrification, plant uptake, the DAP- and
CBD-based and automatic N applications, and the concentration thresholds.
"""

import math

import pytest

from ssm_icrop.inputs import (
    AutoNitrogen,
    ManagementConfig,
    NitrogenEvent,
    NitrogenSchedule,
    SoilConfig,
    SoilLayer,
)
from ssm_icrop.soil_n import step_soil_n
from ssm_icrop.state import SimState

# Layers of 200 mm: WLLL = 30, WLUL = 70, WLST = 100 mm.
DEPTH = 200.0


def make_soil(n_layers: int = 3, **layer_overrides) -> SoilConfig:
    layer = dict(depth_mm=DEPTH, sat=0.5, dul=0.35, cll=0.15, adry=0.05,
                 init_water=0.3, drainf=0.4,
                 coarse_fraction=0.0, bulk_density=1.25, organic_n_pct=0.1,
                 min_fraction=0.1, init_no3=10.0)
    layer.update(layer_overrides)
    return SoilConfig(name="test", n_layers=n_layers, ldrain=n_layers, salb=0.13,
                      cn=73.0, layers=[SoilLayer(**layer) for _ in range(n_layers)])


def make_management(schedule: NitrogenSchedule | None = None) -> ManagementConfig:
    if schedule is None:
        schedule = NitrogenSchedule(
            timing_basis=1, events=[NitrogenEvent(time=999, amount=5.0,
                                                  volatilization_fraction=10.0)])
    return ManagementConfig(
        name="test", plant_year=2000, sim_years=1, fix_find=0, sim_doy=1, pdoy=5,
        lpdoy=365, stop_doy=400, sow_tmp=5.0, sow_wat=0.5, plant_density=300.0,
        water=2, nitrogen=2, irg_level=0.5, nitrogen_schedule=schedule,
    )


def make_state(wl: float = 60.0, n_layers: int = 3, **overrides) -> SimState:
    """Soil water as SoilWater would leave it: no drainage, roots in layer 1."""
    state = SimState()
    state.tmp = 20.0
    for i in range(n_layers):
        state.wl[i] = wl
        state.atsw[i] = wl - 30.0
        state.ftsw[i] = (wl - 30.0) / 40.0
    state.rlyer[0] = DEPTH
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


def run_day(state, soil=None, management=None):
    step_soil_n(state, soil or make_soil(), management or make_management())


class TestInitialisation:
    """iCrop.vba:1577-1618"""

    def test_pools_from_soil_sheet(self):
        state = make_state()
        state.ftsw = [1.0] * 10      # RN = 0: no mineralization on day 1
        run_day(state)
        soilml = DEPTH * 1.25 * 1000
        assert state.mnorg[0] == pytest.approx(0.1 * 0.01 * soilml * 0.1)
        assert state.insol[0] == 1.0                       # 10 kg N ha-1 = 1 g N m-2
        assert state.isoln == pytest.approx(3.0)
        assert state.ini_snb == 1

    def test_coarse_fraction_reduces_organic_n(self):
        state = make_state()
        state.ftsw = [1.0] * 10
        run_day(state, soil=make_soil(coarse_fraction=0.25))
        assert state.mnorg[0] == pytest.approx(DEPTH * 1.25 * 0.75 * 1000 * 1e-4)

    def test_top_600_mm_takes_a_straddling_layer_pro_rata(self):
        """Layers 0-250, 250-500, 500-750 mm: half of the third layer counts."""
        state = make_state()
        state.ftsw = [1.0] * 10
        run_day(state, soil=make_soil(depth_mm=250.0))
        assert state.cnsol60 == pytest.approx(1.0 + 1.0 + 1.0 * 100 / 250)

    def test_runs_once_per_season(self):
        state = make_state()
        run_day(state)
        state.nsol[0] = 0.5
        run_day(state)
        assert state.insol[0] == 1.0
        assert state.nsol[0] != 1.0


class TestMineralization:
    """iCrop.vba:1627-1642"""

    @staticmethod
    def first_day_nmin(ftsw: float, tmp: float = 20.0) -> float:
        state = make_state(tmp=tmp)
        state.ftsw[0] = ftsw
        run_day(state)
        return state.snmin

    def expected(self, rn: float, tmp: float = 20.0) -> float:
        kn = 24 * math.exp(17.753 - 6350.5 / (min(tmp, 35.0) + 273)) / 168
        mnorg = 0.1 * 0.01 * DEPTH * 1.25 * 1000 * 0.1
        ncon = 1.0 / (60.0 * 1000)
        return mnorg * rn * (1 - math.exp(-kn)) * (0.0002 - ncon) / 0.0002

    @pytest.mark.parametrize("ftsw,rn", [(0.45, 1.111 * 0.45), (0.9, 1.0),
                                         (0.95, 0.5), (1.0, 0.0), (1.2, 0.0),
                                         (-0.1, 0.0)])
    def test_water_factor(self, ftsw, rn):
        """Only layer 1 differs from FTSW = 0.75; the others add a constant."""
        base = self.first_day_nmin(1.0)   # layer 1 contributes 0
        assert self.first_day_nmin(ftsw) - base == pytest.approx(self.expected(rn))

    def test_temperature_capped_at_35(self):
        assert self.first_day_nmin(0.75, tmp=40.0) == self.first_day_nmin(0.75, tmp=35.0)

    def test_stops_at_200_mg_per_litre(self):
        state = make_state()
        run_day(state, soil=make_soil(init_no3=0.0002 * 60.0 * 1000 * 10))
        assert state.snmin == 0.0

    def test_depletes_mineralizable_pool(self):
        state = make_state()
        run_day(state)
        mnorg0 = 0.1 * 0.01 * DEPTH * 1.25 * 1000 * 0.1
        assert sum(state.mnorg[:3]) == pytest.approx(3 * mnorg0 - state.snmin)


class TestResetAtSowing:
    """iCrop.vba:1620-1624"""

    def test_three_sums_reset_two_kept(self):
        schedule = NitrogenSchedule(timing_basis=1, events=[
            NitrogenEvent(time=0, amount=2.0, volatilization_fraction=10.0)])
        management = make_management(schedule)
        state = make_state()
        state.flout = [1.0] * 10
        run_day(state, management=management)          # spin-up day, DAP 0
        cnmin, cnleach = state.cnmin, state.cnleach
        state.dap = 1
        run_day(state, management=management)
        assert state.cnmin0 == cnmin and state.cnleach0 == cnleach
        assert state.cnmin == state.snmin
        assert state.cnleach == state.nleach
        assert state.cnfert == 2.0 and state.cnvol == pytest.approx(0.2)


class TestScheduledApplication:
    """iCrop.vba:1646-1670, 1688-1689"""

    def test_volatilization_fraction_is_per_cent(self):
        schedule = NitrogenSchedule(timing_basis=3, events=[
            NitrogenEvent(time=100, amount=2.3, volatilization_fraction=2.0)])
        state = make_state(doy=100)
        run_day(state, management=make_management(schedule))
        assert state.nfert == 2.3
        assert state.nvol == pytest.approx(0.046)

    def test_fertilizer_enters_layer_one(self):
        schedule = NitrogenSchedule(timing_basis=3, events=[
            NitrogenEvent(time=100, amount=2.0, volatilization_fraction=10.0)])
        with_n, without = make_state(doy=100), make_state(doy=101)
        run_day(with_n, management=make_management(schedule))
        run_day(without, management=make_management(schedule))
        assert with_n.nsol[0] - without.nsol[0] == pytest.approx(1.8)
        assert with_n.nsol[1] == without.nsol[1]

    def test_dap_zero_event_fires_on_every_spinup_day(self):
        """No applied-flag for DAP timing; DAP is 0 on all spin-up days."""
        schedule = NitrogenSchedule(timing_basis=1, events=[
            NitrogenEvent(time=0, amount=1.0, volatilization_fraction=0.0)])
        state = make_state()
        for _ in range(3):
            run_day(state, management=make_management(schedule))
        assert state.cnfert == 3.0

    def test_cbd_events_due_together_apply_only_the_last(self):
        """NFERT is assigned, not added; both events are flagged as applied."""
        schedule = NitrogenSchedule(timing_basis=2, events=[
            NitrogenEvent(time=5.0, amount=1.0, volatilization_fraction=0.0),
            NitrogenEvent(time=6.0, amount=3.0, volatilization_fraction=0.0)])
        management = make_management(schedule)
        state = make_state(cbd=7.0)
        run_day(state, management=management)
        assert state.nfert == 3.0
        assert state.nfa01 == [1, 1]
        run_day(state, management=management)
        assert state.nfert == 0.0
        assert state.cnfert == 3.0


class TestAutomaticApplication:
    """iCrop.vba:1671-1686"""

    AUTO = AutoNitrogen(ntrsh0=10.0, nvolf0=2.0, bd_bfrt=4.0, bd_tfrt=28.0,
                        frtwat=30.0, ntrsh1=18.0, napply1=7.0, nvolf1=10.0)

    def management(self):
        return make_management(NitrogenSchedule(timing_basis=4, auto=self.AUTO))

    def test_tops_up_top_600_mm_at_dap_1(self):
        state = make_state()
        run_day(state, management=self.management())    # init: CNSOL60 about 3
        cnsol60 = state.cnsol60
        state.dap = 1
        run_day(state, management=self.management())
        assert state.nfert == pytest.approx(10.0 - cnsol60)
        assert state.nvol == pytest.approx(0.02 * state.nfert)

    @pytest.mark.parametrize("cbd,atswrz,applied", [
        (10.0, 50.0, True), (4.0, 50.0, False), (28.0, 50.0, False), (10.0, 30.0, False)])
    def test_top_dressing_window(self, cbd, atswrz, applied):
        state = make_state(dap=20, cbd=cbd, atswrz=atswrz)
        run_day(state, management=self.management())
        assert state.nfert == (7.0 if applied else 0.0)


class TestDownwardMovement:
    """iCrop.vba:1692-1698"""

    def test_moves_with_drainage_and_leaches_from_last_layer(self):
        state = make_state()
        state.ftsw = [1.0] * 10
        state.flout = [20.0] * 10
        run_day(state)
        share = 20.0 / (60.0 + 20.0)
        assert state.nleach == pytest.approx(1.0 * share)
        # layer 2 receives what layer 1 lost and loses the same share
        assert state.nsol[1] == pytest.approx(1.0 + share - share)
        assert state.nsol[0] == pytest.approx(1.0 - share)

    def test_nothing_moves_at_or_below_1_mg_per_litre(self):
        state = make_state()
        state.ftsw = [1.0] * 10
        state.flout = [20.0] * 10
        run_day(state, soil=make_soil(init_no3=0.000001 * 60.0 * 1000 * 10))
        assert state.nleach == 0.0


class TestDenitrification:
    """iCrop.vba:1701-1722"""

    def wet_state(self, n_layers: int = 3) -> SimState:
        state = make_state(wl=85.0, n_layers=n_layers)   # halfway DUL -> SAT
        return state

    def expected_layer(self, ncon: float, wl: float = 85.0, tmp: float = 20.0) -> float:
        kdnit = 6 * math.exp(0.07735 * tmp - 6.593)
        return min(ncon, 0.0004) * (1 - math.exp(-kdnit)) * wl * 1000 * 0.5

    def test_only_layers_one_and_two_above_field_capacity(self):
        state = self.wet_state()
        run_day(state)
        ncon = 1.0 / (85.0 * 1000)
        assert state.sndnit == pytest.approx(2 * self.expected_layer(ncon))

    def test_none_at_field_capacity(self):
        state = make_state(wl=70.0)
        run_day(state)
        assert state.sndnit == 0.0

    def test_thick_first_layer_switches_off_layer_two(self):
        state = make_state(wl=85.0 * 260 / 200)
        state.rlyer[0] = 260.0
        run_day(state, soil=make_soil(depth_mm=260.0))
        ncon = 1.0 / (85.0 * 1.3 * 1000)
        assert state.sndnit == pytest.approx(self.expected_layer(ncon, wl=85.0 * 1.3))

    def test_concentration_capped_at_400_mg_per_litre(self):
        state = self.wet_state(n_layers=1)
        soil = make_soil(n_layers=1, init_no3=0.001 * 85.0 * 1000 * 10)
        run_day(state, soil=soil)
        assert state.sndnit == pytest.approx(self.expected_layer(0.0004))


class TestPlantUptake:
    """iCrop.vba:1725-1744"""

    def test_available_n_only_in_rooted_part(self):
        state = make_state()
        state.ftsw = [1.0] * 10
        state.rlyer[1] = DEPTH / 2
        run_day(state)
        ncon = 1.0 / (60.0 * 1000)
        assert state.navl[0] == pytest.approx((ncon - 1e-6) * 30.0 * 1000)
        assert state.navl[1] == pytest.approx(state.navl[0] / 2)
        assert state.navl[2] == 0.0
        assert state.snavl == pytest.approx(1.5 * state.navl[0])

    def test_uptake_split_by_yesterdays_available_n(self):
        state = make_state()
        state.ftsw = [1.0] * 10
        state.rlyer[1] = DEPTH / 2
        run_day(state)
        before = list(state.nsol[:3])
        state.nup, state.bnf = 0.3, 0.06
        run_day(state)
        taken = [b - a for b, a in zip(before, state.nsol[:3])]
        assert taken[0] == pytest.approx(2 * taken[1])
        assert taken[2] == 0.0
        assert sum(taken) == pytest.approx(0.24, rel=1e-5)   # SNAVL + 1e-6


class TestMassBalance:
    def test_profile_change_equals_fluxes(self):
        schedule = NitrogenSchedule(timing_basis=3, events=[
            NitrogenEvent(time=100, amount=2.0, volatilization_fraction=10.0)])
        management = make_management(schedule)
        state = make_state(wl=85.0, doy=99)
        state.flout = [5.0] * 10
        state.rlyer[1] = DEPTH
        run_day(state, management=management)
        start, snavl = state.cnsol, state.snavl
        state.doy, state.nup = 100, 0.1
        run_day(state, management=management)
        uptake = snavl / (snavl + 1e-6) * 0.1
        change = (state.nfert - state.nvol + state.snmin - state.nleach
                  - state.sndnit - uptake)
        assert state.cnsol - start == pytest.approx(change, abs=1e-6)


def test_nitrogen_needs_a_water_balance():
    """iCrop.vba:1598 divides by WL, which stays 0 when SoilWater never runs."""
    schedule = NitrogenSchedule(timing_basis=1, events=[
        NitrogenEvent(time=1, amount=1.0, volatilization_fraction=0.0)])
    with pytest.raises(ValueError, match="water=0"):
        ManagementConfig(
            name="test", plant_year=2000, sim_years=1, fix_find=0, sim_doy=1, pdoy=5,
            lpdoy=365, stop_doy=400, sow_tmp=5.0, sow_wat=0.5, plant_density=300.0,
            water=0, nitrogen=2, irg_level=0.5, nitrogen_schedule=schedule,
        )


class TestSeasonCarryOver:
    """NAVL, SNAVL, NUP and BNF survive into the next season (soil_n.SEASON_CARRY_FIELDS)."""

    def test_spinup_removes_last_seasons_uptake(self):
        from pathlib import Path

        from ssm_icrop.inputs import load_crop_params, load_scenario
        from ssm_icrop.model import _run_season, _soil_water_inputs, build_params
        from ssm_icrop.weather import load_weather

        config = load_scenario(Path(__file__).parent.parent / "configs" / "example"
                               / "gorgan_wheat_taj1.yaml")
        params = build_params(load_crop_params(config.crop_file), config.location)
        weather = load_weather(config.location.weather_file)

        def first_day(previous):
            records, _ = _run_season(
                weather_df=weather, params=params, lat=config.location.latitude,
                pyear=2005, simdoy=340, pdoy=348, pden=386.0, water=3, nitrogen=2,
                max_days=1, previous=previous,
                soil_water=_soil_water_inputs(params, config.soil, config.management),
            )
            return records[0]

        previous = SimState()
        previous.navl[0], previous.snavl = 1.0, 1.0
        previous.nup, previous.bnf = 0.5, 0.1
        removed = first_day(None)["cnsol"] - first_day(previous)["cnsol"]
        assert removed == pytest.approx(0.4 * 1.0 / (1.0 + 1e-6))
