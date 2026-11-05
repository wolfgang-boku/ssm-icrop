"""DM partitioning and yield formation (replaces VBA DMDistribution GoSub).

Three phases, keyed off CBD relative to cbd_bsg (begin seed growth) and
cbd_tsg (end seed growth):

  CBD <= cbd_bsg (pre-grain-fill):
    No grain growth. WTOP is continuously latched into state.bsgdm (the
    biomass "frozen" at the moment grain filling begins) and used to derive
    a biomass-adequacy factor (DHIDMF) that scales the potential daily
    harvest index (state.dhi) and a translocatable reserve pool
    (state.trldm) for later grain filling.

  cbd_bsg < CBD <= cbd_tsg (active grain filling):
    SGR (seed growth rate) combines a linear-harvest-index demand term with
    today's production at the current HI ratio, capped by what today's DDMP
    plus translocation from state.trldm can supply.

  CBD > cbd_tsg (grain filling over): no more grain growth.

Independently, when heat/frost response is enabled, a Bindi-et-al. flowering
curve tracks cumulative heat- and frost-induced floret loss during the
flowering window (cbd_bxtf..cbd_txtf) into state.frhtdhi, which scales DHI
during grain filling. With a water balance (water 1-3) the curve uses canopy
temperatures adjusted with state.etlai/state.sevp/state.tr as last set
(SoilWater runs after DMDistribution, iCrop.vba:1021-1022); with water=0 it uses air temperature
(iCrop.vba:1017-1019).

Whatever's left of DDMP after grain filling's glucose cost splits between
leaf (GLF, feeding crop_lai.py) and stem (GST) by a two-regime partition
coefficient. state.wveg accumulates DDMP minus grain's glucose cost
*unclamped* (can go negative when translocation draws down reserves faster
than production replaces them) even though GLF+GST partitioning uses the
clamped-at-zero version — this asymmetry is a genuine VBA behavior (WVEG can
shrink on heavy-translocation days while WLF/WST only ever grow), replicated
here rather than "fixed".
"""

import math
from dataclasses import dataclass

from .state import SimState


@dataclass
class DMDistributionParams:
    # leaf/stem partition
    flf1a: float            # leaf-partition fraction, WTOP < wtopl regime
    flf1b: float            # leaf-partition fraction, WTOP >= wtopl regime
    wtopl: float             # WTOP threshold switching flf1a/flf1b
    flf2: float              # leaf-partition fraction after main-stem leaf growth ends
    # grain filling
    frtrl: float             # fraction of BSG biomass available for translocation
    gcc: float                # grain conversion coefficient (glucose -> grain DM cost)
    pdhi: float               # potential daily harvest index
    wdhi1: float              # WTOP-at-BSG thresholds for the DHIDMF trapezoid
    wdhi2: float
    wdhi3: float
    wdhi4: float
    sncs: float               # stem N conc. at senescence (blocks SGR if N-exhausted)
    mc: float = 0.0           # grain moisture content (%) — for future SummaryPrintOut
    # heat/frost effect on flowering (Bindi et al.)
    heat: int = 0             # 0=off, 1=on
    tp2h: float = 0.0         # heat cardinal temp (canopy Tmax)
    tch: float = 0.0          # heat ceiling temp
    tp1f: float = 0.0         # frost cardinal temp (canopy Tmin)
    tbf: float = 0.0          # frost base temp
    rfmax: float = 1.0        # maximum relative flowering rate


def _dhidmf(bsgdm: float, wdhi1: float, wdhi2: float,
           wdhi3: float, wdhi4: float) -> float:
    """Trapezoidal biomass-adequacy factor: 0 if BSG biomass is too low or
    too high, ramping to 1 across [wdhi1,wdhi2], full effect on [wdhi2,wdhi3],
    ramping back down across [wdhi3,wdhi4]."""
    if bsgdm <= wdhi1 or bsgdm >= wdhi4:
        return 0.0
    if wdhi1 < bsgdm < wdhi2:
        return (bsgdm - wdhi1) / (wdhi2 - wdhi1)
    if wdhi3 < bsgdm < wdhi4:
        return (wdhi4 - bsgdm) / (wdhi4 - wdhi3)
    if wdhi2 <= bsgdm <= wdhi3:
        return 1.0
    return 0.0


