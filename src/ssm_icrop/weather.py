"""Weather reader and daily update (replaces VBA Weather GoSub).

CSV weather file format (one row per day):
  year, doy, srad, tmax, tmin, rain
  e.g.: 1990, 1, 12.3, 8.5, -2.1, 0.0
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .state import SimState


@dataclass
class WeatherDay:
    yr: int
    doy: int
    srad: float    # MJ m-2 d-1
    tmax: float    # °C
    tmin: float    # °C
    rain: float    # mm


def load_weather(path: str | Path) -> pd.DataFrame:
    """Load CSV weather file; returns DataFrame sorted by year, doy."""
    df = pd.read_csv(path, header=0)
    df = df.sort_values(["year", "doy"]).reset_index(drop=True)
    return df


def step_weather(
    state: SimState,
    weather_df: pd.DataFrame,
    row_idx: int,
    temp_change: float = 0.0,
    precip_change: float = 1.0,
) -> None:
    """Read one day of weather into state, apply climate-change adjustments, handle snow.

    Args:
        state: SimState to update
        weather_df: loaded weather DataFrame (sorted by year, doy)
        row_idx: current row index in weather_df to read
        temp_change: temperature offset (°C), added to TMAX and TMIN
        precip_change: precipitation multiplier
    """
    if row_idx >= len(weather_df):
        raise IndexError(f"Weather row {row_idx} out of range (max {len(weather_df) - 1})")

    row = weather_df.iloc[row_idx]
    state.yr = int(row["year"])
    state.doy = int(row["doy"])
    state.srad = float(row["srad"])
    state.tmax = float(row["tmax"]) + temp_change
    state.tmin = float(row["tmin"]) + temp_change
    state.rain = float(row["rain"]) * precip_change

    state.tmp = (state.tmax + state.tmin) / 2.0

    # Get previous day's TMAX and next day's TMIN (for some calculations)
    state.tmaxb = 0.0
    state.tmina = 0.0
    if row_idx > 0:
        state.tmaxb = float(weather_df.iloc[row_idx - 1]["tmax"]) + temp_change
    if row_idx < len(weather_df) - 1:
        state.tmina = float(weather_df.iloc[row_idx + 1]["tmin"]) + temp_change

    # Snow accumulation and melt
    if state.tmax <= 1.0:
        state.snow += state.rain
        state.rain = 0.0
    elif state.tmax > 1.0 and state.snow > 0.0:
        snomlt = state.tmax + state.rain * 0.4
        if snomlt > state.snow:
            snomlt = state.snow
        state.snow -= snomlt
        state.rain += snomlt
