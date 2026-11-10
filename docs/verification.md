# Verification against the original VBA model

The Python port is checked day by day against output produced by the original
VBA model. This document describes that reference output, how it was
generated, what it verifies today, what it does not, and how to extend it.

## Terminology

These terms are used throughout the repository with exactly these meanings.
They follow the AIAA guide for verification and validation of simulations
(G-077-1998) and the ISTQB testing glossary.

| Term | Meaning |
|---|---|
| **Verification** | Checking that an implementation computes what its model specifies. Here the specification is the original VBA model, and the check is that the Python port computes the same values. This is what this project does. |
| **Validation** | Checking how well a model represents the real world, against observations such as measured yields. Crop modellers usually call this *model evaluation*. This project does **not** do it: a verified port is as valid as the original model, no more. |
| **Back-to-back testing** | The verification method used here: the same inputs go into the VBA model and the port, and their outputs are compared (ISTQB term). It shows that the two agree, not that either is correct. |
| **Source workbook** | The published workbook of one model version, always named with its year. The **2022 source workbook**, `SSM-iCrop/SSM_iCrop__2022_05_29.xlsm` (SSM-iCrop 2022-05-29), is the version this port targets: `iCrop.vba` and every crop parameter come from it, and it is never edited. [model_versions.md](model_versions.md) describes the model versions, including the **2026 source workbook** `SSM-iCrop/SSM_iCrop_REF_2026_10_24.xlsm`. |
| **Verification workbook** | `SSM-iCrop/SSM_iCrop__2022_05_29_verification.xlsm`, a copy of the 2022 source workbook with an output patch and three added scenarios (see below). Its model calculations are unchanged. |
| **Reference run** | One macro run of the verification workbook. |
| **Reference output** | The daily output of the reference run, `data/verification/2022-05-29/wheat_gorgan_reference_output.csv`, one directory per model version. It is the *golden master*: the recorded output of the original program that the port must reproduce. |
| **Reference scenarios** | The four scenarios of the reference run (table below). |
| **Unit test** | A test of one function or section in isolation, with inputs written by hand. It shows that the code does what its author read in the VBA, not that the reading was right. Only a comparison with the reference output can show that, and only for the code paths the reference scenarios run. |

## Reference output

`data/verification/2022-05-29/wheat_gorgan_reference_output.csv` is the `DailyO` sheet of
the verification workbook after the reference run: 63
columns in `DailyPrintOut` order (`iCrop.vba:2003-2098`), one row per simulated
day, four scenarios distinguished by the `sName` column.

All four scenarios share the same crop, soil, location and sowing date and
differ only in the water and nitrogen modes:

| `sName` | Manag block (`MangRowNo`) | `water` | `nitrogen` | Days | Purpose |
|---|---|---|---|---|---|
| `Taj1 Arab` | 13 | 3 (scheduled irrigation) | 2 | 185 | Full model; unchanged from the 2022 source workbook |
| `Taj1-Potential` | 36 | 0 (no water balance) | 0 | 185 | Potential production |
| `Taj1-WaterLim` | 59 | 2 (rainfed) | 0 | 181 | Water-limited |
| `Taj1-Nlim` | 82 | 1 (auto-irrigated, `IRGLVL` 0.9) | 2 | 185 | N-limited, water near field capacity |

Shared inputs: wheat cultivar "Tajan" (Crop sheet column D), Gorgan (Location
sheet row 7, latitude 36.85°N), soil at `SoilRowNo` 24, simulation start DOY
340 and sowing DOY 348 of 2005, plant density 386 m⁻².

