"""Plant nitrogen uptake and distribution (replaces VBA PlantN, iCrop.vba:1416-1574).

NOT YET PORTED. Runs only when nitrogen == 2, and runs BEFORE SoilWater in the
daily sequence (iCrop.vba:84-86) -- a ported loop must preserve that order.

Includes biological N fixation for legumes, gated on bdBNF (Crop row 104), which
the phenology section already reads (iCrop.vba:600).
"""

from dataclasses import dataclass

from .state import SimState


@dataclass
class PlantNParams:
    """Crop-sheet parameters for plant N (iCrop.vba:1418-1425).

    Not yet emitted by scripts/extract_crop_params.py -- add these rows to its
    map when this module is ported.
    """

    slng: float                # row 61 -- SLNG: specific leaf N, green leaves
    slns: float                # row 62 -- SLNS: specific leaf N, senesced leaves
    sncg: float                # row 63 -- SNCG: stem N concentration, growth
    sncs1: float               # row 64 -- SNCS1: stem N at senescence, before bdBSG
    sncs2: float               # row 65 -- SNCS2: stem N at senescence, after bdBSG
    gnc_min: float             # row 66 -- GNCmin: minimum grain N concentration
    gnc_max: float             # row 67 -- GNCmax: maximum grain N concentration
    mxnup: float               # row 68 -- MXNUP: maximum daily N uptake


def step_plant_n(state: SimState, params: PlantNParams) -> None:
    """Update plant N pools and the N stress factor for one day.

    Note for the port: SNCS is *derived*, not a parameter --
    `If CBD < bdBSG Then SNCS = SNCS1 Else SNCS = SNCS2` (iCrop.vba:1433).
    DMDistributionParams currently carries a static `sncs` field, which is inert
    under potential production (NST=0 makes the SGR check true either way,
    iCrop.vba:1066) but must move here once N is live.
    """
    raise NotImplementedError
