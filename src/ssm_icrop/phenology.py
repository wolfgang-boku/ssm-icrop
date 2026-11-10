"""Phenology — biological day calculation and stage tracking (replaces VBA PhenologyBD).

Each crop type has its own thermal/photoperiod function:
  WHEAT   — cardinal temperatures + vernalization + photoperiod
  MAIZE   — cardinal temperatures + dynamic photoperiod response
  LEGUME  — cardinal temperatures + photoperiod
"""

import math
from dataclasses import dataclass

from .state import SimState


@dataclass
class WheatParams:
    """Wheat-specific phenology parameters."""
    # cardinal temperatures
    tbd: float
    tp1d: float
    tp2d: float
    tcd: float
    # vernalization
    tbver: float = -1.0
    tp1ver: float = 0.0
    tp2ver: float = 8.0
    tcver: float = 12.0
    vdsat: float = 50.0            # vernalization days requirement
    vsen: float = 0.0              # vernalization sensitivity
    # photoperiod
    cpp: float = 12.0              # critical photoperiod (hours)
    ppsen: float = 0.0             # photoperiod sensitivity
    # stage thresholds (CBD units)
    bd_sowemr: float = 0.0
    bd_emrtil: float = 0.0
    bd_tilsel: float = 0.0
    bd_selbot: float = 0.0
    bd_botear: float = 0.0
    bd_earant: float = 0.0
    bd_antpm: float = 0.0
    bd_pmhm: float = 0.0


@dataclass
class MaizeParams:
    """Maize-specific phenology parameters."""
    tbd: float
    tp1d: float
    tp2d: float
    tcd: float
    cpp: float                     # critical photoperiod
    ppsen: float
    bd_sowemr: float
    bd_emreju: float               # emergence to end-of-juvenile
    bd_silpm: float                # silking to physiological maturity
    phyl: float                    # phyllochron (thermal time per leaf)


@dataclass
class LegumeParams:
    """Legume-specific phenology parameters.

    Unlike wheat/maize, several physiological-stage thresholds are given
    directly as crop parameters rather than derived from the R-stage chain
    (matches the VBA "Crop" sheet layout, cells 91-98).
    """
    tbd: float
    tp1d: float
    tp2d: float
    tcd: float
    cpp: float
    ppsen: float                   # can be positive or negative
    bd_sowemr: float
    bd_emrr1: float
    bd_r1r3: float
    bd_r3r5: float
    bd_r5r7: float
    bd_r7r8: float
    # explicit physiological-stage thresholds (absolute CBD values)
    bd_brp: float                  # begin response to photoperiod
    bd_trp: float                  # end response to photoperiod
    bd_bsg: float                  # begin seed growth
    bd_tsg: float                  # end seed growth
    bd_tlm: float                  # leaf production ends on main stem
    bd_tlp: float                  # leaf production ends on whole plant
    bd_bls: float                  # begin leaf senescence


def _temperature_response_beta(tmp: float, tbd: float, tp1d: float,
                                tp2d: float, tcd: float) -> float:
    """Beta-distribution-shaped temperature response: single smooth peak
    near tp1d, tapering to 0 at tbd and tcd. tp2d is accepted for signature
    parity with the dent function but is unused (matches VBA's wheat beta
    function, which never references TP2D).

    Used by wheat phenology's biological-day calculation; also selectable
    for DM production's RUE temperature response (see DMProductionParams).
    """
    if tmp <= tbd or tmp >= tcd:
        return 0.0
    part1 = (tcd - tmp) / (tcd - tp1d)
    part2 = (tmp - tbd) / (tp1d - tbd)
    pow = (tp1d - tbd) / (tcd - tp1d)
    tempfun = part1 * (part2 ** pow)
    return max(0.0, tempfun)


def _temperature_response_dent(tmp: float, tbd: float, tp1d: float,
                                tp2d: float, tcd: float) -> float:
    """Dent-like function for legume phenology and DM production's TCFRUE."""
    if tmp <= tbd or tmp >= tcd:
        return 0.0
    if tbd < tmp < tp1d:
        return (tmp - tbd) / (tp1d - tbd)
    if tp2d < tmp < tcd:
        return (tcd - tmp) / (tcd - tp2d)
    if tp1d <= tmp <= tp2d:
        return 1.0
    return 0.0


