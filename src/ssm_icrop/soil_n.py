"""Soil nitrogen balance (replaces VBA SoilN GoSub, iCrop.vba:1575-1766).

Runs when nitrogen == 2, after SoilWater (iCrop.vba:86), on every pre-sowing
day of the FindSimSowDate spin-up (iCrop.vba:1794) as well as every crop day.
Daily order, as in the VBA:

  1. Season initialisation, once (iniSNB, :1577-1618)
  2. Reset of the mineralization, leaching and denitrification sums at DAP 1
     (:1620-1624); fertilizer and volatilization sums are NOT reset
  3. Net mineralization per layer (:1627-1642)
  4. Fertilizer application and volatilization (:1645-1689)
  5. Downward movement with drainage water, leaching (:1692-1698)
  6. Denitrification, layers 1 and 2 only (:1701-1722)
  7. Plant uptake per layer, from today's NUP (:1725-1727)
  8. Layer update, concentration, plant-available N (:1730-1744)
  9. Mineral N in the top 600 mm (:1747-1759)

Inputs: the Soil sheet per layer (iCrop.vba:1580-1586, on SoilLayer), the
Manag sheet's N schedule (ManagementConfig.nitrogen_schedule), today's TMP,
DAP, CBD and DOY, today's NUP and BNF from PlantN, and SoilWater's state of
the same day: WL, ATSW, FTSW, FLOUT and RLYER are all today's values, because
SoilWater runs first. The per-layer N state of the
previous day (NCON, NAVL, SNAVL, CNSOL60) is read before it is updated.

Constants are hardcoded in the VBA lines cited at each use.

VBA behaviour kept although it looks unintended, each in its own function:
- _scheduled_application: an event matching several times is applied several
  times (DAP-based events at DAP 0 fire on every spin-up day), and when
  several CBD-based events become due on the same day only the last one's
  amount is applied (:1646-1670).
- _leaching_out_of_profile: leached N is the outflow of layer NLYER, while the
  water balance's DRAIN is the outflow of layer LDRAIN (:1697, :1251).

nitrogen = 2 needs water = 1, 2 or 3, and ManagementConfig rejects water = 0.
Without SoilWater, NLYER (:1138) and WL are never set: VBA then simulates no
soil layer at all, or stops with a division by zero at :1598 if an earlier
scenario of the same macro run left NLYER set.
"""

import math

from .inputs import ManagementConfig, NitrogenSchedule, SoilConfig
from .soil_water import LayerLimits, layer_limits
from .state import SimState

# Fields the VBA carries from one season into the next: globals that neither
# LocManagInputs nor iniSNB resets (NAVL is ReDim'd only per scenario, :64).
# On every spin-up day SoilN removes NAVL / SNAVL * (NUP - BNF) from each layer
# (:1726), with NUP and BNF left by the last crop day, because PlantN does not
# run before sowing. NUP - BNF < 0 adds N: past bdTSG PlantN sets NUP = 0 but
# leaves BNF at its last value (:1435-1436).
# NAVL's ReDim zeroes it only until the first spin-up day's update (:1739), so
# the NUP and BNF of the previous scenario in a VBA macro run reach SoilN from
# the second spin-up day on; the port runs each scenario on its own.
SEASON_CARRY_FIELDS = ("navl", "snavl", "nup", "bnf")

TOP_DEPTH = 600.0         # mm, depth of the CNSOL60 sum (:1604)
NCON_MIN_MIN = 0.0002      # g N g-1 water: mineralization stops here (:1636)
NCON_DNIT_MAX = 0.0004     # g N g-1 water: cap on denitrified concentration (:1706)
NCON_MOBILE = 0.000001     # g N g-1 water: at or below it N does not move (:1694); this much
#                            is never available for uptake, whatever NCON (:1739)
SNAVL_EPS = 0.000001       # added to SNAVL against division by zero (:1726)
THICK_LAYER1 = 250.0       # mm: above it, layer 2 does not denitrify (:1713)


