"""Verify the Python port against the reference output of the original VBA model.

Reference output (golden master): data/verification/2022-05-29/wheat_gorgan_reference_output.csv,
exported from the verification workbook SSM_iCrop__2022_05_29_verification.xlsm
via openpyxl at full float precision -- NOT the spreadsheet application's own
CSV export, which rounds to each column's display format. docs/verification.md
describes how the reference run was set up and what it covers.

Wheat cultivar "Tajan" (Crop sheet column D) at Gorgan, sown DOY 348 2005
(the "Taj1" management config). Two scenarios are checked:

- "Taj1-Potential" (water=0, nitrogen=0), from hand-transcribed literals;
- "Taj1-WaterLim" (water=2, rainfed), from configs/example/gorgan_wheat_waterlim.yaml.

The N-limited ("Taj1-Nlim") and full-model ("Taj1 Arab") scenarios in the same
file are compared up to emergence only: their spin-up days and DAP 1-8. From
emergence on they need PlantN and CropLAIN. When those are built, add a test
class per scenario the same way, loading the matching sName slice.

Spin-up rows (DAP=0, the days up to sowing) carry only the soil water balance.
Their crop columns are not compared: the reference run computed all four
scenarios in one macro run, and VBA globals carry over, so those columns hold the previous
scenario's end-of-season values (WTOP=1404.96 from "Taj1-Potential" on every
"Taj1-WaterLim" spin-up row).
"""

from pathlib import Path

import pandas as pd
import pytest

from ssm_icrop.crop_lai import LAIParams
from ssm_icrop.dm_distribution import DMDistributionParams
from ssm_icrop.dm_production import DMProductionParams
from ssm_icrop.inputs import load_crop_params, load_scenario
from ssm_icrop.model import (
    _run_season,
    _soil_water_inputs,
    build_params,
    run_potential_production,
    run_simulation,
)
from ssm_icrop.phenology import WheatParams
from ssm_icrop.soil_water import SoilWaterParams
from ssm_icrop.weather import load_weather

REPO_ROOT = Path(__file__).parent.parent
REFERENCE_OUTPUT_CSV = (
    REPO_ROOT / "data" / "verification" / "2022-05-29" / "wheat_gorgan_reference_output.csv"
)

# --- Wheat "Tajan", Crop sheet column D (Taj1 Arab's cultivar) ---
TAJAN_PHENOLOGY = WheatParams(
    tbd=0.0, tp1d=27.5, tp2d=30.0, tcd=40.0,  # tp2d unused (blank in sheet)
    tbver=-1.0, tp1ver=0.0, tp2ver=8.0, tcver=12.0,
    vdsat=50.0, vsen=0.00089,
    cpp=21.0, ppsen=0.001467,
    bd_sowemr=3.5, bd_emrtil=4.95, bd_tilsel=11.4, bd_selbot=6.0,
    bd_botear=2.0, bd_earant=8.0, bd_antpm=34.0, bd_pmhm=8.0,
)

TAJAN_LAI = LAIParams(
    phyl=95.0, placon=1.0, plapow=2.4336,
    a_pla_den=1.1718, b_pla_den=-0.0006,
    sla=0.021, frztkil=-5.0, frzldr=0.01, htlth=30.0, htldr=0.1,
)

TAJAN_DM_PRODUCTION = DMProductionParams(
    irue=2.42, kpar=0.65,
    tbrue=0.0, tp1rue=15.0, tp2rue=22.0, tcrue=35.0,
    vpd_type=0, vpd_threshold=2.0, vpdf=0.63,
    co2=385.0, co2_ref=385.0, co2_res=0.8,
    tec_ref=5.8,
)