def _temperature_response_dent_maize(tmp: float, tbd: float, tp1d: float,
                                      tp2d: float, tcd: float) -> float:
    """Dent-like function for maize phenology — faithfully replicates a VBA bug.

    iCrop.vba:455 divides by TCD instead of (TCD - TP2D) in the falling-off
    branch, because the source references an undeclared variable TP2
    (silently 0 under VBA's implicit-declaration rules — this module has no
    Option Explicit) instead of TP2D. Grepping the whole VBA file confirms
    TP2 appears nowhere else; legume phenology (line 616) and DM production's
    TCFRUE (lines 906-907) both correctly use TP2D/TP2RUE, so this typo is
    isolated to maize. Kept distinct from _temperature_response_dent (used
    by legume and DM production, both bug-free) so those stay correct.
    """
    if tmp <= tbd or tmp >= tcd:
        return 0.0
    if tbd < tmp < tp1d:
        return (tmp - tbd) / (tp1d - tbd)
    if tp2d < tmp < tcd:
        return (tcd - tmp) / tcd  # VBA bug: should be (tcd - tp2d)
    if tp1d <= tmp <= tp2d:
        return 1.0
    return 0.0


def _solar_geometry(doy: int, lat: float) -> tuple[float, float, float, float]:
    """Day length and solar declination geometry.

    Shared by phenology (photoperiod response) and DM production (hourly
    VPD method), matching the VBA globals SINLD/COSLD/AOB/DAYL that both
    GoSub sections read.

    Returns: (dayl, sinld, cosld, aob)
    """
    pi = math.pi
    rdn = pi / 180.0

    dec = math.sin(23.45 * rdn) * math.cos(2 * pi * (doy + 10) / 365.0)
    dec = math.atan(dec / math.sqrt(max(1e-12, 1 - dec ** 2))) * -1
    sinld = math.sin(rdn * lat) * math.sin(dec)
    cosld = math.cos(rdn * lat) * math.cos(dec)
    aob = sinld / (cosld + 1e-10)
    aob2 = math.atan(aob / math.sqrt(max(1e-12, 1 - aob ** 2)))
    dayl = 12.0 * (1.0 + 2.0 * aob2 / pi)
    return dayl, sinld, cosld, aob


def _photoperiod_response(pp: float, cpp: float, ppsen: float,
                          cbd: float, cbd_brp: float, cbd_trp: float,
                          crop_type: str = "WHEAT") -> float:
    """Calculate photoperiod response (day length effect).

    Args:
        pp: effective day length (dayl + 0.9), from _solar_geometry()
    """
    if cbd < cbd_brp or cbd > cbd_trp:
        return 1.0

    if crop_type == "WHEAT":
        if pp < cpp:
            ppfun = 1.0 - ppsen * ((cpp - pp) ** 2)
            return max(0.0, ppfun)  # VBA only clamps the lower bound
        return 1.0

    elif crop_type == "MAIZE":
        if pp > cpp:
            ratein = 1.0 / (4.0 + ppsen * (pp - cpp))
            rmax = 1.0 / 4.0
            ppfun = ratein / rmax
            return max(0.0, ppfun)
        return 1.0

    else:  # LEGUME
        if ppsen >= 0:
            ppfun = 1.0 - ppsen * (cpp - pp)
        else:
            ppfun = 1.0 - (-ppsen) * (pp - cpp)
        return max(0.0, min(1.0, ppfun))


def _vernalization_response(tmin: float, tmax: float, snow: float,
                             tbver: float, tp1ver: float, tp2ver: float,
                             tcver: float, vdsat: float, vsen: float,
                             cumver: float, cbd: float,
                             cbd_brv: float, cbd_trv: float) -> tuple[float, float]:
    """Wheat vernalization: update cumulative vernalization days and factor.

    Returns: (vernalization_factor, updated_cumver)
    """
    # Crown temperature (modified by snow cover)
    tmincr = tmin
    tmaxcr = tmax
    xs = min(snow, 15.0)
    if tmin < 0 and xs > 0:
        tmincr = 2 + tmin * (0.4 + 0.0018 * ((xs - 15) ** 2))
    if tmax < 0 and xs > 0:
        tmaxcr = 2 + tmax * (0.4 + 0.0018 * ((xs - 15) ** 2))
    tmpcr = (tmaxcr + tmincr) / 2.0

    # Daily vernalization
    verday = 0.0
    if tmpcr <= tbver or tmpcr >= tcver:
        verday = 0.0
    elif tbver < tmpcr < tp1ver:
        verday = (tmpcr - tbver) / (tp1ver - tbver)
    elif tp2ver < tmpcr < tcver:
        verday = (tcver - tmpcr) / (tcver - tp2ver)
    elif tp1ver <= tmpcr <= tp2ver:
        verday = 1.0

    # Cumulative vernalization (with high-temp reversion)
    cumver += verday
    if cumver < 10 and tmax > 30:
        cumver -= 0.5 * (tmax - 30)
    cumver = max(0.0, cumver)

    # Vernalization factor
    if cbd >= cbd_brv and cbd <= cbd_trv:
        verfun = 1.0 - vsen * (vdsat - cumver)
        verfun = max(0.0, min(1.0, verfun))
    else:
        verfun = 1.0

    return verfun, cumver