The N-limited scenario uses `water=1` because `nitrogen = 2` has no soil N
balance with `water = 0`: the soil water balance never runs, so neither the
layer count `NLYER` (`iCrop.vba:1138`) nor the layer water content `WL` is
set. In this workbook `Taj1 Arab` runs first and leaves `NLYER = 5`, so with
`water = 0` `SoilN` would stop the VBA with a division by zero when it first
computes the N concentration (`iCrop.vba:1598`). In a run without an earlier
water balance `NLYER` is empty and `SoilN` simulates no layer at all. The port
rejects the combination. With `water=1` the scenario is free of water stress
but not of the soil water's effect on soil N. In the reference output
`FTSWRZ` never falls below 0.88, above every water-stress threshold of
"Tajan" (`WSSG` 0.3, `WSSL` 0.4, `WSSD` 0.5). But the daily irrigation keeps the
root zone at or above field capacity (`FTSWRZ > 1` on 63 days, see `IRGLVL`
below), where mineralization falls to 0 (`iCrop.vba:1632-1633`) and layers 1
and 2 denitrify: the season mineralizes 5.9 g N m⁻² against 12.7 in
`Taj1 Arab`.

## How the verification workbook was built

The verification workbook is a copy of the 2022 source workbook with the following
changes.

### 1. VBA patch: one `DailyO` block per scenario

By default `DailyPrintOut` writes only when the Run sheet holds exactly one
scenario (`If scnNo = 1 And yrno = 1`, `iCrop.vba:2032`). Three edits give
each scenario its own 500-row block in `DailyO` (rows 2, 502, 1002, 1502).
They change only where output is written, not any model calculation.

**Edit 1**, near the top of `Sub iCrops()` (around line 41):

```vb
 dayCntr = 0
 outStart = 500   'start row for 2nd scenario output: outStart + 2
 nfrt_cntr = 1
```

**Edit 2**, at the end of each scenario iteration (around line 100):

```vb
    wb.Close False
    Do Until outStart > dayCntr   'snap to next 500-row block (2, 502, 1002, ...)
        outStart = outStart + 500
    Loop
    dayCntr = outStart
    Set wb = Nothing
Next scnCntr
```

**Edit 3**: comment out the `If scnNo = 1 And yrno = 1 Then` line in
`DailyPrintOut` (around line 2032) and its matching `End If`, leaving the 63
assignments between them untouched.

`Sub Headers()` needs no change; its equivalent gate is already commented out
(around line 2261).

### 2. Three additional Manag blocks

The `Taj1 Arab` block (Manag rows 13–33) was copied to rows 36, 59 and 82.
The scenario name was set in columns A and C of each copy's third row, and only
these cells were changed in the row seven below the block start (`nitrogen` in
column B, `water` in column F) and the row below it (`IRGLVL` in column G):

| Block | `nitrogen` | `water` | `IRGLVL` |
|---|---|---|---|
| 36 `Taj1-Potential` | 2 → 0 | 3 → 0 | unchanged (unused) |
| 59 `Taj1-WaterLim` | 2 → 0 | 3 → 2 | unchanged (unused) |
| 82 `Taj1-Nlim` | unchanged | 3 → 1 | 0.5 → 0.9 |

The remaining cells (fertilizer and irrigation schedules, automatic-N
parameters) were left as copied. The VBA does not read them when the
corresponding mode is off.

### 3. Run sheet

The scenario loop reads `FrstScnRow+1 .. FrstScnRow+scnNo` as one contiguous
block, so the four scenarios occupy Run rows 8–11:

| Row | Scenario | LocRowNo | MangRowNo | SoilRowNo | CropColNo |
|---|---|---|---|---|---|
| 8 | Taj1 Arab | 5 | 13 | 24 | 4 |
| 9 | Taj1-Potential | 5 | 36 | 24 | 4 |
| 10 | Taj1-WaterLim | 5 | 59 | 24 | 4 |
| 11 | Taj1-Nlim | 5 | 82 | 24 | 4 |

with `First Scenario Row` (Run!B5) = 8 and `No of scenarios` (Run!B6) = 4.

### 4. Export at full precision

Do not use the spreadsheet application's own CSV export: it rounds each column
to its display format, which shifts integer-formatted columns such as `WLF`,
`WST` and `WTOP` by up to 0.5. Read the cached cell values with openpyxl
instead. This reproduces the committed reference output exactly:

