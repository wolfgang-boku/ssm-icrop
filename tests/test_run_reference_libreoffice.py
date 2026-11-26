"""Unit tests for the pure helpers of scripts/run_reference_libreoffice.py.

The LibreOffice run itself needs soffice and the UNO bridge and is not run in
CI. These tests pin what the script changes in the macro before running it:
only the renaming of `Pi` and the disabled `wb.Close`, no model calculation.
They patch `iCrop.vba`, the 2022 source; the script patches the verification
workbook's module, which differs only by the output edits of
docs/verification.md. That module is checked by the LibreOffice run itself:
the patch refuses a source in which it finds nothing to change.
"""

import argparse
import csv
import importlib.util
import re
import sys
from pathlib import Path

import openpyxl
import pytest
from openpyxl.utils import get_column_letter

from tests.test_verification import REFERENCE_OUTPUT_CSV

REPO_ROOT = Path(__file__).parent.parent
VBA_SOURCE = REPO_ROOT / "iCrop.vba"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_reference_libreoffice", REPO_ROOT / "scripts" / "run_reference_libreoffice.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_reference_libreoffice"] = module
    spec.loader.exec_module(module)
    return module


lo = _load_runner()


def test_patch_changes_only_pi_and_the_weather_close():
    source = VBA_SOURCE.read_text()
    patched, report = lo.patch_vba_source(source)
    assert report == {"Pi renamed": 19, "wb.Close disabled": 1}

    old_lines, new_lines = source.split("\n"), patched.split("\n")
    assert len(old_lines) == len(new_lines)
    changed = [(o, n) for o, n in zip(old_lines, new_lines) if o != n]
    for old, new in changed:
        if "wb.Close" in old:
            assert new.strip().startswith("'wb.Close False")
        else:
            # Undo the renaming: the line must be the original again.
            assert re.sub(r"\bPiV\b", "Pi", new) == re.sub(r"\bPi\b", "Pi", old, flags=re.I)
    # The value VBA assigns is kept.
    assert patched.count("PiV = 3.141592654") == 3


def test_patch_refuses_unexpected_source():
    with pytest.raises(ValueError, match="already contains"):
        lo.patch_vba_source("PiV = 1\nPi = 3.141592654\nwb.Close False\n")
    with pytest.raises(ValueError, match="expected"):
        lo.patch_vba_source("x = 1\n")


def test_input_sheets_of_icrop_vba():
    assert lo.input_sheets(VBA_SOURCE.read_text()) == ["Run", "Location", "Manag", "Soil",
                                                       "Crop"]


def test_column_letters_match_openpyxl():
    assert all(lo.column_letters(i) == get_column_letter(i + 1) for i in range(18278))


def test_numeric_text_cells():
    rows = [["name", "0.9", 0.9, None], ["", " 2 ", "1e3x", "-4E-2"]]
    assert lo.numeric_text_cells("S", rows) == ["S!B1", "S!B2", "S!D2"]


@pytest.mark.parametrize("text", ["0.9", "0,9", ".5", "-4E-2", "12", " 3. ",
                                  "1,000.5", "1.000,5", "12,345", "1D3", "&H1F", "&o17"])
def test_numeric_text_includes_what_libreoffice_may_convert(text):
    assert lo.is_numeric_text(text)


@pytest.mark.parametrize("text", ["nan", "inf", "Infinity", "1_0", "", "x1", "1,2,3", "&H"])
def test_numeric_text_excludes_what_is_no_plain_number(text):
    assert not lo.is_numeric_text(text)


def test_verification_workbook_has_one_numeric_text_cell():
    """Manag!G89 (IRGLVL of Taj1-Nlim) is the only number stored as text.

    The documented LibreOffice run overrides exactly this cell; a second one
    would need its own override (docs/verification.md).
    """
    wb = openpyxl.load_workbook(lo.DEFAULT_WORKBOOK, read_only=True, data_only=True)
    # The sheets the script checks: those read by name, plus the first one.
    names = dict.fromkeys(lo.input_sheets(VBA_SOURCE.read_text()) + [wb.sheetnames[0]])
    found = []
    for name in names:
        found += lo.numeric_text_cells(name, wb[name].iter_rows(values_only=True))
    assert found == ["Manag!G89"]


