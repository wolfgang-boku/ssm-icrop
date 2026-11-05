"""Assert the output dataclasses match the VBA's column order, parsed from source.

DailyPrintOut and SummaryPrintOut write positionally into worksheet columns, so
field *order* in DailyRecord/SeasonSummary is part of the contract, not a style
choice. Rather than trusting a one-time reading, this parses the assignments out
of iCrop.vba on every run: reorder a field, drop one, or add one, and this fails.

VBA_TO_FIELD maps VBA variable names to our field names wherever they differ
(expanded names, or derived expressions that have no VBA variable at all).
"""

import re
from dataclasses import fields
from pathlib import Path

import pytest

from ssm_icrop.outputs import DailyRecord, SeasonSummary

VBA = Path(__file__).parent.parent / "iCrop.vba"

# Identifier columns: the VBA writes .Formula from scnName/locName/... names.
IDENTIFIERS = {
    "scnName": "scenario",
    "locName": "location",
    "mngName": "management",
    "solName": "soil",
    "crpName": "crop",
    "Pyear": "year",
}

DAILY_RENAMES = {**IDENTIFIERS}

SUMMARY_RENAMES = {
    **IDENTIFIERS,
    "dtEMR": "dt_emr",
    "dtR0": "dt_r0",
    "dtR1": "dt_r1",
    "dtR2": "dt_r2",
    "dtR3": "dt_r3",
    "dtR4": "dt_r4",
    "dtR5": "dt_r5",
    "dtR6": "dt_r6",
    "dtR7": "dt_r7",
    "dtR8": "dt_r8",
    "MXLAI": "mxlai",
    "R5ANTDM": "r5ant_dm",
    "MATYP": "matyp",
    "Ywet": "ywet",
    # Derived expressions with no VBA variable of their own.
    "WGRN / (WTOP + 0.00001)": "hi",
    "CE + CTR": "et_total",
    "CE / (CE + CTR + 0.00001)": "e_fraction",
    # Environmental sums: VBA suffixes T/2/3 for season/vegetative/seed-filling.
    "SRAINT": "srain_total",
    "MTMINT": "mtmin_total",
    "MTMAXT": "mtmax_total",
    "SSRADT": "ssrad_total",
    "SUMETT": "sumet_total",
    "SRAIN2": "srain_veg",
    "MTMIN2": "mtmin_veg",
    "MTMAX2": "mtmax_veg",
    "SSRAD2": "ssrad_veg",
    "SUMET2": "sumet_veg",
    "SRAIN3": "srain_fill",
    "MTMIN3": "mtmin_fill",
    "MTMAX3": "mtmax_fill",
    "SSRAD3": "ssrad_fill",
    "SUMET3": "sumet_fill",
}


def _parse_columns(sheet: str, counter: str, renames: dict[str, str]) -> list[str]:
    """Extract `Sheet<N>.Cells(<counter> + 1, C) = VAR` in column order."""
    source = VBA.read_text(errors="replace")
    pattern = re.compile(
        rf"{sheet}\.Cells\({re.escape(counter)} \+ 1,\s*(\d+)\)(?:\.Formula)?\s*=\s*([^'\r\n]+)"
    )

    by_column: dict[int, str] = {}
    for match in pattern.finditer(source):
        column = int(match.group(1))
        raw = match.group(2).strip()
        # Keep the first write to a column; later ones would be overwrites.
        by_column.setdefault(column, renames.get(raw, raw.lower()))

    assert by_column, f"parsed no columns for {sheet} -- has iCrop.vba moved?"
    expected = list(range(1, max(by_column) + 1))
    assert sorted(by_column) == expected, (
        f"{sheet} columns are not contiguous 1..{max(by_column)}: "
        f"missing {sorted(set(expected) - set(by_column))}"
    )
    return [by_column[c] for c in expected]


@pytest.fixture(scope="module")
def daily_columns() -> list[str]:
    return _parse_columns("Sheet4", "dayCntr", DAILY_RENAMES)


@pytest.fixture(scope="module")
def summary_columns() -> list[str]:
    return _parse_columns("Sheet10", "scyrCntr", SUMMARY_RENAMES)


def test_daily_column_count(daily_columns):
    """CLAUDE.md documents 63 daily output columns."""
    assert len(daily_columns) == 63


def test_summary_column_count(summary_columns):
    assert len(summary_columns) == 64


def test_daily_record_matches_vba_order(daily_columns):
    assert [f.name for f in fields(DailyRecord)] == daily_columns


def test_season_summary_matches_vba_order(summary_columns):
    assert [f.name for f in fields(SeasonSummary)] == summary_columns