```python
import openpyxl
import pandas as pd

wb = openpyxl.load_workbook(
    "SSM-iCrop/SSM_iCrop__2022_05_29_verification.xlsm", data_only=True, read_only=True
)
rows = list(wb["DailyO"].iter_rows(values_only=True))
header, body = rows[0], [r for r in rows[1:] if r[0] is not None]
pd.DataFrame(body, columns=header).to_csv(
    "data/verification/2022-05-29/wheat_gorgan_reference_output.csv", index=False
)
```

## What is verified

`tests/test_verification.py` compares the port with the reference output.

**`Taj1-Potential`** runs from hand-transcribed parameter literals. 18 daily
columns are compared over the whole season (DAP > 0):

`TMP RAIN DTU CBD MSNN GLAI DLAI LAI FINT DDMP GLF GST SGR WLF WST WVEG WGRN WTOP`

The absolute tolerance is 1e-6 for every column; the port matches to about
1e-9 on every day (`WTOP`: below 1e-12 g m⁻²).

**`Taj1-WaterLim`** runs from `configs/example/gorgan_wheat_waterlim.yaml`.
The same 18 columns (DAP > 0) and the 16 `SoilWater` columns

`DEPORT IRGW RUNOF PET SEVP TR DRAIN ATSWRZ FTSWRZ CRAIN CIRGW IRGNO CRUNOF CE CTR CDRAIN`

are compared with the same tolerance of 1e-6; the port matches to about
1e-9. The water columns are also compared on the eight spin-up days before
sowing (DAP = 0), when `FindSimSowDate` already runs the water balance. The
crop columns of those rows are not compared: the four scenarios ran in one
macro run, VBA globals carry over between scenarios, and the spin-up rows of
`Taj1-WaterLim` show the end-of-season crop values of `Taj1-Potential`.
`DRAIN` is blank on the first spin-up day (`FLOUT` not yet assigned) and is
compared as 0.

**`Taj1 Arab`** (`water = 3`) and **`Taj1-Nlim`** (`water = 1`) run from
`configs/example/gorgan_wheat_taj1.yaml`. Two stretches are compared: the
eight days before sowing, and the first eight crop days (DAP 1–8), which end
the day before emergence. Until emergence `LAI = 0` and `NUP = 0` in the
reference output, so `PlantN` and `CropLAIN` change nothing yet. All 16 days
are compared in the 16 water columns and the 12 `SoilN` columns

`NFERT CNFERT NVOL CNVOL NLEACH CNLEACH NMIN CNMIN NDNIT CNDNIT SNAVL NSOL`

and DAP 1–8 also in the 18 crop columns. The tolerance is 1e-12. `Taj1 Arab`
matches exactly (difference 0.0) once the soil is read as the doubles the
workbook stores (`configs/soils/danesh.yaml`), and `Taj1-Nlim` to within 1e-14.
The tighter tolerance leaves room only for platform differences in `exp` and
`log`. (`NMIN`, `NDNIT`
and `NSOL` hold the VBA variables `SNMIN`, `SNDNIT` and `CNSOL`.)

From emergence (DAP 9) on, both scenarios need `CropLAIN`, which is not ported
yet. Over the whole season they are compared with a stand-in for it that sets
`LAI`, `GLAI`, `DLAI` and `MSNN` to the reference output's values of the day,
and `BLSLAI` as `CropLAIN` latches it (`iCrop.vba:838`). Everything else is
computed by the port: phenology, dry matter, `PlantN`, `SoilWater` with its
in-season irrigation, and `SoilN`. All 185 rows are compared in the 16 water
and 12 soil N columns, and DAP 1–177 in the remaining 14 crop columns and the
8 `PlantN` columns

`NUP NLF NST NVEG NGRN CNUP CUMBNF NSTRS`

with the tolerance of 1e-6; the port matches to about 4e-9 (`DEPORT`). This
verifies `PlantN` given VBA's canopy, not `CropLAIN`.

`tests/test_crop_params_extraction.py` additionally checks that the crop
parameters read from the 2022 source workbook by `scripts/extract_crop_params.py`
equal the verified parameter literals in `tests/test_verification.py`.