TAJAN_DM_DISTRIBUTION = DMDistributionParams(
    flf1a=0.6, flf1b=0.3, wtopl=160.0, flf2=0.1,
    frtrl=0.22, gcc=1.0, pdhi=0.01638,
    wdhi1=0.0, wdhi2=600.0, wdhi3=1200.0, wdhi4=3200.0,
    sncs=0.0063, mc=14.0,
    heat=1, tp2h=31.0, tch=40.0, tp1f=0.0, tbf=-5.0, rfmax=0.3,
)

# Crop rows 46-59, 24-25. WSSN, EPCOND and LTLRWC are blank (read as 0).
TAJAN_SOIL_WATER = SoilWaterParams(
    deport=200.0, meed=1000.0, grtdp=30.0,
    tec_ref=5.8, co2_res=0.8, co2_ref=385.0,
    wssg=0.3, wssl=0.4, wssd=0.5, wssn=0.0,
    fldkil=99.0, vpd_type=0, surviv=0, epcond=0.0, ltlrwc=0.0,
    vpdf=0.63, co2=385.0,
)

LAT = 36.85
PDEN = 386.0
PYEAR = 2005
SIMDOY = 340
PDOY = 348

# VBA column name -> our daily DataFrame column name
VBA_TO_PY = {
    "TMP": "tmp", "RAIN": "rain", "DTU": "dtu", "CBD": "cbd", "MSNN": "msnn",
    "GLAI": "glai", "DLAI": "dlai", "LAI": "lai", "FINT": "fint",
    "DDMP": "ddmp", "GLF": "glf", "GST": "gst", "SGR": "sgr",
    "WLF": "wlf", "WST": "wst", "WVEG": "wveg", "WGRN": "wgrn", "WTOP": "wtop",
}

# One absolute tolerance for every column of every scenario. The port matches
# the reference output to about 1e-9 (WTOP: < 1e-12 potential, 1.4e-9 rainfed);
# 1e-6 only absorbs floating-point accumulation. A looser per-column tolerance
# could let a small consequential error through.
ATOL = 1e-6

# Up to emergence the nitrogen=2 scenarios need neither PlantN nor CropLAIN,
# and they match the reference to within 1e-14 (Taj1 Arab: 0.0) with the soil
# doubles from configs/soils/. 1e-12 keeps room for platform differences in
# exp/log, which SoilN's mineralization uses, and catches what 1e-6 would not.
PRE_EMERGENCE_ATOL = 1e-12


def _load_vba_reference(scenario: str) -> pd.DataFrame:
    df = pd.read_csv(REFERENCE_OUTPUT_CSV)
    df = df[df["sName"] == scenario].copy()
    df = df[df["DAP"] > 0]  # drop spin-up rows (DAP=0, before sowing)
    df["DAP"] = df["DAP"].astype(int)
    df = df.rename(columns=VBA_TO_PY)
    return df.set_index("DAP")


def _load_vba_all_days(scenario: str) -> pd.DataFrame:
    """Every row of a scenario, spin-up included, in output order."""
    df = pd.read_csv(REFERENCE_OUTPUT_CSV)
    df = df[df["sName"] == scenario].reset_index(drop=True)
    # DRAIN is blank on the first spin-up day: FLOUT is still unassigned
    return df.rename(columns={**VBA_TO_PY, **VBA_WATER_TO_PY}).fillna({"drain": 0.0})


# SoilWater's columns in DailyPrintOut (Sheet4 columns 27-43; RAIN is in VBA_TO_PY)
VBA_WATER_TO_PY = {
    "DEPORT": "deport", "IRGW": "irgw", "RUNOF": "runof", "PET": "pet",
    "SEVP": "sevp", "TR": "tr", "DRAIN": "drain", "ATSWRZ": "atswrz",
    "FTSWRZ": "ftswrz", "CRAIN": "crain", "CIRGW": "cirgw", "IRGNO": "irgno",
    "CRUNOF": "crunof", "CE": "ce", "CTR": "ctr", "CDRAIN": "cdrain",
}



