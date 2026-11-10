# SSM-iCrop variable reference

A complete inventory of the model's variables, extracted from `iCrop.vba`, grouped
by the section that introduces them and ordered to follow the daily simulation loop.
Each table gives the VBA name, its meaning, unit and Python type.

The port itself mostly keeps the VBA names, lower-cased (`WGRN` → `wgrn`, `FTSWRZ` →
`ftswrz`). That keeps every line of Python traceable to the `iCrop.vba` line it
ports, which matters more while the port is being built and verified than
readable names do.

## Proposed naming for a later version

The "Suggested" column is a **proposal, not the current code**: an initial idea
for more readable names once the port is complete and verified. The code in
`src/` does not follow it yet, and the names are open to discussion. A rename would
touch every module and test, so it is planned as one separate step after the
port, with the reference output as the check that it changed nothing.

The proposal follows one rule, **not** a blanket expansion:

1. **Keep** genuine domain vocabulary — terms an agronomist reads in the manual and
   literature: `lai`, `cbd`, `dtu`, `ftsw`, `atsw`, `rue`, `vpd`, `pet`, `sla`, `hi`,
   `doy`, `srad`, `tmax`, `co2`, `msnn`. Lower-cased to satisfy PEP 8, acronym intact.
2. **Expand** the model's *internal, systematic prefixes* that are not standard
   science — these are where readability is lost:
   - `W*` = a dry-matter mass → `mass_*`  (e.g. `WGRN` → `mass_grain`)
   - `WSF*` / `WSX*` = a stress factor → `wstress_*`  (e.g. `WSFN` → `wstress_n`)
   - `bd*` = a biological-day threshold → `bd_*_*` (from-stage / to-stage)
   - `dt*` = a calendar date (DOY) of a stage → `date_*`
   - `T**` thermal cardinal temps → `t_base_/t_opt1_/t_opt2_/t_ceiling_*`
3. **Drop** Excel plumbing that has no place in Python (`CropColNo`, `LocRowNo`,
   `dayCntr`, `Sheet4`, …) — replaced by config objects / DataFrame indices.

`Type` is the intended Python type (VBA itself is untyped `Variant`). Units use
the model's own conventions.

---

## 1. Run identifiers & control (mostly Excel plumbing — drop or replace)

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `scnName` | `scenario_name` | Scenario label | — | str |
| `locName` | `location_name` | Location label | — | str |
| `mngName` | `management_name` | Management label | — | str |
| `solName` | `soil_name` | Soil profile label | — | str |
| `crpName` | `crop_name` | `"WHEAT"`/`"MAIZE"`/legume | — | str |
| `wthFile` | `weather_file` | Weather file name | — | str |
| `water` | `water_mode` | 0 none, 1 auto-irrigated, 2 rainfed, 3 scheduled irrigation | — | int |
| `nitrogen` | `nitrogen_mode` | 0 none, 2 full N balance | — | int |
| `CropColNo` | *(drop)* | Excel column of the crop | — | int |
| `LocRowNo`,`MangRowNo`,`SoilRowNo` | *(drop)* | Excel row pointers | — | int |
| `scnNo`,`yrno` | *(drop)* | Scenario / season loop counters | — | int |
| `dayCntr`,`scyrCntr`,`nfrt_cntr` | *(drop)* | Output-row write counters | — | int |
| `wthRow` | *(drop)* | Current weather-sheet row | — | int |

## 2. Location & climate

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `LAT` | `latitude` | Site latitude | ° | float |
| `VPDF` | `vpd_fraction` | Fraction of (sat. deficit) that is daytime VPD | — | float |
| `tchng` | `temp_change` | Climate-change temperature offset, added to TMAX and TMIN | °C | float |
| `pchng` | `precip_factor` | Rainfall multiplier (climate scenario) | — | float |
| `CO2` | `co2` | Atmospheric CO₂ for the run | µmol mol⁻¹ | float |
| `CO2REF` | `co2_ref` | CO₂ during model parameterisation | µmol mol⁻¹ | float |

