"""Integration tests for the potential-production daily loop."""

import pandas as pd

from ssm_icrop.crop_lai import LAIParams
from ssm_icrop.dm_distribution import DMDistributionParams
from ssm_icrop.dm_production import DMProductionParams
from ssm_icrop.model import run_potential_production
from ssm_icrop.phenology import WheatParams


def make_fast_weather(n_days: int = 200) -> pd.DataFrame:
    """Synthetic weather warm enough to reach maturity quickly, for fast tests."""
    return pd.DataFrame({
        "year": [2000] * n_days,
        "doy": list(range(1, n_days + 1)),
        "srad": [20.0] * n_days,
        "tmax": [28.0] * n_days,
        "tmin": [15.0] * n_days,
        "rain": [0.0] * n_days,
    })


def make_fast_wheat_params() -> WheatParams:
    """Small stage thresholds so the crop matures within the synthetic window."""
    return WheatParams(
        tbd=0.0, tp1d=20.0, tp2d=25.0, tcd=35.0,
        vdsat=0.0, vsen=0.0,  # no vernalization required
        cpp=24.0, ppsen=0.0,  # photoperiod-insensitive
        bd_sowemr=2.0, bd_emrtil=3.0, bd_tilsel=3.0, bd_selbot=3.0,
        bd_botear=3.0, bd_earant=3.0, bd_antpm=8.0, bd_pmhm=2.0,
    )


def make_fast_lai_params() -> LAIParams:
    return LAIParams(
        phyl=20.0, placon=1.0, plapow=1.5, a_pla_den=1.0, b_pla_den=0.0,
        sla=0.02, frztkil=-5.0, frzldr=0.01, htlth=38.0, htldr=0.05,
    )


def make_fast_dm_production_params() -> DMProductionParams:
    return DMProductionParams(
        irue=3.0, kpar=0.5, tbrue=0.0, tp1rue=15.0, tp2rue=25.0, tcrue=35.0,
        vpd_type=0, co2=350.0, co2_ref=350.0, co2_res=0.0, tec_ref=6.0,
    )


def make_fast_dm_distribution_params() -> DMDistributionParams:
    return DMDistributionParams(
        flf1a=0.6, flf1b=0.3, wtopl=160.0, flf2=0.1, frtrl=0.2, gcc=1.3,
        pdhi=0.02, wdhi1=0.0, wdhi2=50.0, wdhi3=1000.0, wdhi4=2000.0,
        heat=0,
    )


class TestRunPotentialProduction:
    def test_produces_one_row_per_day(self):
        weather_df = make_fast_weather()
        daily = run_potential_production(
            weather_df=weather_df, lat=36.85, pyear=2000, simdoy=1, pdoy=5,
            crop_type="WHEAT",
            phenology_params=make_fast_wheat_params(),
            lai_params=make_fast_lai_params(),
            dm_production_params=make_fast_dm_production_params(),
            dm_distribution_params=make_fast_dm_distribution_params(),
            pden=300.0,
        )
        # simdoy=1 is consumed unsimulated; DOY 2-5 (sowing) are spin-up days
        assert list(daily["doy"].iloc[:4]) == [2, 3, 4, 5]
        assert list(daily["dap"].iloc[:4]) == [0, 0, 0, 0]
        crop = daily["dap"].iloc[4:]
        assert list(crop) == list(range(1, len(crop) + 1))

    def test_reaches_maturity_within_window(self):
        weather_df = make_fast_weather()
        daily = run_potential_production(
            weather_df=weather_df, lat=36.85, pyear=2000, simdoy=1, pdoy=5,
            crop_type="WHEAT",
            phenology_params=make_fast_wheat_params(),
            lai_params=make_fast_lai_params(),
            dm_production_params=make_fast_dm_production_params(),
            dm_distribution_params=make_fast_dm_distribution_params(),
            pden=300.0,
        )
        assert daily["mat"].iloc[-1] == 1
        assert daily["matyp"].iloc[-1] == 1

    def test_biomass_and_grain_are_positive_and_plausible(self):
        weather_df = make_fast_weather()
        daily = run_potential_production(
            weather_df=weather_df, lat=36.85, pyear=2000, simdoy=1, pdoy=5,
            crop_type="WHEAT",
            phenology_params=make_fast_wheat_params(),
            lai_params=make_fast_lai_params(),
            dm_production_params=make_fast_dm_production_params(),
            dm_distribution_params=make_fast_dm_distribution_params(),
            pden=300.0,
        )
        final = daily.iloc[-1]
        assert final["wtop"] > 0.0
        assert final["wgrn"] > 0.0
        assert 0.0 < final["hi"] < 1.0  # harvest index must be a real fraction
        assert daily["lai"].max() > 0.0

    def test_lai_rises_then_falls(self):
        """Canopy should have a single growth-then-senescence peak, not
        monotonic growth or immediate collapse."""
        weather_df = make_fast_weather()
        daily = run_potential_production(
            weather_df=weather_df, lat=36.85, pyear=2000, simdoy=1, pdoy=5,
            crop_type="WHEAT",
            phenology_params=make_fast_wheat_params(),
            lai_params=make_fast_lai_params(),
            dm_production_params=make_fast_dm_production_params(),
            dm_distribution_params=make_fast_dm_distribution_params(),
            pden=300.0,
        )
        peak_idx = daily["lai"].idxmax()
        assert peak_idx > 0  # not immediately at sowing
        assert peak_idx < len(daily) - 1  # not still rising at maturity
        assert daily["lai"].iloc[-1] < daily["lai"].max()  # senesced by the end

    def test_stops_at_max_days_if_never_matures(self):
        """A crop that can never reach cbd_mat stops at max_days, not forever."""
        weather_df = make_fast_weather(n_days=100)
        params = make_fast_wheat_params()
        params.bd_antpm = 10_000.0  # unreachable within the weather window
        daily = run_potential_production(
            weather_df=weather_df, lat=36.85, pyear=2000, simdoy=1, pdoy=5,
            crop_type="WHEAT",
            phenology_params=params,
            lai_params=make_fast_lai_params(),
            dm_production_params=make_fast_dm_production_params(),
            dm_distribution_params=make_fast_dm_distribution_params(),
            pden=300.0,
            max_days=30,
        )
        assert daily["dap"].max() == 30
        assert daily["mat"].iloc[-1] == 0