def step_phenology_wheat(state: SimState, params: WheatParams, lat: float) -> None:
    """Advance wheat phenology by one day."""
    if state.ini_pheno == 0:
        # First-time initialization
        state.cbd_emr = params.bd_sowemr
        state.cbd_til = state.cbd_emr + params.bd_emrtil
        state.cbd_sel = state.cbd_til + params.bd_tilsel
        state.cbd_bot = state.cbd_sel + params.bd_selbot
        state.cbd_ear = state.cbd_bot + params.bd_botear
        state.cbd_ant = state.cbd_ear + params.bd_earant
        state.cbd_bsg = state.cbd_ant + 5.0
        state.cbd_tsg = state.cbd_ant + params.bd_antpm - 1.5
        state.cbd_pm = state.cbd_ant + params.bd_antpm
        state.cbd_mat = state.cbd_pm + params.bd_pmhm
        state.cbd_blg = state.cbd_emr
        state.cbd_tlm = state.cbd_bot
        state.cbd_tlp = state.cbd_bsg
        state.cbd_bls = state.cbd_bsg
        state.cbd_bxtf = state.cbd_ant - 5.0
        state.cbd_txtf = state.cbd_ant + 12.0
        state.cumver = 0.0
        state.wsfd = 1.0
        # iCrop.vba:283. This block runs after Weather on crop day 1, so snow
        # that fell that day is dropped. FTSW(1) = 0.5 is overwritten by
        # SoilWater the same day when water > 0. With water = 0 it stays; SoilN
        # (:1632) does not run then (ManagementConfig), but the unported
        # FixFind 4/5 read it in later seasons (:1913, :1935).
        state.snow = 0.0
        state.cbd = 0.0
        state.dap = 0
        state.ftsw[0] = 0.5
        state.ini_pheno = 1

    # Temperature response (beta function)
    tempfun = _temperature_response_beta(state.tmp, params.tbd, params.tp1d,
                                         params.tp2d, params.tcd)

    # Solar geometry (also used by DM production's hourly VPD method)
    state.dayl, state.sinld, state.cosld, state.aob = _solar_geometry(state.doy, lat)

    # Photoperiod response
    pp = state.dayl + 0.9
    ppfun = _photoperiod_response(pp, params.cpp, params.ppsen,
                                  state.cbd, state.cbd_emr, state.cbd_sel,
                                  crop_type="WHEAT")

    # Vernalization response (wheat-specific)
    verfun, state.cumver = _vernalization_response(
        state.tmin, state.tmax, state.snow,
        params.tbver, params.tp1ver, params.tp2ver, params.tcver,
        params.vdsat, params.vsen, state.cumver,
        state.cbd, state.cbd_emr, state.cbd_sel
    )

    # Biological day accumulation
    if state.cbd <= state.cbd_emr:
        state.dtu = (params.tp1d - params.tbd) * tempfun
        bd = verfun * tempfun * ppfun
    else:
        state.dtu = (params.tp1d - params.tbd) * tempfun * state.wsfd
        bd = verfun * tempfun * ppfun * state.wsfd  # drought-acceleration factor

    state.cbd += bd
    state.bd = bd
    state.dap += 1

    # Stage transitions
    if state.cbd >= state.cbd_emr and state.dt_emr == 0:
        state.dt_emr = state.dap
    if state.cbd >= state.cbd_til and state.dt_r0 == 0:
        state.dt_r0 = state.dap
    if state.cbd >= state.cbd_sel and state.dt_r1 == 0:
        state.dt_r1 = state.dap
    if state.cbd >= state.cbd_bot and state.dt_r2 == 0:
        state.dt_r2 = state.dap
    if state.cbd >= state.cbd_ear and state.dt_r3 == 0:
        state.dt_r3 = state.dap
    if state.cbd >= state.cbd_ant and state.dt_r4 == 0:
        state.dt_r4 = state.dap
    if state.cbd >= state.cbd_bsg and state.dt_r5 == 0:
        state.dt_r5 = state.dap
    if state.cbd >= state.cbd_tsg and state.dt_r6 == 0:
        state.dt_r6 = state.dap
    if state.cbd >= state.cbd_pm and state.dt_r7 == 0:
        state.dt_r7 = state.dap
    if state.cbd >= state.cbd_mat and state.dt_r8 == 0:
        state.dt_r8 = state.dap

    # Check maturity
    if state.cbd > state.cbd_mat:
        state.mat = 1
        state.matyp = 1


