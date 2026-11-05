# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