## 3. Management & sowing

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `FixFind` | `sow_method` | Sow-date algorithm selector (1–6) | — | int |
| `SimDoy` | `sim_start_doy` | Day-of-year simulation starts | DOY | int |
| `Pdoy` | `plant_doy` | Sowing day-of-year | DOY | int |
| `Lpdoy` | `last_plant_doy` | Latest allowable sowing DOY | DOY | int |
| `StopDoy` | `stop_doy` | Hard stop DOY | DOY | int |
| `SowTmp` | `sow_temp_thresh` | Temperature trigger for sowing | °C | float |
| `SowWat` | `sow_water_thresh` | Soil-water trigger for sowing | frac | float |
| `PDEN` | `plant_density` | Plant population | plants m⁻² | float |
| `Pyear` | `plant_year` | Calendar year of sowing | yr | int |

## 4. Irrigation schedule

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `IRGLVL` | `irrig_trigger_ftsw` | FTSW below which auto-irrigation fires | — | float |
| `IRNUM` | `irrig_count` | Number of scheduled applications | — | int |
| `WATiT` | `irrig_timing_mode` | 1 DAP, 2 CBD, 3 DOY, 4 CBD-auto | — | int |
| `DAPIR(N)` | `irrig_time[]` | Timing of each application | DAP/CBD/DOY | list[float] |
| `IRGWI(N)` | `irrig_amount[]` | Water per application | mm | list[float] |
| `WAT01(N)` | `irrig_done[]` | "Applied already" flag | 0/1 | list[int] |
| `IRGW` | `irrig_water` | Irrigation applied today | mm | float |
| `CIRGW` | `irrig_cum` | Cumulative irrigation | mm | float |
| `IRGNO` | `irrig_number` | Count of applications so far | — | int |

## 5. Nitrogen schedule (auto-application, mainly wheat)

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `FN` | `nfert_count` | Number of N applications | — | int |
| `NATiT` | `nfert_timing_mode` | 1 DAP, 2 CBD, 3 DOY, 4 automatic | — | int |
| `DAPNF(N)` | `nfert_time[]` | Timing of each top-dressing | DAP/CBD/DOY | list[float] |
| `NFERTI(N)` | `nfert_amount[]` | N per application | gN m⁻² | list[float] |
| `VOLFI(N)` | `nfert_volat_frac[]` | Volatilisation, per cent of the amount (`/ 100` at `iCrop.vba:1650`) | % | list[float] |
| `NFA01(N)` | `nfert_done[]` | "Applied already" flag | 0/1 | list[int] |
| `ntrsh0`,`ntrsh1` | `n_stress_thresh0/1` | Auto-N thresholds on `CNSOL60` (N in the top 600 mm): top-up target at DAP 1, top-dressing trigger | gN m⁻² | float |
| `nvolf0`,`nvolf1` | `n_volat_frac0/1` | Volatilisation (auto-N), per cent (`/ 100` at `iCrop.vba:1675`, `:1681`) | % | float |
| `bdBFRT` | `bd_basal_fert` | Start of the auto-N top-dressing window (exclusive) | bd | float |
| `bdTFRT` | `bd_top_fert` | End of the auto-N top-dressing window (exclusive) | bd | float |
| `FRTWAT` | `fert_with_irrig` | Root-zone water `ATSWRZ` needed to top-dress (`iCrop.vba:1678`) | mm | float |
| `napply1` | `n_apply_amount1` | Auto-N amount | gN m⁻² | float |

## 6. Weather (current day)

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `Yr` | `year` | Calendar year | yr | int |
| `doy` | `doy` | Day of year | — | int |
| `SRAD` | `srad` | Solar radiation | MJ m⁻² d⁻¹ | float |
| `TMAX` | `tmax` | Max air temperature | °C | float |
| `TMIN` | `tmin` | Min air temperature | °C | float |
| `RAIN` | `rain` | Precipitation | mm | float |
| `TMP` | `tmean` | Mean of TMAX/TMIN | °C | float |
| `TMAXB` | `tmax_prev` | Yesterday's TMAX (hourly temp model) | °C | float |
| `TMINA` | `tmin_next` | Tomorrow's TMIN (hourly temp model) | °C | float |
| `SNOW` | `snowpack` | Accumulated snow (water eq.) | mm | float |
| `SNOMLT` | `snowmelt` | Snow melted today | mm | float |

