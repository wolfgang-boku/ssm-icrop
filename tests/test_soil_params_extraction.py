"""Pin configs/soils/danesh.yaml against scripts/extract_soil_params.py.

The soil file must be exactly what the extractor reads from the 2022 source
workbook, so a hand edit, or a change to the extractor, fails here instead of
silently moving the verification off the workbook's values.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

from ssm_icrop.inputs import load_scenario, load_soil

REPO_ROOT = Path(__file__).parent.parent
WORKBOOK = REPO_ROOT / "SSM-iCrop" / "SSM_iCrop__2022_05_29.xlsm"
DANESH = REPO_ROOT / "configs" / "soils" / "danesh.yaml"


def _load_extractor():
    spec = importlib.util.spec_from_file_location(
        "extract_soil_params", REPO_ROOT / "scripts" / "extract_soil_params.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["extract_soil_params"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def extracted() -> dict:
    if not WORKBOOK.exists():
        pytest.skip(f"2022 source workbook not present: {WORKBOOK}")
    return _load_extractor().extract(WORKBOOK, 24)


def test_soil_file_is_the_extraction(extracted):
    """The committed file equals a fresh extraction, value for value."""
    with DANESH.open() as fh:
        assert yaml.safe_load(fh) == extracted


def test_stored_doubles_not_displayed_values():
    """The sheet displays LL = 0.204 but stores 0.20400000000000001 (iCrop.vba:1156).

    These are different doubles; VBA reads the stored one.
    """
    soil = load_soil(DANESH)
    assert soil.layers[0].cll == 0.20400000000000001
    assert soil.layers[0].cll != 0.204
    assert soil.layers[0].organic_n_pct == 0.11299999999999999


def test_layers_beyond_nlyer_are_kept():
    """Danesh has six filled layer rows and NLYER = 5 (iCrop.vba:1138, 1152)."""
    soil = load_soil(DANESH)
    assert soil.n_layers == 5
    assert len(soil.layers) == 6


def test_soil_row_must_start_a_block():
    if not WORKBOOK.exists():
        pytest.skip(f"2022 source workbook not present: {WORKBOOK}")
    with pytest.raises(SystemExit, match="does not start a soil block"):
        _load_extractor().extract(WORKBOOK, 25)


class TestScenarioSoilReference:
    """load_scenario takes the soil only from `soil_file`."""

    @staticmethod
    def _write(tmp_path, extra: dict) -> Path:
        scenario = yaml.safe_load(
            (REPO_ROOT / "configs" / "example" / "gorgan_wheat_waterlim.yaml").read_text()
        )
        for key in ("crop_file", "soil_file"):
            scenario[key] = str(REPO_ROOT / "configs" / "example" / scenario[key])
        scenario["location"]["weather_file"] = str(
            REPO_ROOT / "configs" / "example" / scenario["location"]["weather_file"]
        )
        scenario.update(extra)
        path = tmp_path / "scenario.yaml"
        path.write_text(yaml.safe_dump(scenario))
        return path

    def test_inline_soil_is_rejected_even_next_to_soil_file(self, tmp_path):
        path = self._write(tmp_path, {"soil": {"name": "edited"}})
        with pytest.raises(ValueError, match="inline `soil` block is not read"):
            load_scenario(path)

    def test_missing_soil_file_is_rejected(self, tmp_path):
        path = self._write(tmp_path, {})
        text = yaml.safe_load(path.read_text())
        del text["soil_file"]
        path.write_text(yaml.safe_dump(text))
        with pytest.raises(ValueError, match="needs `soil_file`"):
            load_scenario(path)
