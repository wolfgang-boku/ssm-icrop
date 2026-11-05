"""Tests for sowing date finder."""

import pandas as pd
import pytest

from ssm_icrop.sowing import find_sim_and_sow_rows


def test_find_sim_and_sow_rows_basic():
    """Test finding simulation start and sowing dates."""
    df = pd.DataFrame({
        "year": [1990, 1990, 1990, 1990, 1990],
        "doy": [50, 100, 150, 200, 250],
        "srad": [10.0] * 5,
        "tmax": [15.0] * 5,
        "tmin": [5.0] * 5,
        "rain": [0.0] * 5,
    })

    sim_start, sow_row = find_sim_and_sow_rows(df, pyear=1990, simdoy=50, pdoy=150, fix_find=0)

    assert sim_start == 0  # doy=50 at index 0
    assert sow_row == 2    # doy=150 at index 2


def test_find_sim_and_sow_rows_same_date():
    """Test when sim start and sowing are the same day."""
    df = pd.DataFrame({
        "year": [1990, 1990],
        "doy": [100, 150],
        "srad": [10.0] * 2,
        "tmax": [15.0] * 2,
        "tmin": [5.0] * 2,
        "rain": [0.0] * 2,
    })

    sim_start, sow_row = find_sim_and_sow_rows(df, pyear=1990, simdoy=100, pdoy=100, fix_find=0)

    assert sim_start == 0
    assert sow_row == 0


def test_sim_start_not_found():
    """Test error when simulation start date not in weather data."""
    df = pd.DataFrame({
        "year": [1990, 1990],
        "doy": [100, 150],
        "srad": [10.0] * 2,
        "tmax": [15.0] * 2,
        "tmin": [5.0] * 2,
        "rain": [0.0] * 2,
    })

    with pytest.raises(ValueError, match="Simulation start not found"):
        find_sim_and_sow_rows(df, pyear=1990, simdoy=50, pdoy=150, fix_find=0)


def test_sow_date_not_found():
    """Test error when sowing date not found after sim start."""
    df = pd.DataFrame({
        "year": [1990, 1990, 1990],
        "doy": [50, 100, 150],
        "srad": [10.0] * 3,
        "tmax": [15.0] * 3,
        "tmin": [5.0] * 3,
        "rain": [0.0] * 3,
    })

    with pytest.raises(ValueError, match="Sowing date not found"):
        # pdoy=200 is after all available doy values
        find_sim_and_sow_rows(df, pyear=1990, simdoy=50, pdoy=200, fix_find=0)


def test_fixfind_not_zero_raises():
    """Test that FixFind values other than 0 raise NotImplementedError."""
    df = pd.DataFrame({
        "year": [1990],
        "doy": [100],
        "srad": [10.0],
        "tmax": [15.0],
        "tmin": [5.0],
        "rain": [0.0],
    })

    with pytest.raises(NotImplementedError, match="FixFind=1 not yet implemented"):
        find_sim_and_sow_rows(df, pyear=1990, simdoy=100, pdoy=150, fix_find=1)


def test_multiple_years():
    """Test with multi-year weather data."""
    df = pd.DataFrame({
        "year": [1989, 1989, 1990, 1990, 1990, 1991],
        "doy": [300, 365, 50, 150, 250, 100],
        "srad": [10.0] * 6,
        "tmax": [15.0] * 6,
        "tmin": [5.0] * 6,
        "rain": [0.0] * 6,
    })

    # Find sim start in year 1990 at doy=50
    sim_start, sow_row = find_sim_and_sow_rows(df, pyear=1990, simdoy=50, pdoy=150, fix_find=0)

    assert sim_start == 2  # index 2 has year=1990, doy=50
    assert sow_row == 3    # index 3 has doy=150