def _initialise(state: SimState, soil: SoilConfig, limits: LayerLimits) -> None:
    """The iniSNB block (iCrop.vba:1577-1618), once per season.

    Runs on the first spin-up day, after that day's SoilWater, so NCON uses
    the water content WL after the first day's balance. Initial nitrate (Soil
    col 13) is in kg N ha-1 and divided by 10 to g N m-2 (:1595).
    """
    state.cnsol = 0.0
    for i, layer in enumerate(soil.active_layers):
        soilml = limits.dlyer[i] * layer.bulk_density * (1 - layer.coarse_fraction) * 1000
        norg = layer.organic_n_pct * 0.01 * soilml
        state.mnorg[i] = norg * layer.min_fraction
        state.nsol[i] = layer.init_no3 / 10
        state.insol[i] = state.nsol[i]
        state.ncon[i] = state.nsol[i] / (state.wl[i] * 1000)
        state.cnsol += state.nsol[i]

    state.cnsol60 = _top_soil_n(state, limits, soil.n_layers)
    state.isoln = state.cnsol
    state.cnfert = 0.0
    state.cnvol = 0.0
    state.cnleach = 0.0
    state.cnmin = 0.0
    state.cndnit = 0.0
    state.ini_snb = 1


def _reset_balance_at_sowing(state: SimState) -> None:
    """DAP 1: save and reset three of the five N sums (iCrop.vba:1620-1624).

    CNFERT and CNVOL keep running, so fertilizer applied before sowing stays
    in the season totals.
    """
    state.cnmin0, state.cnmin = state.cnmin, 0.0
    state.cnleach0, state.cnleach = state.cnleach, 0.0
    state.cndnit0, state.cndnit = state.cndnit, 0.0


def _soil_temperature(state: SimState) -> float:
    """TMPS: mean air temperature capped at 35 degC (iCrop.vba:1627-1628)."""
    return min(state.tmp, 35.0)


def _mineralization(state: SimState, tmps: float, n_layers: int) -> list[float]:
    """Net mineralization per layer (iCrop.vba:1630-1641).

    The water factor RN rises with FTSW to 1 at FTSW = 0.9, then falls to 0 at
    field capacity; it is 0 above it. Mineralization slows linearly with
    yesterday's N concentration and stops at 200 mg N per litre.
    """
    nmin = [0.0] * 10
    kn = 24 * math.exp(17.753 - 6350.5 / (tmps + 273)) / 168
    for i in range(n_layers):
        ftsw = state.ftsw[i]
        rn = 1.111 * ftsw if ftsw < 0.9 else 10 - 10 * ftsw
        if rn < 0:
            rn = 0.0
        value = state.mnorg[i] * rn * (1 - math.exp(-kn))
        value = value * (NCON_MIN_MIN - state.ncon[i]) / NCON_MIN_MIN
        if value < 0:
            value = 0.0
        nmin[i] = value
        state.mnorg[i] -= value
    return nmin


def _scheduled_application(state: SimState, schedule: NitrogenSchedule) -> tuple[float, float]:
    """NATiT 1, 2 or 3: fertilizer by DAP, CBD or DOY (iCrop.vba:1646-1670).

    Returns (NFERT, NVOL) in g N m-2. VOLFI is in per cent (Manag header
    "(%)"), divided by 100 at :1650.

    Two VBA behaviours are kept:
    - The DAP and DOY tests have no "already applied" flag, so an event fires
      on every day it matches. Before sowing DAP is 0 on every spin-up day, so
      an event at DAP 0 is applied once per spin-up day.
    - NFERT is assigned, not added. When several events match on one day the
      last one's amount wins. With CBD-based timing the earlier events are
      also flagged as applied (NFA01), so their N is lost.
    """
    nfert = nvol = 0.0
    basis = schedule.timing_basis
    for n, event in enumerate(schedule.events):
        if basis == 1:
            due = state.dap == event.time
        elif basis == 2:
            due = state.cbd >= event.time and state.nfa01[n] == 0
        else:
            due = state.doy == event.time
        if due:
            nfert = event.amount
            nvol = event.volatilization_fraction / 100 * nfert
            if basis == 2:
                state.nfa01[n] = 1
    return nfert, nvol


