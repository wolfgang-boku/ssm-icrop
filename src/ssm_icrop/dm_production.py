"""Dry matter production via RUE (replaces VBA DMProduction GoSub).

Daily dry matter production (state.ddmp) comes from radiation-use efficiency:
  FINT = 1 - exp(-KPAR * LAI)          fraction of PAR intercepted
  RUE  = IRUE * TCFRUE * WSFG          actual RUE, zeroed outside [EMR, TSG]
  DDMP = SRAD * 0.48 * FINT * RUE      daily method (vpd_type=0)

The hourly method (vpd_type=1) instead integrates DDMP and transpiration
demand (state.tr) hour-by-hour over daylight hours, using a VPD-based
response that caps RUE when the air is very dry. It needs the solar
geometry (dayl/sinld/cosld/aob) that phenology.step_phenology_* already
computes and stores on state each day.

NOTE: every crop in the 2022 source workbook (SSM_iCrop__2022_05_29.xlsm,
Crop sheet, row 55 "vpd_resp") is parameterized with vpd_type=0, so the
hourly method is never exercised in practice and hasn't been verified
against the reference output. It also contains a faithfully-replicated VBA
oddity (see _step_dm_production_hourly) where the VPD-cap correction is
applied twice in a row. Using vpd_type=1 triggers a runtime warning.

TCFRUE (the temperature response feeding into RUE) uses the trapezoidal
dent function by default, matching VBA exactly. A smooth single-peaked
beta function (the same shape wheat phenology uses for biological days) is
also available via DMProductionParams.temp_response="beta" — this is a
port-time addition beyond the original VBA, useful for calibration
experiments, not something VBA itself supports.

This module does not touch state.wtop/wveg — organ accumulation happens in
DMDistribution, which consumes state.ddmp.
"""

import math
import warnings
from dataclasses import dataclass
from typing import Literal

from .phenology import _temperature_response_beta, _temperature_response_dent
from .state import SimState


@dataclass
class DMProductionParams:
    irue: float              # intrinsic RUE (g MJ-1 PAR), before CO2 adjustment
    kpar: float               # PAR extinction coefficient
    # RUE temperature response cardinals
    tbrue: float
    tp1rue: float
    tp2rue: float             # unused when temp_response="beta"
    tcrue: float
    # RUE temperature response curve shape — VBA only ever uses "dent"
    temp_response: Literal["dent", "beta"] = "dent"
    # VPD method
    vpd_type: int = 0         # 1 = hourly, 0 = daily
    vpd_threshold: float = 1.0  # VPDcr (kPa): response capped above this VPD
    vpdf: float = 0.75        # location-specific VPD correction factor (~0.75)
    # CO2 response (applied once at season start)
    co2: float = 350.0        # actual atmospheric CO2 for this simulation (ppm)
    co2_ref: float = 350.0    # CO2 the crop parameters were measured under (ppm)
    co2_res: float = 0.0      # CO2 response sensitivity
    # transpiration efficiency
    tec_ref: float = 6.0      # reference transpiration-efficiency coefficient (Pa)


def step_dm_production(state: SimState, params: DMProductionParams) -> None:
    """Compute rue/fint/ddmp for one day (and tr, for the hourly VPD method)."""
    if state.ini_dmp == 0:
        log10_ref = math.log(params.co2_ref / 330.0) / math.log(10.0)
        log10_co2 = math.log(params.co2 / 330.0) / math.log(10.0)
        rue_ref = 1.0 + params.co2_res * log10_ref
        rue_co2 = 1.0 + params.co2_res * log10_co2
        state.irue_eff = params.irue * (rue_co2 / rue_ref)
        state.tec = params.tec_ref * (rue_co2 / rue_ref)
        state.wsfg = 1.0
        state.ini_dmp = 1

    # --- Temperature response on RUE (dent by default, matching VBA exactly;
    # beta is an optional port-time addition — see DMProductionParams docstring)
    temp_response_fn = (
        _temperature_response_beta if params.temp_response == "beta"
        else _temperature_response_dent
    )
    state.tcfrue = temp_response_fn(
        state.tmp, params.tbrue, params.tp1rue, params.tp2rue, params.tcrue
    )

    state.rue = state.irue_eff * state.tcfrue * state.wsfg
    if state.cbd < state.cbd_emr or state.cbd > state.cbd_tsg:
        state.rue = 0.0

    if params.vpd_type == 1:
        _step_dm_production_hourly(state, params)
    else:
        state.fint = 1.0 - math.exp(-params.kpar * state.lai)
        state.ddmp = state.srad * 0.48 * state.fint * state.rue
        # NB: VBA does not touch TR in the daily-VPD branch either -- with
        # vpd_type=0 SoilWater computes it as DDMP * VPD / TEC (iCrop.vba:1333).


