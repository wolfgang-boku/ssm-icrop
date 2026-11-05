"""Sowing date finder (replaces VBA FindSimSowDate GoSub).

Only FixFind=0 (fixed sowing date) is implemented.
Other algorithms (rain-free windows, temperature thresholds, soil water) deferred.
"""

import pandas as pd

from .state import SimState


def find_sim_and_sow_rows(
    weather_df: pd.DataFrame,
    pyear: int,
    simdoy: int,
    pdoy: int,
    fix_find: int = 0,
) -> tuple[int, int]:
    """Find row indices for simulation start and sowing date.

    Args:
        weather_df: DataFrame with columns [year, doy, srad, tmax, tmin, rain]
        pyear: year to start simulation
        simdoy: day-of-year to start simulation
        pdoy: day-of-year for sowing (target sowing date)
        fix_find: sowing algorithm (only 0 supported)

    Returns:
        (sim_start_row, sow_row) — indices into weather_df. sow_row is the
        index of the sowing day (doy == pdoy) itself. The sim_start day is
        consumed without being simulated (iCrop.vba:1768-1776); the spin-up
        days sim_start+1 .. sow_row run the water/N balance with DAP=0
        (see read_spinup_day), and the crop loop begins DAP=1 on the day
        AFTER sowing.

    Raises:
        ValueError: if start/sow dates not found in weather data
        NotImplementedError: if fix_find != 0
    """
    if fix_find != 0:
        raise NotImplementedError(f"FixFind={fix_find} not yet implemented (only 0 supported)")

    # Find simulation start: first occurrence of (year=pyear, doy=simdoy)
    sim_start = None
    for idx, row in weather_df.iterrows():
        if int(row["year"]) == pyear and int(row["doy"]) == simdoy:
            sim_start = idx
            break

    if sim_start is None:
        raise ValueError(
            f"Simulation start not found: year={pyear}, doy={simdoy} not in weather data"
        )

    # Find sowing: first occurrence of doy=pdoy after sim_start
    sow_row = None
    for idx in range(sim_start, len(weather_df)):
        if int(weather_df.iloc[idx]["doy"]) == pdoy:
            sow_row = idx
            break

    if sow_row is None:
        raise ValueError(f"Sowing date not found: doy={pdoy} not found after sim start")

    return sim_start, sow_row


def read_spinup_day(
    state: SimState,
    weather_df: pd.DataFrame,
    row_idx: int,
    temp_change: float = 0.0,
    precip_change: float = 1.0,
) -> None:
    """Read one pre-sowing day the way FindSimSowDate does (iCrop.vba:1780-1791).

    Not the Weather GoSub: there is no snow accumulation or melt, so rain on a
    day with TMAX <= 1 still reaches the soil, and TMAXB/TMINA are not updated.
    CBD and DAP are forced to 0 (:1792).
    """
    row = weather_df.iloc[row_idx]
    state.yr = int(row["year"])
    state.doy = int(row["doy"])
    state.srad = float(row["srad"])
    state.tmax = float(row["tmax"]) + temp_change
    state.tmin = float(row["tmin"]) + temp_change
    state.rain = float(row["rain"]) * precip_change
    state.tmp = (state.tmax + state.tmin) / 2.0
    state.cbd = 0.0
    state.dap = 0
