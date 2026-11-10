"""Multi-layer soil water balance (replaces VBA SoilWater GoSub, iCrop.vba:1115-1415).

Runs when water is 1, 2 or 3 (iCrop.vba:85), on every pre-sowing day of the
FindSimSowDate spin-up (iCrop.vba:1793) as well as every crop day. Daily order,
as in the VBA:

  1. Season initialisation, once (iniSW, :1117-1184)
  2. Balance reset at DAP 1 (:1187-1198)
  3. Irrigation: auto, rainfed or scheduled (:1201-1248)
  4. Drainage out of the profile = YESTERDAY's outflow of layer LDRAIN (:1251)
  5. Root depth growth and roots per layer (:1255-1271)
  6. Runoff, modified curve-number method, rainfed only (:1274-1302)
  7. Potential ET, Priestley-Taylor (:1305-1313)
  8. Soil evaporation, two-stage (:1316-1326)
  9. Transpiration (:1329-1339) and drought survival (:1342-1349)
 10. Layer update: uptake, evaporation, tipping-bucket drainage (:1352-1397)
 11. Stress factors and flood kill (:1400-1408)

Layer geometry and retention limits come from SoilConfig (Soil sheet,
iCrop.vba:1138-1161), the irrigation trigger and schedule from ManagementConfig.

Two things look like slips but are VBA behaviour and are kept:
- Uptake uses yesterday's per-layer factor RT and its weighted root length
  AROOT (:1352-1354), both recomputed only afterwards (:1382-1385).
- Evaporation demand left over by layer 1 is taken from the layers below,
  down the whole profile (:1355-1361), not only from the surface layer.

Known VBA bugs replicated, each in its own function:
- _auto_irrigation_amount: water = 1 can irrigate a negative amount (:1203).
- _survival_vpd: VPD is never computed when vpd_type = 1 (:1343).
"""

import math
from dataclasses import dataclass

from .inputs import ManagementConfig, SoilConfig
from .state import SimState

# Hardcoded in the VBA (iCrop.vba:1143)
EOSMIN = 1.5   # minimum soil evaporation once PET exceeds it (mm d-1)
WETWAT = 10.0  # rain + irrigation that rewets the surface (mm)
KET = 0.5      # extinction coefficient for ET partitioning
CALB = 0.23    # canopy albedo

# Fields the VBA carries from one season into the next because they are
# globals not reset by LocManagInputs or iniSW. FTSWRZ feeds the first spin-up
# day's soil-evaporation test (:1321), FLOUT that day's DRAIN (:1251), RT the
# first day's uptake (:1354), and ATSWRZ/TTSWRZ a WATiT=4 event that fires on
# the first spin-up day (:1239). TR matters on every spin-up day when
# vpd_type = 1: nothing recomputes it before sowing (:1329-1336).
SEASON_CARRY_FIELDS = ("ftswrz", "atswrz", "ttswrz", "flout", "rt", "tr")


@dataclass
class SoilWaterParams:
    """Crop-sheet parameters SoilWater reads (iCrop.vba:1118-1132), plus two
    Location-sheet values injected by model.build_params.

    VPDcr (row 56) is read at :1129 but never used by SoilWater, so it is
    absent here.
    """

    deport: float              # row 46 -- DEPORT: initial rooting depth (mm)
    meed: float                # row 47 -- MEED: maximum effective rooting depth (mm)
    grtdp: float               # row 48 -- GRTDP: root depth growth (mm per bd)
    tec_ref: float             # row 49 -- TECREF: transpiration efficiency coeff. (Pa)
    co2_res: float             # row 25 -- CO2RES
    co2_ref: float             # row 24 -- CO2REF (read in LocManagInputs, :117)
    wssg: float                # row 50 -- WSSG: FTSWRZ threshold, DM production
    wssl: float                # row 51 -- WSSL: FTSWRZ threshold, leaf expansion
    wssd: float                # row 52 -- WSSD: slope of the drought speed-up of
    #                             phenology, WSFD = (1 - WSFG) * WSSD + 1 (:1403)
    wssn: float                # row 53 -- WSSN: FTSWRZ threshold, N uptake
    fldkil: float              # row 54 -- FLDKIL: waterlogged days that kill the crop
    vpd_type: int              # row 55 -- vpdtp: 0 = daily VPD here, 1 = hourly in DMProduction
    surviv: int                # row 57 -- surviv: 1 = drought-survival transpiration on
    epcond: float              # row 58 -- EPCOND: epidermal conductance
    ltlrwc: float              # row 59 -- LTLRWC: lethal leaf relative water content
    vpdf: float                # Location col 3 (:113)
    co2: float                 # Location col 7 (:116)


