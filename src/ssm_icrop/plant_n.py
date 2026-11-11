"""Plant nitrogen uptake and distribution (replaces VBA PlantN, iCrop.vba:1416-1569).

Runs when nitrogen == 2, after DMDistribution and BEFORE SoilWater and SoilN
(iCrop.vba:83-86). It is not called on the pre-sowing days of FindSimSowDate.
It therefore reads yesterday's SNAVL, FTSWRZ, WSFN and WSXF, and today's
crop values (CBD, LAI, GLAI, WST, GST, WVEG, SGR, DDMP, BD).

Daily order, as in the VBA:

  1. Season initialisation, once (iniPNB, :1417-1431): stem and leaf N at
     their growth concentrations, CNUP, NGRN, BNF and CUMBNF reset, WSFN = 1
  2. SNCS: SNCS1 before bdBSG, SNCS2 from it on (:1433)
  3. One of three phases (:1435-1557):
     - CBD <= bdEMR or CBD > bdTSG: no uptake, no N flows
     - bdEMR < CBD < bdBSG: uptake to fill the N demand of new leaf and stem
       growth plus the stem's deficit, capped by MXNUP and SNAVL; N fixation
       for legumes past bdBNF
     - bdBSG <= CBD <= bdTSG: grain N demand at GNCmax plus new growth, met by
       uptake and by translocation from leaves and stems; grain N kept between
       GNCmin and GNCmax per gram of SGR
  4. Pool update, N stress factor and the translocatable N for tomorrow
     (:1559-1568)

GCC is DMDistribution's grain conversion coefficient (Crop row 32,
iCrop.vba:985); bdEMR, bdBSG, bdTSG and bdBNF come from phenology.

VBA behaviour kept although it looks unintended:
- _vegetative_fixation: before bdBSG, BNF is assigned only when NUP > SNAVL
  (:1451) and otherwise keeps yesterday's value, which CUMBNF adds again and
  SoilN subtracts from NUP (:1726).
- Past bdTSG, NUP = 0 but BNF keeps its last seed-growth value (:1435-1436),
  so SoilN adds BNF to the soil every day until maturity, and on the next
  season's spin-up days (soil_n.SEASON_CARRY_FIELDS). Zero for wheat and maize.

Dead stores left out: TRLN at :1480 is overwritten at :1565 before any read,
and XNVEG at :1515 and :1518 is not read after it.
"""

from dataclasses import dataclass

from .state import SimState

# LocManagInputs resets none of PlantN's globals, and iniPNB only some. Of the
# rest, NFC is the one PlantN reads before assigning it in a new season: a
# running mean of yesterday's value (:1444). NUP and BNF, which SoilN reads
# before sowing, are carried by soil_n.SEASON_CARRY_FIELDS. In a VBA macro run
# NFC also carries from one scenario into the next; the port runs each
# scenario on its own, with NFC = 0 like the run's first scenario.
SEASON_CARRY_FIELDS = ("nfc",)

GRAIN_SHARE_EPS = 0.00000001        # :1486, against division by zero
NSTRS_EPS = 0.000000000001          # :1564
FXLF_EPS = 0.000000000001           # :1566
DAYS_TO_TSG_EPS = 0.0001            # :1509


@dataclass
class PlantNParams:
    """Crop-sheet parameters for plant N (iCrop.vba:1418-1425)."""

    slng: float                # row 61 -- SLNG: specific leaf N, green leaves (g m-2)
    slns: float                # row 62 -- SLNS: specific leaf N, senesced leaves (g m-2)
    sncg: float                # row 63 -- SNCG: stem N concentration, growth (g g-1)
    sncs1: float               # row 64 -- SNCS1: stem N at senescence, before bdBSG
    sncs2: float               # row 65 -- SNCS2: stem N at senescence, from bdBSG on
    gnc_min: float             # row 66 -- GNCmin: minimum grain N concentration (g g-1)
    gnc_max: float             # row 67 -- GNCmax: maximum grain N concentration (g g-1)
    mxnup: float               # row 68 -- MXNUP: maximum daily N uptake (g m-2 d-1)


