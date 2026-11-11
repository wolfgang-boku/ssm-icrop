"""Simulation state — replaces VBA global variables.

Holds every value the daily loop reads or writes. Two kinds of field live here:
those that carry from one day to the next (integrators / accumulators such as
``cbd``, ``lai``, ``wl``, ``wtop``) and daily working values that are recomputed
each day but shared across sections and written to the output (``ddmp``, ``pet``,
``sgr`` …). Parameters that never change during a run belong in the config
objects, not here.
"""

from dataclasses import dataclass, field


@dataclass
class SimState:
    # --- time / phenology
    cbd: float = 0.0       # cumulative biological days
    dap: int = 0           # days after planting
    das: int = 0           # days after simulation start
    mat: int = 0           # 0=growing, 1=mature (ends daily loop)
    doy: int = 0
    yr: int = 0

    matyp: int = 0         # why it matured: 2=low LAI, 5=waterlogging, ...
    dtu: float = 0.0       # daily thermal units (deg C d)
    bd: float = 0.0        # today's biological-day increment (added to cbd)

    # --- LAI
    lai: float = 0.0
    glai: float = 0.0      # daily LAI gain
    dlai: float = 0.0      # daily LAI loss
    msnn: float = 0.0      # main stem node number

    mxlai: float = 0.0     # season maximum LAI
    blslai: float = 0.0    # LAI latched up to bdBLS (CropLAI) or in bdTLM..bdTLP (CropLAIN)
    etlai: float = 0.0     # LAI used for soil-evaporation calc
    r5antlai: float = 0.0  # LAI at anthesis (R5)
    pla1: float = 0.0      # plant leaf area, previous day (cm2 plant-1)
    pla2: float = 0.0      # plant leaf area, current day (cm2 plant-1)
    fint: float = 0.0      # fraction of PAR intercepted (daily)

    # --- dry matter (g m-2)
    wtop: float = 0.0      # total above-ground biomass
    wgrn: float = 0.0      # grain
    wlf: float = 0.0       # leaf
    wst: float = 0.0       # stem
    wveg: float = 0.0      # vegetative (leaf + stem)
    ddmp: float = 0.0      # daily DM production

    hi: float = 0.0        # harvest index (wgrn / wtop)
    rue: float = 0.0       # actual radiation-use efficiency (daily)
    tcfrue: float = 1.0    # temperature factor on RUE (daily)
    irue_eff: float = 0.0  # CO2-adjusted intrinsic RUE (set once per season)
    tec: float = 0.0       # CO2-adjusted transpiration-efficiency coefficient (Pa)
    sgr: float = 0.0       # daily seed growth rate
    glf: float = 0.0       # daily leaf growth
    gst: float = 0.0       # daily stem growth
    r5antdm: float = 0.0   # biomass at anthesis (R5)

    bsgdm: float = 0.0     # WTOP latched at begin-seed-growth (CBD reaches cbd_bsg)
    dhi: float = 0.0       # potential daily harvest index (set pre-BSG, used post-BSG)
    trldm: float = 0.0     # translocatable DM reserve, seeded at BSG

    # --- heat / frost effect at flowering (carried accumulators)
    frhtdhi: float = 1.0   # combined frost/heat factor on DHI
    cumhtf: float = 0.0    # cumulative heat-induced flower loss
    cumfrf: float = 0.0    # cumulative frost-induced flower loss
    sumflw: float = 0.0    # flowering-curve integral (set once at init)

    # --- water stress factors (1.0 = no stress)
    wsfl: float = 1.0      # leaf expansion
    wsfg: float = 1.0      # RUE / DM production
    wsfd: float = 1.0      # phenology rate factor — drought *accelerates* development
    wsfn: float = 1.0      # N uptake
    wsfds: float = 1.0     # reset at iCrop.vba:166, never read by the VBA
    wsxf: float = 1.0      # excess water (waterlogging); 0 = root zone saturated

    # --- soil water (up to 10 layers)
    # wl is the core integrator: actual water content per layer (mm)
    wl: list[float] = field(default_factory=lambda: [0.0] * 10)
    atsw: list[float] = field(default_factory=lambda: [0.0] * 10)   # actual (mm)
    ttsw: list[float] = field(default_factory=lambda: [0.0] * 10)   # total available (mm)
    ftsw: list[float] = field(default_factory=lambda: [0.0] * 10)   # fraction
    atswrz: float = 0.0    # root-zone actual SWC
    ftswrz: float = 0.0    # root-zone fraction SWC
    deport: float = 0.0    # rooting depth (mm)

    ttswrz: float = 0.0    # root-zone total available SWC (mm)
    atswsl: float = 0.0    # whole-profile actual available water (mm)
    ttswsl: float = 0.0    # whole-profile total available water (mm)
    ftswsl: float = 0.0    # whole-profile fraction available water
    wsol: float = 0.0      # whole-profile water content (mm)
    wdul: float = 0.0      # whole-profile water at DUL (mm), set at init
    wsat: float = 0.0      # whole-profile water at saturation (mm), set at init
    soldep: float = 0.0    # profile depth (mm), set at init
    wrz: float = 0.0       # root-zone water content (mm)
    wrzul: float = 0.0     # root-zone water at DUL (mm)
    wrzst: float = 0.0     # root-zone water at saturation (mm)
    isolwat: float = 0.0   # profile available water at DAP 1 (mm)
    dyse: float = 0.0      # days since soil-evaporation stage-1 reset
    fldur: float = 0.0     # consecutive waterlogged days
    rtln: int = 0          # deepest layer holding roots (1-based, 0 = none)
    aroot: float = 0.0     # root length weighted by layer water-uptake factor (mm)
    vpd: float = 0.0       # daily VPD (kPa), only computed when vpd_type = 0
    # per-layer, 1-based in the VBA, index L-1 here
    flout: list[float] = field(default_factory=lambda: [0.0] * 10)  # drainage out (mm)
    rlyer: list[float] = field(default_factory=lambda: [0.0] * 10)  # root length in layer (mm)
    rt: list[float] = field(default_factory=lambda: [0.0] * 10)     # uptake factor
    iatsw: list[float] = field(default_factory=lambda: [0.0] * 10)  # ATSW at DAP 1 (mm)
    iftsw: list[float] = field(default_factory=lambda: [0.0] * 10)  # FTSW at DAP 1
    wat01: list[int] = field(default_factory=list)  # per irrigation event: 1 = applied

    # --- daily water fluxes (mm, recomputed each day)
    irgw: float = 0.0      # irrigation applied today
    runof: float = 0.0     # surface runoff
    pet: float = 0.0       # potential evapotranspiration
    sevp: float = 0.0      # soil evaporation
    tr: float = 0.0        # transpiration
    drain: float = 0.0     # drainage out of profile

    # --- water balance cumulative (mm)
    crain: float = 0.0
    cirgw: float = 0.0
    irgno: int = 0
    crunof: float = 0.0
    ce: float = 0.0        # cumulative soil evaporation
    ctr: float = 0.0       # cumulative transpiration
    cdrain: float = 0.0

    # pre-sowing baselines, saved when the balance resets at DAP 1
    crain0: float = 0.0
    crunof0: float = 0.0
    ce0: float = 0.0
    ctr0: float = 0.0
    cdrain0: float = 0.0

    # --- plant N (g m-2)
    nup: float = 0.0       # N taken up today (daily); not reset by LocManagInputs,
    #                        so SoilN reads the last season's value before sowing
    bnf: float = 0.0       # biological N fixation (g N m-2), set by PlantN in its growth
    #                        branches only (:1451, :1505); kept past bdTSG and before sowing
    nlf: float = 0.0
    nst: float = 0.0
    nveg: float = 0.0
    ngrn: float = 0.0
    cnup: float = 0.0      # cumulative N uptake
    cumbnf: float = 0.0    # biological N fixation
    nstrs: float = 0.0     # NUP / potential NUP, output only. Assigned only by PlantN
    #                        (:1564); before that VBA's Empty, read as 0
    sncs: float = 0.0      # stem N concentration at senescence (g g-1): SNCS1 before
    #                        bdBSG, SNCS2 from it on; set by PlantN, read by
    #                        DMDistribution the next day (iCrop.vba:1433, :1066)
    nfc: float = 0.0       # N fixation capacity per g WVEG, a running mean (:1444);
    #                        never reset, so it carries into the next season
    trln: float = 0.0      # translocatable leaf + stem N (g m-2), end of yesterday
    fxlf: float = 0.0      # leaf share of TRLN, end of yesterday
    # today's N flows into (in*) and out of (xn*) leaf, stem and grain (g m-2);
    # CropLAIN reads INLF and XNLF the next day (iCrop.vba:817, :842)
    inlf: float = 0.0
    inst: float = 0.0
    xnlf: float = 0.0
    xnst: float = 0.0
    ingrn: float = 0.0

    # --- soil N (g m-2)
    nsol: list[float] = field(default_factory=lambda: [0.0] * 10)   # mineral N per layer
    insol: list[float] = field(default_factory=lambda: [0.0] * 10)  # NSOL at season init
    mnorg: list[float] = field(default_factory=lambda: [0.0] * 10)  # mineralizable org. N
    ncon: list[float] = field(default_factory=lambda: [0.0] * 10)   # g N per g soil water
    navl: list[float] = field(default_factory=lambda: [0.0] * 10)   # plant-available N
    snavl: float = 0.0     # plant-available soil mineral N
    cnsol60: float = 0.0   # mineral N in the top 600 mm (automatic N application)
    isoln: float = 0.0     # profile mineral N at SoilN's season init (first
    #                        spin-up day, iCrop.vba:1616), not at sowing
    nfa01: list[int] = field(default_factory=list)  # per N event: 1 = applied (NATiT 2)

    # daily N fluxes (recomputed each day)
    nfert: float = 0.0     # fertiliser N applied today
    nvol: float = 0.0      # N volatilised today
    nleach: float = 0.0    # N leached today
    snmin: float = 0.0     # N mineralised today
    sndnit: float = 0.0    # N denitrified today

    cnsol: float = 0.0     # profile mineral N today, re-summed daily (:1730-1743)

    # cumulative N balance
    cnfert: float = 0.0
    cnvol: float = 0.0
    cnleach: float = 0.0
    cnmin: float = 0.0
    cndnit: float = 0.0

    # pre-sowing baselines, saved when SoilN resets at DAP 1 (:1620-1624).
    # CNFERT and CNVOL are not reset there and keep the pre-sowing amounts.
    cnmin0: float = 0.0    # VBA name CMNIM0
    cnleach0: float = 0.0
    cndnit0: float = 0.0

    # --- weather (current day)
    tmax: float = 0.0
    tmin: float = 0.0
    tmp: float = 0.0       # mean temperature
    tmaxb: float = 0.0     # previous day TMAX
    tmina: float = 0.0     # next day TMIN
    srad: float = 0.0
    rain: float = 0.0
    snow: float = 0.0

    # --- phenology stage dates (DOY)
    dt_emr: int = 0
    dt_r0: int = 0
    dt_r1: int = 0
    dt_r2: int = 0
    dt_r3: int = 0
    dt_r4: int = 0
    dt_r5: int = 0
    dt_r6: int = 0
    dt_r7: int = 0
    dt_r8: int = 0

    # --- phenology stage thresholds (CBD units, computed at initialization)
    cbd_emr: float = 0.0   # emergence
    cbd_til: float = 0.0   # tillering (wheat)
    cbd_sel: float = 0.0   # stem elongation (wheat)
    cbd_bot: float = 0.0   # booting (wheat)
    cbd_ear: float = 0.0   # ear emergence (wheat)
    cbd_ant: float = 0.0   # anthesis (wheat/maize)
    cbd_bsg: float = 0.0   # begin seed growth
    cbd_tsg: float = 0.0   # end seed growth
    cbd_pm: float = 0.0    # physiological maturity
    cbd_mat: float = 0.0   # harvest maturity
    cbd_eju: float = 0.0   # end juvenile (maize)
    cbd_tsi: float = 0.0   # tassel initiation (maize)
    cbd_sil: float = 0.0   # silking (maize)
    cbd_tse: float = 0.0   # tassel emergence (maize) — feeds dt_r0
    cbd_r1: float = 0.0    # R1 (legume)
    cbd_r3: float = 0.0    # R3 (legume)
    cbd_r5: float = 0.0    # R5 (legume)
    cbd_r7: float = 0.0    # R7 (legume)
    cbd_r8: float = 0.0    # R8 (legume)
    cbd_bnf: float = 0.0   # begin N fixation; 999 for wheat and maize (:280, :437)

    # --- leaf-production window thresholds (CBD units, used by CropLAI)
    cbd_blg: float = 0.0   # begin leaf growth (= emergence)
    cbd_tlm: float = 0.0   # leaf production ends on main stem
    cbd_tlp: float = 0.0   # leaf production ends on whole plant
    cbd_bls: float = 0.0   # begin leaf senescence

    # --- flowering window (CBD units, used by DMDistribution's heat/frost model)
    cbd_bxtf: float = 0.0  # begin flowering window
    cbd_txtf: float = 0.0  # end flowering window

    # --- solar geometry (recomputed daily in phenology, reused by DM production)
    dayl: float = 0.0      # day length (h)
    sinld: float = 0.0
    cosld: float = 0.0
    aob: float = 0.0

    # --- wheat vernalization
    cumver: float = 0.0    # cumulative vernalization days

    # --- maize leaf dynamics
    tuemrtsi: float = 0.0  # thermal time from emergence to TSI
    xtsi: int = 0          # flag: TSI recalculation done

    # --- initialisation flags (set to 1 after first-day setup in each section)
    ini_pheno: int = 0
    ini_lai: int = 0
    ini_dmp: int = 0
    ini_dmd: int = 0
    ini_sw: int = 0
    ini_pnb: int = 0
    ini_snb: int = 0