def test_parse_override():
    assert lo.parse_override("Manag!G89=1e300") == ("Manag", "G89", 1e300)
    assert lo.parse_override(" Crop!ab12 = 0.5 ") == ("Crop", "AB12", 0.5)
    assert lo.parse_override(" Manag ! g89 = 1e300") == ("Manag", "G89", 1e300)
    for bad in ("G89=1", "Manag!G89=abc", "Manag!G89=nan", "Manag!G89=inf",
                "Manag!A0=1", "Manag!G089=1", "Manag!ABCD1=1"):
        with pytest.raises(argparse.ArgumentTypeError):
            lo.parse_override(bad)


def test_csv_value_reproduces_the_reference_export():
    """Every numeric cell of the committed openpyxl export formats back to its text."""
    with open(REFERENCE_OUTPUT_CSV, newline="") as f:
        rows = list(csv.reader(f))[1:]
    cells = [text for row in rows for text in row[lo.N_ID_COLUMNS:] if text != ""]
    assert len(cells) > 40000
    assert [c for c in cells if lo.csv_value(float(c)) != c] == []


def test_csv_value_other_types():
    assert lo.csv_value("") == ""
    assert lo.csv_value("Taj1 Arab") == "Taj1 Arab"
    assert lo.csv_value(1e20) == "1e+20"  # beyond 2**53: float form, as pandas writes it


def test_dailyo_rows():
    data = (("sName", "DAP", "WTOP", ""),
            ("A", 1.0, 0.5, ""),
            ("", "", "", ""),      # gap between two 500-row blocks
            ("B", 2.0, "", "x"))   # stray cell right of the header
    header, rows = lo.dailyo_rows(data)
    assert header == ["sName", "DAP", "WTOP"]
    assert rows == [["A", "1", "0.5"], ["B", "2", ""]]


@pytest.mark.parametrize("a, b, expected", [
    ("", "", 0.0), ("#N/A", "#N/A", 0.0), ("1.5", "1.5", 0.0), ("1", "1.0", 0.0),
    ("1.5", "1.25", 0.25), ("", "0", float("inf")), ("#N/A", "1", float("inf")),
    ("nan", "", float("inf")), ("nan", "nan", 0.0),
])
def test_diff(a, b, expected):
    assert lo._diff(a, b) == expected


def test_compare_csv_relative_tolerance_scales_with_the_value(tmp_path):
    big = [HEADER, ROWS[0][:-1] + ["8192.0"], ROWS[1]]
    _write_csv(tmp_path / "ref.csv", big)
    run = [HEADER, ROWS[0][:-1] + ["8192.000000000004"], ROWS[1]]  # 2 ULP, 3.6e-12
    _write_csv(tmp_path / "run.csv", run)
    assert not lo.compare_csv(tmp_path / "run.csv", tmp_path / "ref.csv", 1e-12)
    assert lo.compare_csv(tmp_path / "run.csv", tmp_path / "ref.csv", 1e-12, 1e-14)


def _write_csv(path, rows):
    path.write_text("\n".join(",".join(r) for r in rows) + "\n")


HEADER = ["sName", "Location", "Manag", "Soil", "Crop", "DAP", "WTOP"]
ROWS = [["A", "L", "M", "S", "C", "1", "10.0"], ["A", "L", "M", "S", "C", "2", ""]]


def test_compare_csv_passes_within_tolerance(tmp_path):
    _write_csv(tmp_path / "ref.csv", [HEADER, *ROWS])
    run = [HEADER, ROWS[0][:-1] + ["10.0000001"], ROWS[1]]
    _write_csv(tmp_path / "run.csv", run)
    assert lo.compare_csv(tmp_path / "run.csv", tmp_path / "ref.csv", 1e-6)
    assert not lo.compare_csv(tmp_path / "run.csv", tmp_path / "ref.csv", 1e-9)


@pytest.mark.parametrize("run", [
    [HEADER, ROWS[0]],                                        # row missing
    [HEADER, *ROWS, ["B", "L", "M", "S", "C", "1", "1"]],     # extra scenario
    [HEADER, ROWS[0], ROWS[1][:-1] + ["0"]],                  # blank vs number
    [HEADER, ROWS[0], ["A", "X", "M", "S", "C", "2", ""]],    # identifier differs
    [HEADER + ["EXTRA"], *[r + [""] for r in ROWS]],          # extra column
    [HEADER, ROWS[0], ROWS[1][:-1]],                          # row too short
])
def test_compare_csv_fails_on_mismatch(tmp_path, run):
    _write_csv(tmp_path / "ref.csv", [HEADER, *ROWS])
    _write_csv(tmp_path / "run.csv", run)
    assert not lo.compare_csv(tmp_path / "run.csv", tmp_path / "ref.csv", 1e-6)