## 7. Phenology — parameters

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `TBD` | `t_base_dev` | Base temperature for development | °C | float |
| `TP1D` | `t_opt1_dev` | Lower optimum temp | °C | float |
| `TP2D` | `t_opt2_dev` | Upper optimum temp | °C | float |
| `TCD` | `t_ceiling_dev` | Ceiling temp | °C | float |
| `vsen` | `vern_sensitivity` | Vernalisation sensitivity (wheat) | — | float |
| `cpp` | `crit_photoperiod` | Critical photoperiod | h | float |
| `ppsen` | `photoperiod_sensitivity` | Photoperiod sensitivity | — | float |
| `PHYL` | `phyllochron` | Thermal time per leaf/node | °Cd | float |
| `bdSOWEMR` | `bd_sow_emr` | Bio-days sowing→emergence | bd | float |
| `bdEMRTIL`…`bdPMHM` | `bd_emr_til` … `bd_pm_hm` | Wheat stage durations | bd | float |
| `bdEMRR1`,`bdR1R3`,`bdR3R5`,`bdR5R7`,`bdR7R8` | `bd_emr_r1` … `bd_r7_r8` | Legume stage durations | bd | float |
| `bdEMREJU`,`bdSILPM` | `bd_emr_eju`,`bd_sil_pm` | Maize stage durations | bd | float |
| `bdBRP`,`bdTRP` | `bd_begin_rep`,`bd_top_rep` | Reproductive window | bd | float |
| `bdBSG`,`bdTSG` | `bd_begin_seedgrowth`,`bd_top_seedgrowth` | Seed-growth window | bd | float |
| `bdBLG`,`bdTLM`,`bdTLP`,`bdBLS` | `bd_begin_leafgrowth`,`bd_top_leafmax`,`bd_top_leaf`,`bd_begin_leafsen` | Leaf-growth/senescence thresholds | bd | float |
| `bdFLW`,`bdBNF` | `bd_flower`,`bd_begin_nfix` | Flowering / N-fixation onset | bd | float |
| `bdBXTF`,`bdTXTF` | `bd_begin_flower_temp`,`bd_top_flower_temp` | Heat/frost flowering window | bd | float |
| `bdMAT`,`bdEMR`,`bdANT`,`bdSIL`,`bdR5` | `bd_mat`,`bd_emr`,`bd_anthesis`,`bd_silk`,`bd_r5` | Key event thresholds in CBD | bd | float |
| `bdBRG`,`bdTRG` | `bd_begin_rootgrowth`,`bd_top_rootgrowth` | Root-growth window | bd | float |

## 8. Phenology — state

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `CBD` | `cbd` | Cumulative biological days (drives stages) | bd | float |
| `bd` | `bd_today` | Biological-day increment today (0–1) | bd | float |
| `DTU` | `dtu` | Daily thermal units | °C d | float |
| `MSNN` | `msnn` | Main-stem node number | — | float |
| `MAT` | `mature` | 0 growing, 1 mature (ends loop) | 0/1 | int |
| `MATYP` | `maturity_type` | Why it matured (2 low-LAI, 5 waterlog…) | — | int |
| `DAP` | `dap` | Days after planting | d | int |
| `DAS` | `das` | Days after simulation start | d | int |
| `VF` | `vern_factor` | Vernalisation factor (wheat) | — | float |
| `PP`,`DL` | `photoperiod_factor`,`daylength` | Photoperiod terms | —, h | float |
| `dtEMR` | `date_emergence` | DOY of emergence | DOY | int |
| `dtR0`…`dtR8` | `date_r0` … `date_r8` | DOY of stages R0–R8 (alias TIL,SEL,BOT,EAR,ANT,BSG,TSG,PM,MAT) | DOY | int |

## 9. Leaf-area (LAI) — parameters

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `PLACON` | `pla_constant` | Plant-leaf-area constant | — | float |
| `PLAPOW` | `pla_power` | Plant-leaf-area exponent | — | float |
| `a_pla_den` | `pla_density_a` | Density adjustment intercept (a=1 if none) | — | float |
| `b_pla_den` | `pla_density_b` | Density adjustment slope (b=0 if none) | — | float |
| `SLA` | `sla` | Specific leaf area | m² g⁻¹ | float |
| `FRZTKIL` | `frost_kill_temp` | Frost temp that kills leaf | °C | float |
| `FRZLDR` | `frost_leaf_death_rate` | Leaf death per °C below kill temp | °C⁻¹ | float |
| `HtLTH` | `heat_leaf_thresh` | Heat threshold for leaf damage | °C | float |
| `HtLDR` | `heat_leaf_death_rate` | Leaf death per °C above threshold | °C⁻¹ | float |

