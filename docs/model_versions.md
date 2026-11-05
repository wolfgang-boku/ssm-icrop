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

The maize defect was reported to the model author, who confirmed it.

## Moving the port to a later model version

1. Make each corrected defect selectable by model version, and keep the 2022
   behaviour as the verified default.
2. Check whether the Crop sheet's column and row layout changed, and make
   `scripts/extract_crop_params.py` aware of the workbook version if it did.
3. Add recalibrated cultivars as new crop files, and keep the existing ones as
   the 2022 parameters.
4. Generate a new reference output (golden master) from the new workbook
   before verifying against it, in its own directory under `data/verification/`.

## SSM-iCrop2 and SSM-iCrop2N

SSM-iCrop2 and SSM-iCrop2N are a separate, simpler model from the same author,
also available from the SSM crop models site. They are not part of this port:
SSM-iCrop2 is a generic crop model with thermal-time phenology and one crop per
row of its Crop sheet, without the WHEAT/MAIZE/LEGUME branches of SSM-iCrop.

An independent Python translation of SSM-iCrop2 exists:
[zackaryleady/Py_SSM_iCrop2](https://github.com/zackaryleady/Py_SSM_iCrop2).
