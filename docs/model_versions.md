# Model versions

The port targets **SSM-iCrop 2022-05-29** (`SSM-iCrop/SSM_iCrop__2022_05_29.xlsm`,
source in `iCrop.vba`), the version published on the
[SSM crop models site](https://sites.google.com/view/ssm-crop-models/home). All
verification, crop YAML files and VBA line citations refer to that version.

## Known defects of the 2022 version

The port reproduces these on purpose (see "How the port is built" in the
README). Each is isolated in its own function, so a later model version that
fixes it can be supported by switching that function.

| Location | Defect | Port |
|---|---|---|
| `iCrop.vba:455` (MAIZE temperature response, `PhenologyBD`) | `tempfun = ((TCD - TMP) / (TCD - TP2))` uses `TP2`, which is never assigned in the phenology section. VBA treats it as 0, so the response above the upper optimum is `(TCD - TMP) / TCD` instead of `(TCD - TMP) / (TCD - TP2D)`. | `phenology._temperature_response_dent_maize` |

The maize defect was reported to the model author, who confirmed it. The
2026 source workbook fixes it (see below).

## SSM-iCrop 2022-05-29 → REF 2026-10-24

The **2026 source workbook**, `SSM-iCrop/SSM_iCrop_REF_2026_10_24.xlsm`, is the
later version of SSM-iCrop published on the SSM crop models site ("REF" is the
author's file name, unrelated to this repository's reference output). The port
does not target it yet. This section records what changed, so that a move to
it can be planned without re-diffing the workbooks.

Line numbers are `iCrop.vba` lines (2022 version).

### VBA code

There is one functional change, and the rest of the module is identical:

| Location | 2022 | 2026 |
|---|---|---|
| `iCrop.vba:455` (MAIZE temperature response, `PhenologyBD`) | `tempfun = ((TCD - TMP) / (TCD - TP2))` | `tempfun = ((TCD - TMP) / (TCD - TP2D))` |

Five commented-out `Sheet14` debug lines (`iCrop.vba:89-93`) and some blank
lines were removed.

### Crop sheet

**Columns shifted.** A new column I (Wheat "Tajan") was inserted. Every column
from I onwards moves one to the right, and their values are unchanged:

| Cultivar | 2022 | 2026 |
|---|---|---|
| Soybean Sahar … MG V | K–O | L–P |
| Peanut Spanish, Virginia | Q–R | R–S |
| Potato late | T | U |
| Maize B73×MO17 (SC704) | Y | Z |
| Fallow1 | AB | AC |

The row layout is unchanged, so `ROW_MAP` in `scripts/extract_crop_params.py`
still applies. Only the column letters differ.

**Wheat "Tajan", column D, recalibrated.** This is the cultivar the port is
verified with (`configs/crops/wheat.yaml`):

| Row | Parameter | 2022 | 2026 |
|---|---|---|---|
| 9 | PLAPOW300 | 2.4336 | 2.34 |
| 23 | IRUE | 2.42 | 2.2 |
| 33 | PDHI | 0.01638 | 0.014 |
| 64 | SNCS1 | 0.0063 | 0.005 |
| 65 | SNCS2 | 0.0022 | 0.005 |
| 66 | GNCmin | 0.016 | 0.0132 |
| 67 | GNCmax | 0.042 | 0.0287 |
| 68 | MXNUP | 0.5 | 0.25 |
| 80 | bdSOWEMR | 3.5 | 4 |
| 81 | bdEMRTIL | 4.95 | 5.5 |
| 82 | bdTILSEL | 11.4 | 12.67 |

Row 62 (SLNS) has the same value, now written as the formula `=40*0.01`.

**Wheat "Tajan", column H, changed:**

| Row | Parameter | 2022 | 2026 |
|---|---|---|---|
| 33 | PDHI | 0.019 | 0.01638 |
| 38 | MC | 11 | 14 |
| 61 | SLNG | 1.8 | 1.5 |
| 63 | SNCG | 0.019 | 0.015 |
| 64 | SNCS1 | 0.0095 | 0.0063 (`=0.005*1.26`) |
| 67 | GNCmax | 0.035 | 0.042 |
| 68 | MXNUP | 0.6 | 0.5 |
| 81–84 | bdEMRTIL / bdTILSEL / bdSELBOT / bdBOTEAR | 5 / 11.5 / 7 / 3 | 4.95 / 11.4 / 6 / 2 |

Row 65 (SNCS2) has the same value, now written as `=0.005*0.44`.

**New column I, Wheat "Tajan".** It holds most of the old column D values
(PLAPOW300 2.4336, IRUE 2.42 via `=2.2*1.1`, PDHI 0.01638, the old N
parameters). It differs from old column D in `vsen = 0` and `ppsen = 0` (no
vernalization or photoperiod sensitivity) and in its phase lengths
(bdSOWEMR 5.4, bdEMRTIL 8.1, bdTILSEL 16.4). **No 2026 column reproduces the
2022 column D exactly.**

### Soil sheet

A new soil, `HC_GEN0008` ("Clay LF120"), was added at `SoilRowNo` 124. It has 5
layers (100/200/300/300/300 mm), with DUL = LL in every layer. Nothing else in
the sheet changed.

### Other sheets

Location, Manag, DOY and Help are unchanged. The Run sheet selects a different
default scenario (potato, Gorgan). DailyO, LayerO and YearlyO only hold the
output of that last run.

## Moving the port to a later model version

1. Make each corrected defect selectable by model version, and keep the 2022
   behaviour as the verified default.
2. Check whether the Crop sheet's column and row layout changed, and make
   `scripts/extract_crop_params.py` aware of the workbook version if it did.
3. Add recalibrated cultivars as new crop files, and keep the existing ones as
   the 2022 parameters.
4. Generate a new reference output (golden master) from the new workbook
   before verifying against it, in its own directory under `data/verification/`.

For the 2026 source workbook this means: the MAIZE temperature response becomes
version-dependent; the extractor needs the shifted column letters; the
recalibrated Tajan becomes a new crop file next to `wheat.yaml`, which stays
the 2022 cultivar.

## SSM-iCrop2 and SSM-iCrop2N

SSM-iCrop2 and SSM-iCrop2N are a separate, simpler model from the same author,
also available from the SSM crop models site. They are not part of this port:
SSM-iCrop2 is a generic crop model with thermal-time phenology and one crop per
row of its Crop sheet, without the WHEAT/MAIZE/LEGUME branches of SSM-iCrop.

An independent Python translation of SSM-iCrop2 exists:
[zackaryleady/Py_SSM_iCrop2](https://github.com/zackaryleady/Py_SSM_iCrop2).