## 10. Leaf-area (LAI) — state

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `LAI` | `lai` | Leaf area index | m² m⁻² | float |
| `GLAI` | `glai` | Daily LAI growth | m² m⁻² | float |
| `DLAI` | `dlai` | Daily LAI senescence | m² m⁻² | float |
| `MXLAI` | `lai_max` | Season maximum LAI | m² m⁻² | float |
| `INODE` | `node_increment` | Nodes added today | — | float |
| `PLA1`,`PLA2` | `pla_prev`,`pla_now` | Plant leaf area, prior/current | cm² plant⁻¹ | float |
| `BLSLAI` | `lai_at_leafsen` | LAI saved at begin-leaf-senescence | m² m⁻² | float |
| `ETLAI` | `et_lai` | LAI used for soil-evaporation calc | m² m⁻² | float |
| `R5ANTLAI` | `lai_at_anthesis` | LAI at anthesis/R5 | m² m⁻² | float |
| `DLAIF`,`DLAIH` | `dlai_frost`,`dlai_heat` | LAI loss from frost / heat | m² m⁻² | float |
| `frstf`,`heatf` | `frost_factor`,`heat_factor` | Frost / heat damage fractions | — | float |
| `FINT` | `frac_intercept` | Fraction of PAR intercepted | — | float |

## 11. Dry-matter production — parameters

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `TBRUE` | `t_base_rue` | Base temp for RUE | °C | float |
| `TP1RUE`,`TP2RUE`,`TCRUE` | `t_opt1_rue`,`t_opt2_rue`,`t_ceiling_rue` | Cardinal temps for RUE | °C | float |
| `KPAR` | `k_par` | Canopy light-extinction coefficient | — | float |
| `IRUE` | `rue_max` | Initial/max radiation-use efficiency | g MJ⁻¹ | float |
| `CO2RES` | `co2_response` | RUE sensitivity to CO₂ | — | float |
| `TECREF` | `tec_ref` | Reference transpiration-efficiency coeff | Pa | float |
| `vpdtp` | `vpd_method` | 0 daily, 1 hourly VPD | — | int |
| `VPDcr` | `vpd_critical` | VPD above which TR/DM are capped | kPa | float |

## 12. Dry-matter production — state

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `RUEREF`,`RUECO2` | `rue_ref`,`rue_co2` | CO₂-adjustment factors for RUE | — | float |
| `TEC` | `tec` | Transpiration-efficiency coefficient | Pa | float |
| `TCFRUE` | `temp_factor_rue` | Temperature response of RUE (0–1) | — | float |
| `RUE` | `rue` | Actual radiation-use efficiency today | g MJ⁻¹ | float |
| `DDMP` | `ddmp` | Daily dry-matter production | g m⁻² d⁻¹ | float |
| `DDMP1`,`DDMP2` | `ddmp_hourly`,`ddmp_veg` | Hourly increment / DM left for leaf+stem | g m⁻² | float |
| `TR` | `transpiration` | Daily transpiration | mm d⁻¹ | float |
| *hourly VPD sub-model:* `DSINB`,`DSINBE`,`DTR`,`SINB`,`BET`,`BETA`,`SRAD1`,`VPD1`,`TR1`,`VPTEMP1`,`VPTMIN`,`TSUNST`,`NIGHTL`,`TEMP1`,`SUNRIS`,`SUNSET`,`TC`,`P`,`H` | *(local intermediates)* | Astronomical/hourly integration of light, temp, VPD → DM & TR | mixed | float |

## 13. Dry-matter distribution & yield — parameters

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `FLF1A`,`FLF1B` | `frac_leaf1a`,`frac_leaf1b` | Leaf DM fraction, early (below/above WTOPL) | — | float |
| `WTOPL` | `wtop_leaf_thresh` | Biomass where leaf fraction switches | g m⁻² | float |
| `FLF2` | `frac_leaf2` | Leaf DM fraction, later phase | — | float |
| `FRTRL` | `frac_translocate` | Reserve fraction available to translocate | — | float |
| `GCC` | `growth_conv_coef` | Glucose cost of seed growth (g g⁻¹) | — | float |
| `PDHI` | `potential_dhi` | Potential daily harvest-index increase | d⁻¹ | float |
| `WDHI1`…`WDHI4` | `dhi_wtop1` … `dhi_wtop4` | Biomass break-points scaling DHI | g m⁻² | float |
| `MC` | `grain_moisture` | Grain moisture content | % | float |
| `heat` | `heat_switch` | Enable heat/frost-at-flowering effect | 0/1 | int |
| `TP2H`,`TCH` | `t_opt2_heat`,`t_ceiling_heat` | Heat-damage cardinal temps | °C | float |
| `TP1F`,`TBF` | `t_opt1_frost`,`t_base_frost` | Frost-damage cardinal temps | °C | float |
| `RFmax` | `flower_rate_max` | Max daily flowering rate | — | float |

