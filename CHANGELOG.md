# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- SoilN, the soil nitrogen balance, and PlantN, plant N uptake and
  distribution. Both `nitrogen = 2` reference scenarios match the reference
  output over the whole season when the canopy (LAI, GLAI, DLAI, MSNN) is
  taken from it. `nitrogen = 2` still raises until CropLAIN is ported.
- Crop files carry a `plant_n` section (Crop rows 61-68) and, for legumes,
  `bd_bnf` (row 104).
- Soil parameter extraction from the 2022 source workbook
  (`scripts/extract_soil_params.py`) and the soil file `configs/soils/danesh.yaml`.
- The 2026 source workbook `SSM-iCrop/SSM_iCrop_REF_2026_10_24.xlsm`, now
  published on the SSM crop models site, and its differences from the 2022
  version in `docs/model_versions.md`. The port still targets 2022.

### Changed

- SNCS, the stem N concentration at senescence, is no longer a
  `DMDistributionParams` field: PlantN sets it each day, as in the VBA.
- Scenarios reference their soil with `soil_file`, as they reference their
  crop with `crop_file`; an inline `soil` block is rejected.
- A scenario with `nitrogen = 2` and `water = 0` is rejected: without the soil
  water balance VBA simulates no soil layer, or divides by zero.

### Fixed

- The example scenarios carried eight soil values as displayed in the Soil
  sheet (e.g. LL 0.204) instead of the doubles it stores and VBA reads
  (0.20400000000000001).

## [0.1.0] - 2026-11-05

First public release of the Python port of SSM-iCrop 2022-05-29.

### Added

- Daily simulation loop in the order of the original VBA model, configured by
  YAML scenarios (location, management, soil, crop).
- Ported sections: weather (including snow and the climate-change
  adjustments), phenology for wheat, maize and grain legumes, leaf area without
  N stress, dry-matter production, dry-matter distribution and yield
  formation, the multi-layer soil water balance, and the fixed sowing date
  with its pre-sowing spin-up.
- Verification against the reference output of the original workbook:
  potential production and the rainfed water balance match on every day of the
  reference season within 1e-6 (see `docs/verification.md` for what is and is
  not covered).
- Crop parameter extraction from the 2022 source workbook
  (`scripts/extract_crop_params.py`) and crop files for wheat, maize and
  soybean.
- Documentation of the verification method, the model's variables and the
  known defects of the 2022 model version.

### Not yet ported

- Plant and soil nitrogen balance, leaf area with N stress.
- Rule-based sowing-date algorithms (`FixFind` 1–5).
- Seasonal summary output, including the seasonal weather sums of the
  phenology section.

[Unreleased]: https://github.com/wolfgang-boku/ssm-icrop/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/wolfgang-boku/ssm-icrop/releases/tag/v0.1.0
