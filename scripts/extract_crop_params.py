"""Extract one cultivar's parameters from a source workbook's Crop sheet into YAML.

The default is the 2022 source workbook, the version the port targets.

The Crop sheet stores one cultivar per column (column C onwards) and one
parameter per row. Row numbers are not documented anywhere in the sheet -- they
are only implied by the `Worksheets("Crop").Cells(<row>, CropColNo)` reads
scattered through iCrop.vba. ROW_MAP below is that mapping, transcribed with the
VBA line number for each entry so it can be re-checked.

Rows 80-87 are *overloaded*: the same cells hold different phase lengths
depending on crop type (WHEAT reads 8 phases, MAIZE 3, LEGUME 6), so the
per-crop phenology maps are separate.

Usage:
    .venv/bin/python scripts/extract_crop_params.py --column D
    .venv/bin/python scripts/extract_crop_params.py --column D -o configs/crops/wheat.yaml
    .venv/bin/python scripts/extract_crop_params.py --list

Verify a generated file against the verified literals in tests/test_verification.py:
    .venv/bin/pytest tests/test_crop_params_extraction.py
"""

import argparse
import sys
from pathlib import Path

import openpyxl
import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKBOOK = REPO_ROOT / "SSM-iCrop" / "SSM_iCrop__2022_05_29.xlsm"

# yaml key -> (Crop sheet row, iCrop.vba line that reads it)
# Shared by all crop types.
LAI_ROWS = {
    "phyl": (7, 721),
    "placon": (8, 722),
    "plapow": (9, 723),
    "a_pla_den": (10, 724),
    "b_pla_den": (11, 725),
    "sla": (12, 726),
    "frztkil": (13, 727),
    "frzldr": (14, 728),
    "htlth": (15, 729),
    "htldr": (16, 730),
}

DM_PRODUCTION_ROWS = {
    "tbrue": (18, 881),
    "tp1rue": (19, 882),
    "tp2rue": (20, 883),
    "tcrue": (21, 884),
    "kpar": (22, 885),
    "irue": (23, 886),
    "co2_ref": (24, 117),
    "co2_res": (25, 887),
    "tec_ref": (49, 888),
    "vpd_type": (55, 889),      # sheet label "vpd_resp"
    "vpd_threshold": (56, 890),  # sheet label "vpd_cr"
}

DM_DISTRIBUTION_ROWS = {
    "flf1a": (27, 980),
    "flf1b": (28, 981),
    "wtopl": (29, 982),
    "flf2": (30, 983),
    "frtrl": (31, 984),
    "gcc": (32, 985),
    "pdhi": (33, 986),
    "wdhi1": (34, 987),
    "wdhi2": (35, 988),
    "wdhi3": (36, 989),
    "wdhi4": (37, 990),
    "mc": (38, 991),
    "heat": (39, 992),
    "tp2h": (40, 993),
    "tch": (41, 994),
    "tp1f": (42, 995),
    "tbf": (43, 996),
    "rfmax": (44, 997),
}

# SoilWater's own reads (iCrop.vba:1118-1132). TECREF and CO2RES are read here a
# second time (DMProduction reads them too) because SoilWater needs TEC on the
# pre-sowing days, before DMProduction first runs. CO2REF is read once, in
# LocManagInputs. VPDcr (row 56, :1129) is read but never used by SoilWater.
SOIL_WATER_ROWS = {
    "deport": (46, 1118),
    "meed": (47, 1119),
    "grtdp": (48, 1120),
    "tec_ref": (49, 1121),
    "co2_res": (25, 1122),
    "co2_ref": (24, 117),
    "wssg": (50, 1123),
    "wssl": (51, 1124),
    "wssd": (52, 1125),
    "wssn": (53, 1126),
    "fldkil": (54, 1127),
    "vpd_type": (55, 1128),
    "surviv": (57, 1130),
    "epcond": (58, 1131),
    "ltlrwc": (59, 1132),
}

# Cardinal temperatures for the biological-day rate; same rows for every crop.
PHENO_COMMON_ROWS = {
    "tbd": (70, 223),
    "tp1d": (71, 224),
    "tp2d": (72, 225),
    "tcd": (73, 226),
    "cpp": (77, 235),
    "ppsen": (78, 236),
}

# Rows 80-87 mean different things per crop type -- see iCrop.vba:238-245 (wheat),
# 406-408 (maize), 565-570 (legume).
PHENO_BY_CROP = {
    "WHEAT": {
        "vsen": (75, 233),
        "bd_sowemr": (80, 238),
        "bd_emrtil": (81, 239),
        "bd_tilsel": (82, 240),
        "bd_selbot": (83, 241),
        "bd_botear": (84, 242),
        "bd_earant": (85, 243),
        "bd_antpm": (86, 244),
        "bd_pmhm": (87, 245),
    },
    "MAIZE": {
        "bd_sowemr": (80, 406),
        "bd_emreju": (81, 407),
        "bd_silpm": (82, 408),
    },
    "LEGUME": {
        "bd_sowemr": (80, 565),
        "bd_emrr1": (81, 566),
        "bd_r1r3": (82, 567),
        "bd_r3r5": (83, 568),
        "bd_r5r7": (84, 569),
        "bd_r7r8": (85, 570),
        "bd_brp": (91, 583),
        "bd_trp": (92, 584),
        "bd_bsg": (93, 586),
        "bd_tsg": (94, 587),
        "bd_tlm": (96, 590),
        "bd_tlp": (97, 591),
        "bd_bls": (98, 592),
    },
}