@dataclass
class LayerLimits:
    """Per-layer limits in mm, computed from the Soil sheet at :1152-1166.

    Ten slots like the VBA arrays (ReDim ...(10), :59-65); slots past NLYER
    stay 0, which is what the VBA reads there.
    """

    dlyer: list[float]
    wlad: list[float]
    wlll: list[float]
    wlul: list[float]
    wlst: list[float]
    drainf: list[float]


def layer_limits(soil: SoilConfig) -> LayerLimits:
    out = LayerLimits(*([0.0] * 10 for _ in range(6)))
    for i, layer in enumerate(soil.active_layers):
        out.dlyer[i] = layer.depth_mm
        out.wlad[i] = layer.adry * layer.depth_mm
        out.wlll[i] = layer.cll * layer.depth_mm
        out.wlul[i] = layer.dul * layer.depth_mm
        out.wlst[i] = layer.sat * layer.depth_mm
        out.drainf[i] = layer.drainf
    return out


def _tec(params: SoilWaterParams) -> float:
    """CO2-adjusted TEC (iCrop.vba:1134-1136), identical to DMProduction's."""
    rue_ref = 1.0 + params.co2_res * (math.log(params.co2_ref / 330.0) / math.log(10.0))
    rue_co2 = 1.0 + params.co2_res * (math.log(params.co2 / 330.0) / math.log(10.0))
    return params.tec_ref * (rue_co2 / rue_ref)


def _initialise(state: SimState, soil: SoilConfig, layers: LayerLimits,
                params: SoilWaterParams, management: ManagementConfig) -> None:
    """The iniSW block (iCrop.vba:1117-1184), once per season.

    It also zeroes LAI, CBD, bd and DDMP (:1149-1150). Harmless in practice:
    the first SoilWater call of a season is always a spin-up day, before any
    crop section has run.
    """
    state.deport = params.deport
    state.tec = _tec(params)

    state.dyse = 1.0
    state.ctr = state.ce = state.crain = state.crunof = 0.0
    state.cirgw = 0.0
    state.irgno = 0
    state.cdrain = 0.0
    state.rtln = 1
    state.wsol = state.wdul = state.wsat = state.soldep = 0.0
    state.isolwat = 0.0
    state.aroot = 1.0
    state.fldur = 0.0
    state.atswsl = 0.0
    state.blslai = state.lai = 0.0
    state.bd = state.cbd = state.ddmp = state.irgw = 0.0
    # The VBA resets WAT01 in LocManagInputs (:138), also once per season and
    # also before the first SoilWater call.
    if management.irrigation is not None:
        state.wat01 = [0] * len(management.irrigation.events)

    for i, layer in enumerate(soil.active_layers):
        state.wl[i] = layer.init_water * layer.depth_mm
        state.atsw[i] = state.wl[i] - layers.wlll[i]
        state.ttsw[i] = layers.wlul[i] - layers.wlll[i]
        state.ftsw[i] = state.atsw[i] / state.ttsw[i]
        state.iatsw[i] = state.atsw[i]
        state.iftsw[i] = state.ftsw[i]

        state.wsol += state.wl[i]
        state.wdul += layers.wlul[i]
        state.wsat += layers.wlst[i]
        state.atswsl += state.atsw[i]
        state.soldep += layers.dlyer[i]
    state.isolwat = state.atswsl

    state.ini_sw = 1


def _reset_balance_at_sowing(state: SimState, n_layers: int) -> None:
    """DAP 1: keep the pre-sowing totals, restart the season ones (:1187-1198).

    CIRGW and IRGNO are not reset.
    """
    for i in range(n_layers):
        state.iatsw[i] = state.atsw[i]
        state.iftsw[i] = state.ftsw[i]
    state.isolwat = state.atswsl
    state.ctr0, state.ctr = state.ctr, 0.0
    state.ce0, state.ce = state.ce, 0.0
    state.crain0, state.crain = state.crain, 0.0
    state.crunof0, state.crunof = state.crunof, 0.0
    state.cdrain0, state.cdrain = state.cdrain, 0.0


def _auto_irrigation_amount(state: SimState) -> float:
    """water = 1 refill to DUL (iCrop.vba:1203).

    VBA BUG, replicated: the amount has no lower bound, so when the root zone
    is above DUL it is negative and is subtracted from the rain entering layer
    1 (FLIN, clipped at 0 only after the sum, :1367-1371) and from CIRGW. The
    WATiT=4 amount is clipped (:1240); this one is not. It only happens when
    IRGLVL >= FTSWRZ > 1, e.g. the reference scenario "Taj1-Nlim", whose IRGLVL is
    stored as text and compares as always true: CIRGW ends at -196 mm.
    """
    return state.ttswrz - state.atswrz