def step_plant_n(state: SimState, params: PlantNParams, gcc: float) -> None:
    """Update plant N uptake, the N pools and the N stress factor for one day."""
    if state.ini_pnb == 0:
        _initialise(state, params)

    # :1433, "higher stem N in senesced stems before BSG"
    state.sncs = params.sncs1 if state.cbd < state.cbd_bsg else params.sncs2

    if state.cbd <= state.cbd_emr or state.cbd > state.cbd_tsg:
        # :1435-1436. BNF is not reset here (see the module docstring).
        state.nup = 0.0
        state.xnlf = state.xnst = state.inlf = state.inst = state.ingrn = 0.0
        pot_nup = 0.0
    elif state.cbd < state.cbd_bsg:
        pot_nup = _vegetative_phase(state, params)
    else:  # bdBSG <= CBD <= bdTSG
        pot_nup = _seed_growth_phase(state, params, gcc)

    # :1559-1568. Evaluation order kept: NST + INST - XNST is (NST + INST) - XNST.
    state.nst = state.nst + state.inst - state.xnst
    state.nlf = state.nlf + state.inlf - state.xnlf
    state.nveg = state.nlf + state.nst
    state.ngrn = state.ngrn + state.ingrn
    state.cnup = state.cnup + state.nup
    state.nstrs = state.nup / (pot_nup + NSTRS_EPS)
    state.trln = state.lai * (params.slng - params.slns) + (
        state.nst - state.wst * state.sncs
    )
    fxlf = state.lai * (params.slng - params.slns) / (state.trln + FXLF_EPS)
    if fxlf > 1:
        fxlf = 1.0
    if fxlf < 0:
        fxlf = 0.0
    state.fxlf = fxlf


def _initialise(state: SimState, params: PlantNParams) -> None:
    """iniPNB block (iCrop.vba:1417-1431), on the first crop day of a season."""
    state.nst = state.wst * params.sncg
    state.nlf = state.lai * params.slng
    state.wsfn = 1.0
    state.cnup = state.nst + state.nlf
    state.ngrn = 0.0
    state.bnf = 0.0
    state.cumbnf = 0.0
    state.ini_pnb = 1


def _vegetative_phase(state: SimState, params: PlantNParams) -> float:
    """bdEMR < CBD < bdBSG (iCrop.vba:1437-1480). Returns the potential NUP."""
    state.ingrn = 0.0
    nstdf = (state.wst * params.sncg) - state.nst
    if nstdf < 0:
        nstdf = 0.0
    nup = (state.gst * params.sncg) + (state.glai * params.slng) + nstdf
    pot_nup = nup
    if nup > params.mxnup:
        nup = params.mxnup
    # :1444, "from Sinclair et al. 2003". Uses NUP after the MXNUP cap and
    # before the stress factors. VBA stops with a division by zero if WVEG = 0.
    state.nfc = state.nfc * 3 / 4 + nup / state.wveg * (1 / 4)
    if state.cbd > state.cbd_bnf:
        nup = nup * state.wsfn
    if nup < 0:
        nup = 0.0
    if state.ftswrz > 1:
        nup = nup * state.wsxf
    if state.ddmp == 0:
        nup = 0.0
    if state.cbd_bnf >= state.cbd_bsg and nup > state.snavl:
        nup = state.snavl  # non-legume
    if state.cbd < state.cbd_bnf and nup > state.snavl:
        nup = state.snavl  # legume before N fixation starts
    state.nup = nup

    _vegetative_fixation(state)
    state.cumbnf = state.cumbnf + state.bnf

    state.inst, state.xnst, state.inlf, state.xnlf = _allocate_to_leaf_and_stem(
        state, params, nup
    )
    return pot_nup


def _vegetative_fixation(state: SimState) -> None:
    """N fixation before bdBSG, VBA behaviour kept (iCrop.vba:1451-1452).

        If NUP > SNAVL Then BNF = NUP - SNAVL
        If BNF < 0 Then BNF = 0

    BNF is assigned only when uptake exceeds the soil's available N. On any
    other day it keeps yesterday's value, although the crop fixes nothing
    then: CUMBNF adds that value again (:1453), and SoilN removes
    NUP - BNF from the soil (:1726), which is negative, and so adds N, when
    the stale BNF exceeds today's NUP. The seed-growth phase, by contrast,
    assigns BNF every day (:1505-1506).

    Without fixation, BNF stays at the 0 of the season initialisation: for
    wheat and maize (bdBNF = 999 >= bdBSG) NUP has just been capped at SNAVL,
    and so has a legume's before bdBNF. Only a legume past bdBNF reaches the
    stale value. Kept as it is, because the VBA is the authority.
    """
    if state.nup > state.snavl:
        state.bnf = state.nup - state.snavl
    if state.bnf < 0:
        state.bnf = 0.0


