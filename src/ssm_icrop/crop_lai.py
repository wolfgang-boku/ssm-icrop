"""Leaf area index dynamics (replaces VBA CropLAI, iCrop.vba:718-795, and
CropLAIN, iCrop.vba:796-872).

CropLAI runs when nitrogen = 0, CropLAIN when nitrogen = 2 (iCrop.vba:80-81).
Both run before DMProduction and PlantN, so they read yesterday's GLF and,
in CropLAIN, yesterday's INLF and XNLF.

Sequence per day, shared by both:
  1. Apply yesterday's GLAI/DLAI to LAI — this is the canopy that intercepts
     PAR today (DMProduction reads state.lai *before* recomputing it).
     CropLAIN first caps yesterday's GLAI by the leaf N PlantN supplied,
     INLF / SLNG (:817).
  2. Check for premature maturity (LAI collapses below 0.05 during grain fill).
  3. Compute GLAI (today's growth) and DLAI (today's senescence) for use
     tomorrow, including frost/heat damage.

They differ in senescence: CropLAI lets LAI decline linearly from bdBLS to
maturity, CropLAIN from the leaf N that PlantN moved out of the leaves,
DLAI = XNLF / (SLNG - SLNS) (:842). CropLAIN also latches BLSLAI while
bdTLM < CBD <= bdTLP (:838), where CropLAI latches it until bdBLS. And it
sets R5ANTLAI, the LAI at anthesis, which CropLAI only resets; nothing in the
VBA reads R5ANTLAI, and DailyPrintOut sets it again by the same rule
(:2007-2015).

VBA behaviour kept although it looks unintended:
- _specific_leaf_n: CropLAIN uses SLNG = 2 on the first crop day, not the
  Crop sheet's value (:812, :1418).
- For maize bdTLM = bdTLP = bdSIL (:429-430), so CropLAIN never latches
  BLSLAI and it stays 0. Past bdBSG ETLAI = BLSLAI (:1305), so with
  nitrogen = 2 soil evaporation, albedo and DMDistribution's canopy
  temperature (:1021-1022) see bare soil. The port keeps this.
"""

from dataclasses import dataclass

from .plant_n import PlantNParams
from .state import SimState

SLNG_FIRST_DAY = 2.0  # iCrop.vba:812


@dataclass
class LAIParams:
    phyl: float             # phyllochron — thermal time per leaf node (deg C d)
    placon: float           # leaf-area-per-node constant
    plapow: float           # leaf-area power exponent (before density adjustment)
    a_pla_den: float        # density-adjustment intercept (1 if no estimate)
    b_pla_den: float        # density-adjustment slope (0 if no estimate)
    sla: float              # specific leaf area (m2 g-1)
    frztkil: float          # Tmin at/below which frost damage starts (deg C)
    frzldr: float           # frost damage rate (per deg C)
    htlth: float            # Tmax above which heat damage starts (deg C)
    htldr: float            # heat damage rate (per deg C)


def step_lai(state: SimState, params: LAIParams, pden: float) -> None:
    """CropLAI: update state.lai (today) and state.glai/state.dlai (for tomorrow).

    Args:
        state: simulation state (reads cbd, dtu, bd, glf, wsfl, tmin, tmax;
            writes lai, mxlai, blslai, msnn, pla1, glai, dlai, matyp)
        params: crop LAI parameters
        pden: plant density (plants m-2) — a management input, not a crop trait
    """
    if state.ini_lai == 0:
        _initialise(state)

    _apply_yesterday(state)
    glai = _leaf_area_growth(state, params, pden)

    # --- Senescence (DLAI) for tomorrow
    if state.cbd < state.cbd_bls:
        dlai = 0.0
        state.blslai = state.lai  # latch LAI right up to the start of senescence
    else:
        dlai = state.bd / (state.cbd_mat - state.cbd_bls) * state.blslai

    state.glai = glai
    state.dlai = _frost_and_heat(state, params, dlai)