def _irrigation(state: SimState, management: ManagementConfig) -> float:
    """Today's irrigation (iCrop.vba:1201-1246); updates IRGNO and WAT01.

    When several scheduled events match the same day, the last one's amount
    wins and each one counts in IRGNO.
    """
    if management.water == 1:
        if (state.ftswrz <= management.irg_level and state.cbd > 0
                and state.cbd < state.cbd_tsg):
            state.irgno += 1
            return _auto_irrigation_amount(state)
        return 0.0
    if management.water != 3:
        return 0.0  # water = 2, rainfed

    schedule = management.irrigation
    irgw = 0.0
    for n, event in enumerate(schedule.events):
        basis = schedule.timing_basis
        if basis == 1 and state.dap == event.time:
            irgw = event.amount_mm
            state.irgno += 1
        elif basis == 3 and state.doy == event.time:
            irgw = event.amount_mm
            state.irgno += 1
        elif basis in (2, 4) and state.cbd >= event.time and state.wat01[n] == 0:
            if basis == 2:
                irgw = event.amount_mm
            else:
                irgw = max(state.ttswrz - state.atswrz, 0.0)
            state.irgno += 1
            state.wat01[n] = 1
    return irgw


def _root_growth(state: SimState, params: SoilWaterParams, layers: LayerLimits) -> float:
    """Today's root depth increase (iCrop.vba:1255-1261), mm.

    Roots grow between bdBRG and bdTRG, which every crop sets to its emergence
    and begin-seed-growth thresholds (wheat :278-279, maize :435-436 and
    :524-525, legume :598-599). ATSW(RTLN) with RTLN = 0 reads the unused
    0th slot of the VBA array, which is 0.
    """
    atsw_rtln = state.atsw[state.rtln - 1] if state.rtln > 0 else 0.0
    if (state.cbd < state.cbd_emr or state.cbd > state.cbd_bsg
            or state.ddmp == 0 or state.deport >= state.soldep
            or state.deport >= params.meed or atsw_rtln == 0):
        return 0.0
    return params.grtdp * state.bd


def _roots_per_layer(state: SimState, layers: LayerLimits, n_layers: int) -> list[float]:
    """Root length in each layer, and the deepest rooted layer (:1264-1271)."""
    rlyer = [0.0] * 10
    dptop = 0.0
    state.rtln = 0
    for i in range(n_layers):
        rlyer[i] = min(max(state.deport - dptop, 0.0), layers.dlyer[i])
        if rlyer[i] > 0:
            state.rtln = i + 1
        dptop += layers.dlyer[i]
    return rlyer


def _runoff(state: SimState, soil: SoilConfig, layers: LayerLimits) -> float:
    """Runoff by a modified curve-number method, rainfed only (iCrop.vba:1274-1297).

    Soltani & Sinclair (2025) cite Williams (1991) and Hoogenboom et al.
    (2019) for it. The retention parameter is the usual
    S = 254 * (100 / CN - 1) mm, but the initial abstraction is not the fixed
    0.2 * S of the standard method: it is SWER * S, with SWER = 0.15 times the
    dryness of the top soil, (SAT - WL) / (SAT - LL), so 0 at saturation and
    0.15 at the lower limit (more below it). Dryness comes from layer 1 if it
    is at least 250 mm deep, else from the mean of layers 1 and 2.
    """
    if state.rain <= 0.01:
        return 0.0

    def dryness(i: int) -> float:
        return (layers.wlst[i] - state.wl[i]) / (layers.wlst[i] - layers.wlll[i])

    s = 254.0 * (100.0 / soil.cn - 1.0)
    if layers.dlyer[0] >= 250:
        swer = 0.15 * dryness(0)
    else:
        swer = 0.15 * (dryness(0) * 0.5 + dryness(1) * 0.5)
    swer = max(swer, 0.0)
    if state.rain - swer * s > 0:
        return (state.rain - swer * s) ** 2 / (state.rain + (1.0 - swer) * s)
    return 0.0


def _potential_et(state: SimState, salb: float) -> float:
    """Priestley-Taylor PET (iCrop.vba:1308-1313), mm d-1."""
    td = 0.6 * state.tmax + 0.4 * state.tmin
    cover = math.exp(-KET * state.etlai)
    albedo = CALB * (1.0 - cover) + salb * cover
    eeq = state.srad * (0.004876 - 0.004374 * albedo) * (td + 29.0)
    pet = eeq * 1.1
    if state.tmax > 34:
        pet = eeq * ((state.tmax - 34.0) * 0.05 + 1.1)
    if state.tmax < 5:
        pet = eeq * 0.01 * math.exp(0.18 * (state.tmax + 20.0))
    return pet