## 14. Dry-matter distribution & yield — state

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `WTOP` | `mass_top` | Total above-ground biomass | g m⁻² | float |
| `WGRN` | `mass_grain` | Grain/seed dry matter | g m⁻² | float |
| `WLF` | `mass_leaf` | Leaf dry matter | g m⁻² | float |
| `WST` | `mass_stem` | Stem dry matter | g m⁻² | float |
| `WVEG` | `mass_veg` | Vegetative (leaf + stem) | g m⁻² | float |
| `SGR` | `seed_growth_rate` | Daily seed growth | g m⁻² d⁻¹ | float |
| `GLF`,`GST` | `growth_leaf`,`growth_stem` | Daily leaf / stem growth | g m⁻² d⁻¹ | float |
| `HI` | `hi` | Harvest index (WGRN/WTOP) | — | float |
| `DHI` | `dhi` | Daily harvest-index rate | d⁻¹ | float |
| `DHIDMF` | `dhi_dm_factor` | Biomass scaling of DHI (0–1) | — | float |
| `BSGDM` | `mass_at_seedgrowth` | Biomass saved at begin-seed-growth | g m⁻² | float |
| `TRANSL` | `translocation` | DM translocated to seed today | g m⁻² | float |
| `TRLDM` | `translocatable_dm` | Remaining translocatable reserve | g m⁻² | float |
| `FrHtDHI` | `frost_heat_dhi` | Combined frost/heat factor on DHI | — | float |
| `cumHtF`,`cumFrF` | `cum_heat_flower`,`cum_frost_flower` | Accumulated heat/frost flower loss | — | float |
| `dayHtF`,`dayFrF` | `day_heat_flower`,`day_frost_flower` | Today's heat/frost flower loss | — | float |
| `HtDHI`,`FrDHI` | `heat_dhi`,`frost_dhi` | Heat / frost DHI factor | — | float |
| `HeatF1`,`FrostF1` | `heat_factor1`,`frost_factor1` | Daily heat / frost intensity (0–1) | — | float |
| `RF`,`frcFlower` | `flower_rate`,`flower_fraction` | Flowering rate / fraction complete | — | float |
| `sumFLW`,`flwDur`,`flwer`,`frcDur` | `flower_sum`,`flower_duration`,`flower_rate_q`,`flower_frac_q` | Pre-computed flowering-curve integral | — | float |
| `TMAXCan`,`TMINCan` | `tmax_canopy`,`tmin_canopy` | Canopy temperature extremes | °C | float |
| `R5ANTDM` | `mass_at_anthesis` | Biomass at anthesis/R5 | g m⁻² | float |
| `Ywet` | `yield_wet` | Yield at market moisture | kg ha⁻¹ | float |

## 15. Soil water — parameters

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `MEED` | `max_root_depth` | Maximum effective rooting depth | mm | float |
| `GRTDP` | `root_growth_rate` | Root depth growth per bio-day | mm bd⁻¹ | float |
| `WSSG` | `wstress_g_thresh` | FTSW threshold for RUE stress | — | float |
| `WSSL` | `wstress_l_thresh` | FTSW threshold for leaf-expansion stress | — | float |
| `WSSD` | `wstress_d_coef` | Slope of the drought speed-up of phenology, `WSFD = (1-WSFG)*WSSD + 1` (`iCrop.vba:1403`) | — | float |
| `WSSN` | `wstress_n_thresh` | FTSW threshold for N-uptake stress | — | float |
| `FLDKIL` | `flood_kill_days` | Days of waterlogging that kill crop | d | float |
| `surviv` | `drought_survival` | Enable drought-survival mode | 0/1 | int |
| `EPCOND` | `epidermal_conductance` | Epidermal conductance (survival) | mm s⁻¹ | float |
| `LTLRWC` | `lethal_rwc` | Lethal relative water content | — | float |
| `NLYER` | `n_layers` | Number of soil layers (≤10) | — | int |
| `LDRAIN` | `drain_layer` | Layer whose drainage leaves the profile | — | int |
| `SALB` | `soil_albedo` | Bare-soil albedo | — | float |
| `CN` | `curve_number` | Runoff curve number | — | float |
| `DLYER(L)` | `layer_thickness[]` | Thickness of each layer | mm | list[float] |
| `SAT` | `sat_vwc[]` | Saturation water content | mm mm⁻¹ | list[float] |
| `DUL` | `dul_vwc[]` | Drained upper limit (field capacity) | mm mm⁻¹ | list[float] |
| `CLL` | `cll_vwc[]` | Crop lower limit (wilting point) | mm mm⁻¹ | list[float] |
| `ADRY` | `air_dry_vwc[]` | Air-dry water content | mm mm⁻¹ | list[float] |
| `WL(L)` *(init)* | `layer_water[]` | Initial water content (also state) | mm | list[float] |
| `DRAINF(L)` | `drain_fraction[]` | Drainage fraction per layer | — | list[float] |
| `KET`,`CALB`,`EOSMIN`,`WETWAT` | `k_et`,`canopy_albedo`,`evap_min`,`wet_thresh` | ET/evaporation constants | mixed | float |