def _automatic_application(state: SimState, schedule: NitrogenSchedule) -> tuple[float, float]:
    """NATiT 4: automatic N application, any crop (iCrop.vba:1671-1686).

    At DAP 1 the top 600 mm are topped up to ntrsh0. On every other day,
    spin-up days included, napply1 is applied while CBD is inside the window
    (bdBFRT, bdTFRT), the root zone holds more than FRTWAT mm and the top
    600 mm hold less than ntrsh1. CNSOL60 is yesterday's value. The counter
    nfrt_cntr (:1685) only numbers rows of a printout and is not ported.
    """
    auto = schedule.auto
    nfert = nvol = 0.0
    if state.dap == 1:
        if state.cnsol60 < auto.ntrsh0:
            nfert = auto.ntrsh0 - state.cnsol60
            nvol = auto.nvolf0 / 100 * nfert
    elif (auto.bd_bfrt < state.cbd < auto.bd_tfrt and state.atswrz > auto.frtwat
          and state.cnsol60 < auto.ntrsh1):
        nfert = auto.napply1
        nvol = auto.nvolf1 / 100 * nfert
    return nfert, nvol


def _downward_movement(state: SimState, n_layers: int) -> list[float]:
    """N carried out of each layer by today's drainage (iCrop.vba:1692-1695).

    The share is FLOUT / (WL + FLOUT): WL is already net of today's outflow.
    No N moves out of a layer whose concentration is at most 1 mg N per litre.
    """
    nout = [0.0] * 10
    for i in range(n_layers):
        nout[i] = state.nsol[i] * (state.flout[i] / (state.wl[i] + state.flout[i]))
        if state.ncon[i] <= NCON_MOBILE:
            nout[i] = 0.0
    return nout


def _leaching_out_of_profile(nout: list[float], n_layers: int) -> float:
    """NLEACH = NOUT(NLYER) (iCrop.vba:1697).

    The water balance takes DRAIN from layer LDRAIN instead (:1251), and from
    yesterday's outflow; NLEACH is today's outflow of the deepest simulated
    layer. The two agree in layer only when LDRAIN = NLYER, as in the "Danesh"
    soil of the reference scenarios.
    """
    return nout[n_layers - 1]


def _denitrification(state: SimState, tmps: float, limits: LayerLimits,
                     n_layers: int) -> list[float]:
    """Denitrification in layers 1 and 2 above field capacity (iCrop.vba:1701-1721).

    Only a layer with FTSW > 1 denitrifies, scaled by how far its water content
    lies between field capacity and saturation. If layer 1 is thicker than
    250 mm, layer 2 does not denitrify (:1713). The VBA sets NDNIT(2) = 0
    inside the layer loop; computing layer 2 and then zeroing it, as here,
    gives the same result for every NLYER.
    """
    ndnit = [0.0] * 10
    for i in range(min(n_layers, 2)):
        if state.ftsw[i] > 1:
            xncon = min(state.ncon[i], NCON_DNIT_MAX)
            kdnit = 6 * math.exp(0.07735 * tmps - 6.593)
            value = xncon * (1 - math.exp(-kdnit))
            value = value * state.wl[i] * 1000
            wfndnit = (state.wl[i] - limits.wlul[i]) / (limits.wlst[i] - limits.wlul[i])
            if wfndnit > 1:
                wfndnit = 1.0
            ndnit[i] = value * wfndnit
    if limits.dlyer[0] > THICK_LAYER1:
        ndnit[1] = 0.0
    return ndnit


def _plant_uptake(state: SimState, n_layers: int) -> list[float]:
    """Today's uptake NUP - BNF, shared by yesterday's available N (iCrop.vba:1725-1727).

    Before sowing PlantN does not run, so NUP and BNF are whatever the last
    crop day left: 0 in a scenario's first season here, where each scenario
    runs on its own, but the previous scenario's values in a VBA macro run.
    """
    nu = [0.0] * 10
    for i in range(n_layers):
        nu[i] = (state.navl[i] / (state.snavl + SNAVL_EPS)) * (state.nup - state.bnf)
    return nu


