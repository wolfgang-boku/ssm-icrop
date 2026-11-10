"""Pin scripts/extract_crop_params.py against the verified parameter literals.

tests/test_verification.py holds the "Tajan" parameters as hand-transcribed Python
literals, and those literals are what produced the exact match against real VBA
output. This module asserts the extractor reads the same numbers straight out of
the workbook, which is what lets the hand-transcribed literals be retired: if
this passes, generated YAML is as trustworthy as the transcription was.

Known, deliberate mismatches are listed in EXPECTED_DIVERGENCE with the reason.
"""

import importlib.util
import sys
from dataclasses import fields
from pathlib import Path

import pytest

from tests.test_verification import (
    TAJAN_DM_DISTRIBUTION,
    TAJAN_DM_PRODUCTION,
    TAJAN_LAI,
    TAJAN_PHENOLOGY,
    TAJAN_PLANT_N,
    TAJAN_SOIL_WATER,
)

REPO_ROOT = Path(__file__).parent.parent
WORKBOOK = REPO_ROOT / "SSM-iCrop" / "SSM_iCrop__2022_05_29.xlsm"

# Fields the extractor deliberately does not emit, with why.
EXPECTED_DIVERGENCE = {
    # Location-sheet parameters (iCrop.vba:113, 116) that currently sit in
    # DMProductionParams. A crop file must not claim them as crop traits.
    "vpdf": "Location sheet, not Crop sheet",
    "co2": "Location sheet, not Crop sheet",
    # Python-side addition: an alternative RUE temperature response, not a
    # workbook value.
    "temp_response": "Python-only option, no sheet cell",
    # Blank in the sheet for Tajan; the literal 30.0 in test_verification.py is an
    # arbitrary stand-in for an unused parameter. VBA reads a blank cell as 0.
    "tp2d": "blank in sheet for this cultivar; VBA reads blank as 0",
}


def _load_extractor():
    spec = importlib.util.spec_from_file_location(
        "extract_crop_params", REPO_ROOT / "scripts" / "extract_crop_params.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["extract_crop_params"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tajan() -> dict:
    if not WORKBOOK.exists():
        pytest.skip(f"2022 source workbook not present: {WORKBOOK}")
    return _load_extractor().extract(WORKBOOK, "D")


@pytest.mark.parametrize(
    "section,verified",
    [
        ("phenology", TAJAN_PHENOLOGY),
        ("lai", TAJAN_LAI),
        ("dm_production", TAJAN_DM_PRODUCTION),
        ("dm_distribution", TAJAN_DM_DISTRIBUTION),
        ("soil_water", TAJAN_SOIL_WATER),
        ("plant_n", TAJAN_PLANT_N),
    ],
)
def test_extracted_matches_verified_literals(tajan, section, verified):
    """Every field of the verified dataclass is reproduced from the workbook."""
    extracted = tajan[section]
    checked = 0

    for f in fields(verified):
        if f.name in EXPECTED_DIVERGENCE:
            continue
        assert f.name in extracted, (
            f"{section}.{f.name} is in the verified params but the extractor "
            f"does not emit it -- add it to the row map or to EXPECTED_DIVERGENCE"
        )
        expected = getattr(verified, f.name)
        actual = extracted[f.name]
        if actual is None:
            actual = 0.0  # blank cell, read as 0 by VBA and by model.build_params
        assert actual == pytest.approx(expected, rel=1e-9), (
            f"{section}.{f.name}: workbook has {actual}, "
            f"verified literal is {expected}"
        )
        checked += 1

    assert checked > 0


def test_divergences_are_actually_absent(tajan):
    """EXPECTED_DIVERGENCE must stay honest -- fail if a listed key is emitted."""
    all_keys = {k for section in tajan.values() if isinstance(section, dict) for k in section}
    for key, reason in EXPECTED_DIVERGENCE.items():
        if key == "tp2d":
            # tp2d IS emitted, just as None (blank cell) rather than the literal.
            assert tajan["phenology"]["tp2d"] is None, reason
            continue
        assert key not in all_keys, (
            f"{key} is now emitted by the extractor -- remove it from "
            f"EXPECTED_DIVERGENCE ({reason})"
        )


def test_crop_type_dispatch(tajan):
    """Rows 80-87 are overloaded per crop type; check each type reads its own map."""
    extract = _load_extractor().extract
    assert tajan["crop_type"] == "WHEAT"
    assert "bd_emrtil" in tajan["phenology"]

    maize = extract(WORKBOOK, "Y")
    assert maize["crop_type"] == "MAIZE"
    assert "bd_emreju" in maize["phenology"]
    assert "bd_emrtil" not in maize["phenology"]
    assert maize["phenology"]["phyl"] is not None  # iCrop.vba:409

    soybean = extract(WORKBOOK, "K")
    assert soybean["crop_type"] == "LEGUME"
    assert "bd_emrr1" in soybean["phenology"]
    assert "bd_r7r8" in soybean["phenology"]
    assert soybean["phenology"]["bd_bnf"] == 12.0  # row 104, iCrop.vba:600
    assert "bd_bnf" not in tajan["phenology"]  # wheat hardcodes 999 (:280)