## 16. Soil water — state

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `WL(L)` | `layer_water[]` | **Actual water content per layer** (core state) | mm | list[float] |
| `ATSW(L)` | `atsw[]` | Available soil water per layer | mm | list[float] |
| `TTSW(L)` | `ttsw[]` | Total available water per layer | mm | list[float] |
| `FTSW(L)` | `ftsw[]` | Fraction of total available water | — | list[float] |
| `WLLL,WLUL,WLST,WLAD(L)` | `water_ll/ul/sat/airdry[]` | Per-layer thresholds expressed in mm | mm | list[float] |
| `iATSW,iFTSW(L)` | `atsw_init[]`,`ftsw_init[]` | Initial per-layer water (for balance) | mm,— | list[float] |
| `ATSWRZ`,`TTSWRZ`,`FTSWRZ` | `atsw_rz`,`ttsw_rz`,`ftsw_rz` | Root-zone aggregates | mm,mm,— | float |
| `ATSWSL`,`TTSWSL`,`FTSWSL` | `atsw_profile`,`ttsw_profile`,`ftsw_profile` | Whole-profile aggregates | mm,mm,— | float |
| `WRZ`,`WRZUL`,`WRZST` | `water_rz`,`water_rz_ul`,`water_rz_sat` | Root-zone water / limits (waterlogging) | mm | float |
| `WSOL`,`WDUL`,`WSAT` | `water_profile`,`water_profile_ul`,`water_profile_sat` | Profile water / limits | mm | float |
| `ISOLWAT` | `initial_soil_water` | Profile water at DAP 1 | mm | float |
| `SOLDEP` | `soil_depth` | Total profile depth | mm | float |
| `DEPORT` | `root_depth` | Current rooting depth (param init → grows) | mm | float |
| `GRTD` | `root_growth_today` | Root depth added today | mm | float |
| `RLYER(L)` | `root_in_layer[]` | Root length present in each layer | mm | list[float] |
| `RTLN` | `deepest_root_layer` | Deepest layer with roots | — | int |
| `RT(L)` | `root_water_factor[]` | Per-layer water-uptake weighting | — | list[float] |
| `AROOT` | `root_activity` | Σ(root × water factor) | mm | float |
| `DPTOP` | `depth_to_top` | Running depth to top of layer | mm | float |
| `PET` | `pet` | Potential evapotranspiration | mm d⁻¹ | float |
| `EEQ` | `et_equilibrium` | Equilibrium evaporation | mm d⁻¹ | float |
| `EOS` | `pot_soil_evap` | Potential soil evaporation | mm d⁻¹ | float |
| `SEVP` | `soil_evap` | Actual soil evaporation today | mm d⁻¹ | float |
| `DRAIN` | `drainage` | Drainage out of profile today | mm | float |
| `RUNOF` | `runoff` | Surface runoff today | mm | float |
| `FLIN(L)`,`FLOUT(L)` | `flow_in[]`,`flow_out[]` | Inter-layer water flux | mm | list[float] |
| `WU(L)`,`SE(L)` | `water_uptake[]`,`soil_evap_layer[]` | Per-layer uptake / evaporation | mm | list[float] |
| `TD` | `temp_et` | Weighted temperature for ET | °C | float |
| `ALBEDO` | `albedo` | Combined canopy+soil albedo | — | float |
| `DYSE` | `days_since_evap` | Days since soil-evap stage-1 reset | d | float |
| `TSE` | `evap_remaining` | Evaporation still to distribute | mm | float |
| `WUUR` | `uptake_per_root` | Transpiration per unit active root | mm mm⁻¹ | float |
| `VPD`,`VPTMAX`,`VPTMIN` | `vpd`,`sat_vp_max`,`sat_vp_min` | Vapour-pressure deficit terms | kPa | float |
| `TRSURV` | `transp_survival` | Survival-mode transpiration | mm | float |
| `FLDUR` | `flood_duration` | Consecutive waterlogged days | d | float |
| `S`,`SWER` | `runoff_s`,`runoff_swater` | Curve-number runoff intermediates | mm,— | float |
| `WSFL` | `wstress_l` | Stress factor: leaf expansion (1 = none) | — | float |
| `WSFG` | `wstress_g` | Stress factor: RUE / DM production | — | float |
| `WSFN` | `wstress_n` | Stress factor: N uptake | — | float |
| `WSFD` | `wstress_d` | Phenology rate factor, ≥ 1: drought speeds up development | — | float |
| `WSXF` | `wstress_x` | Excess-water factor (waterlogging): flood kill and PlantN uptake | — | float |
| `CRAIN`,`CIRGW`,`CRUNOF`,`CE`,`CTR`,`CDRAIN` | `rain_cum`,`irrig_cum`,`runoff_cum`,`evap_cum`,`transp_cum`,`drain_cum` | Cumulative water-balance totals | mm | float |
| `CTR0,CE0,CRAIN0,CRUNOF0,CDRAIN0` | `*_cum_pre` | Pre-sowing cumulatives (reset at DAP 1) | mm | float |

