"""Main simulation loop (replaces VBA Sub iCrops, iCrop.vba:44-102).

One daily pipeline, gated by mode exactly as the VBA gates its GoSubs
(iCrop.vba:78-87):

    Weather
    PhenologyBD
    CropLAI            if nitrogen = 0
    CropLAIN           if nitrogen = 2
    DMProduction
    DMDistribution
    PlantN             if nitrogen = 2      <- before SoilWater, not after
    SoilWater          if water in (1, 2, 3)
    SoilN              if nitrogen = 2
    DailyPrintOut

Before the crop loop, the pre-sowing days of FindSimSowDate run SoilWater
(and SoilN) with DAP=0 and are recorded like crop days (iCrop.vba:1779-1797).

`run_potential_production` is a thin preset over that pipeline for water=0 /
nitrogen=0, not a separate model. FixFind 1-5 raise NotImplementedError.
StopDoy (forced removal, MATYP 4) is not ported either and is ignored: a
scenario whose StopDoy falls inside the season runs on to maturity.
"""

from dataclasses import dataclass

import pandas as pd

from .crop_lai import LAIParams, step_lai, step_lai_n
from .dm_distribution import DMDistributionParams, step_dm_distribution
from .dm_production import DMProductionParams, step_dm_production
from .inputs import (
    LocationConfig,
    ManagementConfig,
    ScenarioConfig,
    SoilConfig,
    load_crop_params,
)
from .phenology import LegumeParams, MaizeParams, WheatParams, step_phenology
from .plant_n import SEASON_CARRY_FIELDS as PLANT_N_CARRY_FIELDS
from .plant_n import PlantNParams, step_plant_n
from .soil_n import SEASON_CARRY_FIELDS as SOIL_N_CARRY_FIELDS
from .soil_n import step_soil_n
from .soil_water import SEASON_CARRY_FIELDS, SoilWaterParams, step_soil_water
from .sowing import find_sim_and_sow_rows, read_spinup_day
from .state import SimState
from .weather import load_weather, step_weather

PhenologyParams = WheatParams | MaizeParams | LegumeParams

# Daily variables recorded by the current pipeline, as
# {output column: SimState attribute}. Not yet the full 63-column DailyPrintOut
# set (see outputs.DailyRecord).
# tests/test_verification.py compares against these names.
_DAILY_FIELDS = {
    "year": "yr", "doy": "doy", "dap": "dap", "tmp": "tmp", "srad": "srad",
    "rain": "rain", "dtu": "dtu", "cbd": "cbd", "msnn": "msnn",
    "lai": "lai", "glai": "glai", "dlai": "dlai", "fint": "fint",
    "rue": "rue", "ddmp": "ddmp", "glf": "glf", "gst": "gst", "sgr": "sgr",
    "wlf": "wlf", "wst": "wst", "wveg": "wveg", "wgrn": "wgrn", "wtop": "wtop",
    "hi": "hi", "mat": "mat", "matyp": "matyp",
    "deport": "deport", "irgw": "irgw", "runof": "runof", "pet": "pet",
    "sevp": "sevp", "tr": "tr", "drain": "drain", "atswrz": "atswrz",
    "ftswrz": "ftswrz", "crain": "crain", "cirgw": "cirgw", "irgno": "irgno",
    "crunof": "crunof", "ce": "ce", "ctr": "ctr", "cdrain": "cdrain",
    "nfert": "nfert", "cnfert": "cnfert", "nvol": "nvol", "cnvol": "cnvol",
    "nleach": "nleach", "cnleach": "cnleach", "snmin": "snmin", "cnmin": "cnmin",
    "sndnit": "sndnit", "cndnit": "cndnit", "snavl": "snavl", "cnsol": "cnsol",
    "nup": "nup", "nlf": "nlf", "nst": "nst", "nveg": "nveg", "ngrn": "ngrn",
    "cnup": "cnup", "cumbnf": "cumbnf", "nstrs": "nstrs",
}