def step_lai_n(
    state: SimState, params: LAIParams, plant_n: PlantNParams, pden: float,
    crop_type: str,
) -> None:
    """CropLAIN (iCrop.vba:796-872): leaf area limited by PlantN's leaf N flows.

    Reads yesterday's INLF and XNLF; writes the same fields as step_lai, plus
    r5antlai.
    """
    first_day = state.ini_lai == 0
    if first_day:
        _initialise(state)
    slng = _specific_leaf_n(first_day, plant_n)

    # :817, yesterday's growth limited by the N that went into new leaves
    if state.glai > (state.inlf / slng):
        state.glai = state.inlf / slng
    _apply_yesterday(state)
    glai = _leaf_area_growth(state, params, pden)
    # :838, "Saving LAI at TLP", in the ElseIf chain below CBD <= bdBLG (:827)
    if state.cbd > state.cbd_blg and state.cbd_tlm < state.cbd <= state.cbd_tlp:
        state.blslai = state.lai

    dlai = state.xnlf / (slng - plant_n.slns)  # :842

    # :844-850, LAI at anthesis (wheat), silking (maize) or R5 (legumes)
    if crop_type == "WHEAT" and state.cbd <= state.cbd_ant:
        state.r5antlai = state.lai
    elif crop_type == "MAIZE" and state.cbd <= state.cbd_sil:
        state.r5antlai = state.lai
    elif crop_type not in ("WHEAT", "MAIZE") and state.cbd <= state.cbd_r5:
        state.r5antlai = state.lai

    state.glai = glai
    state.dlai = _frost_and_heat(state, params, dlai)


def _specific_leaf_n(first_day: bool, plant_n: PlantNParams) -> float:
    """SLNG as CropLAIN sees it, VBA behaviour kept (iCrop.vba:812, :1418).

    CropLAIN's initialisation sets the global SLNG = 2. PlantN's own
    initialisation reads the Crop sheet value (row 61) later the same day, so
    CropLAIN uses 2 on the first crop day and the sheet value from the second
    day on. On that first day SLNS is whatever PlantN last read: Empty (0) in
    the first nitrogen = 2 scenario of a VBA macro run, the previous
    scenario's value in a later one, the same crop's value from the second
    season on. The port uses the sheet value.

    Neither matters as long as INLF and XNLF are 0 on the first crop day,
    which they are in the port on every season's first day (each starts with
    a fresh state) and in VBA after a season that ended past bdTSG
    (:1435-1436). Kept as it is, because the VBA is the authority.
    """
    return SLNG_FIRST_DAY if first_day else plant_n.slng


def _initialise(state: SimState) -> None:
    """iniLAI block (iCrop.vba:720-735, :798-814). PLAPOW's density adjustment
    is applied in _leaf_area_growth."""
    state.msnn = 1.0
    state.pla1 = 0.0
    state.pla2 = 0.0
    state.lai = 0.0
    state.blslai = 0.0
    state.r5antlai = 0.0
    state.mxlai = 0.0
    state.wsfl = 1.0
    state.ini_lai = 1


def _apply_yesterday(state: SimState) -> None:
    """Yesterday's growth/death becomes today's canopy (for PAR interception)."""
    state.lai = state.lai + state.glai - state.dlai
    if state.cbd_bsg < state.cbd < state.cbd_tsg and state.lai < 0.05:
        state.cbd = state.cbd_tsg
        state.matyp = 2  # premature maturity: canopy collapsed during grain fill
    state.lai = max(0.0, state.lai)
    state.mxlai = max(state.mxlai, state.lai)


def _leaf_area_growth(state: SimState, params: LAIParams, pden: float) -> float:
    """Today's GLAI, for tomorrow; advances MSNN and PLA1 on the main stem."""
    plapow_adj = params.plapow * (params.b_pla_den * pden + params.a_pla_den)
    if state.cbd <= state.cbd_blg:
        return 0.0
    if state.cbd <= state.cbd_tlm:
        inode = state.dtu / params.phyl
        state.msnn += inode
        pla2 = params.placon * (state.msnn ** plapow_adj)
        glai = (pla2 - state.pla1) * pden / 10000.0 * state.wsfl
        state.pla1 = pla2
        state.pla2 = pla2
        return glai
    if state.cbd <= state.cbd_tlp:
        return state.glf * params.sla
    return 0.0


def _frost_and_heat(state: SimState, params: LAIParams, dlai: float) -> float:
    """Raise DLAI for frost and heat damage."""
    # --- Frost effect (overrides DLAI upward)
    if state.cbd > state.cbd_blg and state.tmin < params.frztkil:
        frstf = min(1.0, max(0.0, abs(state.tmin - params.frztkil) * params.frzldr))
        dlai = max(dlai, state.lai * frstf)

    # --- Heat effect (overrides DLAI upward, multiplicative on current DLAI)
    if state.cbd > state.cbd_blg and state.tmax > params.htlth:
        heatf = max(1.0, 1.0 + (state.tmax - params.htlth) * params.htldr)
        dlai = max(dlai, dlai * heatf)
    return dlai