# Hardcoded in the VBA, NOT read from the sheet -- see iCrop.vba:228-232.
# An extractor cannot find these; they are emitted as literals with that note.
WHEAT_VBA_CONSTANTS = {
    "tbver": -1.0,
    "tp1ver": 0.0,
    "tp2ver": 8.0,
    "tcver": 12.0,
    "vdsat": 50.0,
}

# Read from the Location sheet, not the Crop sheet (iCrop.vba:113, 116). They sit
# in DMProductionParams on the Python side, so they are deliberately NOT emitted
# here -- a crop file that carried them would be claiming they are crop traits.
LOCATION_OWNED = {"vpdf": 113, "co2": 116}


def _crop_type(ws, column: int) -> str:
    """Read and normalise the crop name from row 5 (iCrop.vba:55, 219)."""
    raw = ws.cell(5, column).value
    if raw is None:
        raise SystemExit(f"No crop name in row 5 of column {column} -- empty cultivar?")
    name = str(raw).strip().upper()
    if name in ("WHEAT", "MAIZE"):
        return name
    return "LEGUME"  # everything else runs the legume phenology (iCrop.vba:220-556)


def _read(ws, column: int, rows: dict[str, tuple[int, int]]) -> dict:
    """Read a row map, keeping blanks and text cells visible instead of coercing."""
    out = {}
    for key, (row, vba_line) in rows.items():
        value = ws.cell(row, column).value
        if value is None:
            out[key] = None  # blank in the sheet; VBA reads this as 0
        elif isinstance(value, (int, float)):
            out[key] = float(value)
        else:
            # e.g. row 91 holds the text "bdEMR" for wheat -- a cross-reference,
            # not a number. Surface it rather than crashing or silently zeroing.
            out[key] = f"__TEXT__{value}"
            print(
                f"  note: row {row} ({key}, iCrop.vba:{vba_line}) holds text "
                f"{value!r}, not a number",
                file=sys.stderr,
            )
    return out


def extract(workbook: Path, column: str) -> dict:
    wb = openpyxl.load_workbook(workbook, data_only=True)
    ws = wb["Crop"]
    col_idx = openpyxl.utils.column_index_from_string(column)

    crop_type = _crop_type(ws, col_idx)
    cultivar = str(ws.cell(6, col_idx).value or "").strip()

    pheno = _read(ws, col_idx, PHENO_COMMON_ROWS)
    pheno.update(_read(ws, col_idx, PHENO_BY_CROP[crop_type]))
    if crop_type == "WHEAT":
        pheno.update(WHEAT_VBA_CONSTANTS)
    if crop_type == "MAIZE":
        pheno["phyl"] = float(ws.cell(7, col_idx).value)  # iCrop.vba:409

    return {
        "crop_type": crop_type,
        "cultivar": cultivar or f"column_{column}",
        "_source": {
            "workbook": str(workbook.relative_to(REPO_ROOT)),
            "sheet": "Crop",
            "column": column,
            "note": (
                "Generated by scripts/extract_crop_params.py -- do not hand-edit. "
                "vpdf and co2 are Location-sheet parameters and are set per "
                "scenario, not here."
            ),
        },
        "phenology": pheno,
        "lai": _read(ws, col_idx, LAI_ROWS),
        "dm_production": _read(ws, col_idx, DM_PRODUCTION_ROWS),
        "dm_distribution": _read(ws, col_idx, DM_DISTRIBUTION_ROWS),
        "soil_water": _read(ws, col_idx, SOIL_WATER_ROWS),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--column", default="D", help="Crop sheet column (default: D = Tajan)")
    ap.add_argument("-o", "--output", type=Path, help="write YAML here (default: stdout)")
    ap.add_argument("--workbook", type=Path, default=WORKBOOK)
    ap.add_argument("--list", action="store_true", help="list cultivars and exit")
    args = ap.parse_args()

    if args.list:
        ws = openpyxl.load_workbook(args.workbook, data_only=True)["Crop"]
        for c in range(3, ws.max_column + 1):
            name = ws.cell(5, c).value
            if name:
                letter = openpyxl.utils.get_column_letter(c)
                print(f"{letter:>3}  {name:<12} {ws.cell(6, c).value or ''}")
        return

    params = extract(args.workbook, args.column.upper())
    text = yaml.safe_dump(params, sort_keys=False, default_flow_style=False)

    if args.output:
        args.output.write_text(text)
        print(f"wrote {args.output} ({params['crop_type']}, column {args.column})")
    else:
        print(text)


if __name__ == "__main__":
    main()