## What the reference output covers, and what it does not

A column that matches the reference output only proves the code paths the
scenario actually runs. The reference output holds one crop (wheat "Tajan"),
one location (Gorgan), one soil ("Danesh", five layers, top layer 150 mm,
`LDRAIN = 5`) and one season (sown DOY 348 of 2005). Everything outside that is
checked by unit tests at best.

A matching `WTOP` is strong evidence but not enough on its own, although it
integrates almost every process:

- An error in the split between leaf and stem feeds back: leaf growth sets
  leaf area (`GLAI = GLF * SLA`, `iCrop.vba:758`), and leaf area sets light
  interception and therefore `WTOP`.
- An error in grain growth `SGR` does not, for the reference cultivar: `WTOP`
  grows each day by `DDMP + SGR * (1 - 1/GCC)` (`iCrop.vba:1103-1105`), and
  "Tajan" has `GCC = 1`, so whatever `SGR` takes from the stem the grain gets.
  With `GCC < 1` (the legumes) it would show. The stem mass is read back only
  together with stem N (`iCrop.vba:1066`), which is 0 without the N balance.
- The water balance reaches `WTOP` only through `WSFG`, once `FTSWRZ` falls
  below `WSSG`. Errors in runoff or drainage on wet soil do not show in `WTOP`.
- Two independent errors that cancel exactly, day after day, are unlikely at a
  tolerance of 1e-6, but not at a looser one.
- Code paths the scenario never runs show in no column.

Every output column is therefore compared separately.

The tables below were made by tracing which statements of the module the
scenario executes, not by reading the code.

### `Weather` (`weather.py`, `iCrop.vba:182-217`)

**Checked against the reference output:** `TMP` and `RAIN` directly, after
snow handling; `SRAD`, `TMAX` and `TMIN` only indirectly, through the columns
computed from them (`DDMP`, `PET` and others), because the output has no
column for them.

**Unit tests only:** the climate-change adjustments of the Location sheet
(`tchng` added to `TMAX` and `TMIN`, `pchng` multiplying `RAIN`): the
reference scenarios use 0 and 1. Snow accumulation and melt: the reference
season has no day with `TMAX <= 1`. The previous day's `TMAX` and the next
day's `TMIN` (`TMAXB`, `TMINA`): only the hourly VPD method reads them, and
no cultivar uses it.

### `SoilWater` (`soil_water.py`, `iCrop.vba:1115-1415`)

**Checked against the reference output, every day (`Taj1-WaterLim`, rainfed):**

| Process | VBA lines | Note |
|---|---|---|
| Season initialisation, DAP-1 balance reset | 1117-1198 | |
| Water balance on the days before sowing | 1779-1797 | |
| Rainfed mode, no irrigation | 1209-1211 | |
| Drainage out of the profile, one-day lag | 1251-1252 | only `LDRAIN = NLYER` |
| Root depth growth, including the stop at `MEED` | 1255-1271 | |
| Runoff, layers 1 and 2 averaged | 1286-1296 | top layer < 250 mm only |
| PET, including the `TMAX > 34` and `TMAX < 5` branches | 1308-1313 | |
| Soil evaporation, stage 1, stage 2 and rewetting | 1316-1326 | |
| Transpiration, daily VPD (`vpd_type = 0`) | 1329-1339 | |
| Layer update, drainage between layers | 1352-1397 | see the gaps below |
| Stress factors `WSFL`, `WSFG`, `WSFD` and their effect on the crop | 1400-1403 | |
| Waterlogging day count (`FLDUR`) | 1404-1407 | the kill itself is not reached |

**Checked against the reference output, every day, with the canopy taken from
it (`Taj1 Arab`, `Taj1-Nlim`, see above):**

| Process | VBA lines | Note |
|---|---|---|
| Automatic irrigation (`water = 1`), including the negative-amount bug | 1201-1207 | `Taj1-Nlim`: 166 events, `CIRGW` ends at −196 mm |
| Scheduled irrigation, DAP-based (`water = 3`, `WATiT = 1`) | 1212-1220 | `Taj1 Arab`: one event, 70 mm on DAP 117 |

