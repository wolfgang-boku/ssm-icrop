"""Soil nitrogen balance (replaces VBA SoilN GoSub, iCrop.vba:1575-1766).

NOT YET PORTED. Runs only when nitrogen == 2, after SoilWater (iCrop.vba:86).

There is deliberately no SoilNParams here: every input the VBA reads in this
section comes from the Soil sheet per layer (iCrop.vba:1580-1586) and is already
modelled on SoilLayer in inputs.py -- coarse_fraction (FG), bulk_density (BDL),
organic_n_pct (NORGP), min_fraction (FMIN), init_no3 (NSOL1). Fertilizer timing
and amounts come from ManagementConfig.nitrogen_schedule. MAI is *derived*
from NORGP/FMIN/BDL, not read from the sheet.

Per-layer processes (map for porting, not verified line by line):
  - Net mineralization -- rate set by each layer's FTSW (iCrop.vba:1632-1633),
    highest at FTSW = 0.9 and 0 at field capacity. Which water setting makes
    an N-limited run water-unlimited is open: see the note in CLAUDE.md.
  - Fertilizer application and volatilization
  - Downward N movement with drainage water
  - Denitrification
  - Plant uptake (rooted layers only)
"""

from .inputs import ManagementConfig, SoilConfig
from .state import SimState


def step_soil_n(
    state: SimState,
    soil: SoilConfig,
    management: ManagementConfig,
) -> None:
    """Update per-layer and cumulative soil N variables for one day."""
    raise NotImplementedError
