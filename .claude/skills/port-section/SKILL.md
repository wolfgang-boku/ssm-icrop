---
name: port-section
description: Port one GoSub section of iCrop.vba to a Python module in src/ssm_icrop/, following this project's established porting workflow. Use when implementing or completing SoilWater, SoilN, PlantN, CropLAIN, FindSimSowDate algorithms 1-5, or SummaryPrintOut.
---

# Porting a VBA section

Follow this order. It is what produced the modules that already match real VBA
output exactly, and the steps are ordered so that mistakes surface early and
cheaply.

## 1. Read the VBA first, completely

Read the whole section before writing anything. Section boundaries:

| GoSub | Lines | Status |
|---|---|---|
| `LocManagInputs` | 111-176 | done (inputs.py) |
| `Weather` | 182-217 | done |
| `PhenologyBD` | 218-712 | done except the ENVIRONMENTAL tail (678-710) |
| `CropLAI` | 718-795 | done |
| `CropLAIN` | 796-872 | done |
| `DMProduction` | 878-976 | done |
| `DMDistribution` | 977-1114 | done |
| `SoilWater` | 1115-1415 | done (verified rainfed, water 1, water 3 with WATiT=1) |
| `PlantN` | 1416-1569 | done (verified for wheat) |
| `SoilN` | 1575-1766 | done (verified for NATiT=3) |
| `FindSimSowDate` | 1767-2002 | done for FixFind=0 only, incl. spin-up |
| `DailyPrintOut` | 2003-2098 | schema done (outputs.py), writer stub |
| `SummaryPrintOut` | 2102-2486 | schema done, writer stub |

The daily call order is fixed by `iCrop.vba:78-87` and must be preserved:
Weather, PhenologyBD, CropLAI *or* CropLAIN, DMProduction, DMDistribution, then
PlantN (nitrogen=2), SoilWater (water 1/2/3), SoilN (nitrogen=2).

## 2. Resolve every input to its source

For each variable the section reads, find where it comes from — never guess a
name or a unit:

- **Crop sheet cell**: add the row to `ROW_MAP` in
  `scripts/extract_crop_params.py` with the `iCrop.vba` line that reads it, then
  regenerate the crop YAMLs. Rows 80-87 are overloaded per crop type.
- **Location / Manag / Soil sheet**: it belongs on a dataclass in `inputs.py`.
  Check whether it is already there under a different name. A new Soil-sheet
  column also goes into `LAYER_COLUMNS` or `SOIL_COLUMNS` in
  `scripts/extract_soil_params.py`; then regenerate the soil YAMLs.
- **Computed in another section**: it belongs on `SimState`, not in a params
  dataclass.
- **Hardcoded in the VBA** (e.g. `VDSAT=50`, `iCrop.vba:228-232`): a literal with
  the VBA line in a comment. An extractor cannot find these.

Verify sheet values directly rather than trusting a transcription:

```bash
.venv/bin/python -c "
import openpyxl
ws = openpyxl.load_workbook('SSM-iCrop/SSM_iCrop__2022_05_29.xlsm', data_only=True)['Crop']
print([ws.cell(46, c).value for c in range(1, 8)])"
```

Units are a known trap: `DLYER` and `DEPORT` are **mm**.

## 3. Write the module

- One `<Section>Params` dataclass (crop-sheet parameters only) plus a
  `step_<section>(state, ...)` function mutating `SimState` in place.
- Cite `iCrop.vba:<line>` for every non-obvious formula.
- **Replicate VBA bugs faithfully.** Isolate each in its own function and write
  out what the bug is, the VBA line, and why you are keeping it — see
  `phenology._temperature_response_dent_maize`. Never silently correct the VBA;
  a "fix" is itself a porting error here.
- Add new state variables to `state.py` with unit comments.
- Modes whose dependencies are missing must raise `NotImplementedError`, never
  silently skip a process (`model._check_modes_supported`).

## 4. Test in three layers

1. **Unit tests** per behaviour, in `tests/test_<section>.py`, following the
   existing files' style: one class per behaviour group, VBA line in the docstring.
2. **Extraction pin**: if you added Crop-sheet rows, extend
   `tests/test_crop_params_extraction.py`.
3. **Verification against the reference output** (golden master): extend `tests/test_verification.py` with a test
   function for the matching scenario from
   `data/verification/2022-05-29/wheat_gorgan_reference_output.csv`. The file already contains
   water-limited, N-limited and full-model scenarios waiting for their modules —
   load the slice by `sName`. This is the only step that proves correctness;
   unit tests only prove self-consistency.
4. **Coverage**: a matching column proves only the code paths the scenario
   runs. Trace which statements of the module the reference scenarios execute
   (e.g. with `sys.settrace`), and record in `docs/verification.md`, per process
   and VBA line range, what is checked against VBA output, what only by unit
   tests, and what not at all.

Run: `.venv/bin/pytest -q` and `.venv/bin/ruff check src/ tests/ scripts/`.

## 5. Audit before committing

Launch the `vba-fidelity-auditor` agent on the new module and its VBA range. It
checks comments and configs too, which is where this project's real defects have
been. Fix what it finds, then re-run the suite.

## 6. Commit

Message body states: which VBA lines were ported, which VBA bugs were replicated
and where, what was verified against real VBA output, what was NOT (unit tests
only), and what is still missing.
Update the status table in this file and the "Port Status" section in `CLAUDE.md`.