**Unit tests only, never checked against the reference output:**

| Process | VBA lines | Why not covered |
|---|---|---|
| Scheduled irrigation with `WATiT` 2-4 | 1221-1246 | `Taj1 Arab` uses only `WATiT = 1` |
| Runoff from layer 1 alone | 1276-1285 | needs a top layer ≥ 250 mm |
| Soil evaporation capped by layer 1 and taken from deeper layers; none from air-dry layers | 1357-1358 | the cap is never reached in this scenario |
| Drought survival, and its VPD bug with `vpd_type = 1` | 1342-1349 | `surviv = 0` for every cultivar in the workbook |
| Transpiration taken from `DMProduction` (`vpd_type = 1`) | 1334-1336 | `vpd_type = 0` for every cultivar in the workbook |
| Crop killed by waterlogging (`MATYP = 5`) | 1408 | `FLDUR` never exceeds `FLDKIL = 99` |
| Values carried from one season into the next | — | the reference output has one season |
| `LDRAIN` outside 1 … `NLYER` | 1251 | |

**Not tested at all:** maize and legume crops, other soils and layer counts.

### `SoilN` (`soil_n.py`, `iCrop.vba:1575-1766`)

**Checked against the reference output (`Taj1 Arab`, `Taj1-Nlim`): up to
emergence on their own, over the whole season with the canopy taken from the
reference output (see above):**

| Process | VBA lines | Note |
|---|---|---|
| Season initialisation of the N pools | 1577-1618 | `FG = 0` in every layer |
| Reset of `CNMIN`, `CNLEACH`, `CNDNIT` at DAP 1 | 1620-1624 | |
| Net mineralization, both branches of the water factor | 1627-1642 | `TMP` below 35 °C |
| DOY-based fertilizer and volatilization (`NATiT = 3`) | 1663-1670, 1688-1689 | three events: the sowing day, DOY 42 and DOY 110 |
| Downward movement and leaching | 1692-1698 | only `LDRAIN = NLYER` |
| Denitrification in layers 1 and 2 | 1700-1722 | layer 1 is 150 mm, so the switch-off for layer 2 is not reached |
| Plant uptake per layer | 1725-1727 | from emergence on |
| Layer update, concentration, plant-available N | 1730-1744 | |
| N in the top 600 mm | 1747-1759 | layers end exactly at 600 mm |

**Unit tests only, never checked against the reference output:**

| Process | VBA lines | Why not covered |
|---|---|---|
| Switch-off of denitrification in layer 2 under a thick layer 1 | 1713 | layer 1 is 150 mm |
| Cap of the denitrified concentration at 400 mg N l⁻¹ | 1706 | |
| DAP- and CBD-based fertilizer (`NATiT` 1, 2), and the CBD same-day bug | 1646-1662 | the scenarios use `NATiT = 3` |
| Automatic N application (`NATiT = 4`) | 1671-1686 | same |
| Mineralization stopping at 200 mg N l⁻¹, no movement at ≤ 1 mg N l⁻¹ | 1636, 1694 | concentrations stay between |
| A layer straddling 600 mm | 1608-1611 | |
| Values carried from one season into the next (`NAVL`, `SNAVL`, `NUP`, `BNF`), which change soil N before sowing: `NUP − BNF > 0` removes N, `< 0` adds it | 1726 | the reference output has one season |

The reference output does show the carry-over between *scenarios*: the
spin-up rows of `Taj1-Nlim` print `CNUP = 18.96` from the end of `Taj1 Arab`.
The port runs each scenario on its own, with `NUP = BNF = 0` before sowing,
and does not reproduce this. The re-dimensioning at `iCrop.vba:64` zeroes
`NAVL` only for the first spin-up day: that day's update (`:1739`) makes it
positive again, so from the second spin-up day on `SoilN` removes
`NAVL / SNAVL * (NUP − BNF)` with the `NUP` and `BNF` the previous scenario
left. The soil N columns agree in the reference run only because those were 0:
`Taj1 Arab` ran first, and it ended past `bdTSG`, where `PlantN` sets
`NUP = 0` (`:1435-1436`), with `BNF = 0` (wheat does not fix N). The port would
differ from a macro run in which the previous `nitrogen = 2` scenario ends with
`NUP ≠ BNF`: a legume, whose `BNF` that branch leaves at its last value, or a
season stopped before `bdTSG`.