@dataclass
class ModelParams:
    """Everything the daily pipeline needs, assembled per crop + location."""

    crop_type: str
    phenology: PhenologyParams
    lai: LAIParams
    dm_production: DMProductionParams
    dm_distribution: DMDistributionParams
    soil_water: SoilWaterParams | None = None   # None: crop file has no soil_water section
    plant_n: PlantNParams | None = None         # None: crop file has no plant_n section
    cultivar: str = ""


@dataclass
class SimResult:
    daily: pd.DataFrame      # one row per simulated day
    summary: pd.DataFrame    # one row per season


def build_params(crop: dict, location: LocationConfig) -> ModelParams:
    """Assemble module parameter objects from a crop YAML plus its location.

    The crop YAML comes from scripts/extract_crop_params.py. Two values the
    Python DMProductionParams carries are *location* parameters in the VBA and
    are injected here rather than stored in the crop file: `vpdf` (Location col
    3, iCrop.vba:113) and `co2` (Location col 7, iCrop.vba:116). Keeping them out
    of the crop file is what lets one cultivar run at several locations --
    Gorgan's VPDF is 0.63, Tabriz's is 0.75.
    """
    crop_type = crop["crop_type"]
    pheno_raw = dict(crop["phenology"])

    # A blank Crop-sheet cell is read as 0 by VBA; YAML carries it as null.
    pheno = {k: (0.0 if v is None else v) for k, v in pheno_raw.items()}

    pheno_cls = {"WHEAT": WheatParams, "MAIZE": MaizeParams, "LEGUME": LegumeParams}
    if crop_type not in pheno_cls:
        raise ValueError(f"unknown crop_type {crop_type!r}")

    dm_prod = dict(crop["dm_production"])
    dm_prod["vpd_type"] = int(dm_prod["vpd_type"])
    dm_prod["vpdf"] = location.vpdf
    dm_prod["co2"] = location.co2

    dm_dist = dict(crop["dm_distribution"])
    dm_dist["heat"] = int(dm_dist["heat"])

    soil_water = None
    if "soil_water" in crop:
        sw = {k: (0.0 if v is None else v) for k, v in crop["soil_water"].items()}
        sw["vpd_type"] = int(sw["vpd_type"])
        sw["surviv"] = int(sw["surviv"])
        sw["vpdf"] = location.vpdf
        sw["co2"] = location.co2
        soil_water = SoilWaterParams(**sw)

    plant_n = None
    if "plant_n" in crop:
        plant_n = PlantNParams(
            **{k: (0.0 if v is None else v) for k, v in crop["plant_n"].items()}
        )

    return ModelParams(
        crop_type=crop_type,
        cultivar=crop.get("cultivar", ""),
        phenology=pheno_cls[crop_type](**pheno),
        lai=LAIParams(**crop["lai"]),
        dm_production=DMProductionParams(**dm_prod),
        dm_distribution=DMDistributionParams(**dm_dist),
        soil_water=soil_water,
        plant_n=plant_n,
    )


@dataclass
class _SoilWaterInputs:
    """What SoilWater needs beyond the crop parameters; None when water=0."""

    params: SoilWaterParams
    soil: SoilConfig
    management: ManagementConfig
    sla: float


def _soil_water_inputs(
    params: ModelParams, soil: SoilConfig | None, management: ManagementConfig
) -> _SoilWaterInputs | None:
    if management.water == 0:
        return None
    if params.soil_water is None:
        raise ValueError(
            f"water={management.water} needs a `soil_water` section in the crop "
            f"file; regenerate it with scripts/extract_crop_params.py"
        )
    if soil is None:
        raise ValueError(f"water={management.water} needs a soil")
    return _SoilWaterInputs(params.soil_water, soil, management, params.lai.sla)


def _record(state: SimState) -> dict:
    return {column: getattr(state, attr) for column, attr in _DAILY_FIELDS.items()}