def step_phenology_maize(state: SimState, params: MaizeParams, lat: float) -> None:
    """Advance maize phenology by one day."""
    if state.ini_pheno == 0:
        state.cbd_emr = params.bd_sowemr
        state.cbd_eju = state.cbd_emr + params.bd_emreju
        state.cbd_tsi = state.cbd_eju + 4.0
        # Initial estimate of silking, refined once actual TSI is reached
        emr_to_tsi = state.cbd_tsi - state.cbd_emr
        bd_tsisil_est = (15.0 + 5.0) * params.phyl / (34.0 - 8.0) - emr_to_tsi
        state.cbd_sil = state.cbd_tsi + bd_tsisil_est
        state.cbd_tse = state.cbd_sil - 76.0 / (params.tp1d - params.tbd)
        state.cbd_bsg = state.cbd_sil + 170.0 / (params.tp1d - params.tbd)
        state.cbd_tsg = state.cbd_sil + 0.95 * params.bd_silpm
        state.cbd_pm = state.cbd_tsg + 0.05 * params.bd_silpm
        state.cbd_mat = state.cbd_pm + 4.0
        state.cbd_blg = state.cbd_emr
        state.cbd_tlm = state.cbd_sil
        state.cbd_tlp = state.cbd_sil
        state.cbd_bls = state.cbd_bsg
        state.cbd_bxtf = state.cbd_sil - 5.0
        state.cbd_txtf = state.cbd_sil + 10.0
        state.tuemrtsi = 0.0
        state.xtsi = 0
        state.wsfd = 1.0
        state.cbd = 0.0  # iCrop.vba:440; maize leaves SNOW and FTSW(1) alone
        state.dap = 0
        # not applicable to maize (VBA: dtR2=dtR3=dtR4=dtR5=dtR6=-9)
        state.dt_r2 = -9
        state.dt_r3 = -9
        state.dt_r4 = -9
        state.dt_r5 = -9
        state.dt_r6 = -9
        state.ini_pheno = 1

    # Temperature response (dent function, faithfully replicating VBA's
    # TP2/TP2D typo — see _temperature_response_dent_maize docstring)
    tempfun = _temperature_response_dent_maize(state.tmp, params.tbd, params.tp1d,
                                               params.tp2d, params.tcd)

    # Solar geometry — computed every day (VBA only computes this inside the
    # photoperiod-sensitive window for maize, leaving stale values outside it;
    # we compute it unconditionally so DM production always has a fresh value).
    state.dayl, state.sinld, state.cosld, state.aob = _solar_geometry(state.doy, lat)

    # Photoperiod response (only during sensitive phase)
    pp = state.dayl + 0.9
    ppfun = _photoperiod_response(pp, params.cpp, params.ppsen,
                                  state.cbd, state.cbd_eju, state.cbd_tsi,
                                  crop_type="MAIZE")

    # Biological day accumulation
    state.dtu = (params.tp1d - params.tbd) * tempfun
    if state.cbd_eju <= state.cbd <= state.cbd_tsi:
        bd = ppfun
    else:
        bd = tempfun

    if state.cbd > state.cbd_bsg:
        state.dtu *= state.wsfd
        bd *= state.wsfd  # drought-acceleration factor, grain filling only

    state.cbd += bd
    state.bd = bd
    state.dap += 1

    # Re-calculate stages once actual tassel initiation (TSI) is reached
    if state.cbd_emr <= state.cbd <= state.cbd_tsi:
        state.tuemrtsi += state.dtu
    if state.cbd > state.cbd_tsi and state.xtsi == 0:
        tlno = state.tuemrtsi / (params.phyl * 0.5) + 5.0
        leaf_thermal_time = (tlno + 5.0) * params.phyl - state.tuemrtsi
        bd_tsisil = leaf_thermal_time / (params.tp1d - params.tbd)
        state.cbd_sil = state.cbd_tsi + bd_tsisil
        state.cbd_tse = state.cbd_sil - 76.0 / (params.tp1d - params.tbd)
        state.cbd_bsg = state.cbd_sil + 170.0 / (params.tp1d - params.tbd)
        state.cbd_tsg = state.cbd_sil + 0.95 * params.bd_silpm
        state.cbd_pm = state.cbd_tsg + 0.05 * params.bd_silpm
        state.cbd_mat = state.cbd_pm + 4.0
        state.cbd_tlm = state.cbd_sil
        state.cbd_tlp = state.cbd_sil
        state.cbd_bls = state.cbd_bsg
        state.cbd_bxtf = state.cbd_sil - 5.0
        state.cbd_txtf = state.cbd_sil + 10.0
        state.xtsi = 1

    # Stage transitions
    if state.cbd >= state.cbd_emr and state.dt_emr == 0:
        state.dt_emr = state.dap
    if state.cbd >= state.cbd_tse and state.dt_r0 == 0:
        state.dt_r0 = state.dap
    if state.cbd >= state.cbd_sil and state.dt_r1 == 0:
        state.dt_r1 = state.dap
    if state.cbd >= state.cbd_pm and state.dt_r7 == 0:
        state.dt_r7 = state.dap
    if state.cbd >= state.cbd_mat and state.dt_r8 == 0:
        state.dt_r8 = state.dap

    if state.cbd > state.cbd_mat:
        state.mat = 1
        state.matyp = 1