### `PlantN` (`plant_n.py`, `iCrop.vba:1416-1569`)

**Checked against the reference output, with the canopy taken from it
(`Taj1 Arab`, `Taj1-Nlim`, DAP 1–177):**

| Process | VBA lines | Note |
|---|---|---|
| Season initialisation of the N pools | 1417-1431 | |
| `SNCS1` before `bdBSG`, `SNCS2` from it on | 1433 | |
| No uptake before emergence and after `bdTSG` | 1435-1436 | |
| Vegetative uptake: demand, `MXNUP` and `SNAVL` caps, waterlogging (`WSXF`), `DDMP = 0` | 1437-1450 | |
| Split of uptake between leaf and stem, all four cases | 1455-1479 | |
| Seed-growth uptake at `GNCmax`, `MXNUP` and `SNAVL` caps, `NUP = 0` while grain draws on reserves | 1482-1503 | waterlogging only in `Taj1-Nlim` |
| Grain N from uptake and translocation, `GNCmin` and `GNCmax` limits | 1509-1519 | |
| Translocation from leaf and stem to grain, split by `FXLF` | 1550-1555 | |
| Pool update, `NSTRS`, translocatable N | 1559-1568 | |
| `SNCS` and `NST` read by `DMDistribution` | 1066 | the condition never becomes true: `LAI > 0` throughout seed growth |

**Unit tests only, never checked against the reference output:**

| Process | VBA lines | Why not covered |
|---|---|---|
| N fixation: `WSFN`, `BNF`, `CUMBNF`, `DNF`, the `SNAVL + DNF` cap; the stale `BNF` before `bdBSG` | 1445, 1450-1453, 1490-1498, 1504-1507 | wheat has `bdBNF = 999` |
| `NFC` as used (it is computed every vegetative day but read only by `DNF`) | 1444, 1493 | same |
| Negative uptake set to 0 | 1446, 1487 | demand is never negative |
| Uptake beyond grain demand, split between leaf and stem | 1521-1548 | the grain's demand always exceeds uptake |
| `SGR = 0` and `DDMP = 0` during seed growth | 1502, 1510 | |
| `FXLF` limited to 0 … 1 | 1567-1568 | |
| `NFC` carried from one season into the next | 1444 | the reference output has one season |

**Not tested at all:** `PlantN` with the port's own canopy, until `CropLAIN`
is ported.

## Running it

```bash
pytest tests/test_verification.py           # pass/fail per column
python scripts/compare_verification.py      # table: mismatches and max |diff| per column
```

## Extending it

When `CropLAIN` is ported, run `Taj1 Arab` and `Taj1-Nlim` over the whole
season without the canopy stand-in, following the `Taj1-WaterLim` class.

Two points to resolve before relying on those scenarios:

- **`IRGLVL` in `Taj1-Nlim` is stored as text.** Manag cell G89 holds the
  string `'0.9'`, not the number 0.9. `IRGLVL` is an undeclared Variant
  (`iCrop.vba:130`), so the comparison `FTSWRZ <= IRGLVL` (`iCrop.vba:1202`)
  compares a number with a string. In the reference run it was always true:
  VBA irrigated on every day with 0 < CBD < bdTSG (166 events), even when the
  previous day's FTSWRZ was 2.86, and each amount equals the previous day's
  TTSWRZ − ATSWRZ. Because `water = 1` refills to DUL without a lower bound
  (`soil_water._auto_irrigation_amount`), the amount turns negative above DUL
  and `CIRGW` ends at −196 mm. A Python config reproduces this with
  `irg_level: .inf`; on DAP 1–8 the port's `IRGW` matches the reference
  output with it.