def _step_day(
    state: SimState,
    weather_df: pd.DataFrame,
    row_idx: int,
    params: ModelParams,
    lat: float,
    pden: float,
    water: int,
    nitrogen: int,
    soil_water: _SoilWaterInputs | None = None,
    temp_change: float = 0.0,
    precip_change: float = 1.0,
) -> None:
    """One day of the model, in VBA's GoSub order (iCrop.vba:78-87).

    The call order matters beyond bookkeeping: crop_lai runs before
    dm_distribution, so its GLF*SLA growth phase reads *yesterday's* GLF. That
    one-day lag is VBA behaviour, not an artefact.
    """
    step_weather(state, weather_df, row_idx, temp_change, precip_change)
    step_phenology(state, params.phenology, params.crop_type, lat)

    if nitrogen == 2:  # iCrop.vba:80-81
        step_lai_n(state, params.lai, _plant_n_params(params), pden, params.crop_type)
    else:
        step_lai(state, params.lai, pden)

    step_dm_production(state, params.dm_production)
    step_dm_distribution(state, params.dm_distribution, water_mode=water)

    if nitrogen == 2:  # before SoilWater (iCrop.vba:84-85)
        _step_plant_n(state, params)

    if soil_water is not None:  # water = 1, 2 or 3
        _step_soil_water(state, soil_water)

    if nitrogen == 2:
        _step_soil_n(state, soil_water)


def _plant_n_params(params: ModelParams) -> PlantNParams:
    if params.plant_n is None:
        raise ValueError(
            "nitrogen=2 needs a `plant_n` section in the crop file; "
            "regenerate it with scripts/extract_crop_params.py"
        )
    return params.plant_n


def _step_plant_n(state: SimState, params: ModelParams) -> None:
    step_plant_n(state, _plant_n_params(params), params.dm_distribution.gcc)


def _step_soil_n(state: SimState, inputs: _SoilWaterInputs | None) -> None:
    if inputs is None:
        # ManagementConfig rejects nitrogen=2 with water=0; this catches
        # callers that bypass it. Without SoilWater the VBA has no soil
        # layers (NLYER is set only at iCrop.vba:1138).
        raise ValueError("nitrogen=2 needs the soil water balance (water 1, 2 or 3)")
    step_soil_n(state, inputs.soil, inputs.management)


def _step_soil_water(state: SimState, inputs: _SoilWaterInputs) -> None:
    step_soil_water(state, inputs.params, inputs.soil, inputs.management, inputs.sla)


def _run_season(
    weather_df: pd.DataFrame,
    params: ModelParams,
    lat: float,
    pyear: int,
    simdoy: int,
    pdoy: int,
    pden: float,
    water: int,
    nitrogen: int,
    fix_find: int = 0,
    max_days: int = 400,
    soil_water: _SoilWaterInputs | None = None,
    previous: SimState | None = None,
    temp_change: float = 0.0,
    precip_change: float = 1.0,
) -> tuple[list[dict], SimState]:
    """Run one season (one iteration of VBA's `For yrCntr` body, iCrop.vba:75-96).

    Starts with the FindSimSowDate spin-up: every day after the simulation
    start up to and including sowing runs SoilWater (and SoilN) with DAP=0 and
    is recorded (iCrop.vba:1779-1797). `previous` is the last season's state,
    for the few soil water and N values the VBA carries across seasons
    (SEASON_CARRY_FIELDS of soil_water, soil_n and plant_n).
    `temp_change` and `precip_change` are the Location sheet's climate-change
    adjustments tchng (added to TMAX/TMIN) and pchng (multiplying RAIN),
    iCrop.vba:114-115, applied to every day read, before sowing as well
    (:1786-1788).

    VBA loops `Do Until MAT = 1` with no day bound; max_days is a safety stop
    this port adds, since StopDoy (forced field removal) is not ported yet.
    """
    if simdoy == pdoy:
        simdoy = pdoy - 1  # iCrop.vba:122, also for callers bypassing ManagementConfig
    sim_start, sow_row = find_sim_and_sow_rows(
        weather_df, pyear, simdoy, pdoy, fix_find=fix_find
    )
    state = SimState()
    if previous is not None:
        for name in SEASON_CARRY_FIELDS + SOIL_N_CARRY_FIELDS + PLANT_N_CARRY_FIELDS:
            value = getattr(previous, name)
            setattr(state, name, list(value) if isinstance(value, list) else value)
    records: list[dict] = []

    for row_idx in range(sim_start + 1, sow_row + 1):
        read_spinup_day(state, weather_df, row_idx, temp_change, precip_change)
        if soil_water is not None:
            _step_soil_water(state, soil_water)
        if nitrogen == 2:
            _step_soil_n(state, soil_water)
        state.das += 1
        records.append(_record(state))

    for row_idx in range(sow_row + 1, len(weather_df)):
        _step_day(
            state, weather_df, row_idx, params, lat, pden, water, nitrogen,
            soil_water, temp_change, precip_change,
        )
        records.append(_record(state))

        if state.mat == 1 or state.dap >= max_days:
            break

    return records, state


