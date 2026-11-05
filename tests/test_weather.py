"""Tests for the weather module."""

import pandas as pd
import pytest

from ssm_icrop.state import SimState
from ssm_icrop.weather import load_weather, step_weather


def test_load_weather_columns(tmp_path):
    csv = tmp_path / "weather.csv"
    csv.write_text("year,doy,srad,tmax,tmin,rain\n1990,1,12.3,8.5,-2.1,0.0\n")
    df = load_weather(csv)
    assert list(df.columns) == ["year", "doy", "srad", "tmax", "tmin", "rain"]
    assert len(df) == 1
    assert df.iloc[0]["year"] == 1990


def test_step_weather_basic():
    df = pd.DataFrame({
        "year": [1990, 1990],
        "doy": [1, 2],
        "srad": [12.3, 11.5],
        "tmax": [8.5, 10.0],
        "tmin": [-2.1, -1.0],
        "rain": [0.0, 2.5],
    })

    state = SimState()
    step_weather(state, df, row_idx=0)
    assert state.yr == 1990
    assert state.doy == 1
    assert state.srad == 12.3
    assert state.tmax == 8.5
    assert state.tmin == -2.1
    assert state.rain == 0.0
    assert state.tmp == (8.5 - 2.1) / 2


def test_step_weather_climate_adjustment():
    df = pd.DataFrame({
        "year": [1990],
        "doy": [1],
        "srad": [12.3],
        "tmax": [8.5],
        "tmin": [-2.1],
        "rain": [10.0],
    })

    state = SimState()
    step_weather(state, df, row_idx=0, temp_change=2.0, precip_change=1.5)
    assert state.tmax == pytest.approx(8.5 + 2.0)
    assert state.tmin == pytest.approx(-2.1 + 2.0)
    assert state.rain == pytest.approx(10.0 * 1.5)


def test_snow_accumulation():
    df = pd.DataFrame({
        "year": [1990, 1990, 1990],
        "doy": [1, 2, 3],
        "srad": [10.0, 10.0, 10.0],
        "tmax": [-5.0, 0.5, 3.0],  # cold, cold, thaw
        "tmin": [-10.0, -2.0, 1.0],
        "rain": [5.0, 5.0, 5.0],
    })

    state = SimState()

    # Day 1: cold, rain becomes snow
    step_weather(state, df, row_idx=0)
    assert state.snow == 5.0
    assert state.rain == 0.0

    # Day 2: still cold, more snow accumulates
    step_weather(state, df, row_idx=1)
    assert state.snow == 10.0  # 5 + 5
    assert state.rain == 0.0

    # Day 3: warm, snow melts
    step_weather(state, df, row_idx=2)
    assert state.snow < 10.0  # some melted
    assert state.rain > 0.0   # meltwater added to rain
