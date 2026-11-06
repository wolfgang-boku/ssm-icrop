# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Public repository
This repository is public. Everything tracked here — this file, `.claude/`,
docs, comments, commit messages — must read as project documentation.
Personal settings and local notes belong in `CLAUDE.local.md` (git-ignored,
loaded automatically), never in a tracked file. When in doubt, put it in
`CLAUDE.local.md`.

All tracked content is written in English — code, comments, docstrings, docs,
config comments, commit messages and PR descriptions — regardless of the
language used in conversation.

## Git workflow
Branches, commits and merges follow [CONTRIBUTING.md](CONTRIBUTING.md)
(GitHub Flow, 50/72 messages). Make every commit through the `/commit` skill:
it checks that the change belongs on the current branch and says when a branch
is ready for a pull request. `.githooks/` refuses commits on `main` and
malformed messages; CI repeats the message check on pull requests.

## Project Goal
Port the SSM-iCrop crop simulation model from VBA to Python, faithfully, and verify
the port against the reference output of the original workbook.

## Source Model
- **VBA source**: `iCrop.vba` (~2500 lines) — extracted from `SSM-iCrop/SSM_iCrop__2022_05_29.xlsm`.
  The port targets this 2022 version, the one published on the SSM crop models site.
  `docs/model_versions.md` records its known defects and how to move the port to a later version.