def _soil_evaporation(state: SimState, irgw: float) -> float:
    """Two-stage soil evaporation (iCrop.vba:1316-1324), mm d-1.

    Stage 2 (square-root decline with days since wetting) starts when the
    surface has dried for a day, when YESTERDAY's FTSWRZ is below 0.5, or when
    layer 1 is nearly empty. On the first spin-up day FTSWRZ is the previous
    season's last value (SEASON_CARRY_FIELDS), or 0 in the first season of a
    run, which makes that day stage 2.
    """
    eos = state.pet * math.exp(-KET * state.etlai)
    if state.pet > EOSMIN and eos < EOSMIN:
        eos = EOSMIN

    sevp = eos
    if state.rain + irgw > WETWAT:
        state.dyse = 1.0
    if state.dyse > 1 or state.ftswrz < 0.5 or state.atsw[0] <= 1:
        sevp = eos * ((state.dyse + 1.0) ** 0.5 - state.dyse ** 0.5)
        state.dyse += 1.0
    return sevp


def _transpiration(state: SimState, params: SoilWaterParams) -> None:
    """Transpiration from today's growth (iCrop.vba:1329-1338).

    With vpd_type = 1 the hourly DMProduction has already set TR and SoilWater
    keeps it.
    """
    if params.vpd_type == 0:
        vptmin = 0.6108 * math.exp(17.27 * state.tmin / (state.tmin + 237.3))
        vptmax = 0.6108 * math.exp(17.27 * state.tmax / (state.tmax + 237.3))
        state.vpd = params.vpdf * (vptmax - vptmin)
        state.tr = state.ddmp * state.vpd / state.tec
    if state.tr < 0:
        state.tr = 0.0


def _survival_vpd(state: SimState, params: SoilWaterParams) -> float:
    """VPD used by the drought-survival transpiration (iCrop.vba:1343).

    VBA BUG, replicated: VPD is assigned only in the vpd_type = 0 branch of
    SoilWater (:1332); the hourly DMProduction keeps its VPD in VPD1 (:953).
    With vpd_type = 1 the survival formula therefore reads an unassigned VPD,
    which VBA treats as 0, and TRSURV is always 0. (VPD is a global: in a
    multi-scenario macro run it can instead hold a value left by an earlier
    vpd_type = 0 scenario, which a single-scenario run cannot reproduce.) No
    cultivar in the 2022 source workbook uses vpd_type = 1 or surviv = 1.
    """
    return state.vpd if params.vpd_type == 0 else 0.0


def _drought_survival(state: SimState, params: SoilWaterParams, sla: float) -> None:
    """Minimum transpiration through the epidermis under severe drought
    (iCrop.vba:1342-1349): when it exceeds TR, it replaces TR and the water
    lost is paid for with leaf area.

    Runs after CTR has been accumulated (:1339), so the extra transpiration
    reaches the soil but not CTR.
    """
    if params.surviv != 1:
        return
    vpd = _survival_vpd(state, params)
    trsurv = state.lai * params.epcond * vpd * state.dayl * 3600 * 0.0022 / (state.tmp + 273)
    if state.ftswrz < params.wssg and trsurv > state.tr:
        state.tr = trsurv
        state.lai -= state.tr / (9 * (1 - params.ltlrwc)) * sla * 1000
        if state.lai < 0:
            state.lai = 0.0