def _update_layers(state: SimState, limits: LayerLimits, n_layers: int,
                   nmin: list[float], nout: list[float], ndnit: list[float],
                   nu: list[float]) -> None:
    """New mineral N, concentration and available N per layer (iCrop.vba:1730-1744).

    Fertilizer and volatilization enter layer 1 only. Available N counts the
    N above 1 mg N per litre in the plant-available water of the rooted part
    of the layer.
    """
    state.snavl = 0.0
    state.cnsol = 0.0
    for i in range(n_layers):
        if i == 0:
            state.nsol[i] = (state.nsol[i] + nmin[i] + state.nfert - state.nvol
                             - nout[i] - ndnit[i] - nu[i])
        else:
            state.nsol[i] = (state.nsol[i] + nout[i - 1] + nmin[i]
                             - nout[i] - ndnit[i] - nu[i])
        state.ncon[i] = state.nsol[i] / (state.wl[i] * 1000)

        navl = ((state.ncon[i] - NCON_MOBILE) * state.atsw[i] * 1000
                * (state.rlyer[i] / limits.dlyer[i]))
        state.navl[i] = navl if navl > 0 else 0.0

        state.snavl += state.navl[i]
        state.cnsol += state.nsol[i]


def _top_soil_n(state: SimState, limits: LayerLimits, n_layers: int) -> float:
    """Mineral N in the top 600 mm, a layer straddling 600 mm pro rata (iCrop.vba:1602-1614)."""
    dep60 = 0.0
    cnsol60 = 0.0
    for i in range(n_layers):
        dlyer = limits.dlyer[i]
        if dep60 >= TOP_DEPTH:
            nsoly1 = 0.0
        elif dep60 + dlyer <= TOP_DEPTH:
            nsoly1 = state.nsol[i]
        else:
            diff = dep60 + dlyer - TOP_DEPTH
            nsoly1 = state.nsol[i] * (dlyer - diff) / dlyer
        cnsol60 += nsoly1
        dep60 += dlyer
    return cnsol60


def _sequential_sum(values: list[float], n_layers: int) -> float:
    """Left-to-right sum, as the VBA's `S = S + X(L)` loops (:1640, :1720).

    Not the built-in sum(): from Python 3.12 it compensates rounding errors
    and can differ from the VBA in the last bit.
    """
    total = 0.0
    for i in range(n_layers):
        total += values[i]
    return total


def step_soil_n(
    state: SimState,
    soil: SoilConfig,
    management: ManagementConfig,
) -> None:
    """Update per-layer and cumulative soil N variables for one day."""
    schedule = management.nitrogen_schedule
    limits = layer_limits(soil)
    n_layers = soil.n_layers

    if state.ini_snb == 0:
        _initialise(state, soil, limits)
        # NFA01 is reset in LocManagInputs (:151), before this first call
        state.nfa01 = [0] * len(schedule.events)

    if state.dap == 1:
        _reset_balance_at_sowing(state)

    tmps = _soil_temperature(state)
    nmin = _mineralization(state, tmps, n_layers)
    state.snmin = _sequential_sum(nmin, n_layers)
    state.cnmin += state.snmin

    if schedule.timing_basis == 4:
        state.nfert, state.nvol = _automatic_application(state, schedule)
    else:
        state.nfert, state.nvol = _scheduled_application(state, schedule)
    state.cnfert += state.nfert
    state.cnvol += state.nvol

    nout = _downward_movement(state, n_layers)
    state.nleach = _leaching_out_of_profile(nout, n_layers)
    state.cnleach += state.nleach

    ndnit = _denitrification(state, tmps, limits, n_layers)
    state.sndnit = _sequential_sum(ndnit, n_layers)
    state.cndnit += state.sndnit

    nu = _plant_uptake(state, n_layers)
    _update_layers(state, limits, n_layers, nmin, nout, ndnit, nu)
    state.cnsol60 = _top_soil_n(state, limits, n_layers)
