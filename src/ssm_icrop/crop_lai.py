"""Leaf area index dynamics (replaces VBA CropLAI GoSub — no N stress).

CropLAIN (with N stress) is deferred until the plant-N module exists;
its only differences are an N-limited GLAI cap and an N-driven DLAI.

Sequence per day:
  1. Apply yesterday's GLAI/DLAI to LAI — this is the canopy that intercepts
     PAR today (DMProduction reads state.lai *before* recomputing it).
  2. Check for premature maturity (LAI collapses below 0.05 during grain fill).
  3. Compute GLAI (today's growth) and DLAI (today's senescence) for use
     tomorrow, including frost/heat damage.
"""

from dataclasses import dataclass

from .state import SimState


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
    """Update state.lai (today) and state.glai/state.dlai (for tomorrow).

    Args:
        state: simulation state (reads cbd, dtu, bd, glf, wsfl, tmin, tmax;
            writes lai, mxlai, blslai, msnn, pla1, glai, dlai, matyp)
        params: crop LAI parameters
        pden: plant density (plants m-2) — a management input, not a crop trait
    """
    if state.ini_lai == 0:
        state.msnn = 1.0
        state.pla1 = 0.0
        state.pla2 = 0.0
        state.lai = 0.0
        state.blslai = 0.0
        state.r5antlai = 0.0
        state.mxlai = 0.0
        state.wsfl = 1.0
        state.ini_lai = 1

    # --- Yesterday's growth/death becomes today's canopy (for PAR interception)
    state.lai = state.lai + state.glai - state.dlai
    if state.cbd_bsg < state.cbd < state.cbd_tsg and state.lai < 0.05:
        state.cbd = state.cbd_tsg
        state.matyp = 2  # premature maturity: canopy collapsed during grain fill
    state.lai = max(0.0, state.lai)
    state.mxlai = max(state.mxlai, state.lai)

    # --- Growth (GLAI) for tomorrow
    plapow_adj = params.plapow * (params.b_pla_den * pden + params.a_pla_den)
    if state.cbd <= state.cbd_blg:
        glai = 0.0
    elif state.cbd <= state.cbd_tlm:
        inode = state.dtu / params.phyl
        state.msnn += inode
        pla2 = params.placon * (state.msnn ** plapow_adj)
        glai = (pla2 - state.pla1) * pden / 10000.0 * state.wsfl
        state.pla1 = pla2
        state.pla2 = pla2
    elif state.cbd <= state.cbd_tlp:
        glai = state.glf * params.sla
    else:
        glai = 0.0

    # --- Senescence (DLAI) for tomorrow
    if state.cbd < state.cbd_bls:
        dlai = 0.0
        state.blslai = state.lai  # latch LAI right up to the start of senescence
    else:
        dlai = state.bd / (state.cbd_mat - state.cbd_bls) * state.blslai

    # --- Frost effect (overrides DLAI upward)
    if state.cbd > state.cbd_blg and state.tmin < params.frztkil:
        frstf = min(1.0, max(0.0, abs(state.tmin - params.frztkil) * params.frzldr))
        dlai = max(dlai, state.lai * frstf)

    # --- Heat effect (overrides DLAI upward, multiplicative on current DLAI)
    if state.cbd > state.cbd_blg and state.tmax > params.htlth:
        heatf = max(1.0, 1.0 + (state.tmax - params.htlth) * params.htldr)
        dlai = max(dlai, dlai * heatf)

    state.glai = glai
    state.dlai = dlai