def _update_layers(state: SimState, layers: LayerLimits, rlyer: list[float],
                   n_layers: int, params: SoilWaterParams) -> None:
    """Uptake, evaporation and drainage per layer, then the root-zone and
    profile totals (iCrop.vba:1352-1397)."""
    wuur = state.tr / (state.aroot + 0.00000001)
    tse = state.sevp
    wu = [0.0] * 10
    se = [0.0] * 10
    for i in range(n_layers):
        wu[i] = rlyer[i] * state.rt[i] * wuur
        se[i] = tse
        if se[i] > (state.wl[i] - layers.wlad[i]) * layers.drainf[i]:
            se[i] = (state.wl[i] - layers.wlad[i]) * layers.drainf[i]
        if state.wl[i] <= layers.wlad[i]:
            se[i] = 0.0
        tse = max(tse - se[i], 0.0)

    state.wrz = state.wrzul = state.wrzst = state.atswrz = 0.0
    state.ttswrz = state.wsol = state.atswsl = state.ttswsl = state.aroot = 0.0
    for i in range(n_layers):
        if i == 0:
            flin = state.rain + state.irgw - state.runof
        else:
            flin = state.flout[i - 1]
        flin = max(flin, 0.0)

        state.wl[i] += flin - wu[i] - se[i]
        state.flout[i] = max((state.wl[i] - layers.wlul[i]) * layers.drainf[i], 0.0)
        state.wl[i] -= state.flout[i]

        state.atsw[i] = max(state.wl[i] - layers.wlll[i], 0.0)
        state.ttsw[i] = layers.wlul[i] - layers.wlll[i]
        state.ftsw[i] = state.atsw[i] / state.ttsw[i]
        if state.ftsw[i] > params.wssg:
            state.rt[i] = 1.0
        else:
            state.rt[i] = max(state.ftsw[i] / params.wssg, 0.0)

        share = rlyer[i] / layers.dlyer[i]
        state.aroot += rlyer[i] * state.rt[i]
        state.wrz += state.wl[i] * share
        state.wrzul += layers.wlul[i] * share
        state.wrzst += layers.wlst[i] * share
        state.atswrz += state.atsw[i] * share
        state.ttswrz += state.ttsw[i] * share
        state.ftswrz = state.atswrz / state.ttswrz

        state.wsol += state.wl[i]
        state.atswsl += state.atsw[i]
        state.ttswsl += state.ttsw[i]
        state.ftswsl = state.atswsl / state.ttswsl


def _stress_factors(state: SimState, params: SoilWaterParams) -> None:
    """Water-stress factors and flood kill (iCrop.vba:1400-1408).

    WSFN divides by WSSN + 0.0001 (:1402) where WSFL and WSFG do not. With a
    blank WSSN (read as 0) WSFN is 1 whenever FTSWRZ > 0; the 0.0001 only
    avoids a division by zero when FTSWRZ is exactly 0, giving WSFN = 0.
    """
    f = state.ftswrz
    state.wsfl = 1.0 if f > params.wssl else f / params.wssl
    state.wsfg = 1.0 if f > params.wssg else f / params.wssg
    state.wsfn = 1.0 if f > params.wssn else f / (params.wssn + 0.0001)
    state.wsfd = (1.0 - state.wsfg) * params.wssd + 1.0
    if state.wrz <= state.wrzul:
        state.wsxf = 1.0
    else:
        state.wsxf = (state.wrzst - state.wrz) / (state.wrzst - state.wrzul)
    state.wsxf = max(state.wsxf, 0.0)

    if state.wsxf <= 0.02:
        state.fldur += 1
    else:
        state.fldur = 0.0
    if state.fldur > params.fldkil:
        state.cbd = state.cbd_tsg
        state.matyp = 5


def step_soil_water(
    state: SimState,
    params: SoilWaterParams,
    soil: SoilConfig,
    management: ManagementConfig,
    sla: float,
) -> None:
    """Update all soil water state variables for one day.

    `sla` is CropLAI's specific leaf area (Crop row 12, :726), which the
    drought-survival leaf loss reads (:1346).
    """
    layers = layer_limits(soil)
    n_layers = soil.n_layers

    if state.ini_sw == 0:
        _initialise(state, soil, layers, params, management)

    if state.dap == 1:
        _reset_balance_at_sowing(state, n_layers)

    state.irgw = _irrigation(state, management)
    state.cirgw += state.irgw

    # LDRAIN is a layer number; FLOUT is still yesterday's here (:1251).
    # LDRAIN = 0 reads the never-written FLOUT(0); SoilConfig rejects
    # values outside 0-10, where VBA stops with "subscript out of range".
    ldrain = round(soil.ldrain)
    state.drain = state.flout[ldrain - 1] if ldrain >= 1 else 0.0
    state.cdrain += state.drain

    state.deport += _root_growth(state, params, layers)
    rlyer = _roots_per_layer(state, layers, n_layers)
    state.rlyer = rlyer  # a VBA global: SoilN reads it for plant-available N (:1739)

    state.runof = _runoff(state, soil, layers) if management.water == 2 else 0.0
    state.crain += state.rain
    state.crunof += state.runof

    state.etlai = state.lai if state.cbd <= state.cbd_bsg else state.blslai
    state.pet = _potential_et(state, soil.salb)
    state.sevp = _soil_evaporation(state, state.irgw)
    state.ce += state.sevp

    _transpiration(state, params)
    state.ctr += state.tr
    _drought_survival(state, params, sla)

    _update_layers(state, layers, rlyer, n_layers, params)
    _stress_factors(state, params)