def _step_dm_production_hourly(state: SimState, params: DMProductionParams) -> None:
    """Hourly VPD method: integrate DDMP and TR over daylight hours.

    Faithful port of the VBA hourly loop, with two simplifications for
    dead code that VBA's own loop bounds make unreachable:
      - the night-time temperature formula (TC/NIGHTL/TSUNST) is never
        reached because the loop only processes SUNRIS < H < SUNSET;
      - BETA (solar elevation in degrees) is computed in VBA but never
        used afterwards, so it is omitted here.
    """
    warnings.warn(
        "DM production hourly VPD method (vpd_type=1) is active. This path "
        "is not used by any crop in the 2022 source workbook and has not been "
        "verified against the reference output. It also faithfully replicates a "
        "VBA oddity where the VPD-cap correction is applied twice in a row "
        "(see module docstring). Verify results carefully before relying on "
        "this method.",
        UserWarning,
        stacklevel=2,
    )

    pi = math.pi
    dayl, sinld, cosld, aob = state.dayl, state.sinld, state.cosld, state.aob

    sqrt_term = math.sqrt(max(0.0, 1 - aob ** 2))
    dsinbe = 3600.0 * (
        dayl * (sinld + 0.4 * (sinld ** 2 + cosld ** 2 * 0.5))
        + 12.0 * cosld * (2.0 + 3.0 * 0.4 * sinld) * sqrt_term / pi
    )
    dtr = state.srad * 1_000_000.0  # MJ m-2 d-1 -> J m-2 d-1
    p = 1.5
    sunris = 12.0 - 0.5 * dayl
    sunset = 12.0 + 0.5 * dayl
    vptmin = 0.6108 * math.exp(17.27 * state.tmin / (237.3 + state.tmin))
    fint = 1.0 - math.exp(-params.kpar * state.lai)

    tr = 0.0
    ddmp = 0.0
    for h in range(1, 25):
        if not (sunris < h < sunset):
            continue

        if h < 13.5:
            temp1 = state.tmin + (state.tmax - state.tmin) * math.sin(
                pi * (h - sunris) / (dayl + 2 * p)
            )
        else:
            temp1 = state.tmina + (state.tmax - state.tmina) * math.sin(
                pi * (h - sunris) / (dayl + 2 * p)
            )

        sinb = sinld + cosld * math.cos(2 * pi * (h + 12) / 24.0)
        sinb = max(0.0, sinb)
        srad1 = dtr * sinb * (1.0 + 0.4 * sinb) / dsinbe  # J m-2 s-1
        srad1 = srad1 * 3600.0 / 1_000_000.0  # -> MJ m-2 h-1
        srad1 = max(0.0, srad1)

        ddmp1 = srad1 * 0.48 * fint * state.rue

        vptemp1 = 0.6108 * math.exp(17.27 * temp1 / (237.3 + temp1))
        vpd1 = (vptemp1 - vptmin) * (params.vpdf / 0.75)
        tr1 = ddmp1 * vpd1 / state.tec

        if vpd1 > params.vpd_threshold:
            # VBA applies this correction twice in succession (checked
            # against source); replicated as-is, not yet verified against output.
            tr1 = ddmp1 * params.vpd_threshold / state.tec
            ddmp1 = tr1 * state.tec / vpd1
            tr1 = ddmp1 * params.vpd_threshold / state.tec
            ddmp1 = tr1 * state.tec / vpd1

        tr += tr1
        ddmp += ddmp1

    state.fint = fint
    state.tr = tr
    state.ddmp = ddmp