## 17. Plant nitrogen — parameters

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `SLNG` | `sln_green` | Specific leaf N, green leaves | gN m⁻² | float |
| `SLNS` | `sln_senesced` | Specific leaf N, senesced leaves | gN m⁻² | float |
| `SNCG` | `stem_n_conc_green` | Stem N concentration, green | gN g⁻¹ | float |
| `SNCS1`,`SNCS2` | `stem_n_conc_sen1`,`stem_n_conc_sen2` | Stem N concentration, senescing | gN g⁻¹ | float |
| `GNCmin`,`GNCmax` | `grain_n_conc_min`,`grain_n_conc_max` | Grain N concentration range | gN g⁻¹ | float |
| `MXNUP` | `max_n_uptake` | Maximum daily N uptake | gN m⁻² d⁻¹ | float |

## 18. Plant nitrogen — state

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `NUP` | `n_uptake` | N taken up today | gN m⁻² | float |
| `NLF` | `n_leaf` | N in leaves | gN m⁻² | float |
| `NST` | `n_stem` | N in stems | gN m⁻² | float |
| `NVEG` | `n_veg` | N in vegetative parts | gN m⁻² | float |
| `NGRN` | `n_grain` | N in grain | gN m⁻² | float |
| `SNCS` | `stem_n_conc` | Current stem N concentration | gN g⁻¹ | float |
| `CNUP` | `n_uptake_cum` | Cumulative N uptake | gN m⁻² | float |
| `CUMBNF` | `n_fixation_cum` | Cumulative biological N fixation | gN m⁻² | float |
| `NSTRS` | `n_stress` | N-stress factor on growth (1 = none) | — | float |

## 19. Soil nitrogen — parameters

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `FG` | `frac_gravel[]` | Fraction of soil > 2 mm | — | list[float] |
| `BDL` | `bulk_density[]` | Soil bulk density per layer | g cm⁻³ | list[float] |
| `NORGP` | `org_n_percent[]` | Organic-N content | % | list[float] |
| `FMIN` | `frac_mineralizable[]` | Fraction of org-N available to mineralise | — | list[float] |
| `NSOL1` | `soil_n_init[]` | Initial mineral N per layer | kgN ha⁻¹ | list[float] |

## 20. Soil nitrogen — state