def step_phenology_legume(state: SimState, params: LegumeParams, lat: float) -> None:
    """Advance legume phenology by one day."""
    if state.ini_pheno == 0:
        state.cbd_emr = params.bd_sowemr
        state.cbd_r1 = state.cbd_emr + params.bd_emrr1
        state.cbd_r3 = state.cbd_r1 + params.bd_r1r3
        state.cbd_r5 = state.cbd_r3 + params.bd_r3r5
        state.cbd_r7 = state.cbd_r5 + params.bd_r5r7
        state.cbd_r8 = state.cbd_r7 + params.bd_r7r8
        state.cbd_mat = state.cbd_r8
        state.cbd_bsg = params.bd_bsg
        state.cbd_tsg = params.bd_tsg
        state.cbd_blg = state.cbd_emr
        state.cbd_tlm = params.bd_tlm
        state.cbd_tlp = params.bd_tlp
        state.cbd_bls = params.bd_bls
        state.cbd_bxtf = state.cbd_r1 - 5.0
        state.cbd_txtf = state.cbd_r1 + 10.0
        state.wsfd = 1.0
        # iCrop.vba:603; FTSW(1) as for wheat (:283), but SNOW is not reset
        state.cbd = 0.0
        state.dap = 0
        state.ftsw[0] = 0.5
        state.dt_r0 = -9  # not applicable to legumes
        state.ini_pheno = 1

    # Temperature response (dent function)
    tempfun = _temperature_response_dent(state.tmp, params.tbd, params.tp1d,
                                         params.tp2d, params.tcd)

    # Solar geometry (also used by DM production's hourly VPD method)
    state.dayl, state.sinld, state.cosld, state.aob = _solar_geometry(state.doy, lat)

    # Photoperiod response
    pp = state.dayl + 0.9
    ppfun = _photoperiod_response(pp, params.cpp, params.ppsen,
                                  state.cbd, params.bd_brp, params.bd_trp,
                                  crop_type="LEGUME")

    # Biological day accumulation
    if state.cbd <= state.cbd_emr:
        state.dtu = (params.tp1d - params.tbd) * tempfun
        bd = tempfun * ppfun
    else:
        state.dtu = (params.tp1d - params.tbd) * tempfun * state.wsfd
        bd = tempfun * ppfun * state.wsfd  # drought-acceleration factor

    state.cbd += bd
    state.bd = bd
    state.dap += 1

    # Stage transitions
    if state.cbd >= state.cbd_emr and state.dt_emr == 0:
        state.dt_emr = state.dap
    if state.cbd >= state.cbd_r1 and state.dt_r1 == 0:
        state.dt_r1 = state.dap
    if state.cbd >= state.cbd_r3 and state.dt_r3 == 0:
        state.dt_r3 = state.dap
    if state.cbd >= state.cbd_r5 and state.dt_r5 == 0:
        state.dt_r5 = state.dap
    if state.cbd >= state.cbd_r7 and state.dt_r7 == 0:
        state.dt_r7 = state.dap
    if state.cbd >= state.cbd_r8 and state.dt_r8 == 0:
        state.dt_r8 = state.dap

    if state.cbd > state.cbd_mat:
        state.mat = 1
        state.matyp = 1


def step_phenology(state: SimState, params: WheatParams | MaizeParams | LegumeParams,
                   crop_type: str, lat: float) -> None:
    """Dispatch to appropriate phenology function based on crop type."""
    if crop_type == "WHEAT":
        step_phenology_wheat(state, params, lat)
    elif crop_type == "MAIZE":
        step_phenology_maize(state, params, lat)
    else:  # Legume
        step_phenology_legume(state, params, lat)