def step_dm_distribution(state: SimState, params: DMDistributionParams,
                         water_mode: int) -> None:
    """Partition daily DM to organs; update wgrn, wlf, wst, wveg, wtop, hi.

    Args:
        water_mode: management water setting (0=no water balance, matches
            VBA's `water` — canopy temperature falls back to air temperature
            when 0, otherwise adjusts for evaporative cooling)
    """
    if state.ini_dmd == 0:
        flw_dur = int(state.cbd_txtf - state.cbd_bxtf)
        sumflw = 0.0
        for q in range(1, flw_dur + 1):
            frc_dur = q / flw_dur
            flwer_shape = 6.92738 * (frc_dur ** 0.63) - 6.61087 * frc_dur - 0.2613
            sumflw += flwer_shape * params.rfmax
        state.sumflw = sumflw

        state.cumhtf = 0.0
        state.cumfrf = 0.0
        state.wlf = 0.5
        state.wst = 0.5
        state.wveg = state.wlf + state.wst
        state.r5antdm = 0.0
        state.wgrn = 0.0
        state.frhtdhi = 1.0
        state.ini_dmd = 1

    # --- Heat and frost effect on flowering (Bindi et al.), flowering window only
    if params.heat == 1 and state.cbd_bxtf < state.cbd < state.cbd_txtf:
        if water_mode == 0:
            tmax_can = state.tmax
            tmin_can = state.tmin
        else:
            energy_term = -0.1 + 0.241 * state.srad
            intercepted = 1.0 - math.exp(-0.5 * state.etlai)
            evap_term = (intercepted * energy_term - state.sevp) / 2.454
            net_energy = energy_term - evap_term / 2.454 - state.tr
            canopy_adjust = net_energy / (42.7 * 0.034)
            tmax_can = state.tmax + canopy_adjust
            tmin_can = state.tmin + canopy_adjust

        frc_flower = (state.cbd - state.cbd_bxtf) / (state.cbd_txtf - state.cbd_bxtf)
        rf = 6.92738 * (frc_flower ** 0.63) - 6.61087 * frc_flower - 0.2613
        rf = max(0.0, min(1.0, rf))

        heatf1 = (tmax_can - params.tp2h) / (params.tch - params.tp2h)
        heatf1 = max(0.0, min(1.0, heatf1))
        day_htf = heatf1 * rf * params.rfmax
        state.cumhtf += day_htf
        ht_dhi = 1.0 - (state.cumhtf / state.sumflw)
        state.frhtdhi = min(state.frhtdhi, ht_dhi)

        frostf1 = 1.0 - (tmin_can - params.tbf) / (params.tp1f - params.tbf)
        frostf1 = max(0.0, min(1.0, frostf1))
        day_frf = frostf1 * rf * params.rfmax
        state.cumfrf += day_frf
        fr_dhi = 1.0 - (state.cumfrf / state.sumflw)
        state.frhtdhi = min(state.frhtdhi, fr_dhi)

    # --- DM allocated to seed growth
    if state.cbd <= state.cbd_bsg:
        transl = 0.0
        state.sgr = 0.0
        state.bsgdm = state.wtop  # latch WTOP right up to BSG
        dhidmf = _dhidmf(state.bsgdm, params.wdhi1, params.wdhi2,
                         params.wdhi3, params.wdhi4)
        state.dhi = params.pdhi * dhidmf
        state.trldm = state.bsgdm * params.frtrl

    elif state.cbd <= state.cbd_tsg:
        hi_demand = state.dhi * state.frhtdhi * (state.wtop + state.ddmp)
        sgr = hi_demand + state.ddmp * state.hi
        if state.lai == 0.0 and state.nst <= (state.wst * params.sncs):
            sgr = 0.0  # no N available for seed filling
        sgr = max(0.0, sgr)

        if (sgr / params.gcc) > state.ddmp:
            transl = (sgr / params.gcc) - state.ddmp
            transl = min(transl, state.trldm)
        else:
            transl = 0.0

        state.trldm -= transl
        sgr = min(sgr, (state.ddmp + transl) * params.gcc)
        state.sgr = sgr

    else:
        transl = 0.0
        state.sgr = 0.0

    # --- DM available for leaf & stem
    ddmp2 = state.ddmp - state.sgr / params.gcc
    ddmp2 = max(0.0, ddmp2)

    # --- Leaf dry matter growth
    if state.cbd <= state.cbd_blg or state.cbd > state.cbd_tlp:
        state.glf = 0.0
    elif state.cbd <= state.cbd_tlm:
        flf1 = params.flf1a if state.wtop < params.wtopl else params.flf1b
        state.glf = flf1 * ddmp2
    else:  # cbd_tlm < cbd <= cbd_tlp
        state.glf = params.flf2 * ddmp2

    # --- Stem dry matter growth
    state.gst = ddmp2 - state.glf

    # --- Organs accumulated mass
    state.wlf += state.glf
    state.wst += state.gst
    state.wgrn += state.sgr
    state.wveg += state.ddmp - state.sgr / params.gcc  # unclamped, see module docstring
    state.wtop = state.wveg + state.wgrn
    state.hi = state.wgrn / state.wtop
