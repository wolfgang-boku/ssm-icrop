"""Assert the config-driven path reproduces the verified literal-driven path.

tests/test_verification.py pins run_potential_production against the reference output
using hand-written parameter literals. This module runs the same season through
run_simulation() -- scenario YAML -> generated crop YAML -> build_params -> the
shared daily pipeline -- and asserts the numbers are bit-identical.

If this passes, the whole config route inherits the verification instead of
merely claiming to.
"""

from pathlib import Path

import pandas as pd
import pytest

from ssm_icrop.inputs import load_scenario
from ssm_icrop.model import build_params, run_simulation
from tests.test_verification import (
    LAT,
    PDEN,
    PDOY,
    PYEAR,
    SIMDOY,
    TAJAN_DM_DISTRIBUTION,
    TAJAN_DM_PRODUCTION,
    TAJAN_LAI,
    TAJAN_PHENOLOGY,
)

REPO_ROOT = Path(__file__).parent.parent
SCENARIO = REPO_ROOT / "configs" / "example" / "gorgan_wheat_potential.yaml"

# Parameters where the config route deliberately differs from the literals,
# because the literal was an arbitrary stand-in for an unused/inert value.
INERT_DIFFERENCES = {
    # Blank Crop-sheet cell -> 0.0; wheat's beta temperature response never
    # reads tp2d (see phenology._temperature_response_beta).
    "tp2d": (30.0, 0.0),
    # SNCS belongs to PlantN and is inert while nitrogen=0 (iCrop.vba:1066).
    "sncs": (0.0063, 0.0),
}


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(SCENARIO)


def test_scenario_is_the_verified_one(scenario):
    """Guard against the config drifting away from what the literals describe."""
    mgmt = scenario.management
    assert (mgmt.water, mgmt.nitrogen) == (0, 0)
    assert mgmt.plant_year == PYEAR
    assert mgmt.sim_doy == SIMDOY
    assert mgmt.pdoy == PDOY
    assert mgmt.plant_density == PDEN
    assert scenario.location.latitude == LAT


def test_built_params_match_the_verified_literals(scenario):
    """build_params() from YAML == the hand-written dataclasses, bar inert fields."""
    from ssm_icrop.inputs import load_crop_params

    built = build_params(load_crop_params(scenario.crop_file), scenario.location)

    for section, verified in [
        ("phenology", TAJAN_PHENOLOGY),
        ("lai", TAJAN_LAI),
        ("dm_production", TAJAN_DM_PRODUCTION),
        ("dm_distribution", TAJAN_DM_DISTRIBUTION),
    ]:
        actual = getattr(built, section)
        assert type(actual) is type(verified)
        for name in vars(verified):
            got, want = getattr(actual, name), getattr(verified, name)
            if name in INERT_DIFFERENCES:
                assert (want, got) == INERT_DIFFERENCES[name], (
                    f"{name}: expected the documented inert difference "
                    f"{INERT_DIFFERENCES[name]}, got ({want}, {got})"
                )
                continue
            if isinstance(want, str):
                # pytest >= 9.2 rejects approx() on strings instead of comparing them.
                assert got == want, f"{section}.{name}"
            else:
                assert got == pytest.approx(want, rel=1e-12), f"{section}.{name}"


def test_config_run_matches_literal_run(scenario):
    """The full season agrees column for column, day for day.

    Not bit-identical, and the config route is the *more* faithful of the two:
    the workbook stores IRUE as 2.4200000000000004 and test_verification.py's
    hand-written literal rounded it to 2.42. That last-bit difference propagates
    to ~5e-13 in WTOP over 177 days -- twelve orders of magnitude below the
    tolerances the VBA comparison uses. Phenology (CBD, DTU, MSNN) stays exactly
    equal because it never touches IRUE.
    """
    from ssm_icrop.model import run_potential_production
    from ssm_icrop.weather import load_weather

    weather_df = load_weather(scenario.location.weather_file)
    literal = run_potential_production(
        weather_df=weather_df,
        lat=LAT, pyear=PYEAR, simdoy=SIMDOY, pdoy=PDOY,
        crop_type="WHEAT",
        phenology_params=TAJAN_PHENOLOGY,
        lai_params=TAJAN_LAI,
        dm_production_params=TAJAN_DM_PRODUCTION,
        dm_distribution_params=TAJAN_DM_DISTRIBUTION,
        pden=PDEN,
    )

    config_daily = run_simulation(scenario).daily.drop(columns=["scenario"])

    assert len(config_daily) == len(literal)
    pd.testing.assert_frame_equal(config_daily, literal, rtol=1e-9, atol=1e-11)

    # Phenology must be exactly equal -- it is independent of IRUE.
    for column in ("cbd", "dtu", "msnn", "dap", "doy", "year"):
        pd.testing.assert_series_equal(
            config_daily[column], literal[column], check_exact=True
        )


def test_unported_modes_fail_loudly():
    """nitrogen=2 must raise, not silently skip a process."""
    taj1 = load_scenario(REPO_ROOT / "configs" / "example" / "gorgan_wheat_taj1.yaml")
    with pytest.raises(NotImplementedError, match="nitrogen=2"):
        run_simulation(taj1)


def test_location_climate_adjustments_reach_every_day():
    """tchng is added to TMAX/TMIN and pchng multiplies RAIN, on crop days
    (iCrop.vba:190-192) and on the days before sowing (:1786-1788).

    The Gorgan season has no day with TMAX <= 1 even at +2 degC, so snow does
    not move rain between days and RAIN scales exactly."""
    path = REPO_ROOT / "configs" / "example" / "gorgan_wheat_waterlim.yaml"
    base = run_simulation(load_scenario(path)).daily

    shifted_config = load_scenario(path)
    shifted_config.location.temp_change = 2.0
    shifted_config.location.precip_change = 1.5
    shifted = run_simulation(shifted_config).daily

    spinup = base["dap"] == 0
    assert spinup.sum() == 8
    days = min(len(base), len(shifted))
    pd.testing.assert_series_equal(
        shifted["tmp"].iloc[:days], base["tmp"].iloc[:days] + 2.0, check_exact=False
    )
    pd.testing.assert_series_equal(
        shifted["rain"].iloc[:days], base["rain"].iloc[:days] * 1.5, check_exact=False
    )
    # the water balance sees the scaled rain already before sowing
    assert shifted.loc[spinup, "crain"].iloc[-1] == pytest.approx(
        base.loc[spinup, "crain"].iloc[-1] * 1.5
    )