- **Crops**: Wheat, Maize, Grain legumes (soybean, chickpea, etc.)
- **Manuals**: wheat and chickpea PDFs — authoritative model documentation, published on the
  [SSM crop models site](https://sites.google.com/view/ssm-crop-models/home) — and the book
  chapter Soltani & Sinclair (2025), "Crop modeling with simple simulation models (SSM)",
  doi:10.19103/AS.2025.0155.06 (Burleigh Dodds, all rights reserved). None of them are redistributed
  here. Keep local copies in `SSM-iCrop/Manual/` (git-ignored) and never commit them.
- **Example weather**: `data/weather/*.csv` (Tabriz, Isfahan, Gorgan — all Iran), converted from
  the `.xls` files on the same site

## VBA Architecture
The entire model is one `Sub iCrops()` using `GoSub` label sections (not separate subroutines). The daily simulation loop calls them in this order:

```
LocManagInputs → FindSimSowDate → [daily loop:] Weather → PhenologyBD →
CropLAI|CropLAIN → DMProduction → DMDistribution → [PlantN] →
[SoilWater] → [SoilN] → DailyPrintOut → [SummaryPrintOut per season]
```

| GoSub label | What it does |
|---|---|
| `LocManagInputs` | Reads all parameters from Excel sheets; resets state flags |
| `FindSimSowDate` | Finds start-of-simulation date and sowing date (6 algorithms: fixed, rain-free window, temp threshold, soil water threshold, etc.) |
| `Weather` | Reads one day: Year, DOY, SRAD, TMAX, TMIN, RAIN (columns 1–6 of weather sheet); applies the climate-change adjustments (`tchng` added to temperatures, `pchng` multiplying rain); handles snow accumulation/melt |
| `PhenologyBD` | Computes biological days (`CBD`); separate logic for WHEAT (vernalization + photoperiod), MAIZE, and LEGUME; advances through growth stages R0–R8/MAT |
| `CropLAI` | LAI dynamics without N stress: emergence, expansion, senescence, frost/heat effects |
| `CropLAIN` | Same as `CropLAI` but with N-stress factor applied |
| `DMProduction` | RUE-based biomass: temperature response on RUE, VPD response (hourly or daily), CO₂ effect, water-stress factor `WSFG` |
| `DMDistribution` | Partitions daily DM to seed/leaf/stem; yield formation; heat and frost effects on DHI |
| `PlantN` | Plant N uptake, allocation to organs, biological N fixation for legumes |
| `SoilWater` | Multi-layer (up to 10) water balance: irrigation, runoff (curve number), drainage, PET (Priestley-Taylor), soil evaporation, transpiration, root depth growth, drought survival |
| `SoilN` | Per-layer N: mineralization, fertilizer application + volatilization, leaching, denitrification, plant uptake |
| `DailyPrintOut` | Writes 63 daily variables to output sheet |
| `SummaryPrintOut` | Writes seasonal summary (phenology dates, yield, water balance, N balance) |

## Simulation Modes
- `water`: 0 = no water balance (potential production), 1 = auto-irrigated (triggers when `FTSWRZ <= IRGLVL`, refills root zone to field capacity — still water-limited if the threshold/timing doesn't fully prevent stress), 2 = rainfed (no irrigation, `IRGW=0` always), 3 = scheduled irrigation (DAP/CBD/DOY-based, fixed amounts or auto-amount-at-CBD-trigger) — verified against `iCrop.vba:1201-1246`
- `nitrogen`: 0 = no N balance, 2 = full N balance with optional auto-application
- Note: `SoilN`'s mineralization rate depends on each layer's `FTSW` (`iCrop.vba:1632-1633`):
  it rises to its maximum at `FTSW = 0.9` and falls to 0 at field capacity (`FTSW = 1`).
  With `water=0` SoilWater never runs, so `FTSW` stays 0 in every layer except layer 1,
  which wheat and legume phenology set to 0.5 on crop day 1 (`:283`, `:603`). Which water
  setting gives a genuinely "N-limited, water-unlimited" scenario is open until SoilN is
  ported: `water=1` refills the root zone to exactly field capacity, where mineralization is 0.

## Key State Variables
- `CBD` — cumulative biological days (drives phenology stage transitions)
- `DAP` / `DAS` — days after planting / days after simulation start
- `LAI` — leaf area index
- `WTOP` / `WGRN` / `WLF` / `WST` — total / grain / leaf / stem dry matter (g m⁻²)
- `WSFL`, `WSFG`, `WSFN` — water stress factors (1 = no stress); `WSFD` ≥ 1 speeds up
  phenology under drought; `WSXF` is the waterlogging factor (`WSFDS` is never read)
- `ATSW(i)` / `FTSW(i)` — actual / fraction of total soil water per layer
- `SNAVL` — plant-available soil N

## Daily Output Columns (63 total, written by `DailyPrintOut`)
Scenario/location/management/soil/crop identifiers, then: DOY, DAP, TMP, DTU, CBD, MSNN, GLAI, DLAI, LAI, TCFRUE, FINT, DDMP, GLF, GST, SGR, WLF, WST, WVEG, WGRN, WTOP, DEPORT, RAIN, IRGW, RUNOF, PET, SEVP, TR, DRAIN, ATSWRZ, FTSWRZ, CRAIN, CIRGW, IRGNO, CRUNOF, CE, CTR, CDRAIN, NFERT, CNFERT, NVOL, CNVOL, NLEACH, CNLEACH, SNMIN, CNMIN, SNDNIT, CNDNIT, SNAVL, CNSOL, NUP, NLF, NST, NVEG, NGRN, CNUP, CUMBNF, NSTRS

## Port Status

Ported and verified against the reference output (18 weather and crop columns
for potential production; those 18 plus 16 water columns for the rainfed
scenario):
weather, phenology (except the ENVIRONMENTAL tail), crop_lai, dm_production,
dm_distribution, soil_water, sowing (FixFind=0 only, including the pre-sowing
spin-up that runs SoilWater with DAP=0).

"Verified" covers only the code paths the reference scenarios run: wheat only,
one soil, one season, no snow, and no climate-change adjustments (`tchng`,
`pchng`). Maize and legume phenology, irrigation during the
season (water 1 and 3), runoff from a deep top layer, deep-layer evaporation,
drought survival and the flood kill are unit-tested only.
`docs/verification.md` lists per process what the reference output checks and
what it does not.

Still stubs: `soil_n.py`, `plant_n.py`, CropLAIN,
FindSimSowDate algorithms 1–5, and the `record_daily`/`record_summary` writers.
Use the `/port-section` skill — it holds the section line ranges and the workflow.

**Known gap:** `PhenologyBD`'s ENVIRONMENTAL block (`iCrop.vba:678-710`) is not
ported. It accumulates 15 seasonal weather sums over three periods (sowing→MAT,
sowing→BSG, BSG→MAT) that appear only in `SummaryPrintOut`, which is why the
daily verification never caught its absence. `SeasonSummary` declares
the fields; nothing fills them.

### Parameters come from the workbook, not from hand-transcription
`scripts/extract_crop_params.py` reads the Crop sheet (one cultivar per column)
into YAML, carrying the `iCrop.vba` line that reads each row.
`tests/test_crop_params_extraction.py` pins its output against the verified
literals in `tests/test_verification.py`, so generated YAML is as trustworthy as
the transcription was — and more precise (the workbook stores IRUE as
2.4200000000000004; the literal rounded it to 2.42).

`scripts/extract_soil_params.py` does the same for one Soil-sheet block
(`configs/soils/danesh.yaml`); scenarios reference it with `soil_file`. The sheet
displays rounded values but stores other doubles (LL 0.20400000000000001), and
VBA reads the stored one. `tests/test_soil_params_extraction.py` fails if the
soil file drifts from the workbook.

Two parameters that sit in `DMProductionParams` are **Location**-sheet values in
the VBA and are injected by `model.build_params`, not stored in crop files:
`vpdf` (`iCrop.vba:113`) and `co2` (`:116`). Gorgan's VPDF is 0.63, Tabriz's 0.75.

## Terminology
Use these terms exactly; `docs/verification.md` defines them in full.
- **Verification**: checking the port against the original VBA model, by
  back-to-back testing. Not *validation* (crop modellers: *evaluation*), which
  means checking a model against field observations and is not done here.
- **Source workbook**, always with its year: the **2022 source workbook**
  `SSM-iCrop/SSM_iCrop__2022_05_29.xlsm` is what the port targets.
- **Verification workbook**: `SSM-iCrop/SSM_iCrop__2022_05_29_verification.xlsm`,
  a copy of the 2022 source workbook with output patch and added scenarios.
- **Reference output** (golden master): `data/verification/2022-05-29/wheat_gorgan_reference_output.csv`,
  the daily output of one run of the verification workbook (the reference run).
- **Unit test**: tests one section with hand-written inputs; shows self-consistency,
  not agreement with the VBA.

## Fidelity rules
- The VBA is the authority. Replicate its bugs faithfully, each isolated in its
  own function and documented with the VBA line and the reasoning — see
  `phenology._temperature_response_dent_maize`. A silent "fix" is a porting error.
- Comments and config comments are documentation of VBA behaviour and are read by
  later sessions as verified fact. When correcting one, `grep` for its duplicates:
  the `water` mode mapping stayed wrong in three files after being fixed in this
  file, because the correction was applied in one place only.
- Units: `DLYER` and `DEPORT` are **millimetres** (`iCrop.vba:1118`, `:1153`).
- `NLYER` is explicit, never `len(layers)`: the "Danesh" soil of the reference scenarios has
  NLYER=5 with six filled layer rows, and VBA simulates five.
- Blank Crop-sheet cells are read as 0 by VBA. Don't substitute a plausible default.
- Run the `vba-fidelity-auditor` agent on a module before trusting it.

## Commands

### Environment setup (first time)
```bash
# Install uv (fast Python package manager), then create the environment
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --extra dev                 # .venv with the exact versions in uv.lock, as CI
source .venv/bin/activate
git config core.hooksPath .githooks # enable the branch and commit-message hooks
```

### Daily development
```bash
source .venv/bin/activate
pytest                              # run all tests
pytest tests/test_weather.py        # run a single test file
ruff check src/ tests/ scripts/     # lint (CI gates this; format is not gated)
```

### Regenerate crop and soil parameters from the workbook
```bash
python scripts/extract_crop_params.py --list                 # cultivars + columns
python scripts/extract_crop_params.py --column D -o configs/crops/wheat.yaml
python scripts/extract_soil_params.py --list                  # soils + SoilRowNo
python scripts/extract_soil_params.py --row 24 -o configs/soils/danesh.yaml
```

### Run a scenario from config
```bash
python -c "
from ssm_icrop.inputs import load_scenario
from ssm_icrop.model import run_simulation
r = run_simulation(load_scenario('configs/example/gorgan_wheat_potential.yaml'))
print(r.daily.tail())"
```