def _seed_growth_phase(state: SimState, params: PlantNParams, gcc: float) -> float:
    """bdBSG <= CBD <= bdTSG (iCrop.vba:1482-1556). Returns the potential NUP."""
    ingrn = state.sgr * params.gnc_max  # first estimate, at the maximum GNC
    nup = ingrn + (state.gst * params.sncg) + (state.glai * params.slng)
    pot_nup = nup
    nup_fr_grn = ingrn / (nup + GRAIN_SHARE_EPS)  # grain share, before the caps
    if nup < 0:
        nup = 0.0
    if nup > params.mxnup:
        nup = params.mxnup

    # :1490-1498, daily N fixation. Uses NUP before the WSXF and DDMP checks.
    if state.cbd < state.cbd_bnf:
        dnf = 0.0  # before N fixation starts, or not a legume
    else:
        pdnf = state.nfc * state.wveg
        if pdnf > nup:
            pdnf = nup
        dnf = pdnf * state.wsfn
        if state.ddmp <= (state.sgr / gcc):  # <= here, < for NUP below
            dnf = 0.0
        if state.ddmp == 0:
            dnf = 0.0

    if state.ftswrz > 1:
        nup = nup * state.wsxf
    if state.ddmp < (state.sgr / gcc):
        nup = 0.0
    if state.ddmp == 0:
        nup = 0.0
    if state.cbd_bnf >= state.cbd_bsg and nup > state.snavl:
        nup = state.snavl  # non-legume
    if nup > (state.snavl + dnf):
        nup = state.snavl + dnf
    state.nup = nup
    bnf = nup - state.snavl
    if bnf < 0:
        bnf = 0.0
    state.bnf = bnf
    state.cumbnf = state.cumbnf + bnf

    # :1509, today's supply from vegetative tissue, from yesterday's TRLN
    xnveg = state.trln / (state.cbd_tsg + DAYS_TO_TSG_EPS - state.cbd) * state.bd
    if state.sgr == 0:
        xnveg = 0.0
    ingrn = xnveg + nup * nup_fr_grn
    if ingrn < (state.sgr * params.gnc_min):
        ingrn = state.sgr * params.gnc_min
    elif ingrn >= (state.sgr * params.gnc_max):
        ingrn = state.sgr * params.gnc_max
    state.ingrn = ingrn

    if nup > ingrn:
        # uptake exceeds the grain's need: the rest goes to leaf and stem
        state.inst, state.xnst, state.inlf, state.xnlf = _allocate_to_leaf_and_stem(
            state, params, nup - ingrn
        )
    else:
        # the grain draws on leaf and stem, split by yesterday's FXLF
        state.inlf = 0.0
        state.inst = 0.0
        state.xnlf = (ingrn - nup) * state.fxlf
        state.xnst = (ingrn - nup) * (1 - state.fxlf)
    return pot_nup


def _allocate_to_leaf_and_stem(
    state: SimState, params: PlantNParams, supply: float
) -> tuple[float, float, float, float]:
    """Split N supply between stem and leaf (iCrop.vba:1455-1479, :1524-1548).

    The VBA has this block twice, for NUP before bdBSG and for the uptake in
    excess of grain demand (NUP2) after it; the two copies are identical.
    A stem below its senescence N (WST * SNCS) is filled first, and leaf N
    moves to the stem if the supply falls short. Otherwise new leaf area gets
    its N first, and stem N above the senescence level moves to the leaf if
    the supply falls short. Returns (INST, XNST, INLF, XNLF).
    """
    if state.nst <= (state.wst * state.sncs):
        inst = state.wst * state.sncs - state.nst
        xnst = 0.0
        if inst >= supply:
            inlf = 0.0
            xnlf = inst - supply
        else:
            inlf = state.glai * params.slng
            if inlf > (supply - inst):
                inlf = supply - inst
            inst = supply - inlf
            xnlf = 0.0
    else:
        inlf = state.glai * params.slng
        xnlf = 0.0
        if inlf >= supply:
            inst = 0.0
            xnst = inlf - supply
            if xnst > (state.nst - state.wst * state.sncs):
                xnst = state.nst - state.wst * state.sncs
            inlf = supply + xnst
        else:
            inst = supply - inlf
            xnst = 0.0
    return inst, xnst, inlf, xnlf