| VBA | Suggested | Meaning | Unit | Type |
|---|---|---|---|---|
| `NFERT` | `n_fertilizer` | Fertiliser N applied today | gN m⁻² | float |
| `NVOL` | `n_volatilized` | N lost to volatilisation today | gN m⁻² | float |
| `NLEACH` | `n_leached` | N leached today | gN m⁻² | float |
| `SNMIN` | `n_mineralized` | N mineralised today | gN m⁻² | float |
| `SNDNIT` | `n_denitrified` | N denitrified today | gN m⁻² | float |
| `SNAVL` | `soil_n_avail` | Plant-available soil mineral N | gN m⁻² | float |
| `NSOL(L)` | `soil_n_layer[]` | Mineral N per layer | gN m⁻² | list[float] |
| `ISOLN` | `initial_soil_n` | Profile mineral N at SoilN's season init (first spin-up day) | gN m⁻² | float |
| `CNFERT`,`CNVOL`,`CNLEACH`,`CNMIN`,`CNDNIT`,`CNUP` | `n_fert_cum`,`n_volat_cum`,`n_leach_cum`,`n_min_cum`,`n_denit_cum`,`n_uptake_cum` | Cumulative N-balance totals | gN m⁻² | float |
| `CNSOL` | `n_soil_total` | Profile mineral N today, re-summed daily (not cumulative) | gN m⁻² | float |

---

## Cross-check against `src/ssm_icrop/state.py`

Every state variable carried from one day to the next is a field of `SimState`.
Parameters are intentionally excluded: they belong in config objects, not
`SimState`.

### State that is easy to overlook

These fields are not obvious from the output columns alone, but the daily loop
needs them.

| `state.py` field | VBA | Why it is state |
|---|---|---|
| `wl[]` | `WL(L)` | Core water-balance integrator; `atsw/ftsw` are derived from it |
| `mxlai`, `blslai`, `etlai`, `r5antlai` | `MXLAI`,`BLSLAI`,`ETLAI`,`R5ANTLAI` | Carried LAI summaries used across sections |
| `pla1`, `pla2` | `PLA1`,`PLA2` | Leaf-area expansion requires yesterday's value |
| `fint` | `FINT` | Intercepted-PAR fraction shared between DM-prod and output |
| `hi`, `rue`, `tcfrue`, `sgr`, `glf`, `gst`, `r5antdm` | `HI`,`RUE`,`TCFRUE`,`SGR`,`GLF`,`GST`,`R5ANTDM` | DM-distribution state and output columns |
| `frhtdhi`, `cumhtf`, `cumfrf`, `sumflw` | `FrHtDHI`,`cumHtF`,`cumFrF`,`sumFLW` | Heat/frost-at-flowering accumulators (season-long) |
| `matyp`, `dtu` | `MATYP`,`DTU` | Maturity cause code; daily thermal units for output |
| `ttswrz`, `atswsl`, `isolwat` | `TTSWRZ`,`ATSWSL`,`ISOLWAT` | Root-zone/profile aggregates and DAP-1 baseline |
| `dyse`, `fldur` | `DYSE`,`FLDUR` | Evaporation-stage counter; waterlogging kill counter |
| `irgw`, `runof`, `pet`, `sevp`, `tr`, `drain` | `IRGW`,`RUNOF`,`PET`,`SEVP`,`TR`,`DRAIN` | Daily water fluxes written to the 63-column output |
| `crain0` … `cdrain0` | `CRAIN0` … | Pre-sowing cumulatives reset at DAP 1 |
| `nup` | `NUP` | Daily N uptake (output column) |
| `nsol[]` | `NSOL(L)` | Per-layer mineral N (soil-N integrator) |
| `isoln` | `ISOLN` | Profile mineral N at DAP 1 (balance baseline) |
| `nfert`, `nvol`, `nleach`, `snmin`, `sndnit` | `NFERT`,`NVOL`,`NLEACH`,`SNMIN`,`SNDNIT` | Daily N fluxes written to output |

### Units of depths
`deport` and the other depths (`DEPORT`, `MEED`, `DLYER`, `SOLDEP`) are in **mm**,
as the VBA reads them (`iCrop.vba:1118-1119`, `:1153`, `:1179`).

### Still not in `state.py` (by design)
- Per-layer threshold arrays `WLLL/WLUL/WLST/WLAD` — constant during a run, belong in
  a soil-config object.
- Run constants `KET`, `CALB`, `EOSMIN`, `WETWAT` — module constants in
  `soil_water.py`. (`SOLDEP` is on `SimState`: iniSW computes it once per season.)
- Hourly VPD sub-model intermediates (`DSINB`, `SINB`, `TEMP1`, …) — local loop
  variables, not shared state.
