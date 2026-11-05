"""Daily and seasonal output records (replaces DailyPrintOut / SummaryPrintOut).

DailyRecord mirrors Sheet4, columns 1-63 (iCrop.vba:2032-2097), in order.
SeasonSummary mirrors Sheet10, columns 1-64 (iCrop.vba:2158-2221), in order.

Field order is load-bearing: tests/test_outputs_columns.py parses the column
assignments straight out of iCrop.vba and asserts these dataclasses match, so a
reordering or omission fails the build rather than silently shifting a column.

The VBA writes two different summaries. Sheet1 (iCrop.vba:2105-2154) is a
single-season named-cell report; Sheet10 is the general per-scenario-per-year
table and is what SeasonSummary models. They are NOT identical: Sheet1 writes
harvest index as a percentage (`* 100`, iCrop.vba:2123) while Sheet10 writes the
bare fraction (iCrop.vba:2180).
"""

from dataclasses import dataclass

from .state import SimState


@dataclass
class DailyRecord:
    """One row of Sheet4 (iCrop.vba:2032-2097). 63 columns, order matters."""

    # 1-6: identifiers
    scenario: str
    location: str
    management: str
    soil: str
    crop: str
    year: int              # Pyear
    # 7-11: time and thermal
    doy: int
    dap: int
    tmp: float
    dtu: float
    cbd: float
    # 12-18: canopy and interception
    msnn: float
    glai: float
    dlai: float
    lai: float
    tcfrue: float
    fint: float
    ddmp: float
    # 19-26: dry matter
    glf: float
    gst: float
    sgr: float
    wlf: float
    wst: float
    wveg: float
    wgrn: float
    wtop: float
    # 27-43: water balance
    deport: float
    rain: float
    irgw: float
    runof: float
    pet: float
    sevp: float
    tr: float
    drain: float
    atswrz: float
    ftswrz: float
    crain: float
    cirgw: float
    irgno: int
    crunof: float
    ce: float
    ctr: float
    cdrain: float
    # 44-63: N balance
    nfert: float
    cnfert: float
    nvol: float
    cnvol: float
    nleach: float
    cnleach: float
    snmin: float
    cnmin: float
    sndnit: float
    cndnit: float
    snavl: float
    cnsol: float
    nup: float
    nlf: float
    nst: float
    nveg: float
    ngrn: float
    cnup: float
    cumbnf: float
    nstrs: float


@dataclass
class SeasonSummary:
    """One row of Sheet10 (iCrop.vba:2158-2221). 64 columns, order matters."""

    # 1-7: identifiers
    scenario: str
    location: str
    management: str
    soil: str
    crop: str
    year: int              # Pyear
    pdoy: int
    # 8-17: phenology dates (DOY of each stage)
    dt_emr: int
    dt_r0: int
    dt_r1: int
    dt_r2: int
    dt_r3: int
    dt_r4: int
    dt_r5: int
    dt_r6: int
    dt_r7: int
    dt_r8: int
    # 18-20: canopy
    msnn: float
    mxlai: float
    r5ant_dm: float        # R5ANTDM: biomass accumulated between R5 and anthesis
    # 21-23: yield
    wtop: float
    wgrn: float
    hi: float              # WGRN / (WTOP + 1e-5) -- a FRACTION here, not a percent
    # 24-34: water balance
    isolwat: float         # initial soil water
    crain: float
    cirgw: float
    irgno: int
    atswsl: float
    crunof: float
    ce: float
    ctr: float
    cdrain: float
    et_total: float        # CE + CTR (iCrop.vba:2190)
    e_fraction: float      # CE / (CE + CTR + 1e-5) (iCrop.vba:2191)
    # 35-47: N balance
    nlf: float
    nst: float
    nveg: float
    ngrn: float
    cnup: float
    cumbnf: float
    isoln: float           # initial soil N
    cnfert: float
    cnmin: float
    cnsol: float
    cnvol: float
    cnleach: float
    cndnit: float
    # 48: how the season ended
    matyp: int             # MATYP: maturity type

    # 49-63: environmental sums over three periods (iCrop.vba:678-710)
    #   *_total: sowing -> MAT      (CBD <= bdMAT)
    #   *_veg:   sowing -> BSG      (CBD <= bdBSG)
    #   *_fill:  BSG -> MAT         (bdBSG < CBD <= bdMAT)
    # NOT YET ACCUMULATED: the VBA builds these in the ENVIRONMENTAL tail of
    # PhenologyBD, which this port does not yet implement. They stay at 0.0 until
    # that block is ported, and the daily verification does not cover
    # them because they appear only here.
    srain_total: float     # 49  SRAINT: summed rainfall
    mtmin_total: float     # 50  MTMINT: mean TMIN
    mtmax_total: float     # 51  MTMAXT: mean TMAX
    ssrad_total: float     # 52  SSRADT: summed solar radiation
    sumet_total: float     # 53  SUMETT: summed SEVP + TR
    srain_veg: float       # 54  SRAIN2
    mtmin_veg: float       # 55  MTMIN2
    mtmax_veg: float       # 56  MTMAX2
    ssrad_veg: float       # 57  SSRAD2
    sumet_veg: float       # 58  SUMET2
    srain_fill: float      # 59  SRAIN3
    mtmin_fill: float      # 60  MTMIN3
    mtmax_fill: float      # 61  MTMAX3
    ssrad_fill: float      # 62  SSRAD3
    sumet_fill: float      # 63  SUMET3
    # 64
    ywet: float            # WGRN / (1 - MC/100) * 10 (iCrop.vba:2104), kg ha-1


def record_daily(state: SimState, meta: dict) -> DailyRecord:
    """Snapshot current state into a DailyRecord."""
    raise NotImplementedError


def record_summary(state: SimState, meta: dict) -> SeasonSummary:
    """Snapshot end-of-season state into a SeasonSummary."""
    raise NotImplementedError