@pytest.fixture(scope="module")
def taj1_potential_run() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the Python potential-production model and load the matching VBA slice."""
    weather_df = load_weather(REPO_ROOT / "data" / "weather" / "gorgan.csv")
    py_daily = run_potential_production(
        weather_df=weather_df,
        lat=LAT, pyear=PYEAR, simdoy=SIMDOY, pdoy=PDOY,
        crop_type="WHEAT",
        phenology_params=TAJAN_PHENOLOGY,
        lai_params=TAJAN_LAI,
        dm_production_params=TAJAN_DM_PRODUCTION,
        dm_distribution_params=TAJAN_DM_DISTRIBUTION,
        pden=PDEN,
    )
    py_daily = py_daily[py_daily["dap"] > 0].set_index("dap")
    vba_daily = _load_vba_reference("Taj1-Potential")
    return py_daily, vba_daily


class TestPotentialProductionAgainstVBA:
    def test_same_season_length(self, taj1_potential_run):
        py_daily, vba_daily = taj1_potential_run
        assert len(py_daily) == len(vba_daily)
        assert py_daily.index.max() == vba_daily.index.max()

    @pytest.mark.parametrize("col", list(VBA_TO_PY.values()))
    def test_column_matches_vba(self, taj1_potential_run, col):
        py_daily, vba_daily = taj1_potential_run
        common_dap = py_daily.index.intersection(vba_daily.index)
        assert len(common_dap) > 100  # sanity: most of the season overlaps

        py_vals = py_daily.loc[common_dap, col]
        vba_vals = vba_daily.loc[common_dap, col]
        diff = (py_vals - vba_vals).abs()

        max_diff = diff.max()
        max_diff_dap = diff.idxmax()
        assert max_diff <= ATOL, (
            f"{col} diverges from VBA by {max_diff:.4f} at DAP={max_diff_dap} "
            f"(python={py_vals.loc[max_diff_dap]:.4f}, "
            f"vba={vba_vals.loc[max_diff_dap]:.4f})"
        )


@pytest.fixture(scope="module")
def taj1_waterlim_run() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the rainfed scenario from its config, with every VBA row."""
    scenario = load_scenario(REPO_ROOT / "configs" / "example" / "gorgan_wheat_waterlim.yaml")
    py_daily = run_simulation(scenario).daily
    vba_daily = _load_vba_all_days("Taj1-WaterLim")
    return py_daily, vba_daily


def _assert_matches(py: pd.Series, vba: pd.Series, dap: pd.Series, atol: float) -> None:
    diff = (py - vba).abs()
    worst = diff.idxmax()
    assert diff.max() <= atol, (
        f"{py.name} diverges from VBA by {diff.max():.3g} at row {worst} "
        f"(DAP={dap[worst]}, python={py[worst]:.6g}, vba={vba[worst]:.6g})"
    )


class TestWaterLimitedAgainstVBA:
    def test_soil_water_params_from_config(self):
        """The generated crop YAML yields the literal parameters above."""
        scenario = load_scenario(
            REPO_ROOT / "configs" / "example" / "gorgan_wheat_waterlim.yaml"
        )
        params = build_params(load_crop_params(scenario.crop_file), scenario.location)
        assert params.soil_water == TAJAN_SOIL_WATER

    def test_same_days(self, taj1_waterlim_run):
        """181 rows: 8 spin-up days, then a season four days shorter than the
        potential one, because drought speeds up grain filling (WSFD)."""
        py_daily, vba_daily = taj1_waterlim_run
        assert len(py_daily) == len(vba_daily) == 181
        assert list(py_daily["doy"]) == list(vba_daily["DOY"])
        assert list(py_daily["dap"]) == list(vba_daily["DAP"])

    @pytest.mark.parametrize("col", list(VBA_WATER_TO_PY.values()))
    def test_water_column_matches_vba_every_day(self, taj1_waterlim_run, col):
        py_daily, vba_daily = taj1_waterlim_run
        _assert_matches(py_daily[col], vba_daily[col], vba_daily["DAP"], ATOL)

    @pytest.mark.parametrize("col", list(VBA_TO_PY.values()))
    def test_crop_column_matches_vba(self, taj1_waterlim_run, col):
        py_daily, vba_daily = taj1_waterlim_run
        crop = vba_daily["DAP"] > 0
        _assert_matches(
            py_daily.loc[crop, col], vba_daily.loc[crop, col], vba_daily["DAP"], ATOL
        )