def run_potential_production(
    weather_df: pd.DataFrame,
    lat: float,
    pyear: int,
    simdoy: int,
    pdoy: int,
    crop_type: str,
    phenology_params: PhenologyParams,
    lai_params: LAIParams,
    dm_production_params: DMProductionParams,
    dm_distribution_params: DMDistributionParams,
    pden: float,
    max_days: int = 400,
    temp_change: float = 0.0,
    precip_change: float = 1.0,
) -> pd.DataFrame:
    """Run one season under potential production (VBA's water=0, nitrogen=0).

    A preset over the shared daily pipeline: with water=0 and nitrogen=0 the
    stress factors wsfg/wsfd/wsfl/wsfn stay at their no-stress default of 1.0 all
    season, which is what VBA does when water=0 (every scenario's Manag sheet in
    the 2022 source workbook documents "water = 0 for potential production").

    Takes the parameter objects directly rather than a config, so the verification
    suite can pin exact literals. For config-driven runs use run_simulation.

    Returns one row per simulated day: the pre-sowing spin-up days with DAP=0,
    then DAP=1 on the day after sowing (matching VBA's date offset -- see
    sowing.py).
    """
    params = ModelParams(
        crop_type=crop_type,
        phenology=phenology_params,
        lai=lai_params,
        dm_production=dm_production_params,
        dm_distribution=dm_distribution_params,
    )
    records, _ = _run_season(
        weather_df=weather_df,
        params=params,
        lat=lat,
        pyear=pyear,
        simdoy=simdoy,
        pdoy=pdoy,
        pden=pden,
        water=0,
        nitrogen=0,
        max_days=max_days,
        temp_change=temp_change,
        precip_change=precip_change,
    )
    return pd.DataFrame(records)


def run_simulation(config: ScenarioConfig, max_days: int = 400) -> SimResult:
    """Run every year of one scenario (VBA's `For yrCntr` loop, iCrop.vba:74-99).

    Pyear increments per simulated year (iCrop.vba:97). The summary table is
    still empty: SummaryPrintOut is not ported, and part of what it reports (the
    environmental sums of iCrop.vba:678-710) is not accumulated yet either.
    """
    mgmt: ManagementConfig = config.management

    params = build_params(load_crop_params(config.crop_file), config.location)
    weather_df = load_weather(config.location.weather_file)

    soil_water = _soil_water_inputs(params, config.soil, mgmt)

    daily_frames = []
    previous = None
    for year_offset in range(mgmt.sim_years):
        pyear = mgmt.plant_year + year_offset
        records, previous = _run_season(
            weather_df=weather_df,
            params=params,
            lat=config.location.latitude,
            pyear=pyear,
            simdoy=mgmt.sim_doy,
            pdoy=mgmt.pdoy,
            pden=mgmt.plant_density,
            water=mgmt.water,
            nitrogen=mgmt.nitrogen,
            fix_find=mgmt.fix_find,
            max_days=max_days,
            soil_water=soil_water,
            previous=previous,
            temp_change=config.location.temp_change,
            precip_change=config.location.precip_change,
        )
        frame = pd.DataFrame(records)
        frame.insert(0, "scenario", config.name)
        daily_frames.append(frame)

    return SimResult(
        daily=pd.concat(daily_frames, ignore_index=True),
        summary=pd.DataFrame(),
    )