# SoilN's columns in DailyPrintOut (Sheet4 columns 44-55)
VBA_SOIL_N_TO_PY = {
    "NFERT": "nfert", "CNFERT": "cnfert", "NVOL": "nvol", "CNVOL": "cnvol",
    "NLEACH": "nleach", "CNLEACH": "cnleach", "NMIN": "snmin", "CNMIN": "cnmin",
    "NDNIT": "sndnit", "CNDNIT": "cndnit", "SNAVL": "snavl", "NSOL": "cnsol",
}


@pytest.mark.parametrize(
    "scenario,water,irg_level",
    [("Taj1 Arab", 3, 0.5), ("Taj1-Nlim", 1, float("inf"))],  # see docs/verification.md
)
def test_irrigated_nitrogen_scenarios_up_to_emergence(scenario, water, irg_level):
    """The two nitrogen=2 scenarios, from the first spin-up day to DAP 8.

    Only these rows are comparable until PlantN and CropLAIN are ported. The
    crop emerges on DAP 9; until then LAI = 0 and PlantN takes up nothing
    (NUP = 0, iCrop.vba:1435-1436), so the port's PlantN-less stand-in gives
    the same rows. They cover the first top-dressing on the sowing day
    (DOY 348), the reset of the season sums at DAP 1 (:1620-1624) and, in
    Taj1-Nlim, its daily irrigation and the denitrification in layer 1 that
    follows from it.

    Water and soil N columns are compared on every row; crop columns from
    DAP 1 only, because the spin-up rows of a VBA macro run show the previous
    scenario's crop values.
    """
    config = load_scenario(REPO_ROOT / "configs" / "example" / "gorgan_wheat_taj1.yaml")
    mgmt = config.management
    mgmt.water, mgmt.irg_level = water, irg_level
    params = build_params(load_crop_params(config.crop_file), config.location)
    records, _ = _run_season(
        weather_df=load_weather(config.location.weather_file),
        params=params, lat=config.location.latitude,
        pyear=mgmt.plant_year, simdoy=mgmt.sim_doy, pdoy=mgmt.pdoy,
        pden=mgmt.plant_density, water=water, nitrogen=2, max_days=8,
        soil_water=_soil_water_inputs(params, config.soil, mgmt),
    )
    py_daily = pd.DataFrame(records)
    vba_daily = _load_vba_all_days(scenario).rename(columns=VBA_SOIL_N_TO_PY)

    vba_daily = vba_daily.iloc[: len(py_daily)]
    assert list(py_daily["dap"]) == list(vba_daily["DAP"]) == [0] * 8 + list(range(1, 9))
    assert vba_daily["nfert"].iloc[7] == 2.3
    crop = vba_daily["DAP"] > 0
    # the premise: nothing PlantN or CropLAIN would change has happened yet
    assert (vba_daily.loc[crop, "lai"] == 0).all() and (vba_daily.loc[crop, "NUP"] == 0).all()
    for col in [*VBA_WATER_TO_PY.values(), *VBA_SOIL_N_TO_PY.values()]:
        _assert_matches(
            py_daily[col], vba_daily[col], vba_daily["DAP"], PRE_EMERGENCE_ATOL,
        )
    for col in VBA_TO_PY.values():
        _assert_matches(
            py_daily.loc[crop, col], vba_daily.loc[crop, col], vba_daily["DAP"],
            PRE_EMERGENCE_ATOL,
        )
