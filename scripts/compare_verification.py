"""Compare the Python port with the reference output (potential-production scenario).

Reference output (golden master): data/verification/2022-05-29/wheat_gorgan_reference_output.csv,
exported from SSM_iCrop__2022_05_29_verification.xlsm (see docs/verification.md
for how it was generated). Wheat cultivar "Tajan" (Crop sheet column D) at
Gorgan, sown DOY 348 2005 (Taj1 config), scenario "Taj1-Potential"
(water=0, nitrogen=0).

This report covers "Taj1-Potential" only. tests/test_verification.py also
verifies "Taj1-WaterLim" and the pre-sowing days of the irrigated scenarios.

Usage:
    .venv/bin/python scripts/compare_verification.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ssm_icrop.crop_lai import LAIParams
from ssm_icrop.dm_distribution import DMDistributionParams
from ssm_icrop.dm_production import DMProductionParams
from ssm_icrop.model import run_potential_production
from ssm_icrop.phenology import WheatParams
from ssm_icrop.weather import load_weather

REPO_ROOT = Path(__file__).parent.parent

# --- Wheat "Tajan", Crop sheet column D (Taj1 Arab's cultivar) ---
phenology_params = WheatParams(
    tbd=0.0, tp1d=27.5, tp2d=30.0, tcd=40.0,  # tp2d unused (blank in sheet)
    tbver=-1.0, tp1ver=0.0, tp2ver=8.0, tcver=12.0,
    vdsat=50.0, vsen=0.00089,
    cpp=21.0, ppsen=0.001467,
    bd_sowemr=3.5, bd_emrtil=4.95, bd_tilsel=11.4, bd_selbot=6.0,
    bd_botear=2.0, bd_earant=8.0, bd_antpm=34.0, bd_pmhm=8.0,
)

lai_params = LAIParams(
    phyl=95.0, placon=1.0, plapow=2.4336,
    a_pla_den=1.1718, b_pla_den=-0.0006,
    sla=0.021, frztkil=-5.0, frzldr=0.01, htlth=30.0, htldr=0.1,
)

dm_production_params = DMProductionParams(
    irue=2.42, kpar=0.65,
    tbrue=0.0, tp1rue=15.0, tp2rue=22.0, tcrue=35.0,
    vpd_type=0, vpd_threshold=2.0, vpdf=0.63,
    co2=385.0, co2_ref=385.0, co2_res=0.8,
    tec_ref=5.8,
)

dm_distribution_params = DMDistributionParams(
    flf1a=0.6, flf1b=0.3, wtopl=160.0, flf2=0.1,
    frtrl=0.22, gcc=1.0, pdhi=0.01638,
    wdhi1=0.0, wdhi2=600.0, wdhi3=1200.0, wdhi4=3200.0,
    sncs=0.0063, mc=14.0,
    heat=1, tp2h=31.0, tch=40.0, tp1f=0.0, tbf=-5.0, rfmax=0.3,
)

LAT = 36.85
PDEN = 386.0
PYEAR = 2005
SIMDOY = 340
PDOY = 348

# VBA column name -> our daily DataFrame column name, for columns we can
# actually compare (excludes water/N columns, which don't exist in the
# potential-production output yet)
VBA_TO_PY = {
    "TMP": "tmp", "RAIN": "rain", "DTU": "dtu", "CBD": "cbd", "MSNN": "msnn",
    "GLAI": "glai", "DLAI": "dlai", "LAI": "lai", "FINT": "fint",
    "DDMP": "ddmp", "GLF": "glf", "GST": "gst", "SGR": "sgr",
    "WLF": "wlf", "WST": "wst", "WVEG": "wveg", "WGRN": "wgrn", "WTOP": "wtop",
}

# The same absolute tolerance as tests/test_verification.py: it only absorbs
# floating-point accumulation, the port matches to about 1e-9.
ATOL = 1e-6


def load_vba_reference(scenario: str) -> pd.DataFrame:
    """Load the full-precision DailyO export (data/verification/2022-05-29/*.csv,
    written directly from the xlsm via openpyxl -- NOT the spreadsheet
    application's own CSV export, which silently rounds to each column's display format and can
    be off by up to 0.5 on integer-formatted columns like WLF/WST/WTOP)."""
    path = REPO_ROOT / "data" / "verification" / "2022-05-29" / "wheat_gorgan_reference_output.csv"
    df = pd.read_csv(path)
    df = df[df["sName"] == scenario].copy()
    df = df[df["DAP"] > 0]  # drop spin-up rows (DAP=0, before sowing)
    df["DAP"] = df["DAP"].astype(int)
    df = df.rename(columns=VBA_TO_PY)
    return df.set_index("DAP")


def main() -> None:
    weather_df = load_weather(REPO_ROOT / "data" / "weather" / "gorgan.csv")

    py_daily = run_potential_production(
        weather_df=weather_df,
        lat=LAT, pyear=PYEAR, simdoy=SIMDOY, pdoy=PDOY,
        crop_type="WHEAT",
        phenology_params=phenology_params,
        lai_params=lai_params,
        dm_production_params=dm_production_params,
        dm_distribution_params=dm_distribution_params,
        pden=PDEN,
    )
    py_daily = py_daily[py_daily["dap"] > 0].set_index("dap")  # drop spin-up rows

    vba_daily = load_vba_reference("Taj1-Potential")

    py_range = f"{py_daily.index.min()}-{py_daily.index.max()}"
    vba_range = f"{vba_daily.index.min()}-{vba_daily.index.max()}"
    print(f"Python: {len(py_daily)} days (DAP {py_range})")
    print(f"VBA:    {len(vba_daily)} days (DAP {vba_range})")

    common_dap = py_daily.index.intersection(vba_daily.index)
    print(f"Comparing {len(common_dap)} overlapping DAP values\n")

    report = []
    for col in VBA_TO_PY.values():
        py_vals = py_daily.loc[common_dap, col]
        vba_vals = vba_daily.loc[common_dap, col]
        diff = (py_vals - vba_vals).abs()
        tol = ATOL
        n_bad = (diff > tol).sum()
        max_diff = diff.max()
        max_diff_dap = diff.idxmax()
        report.append((col, n_bad, len(common_dap), max_diff, max_diff_dap,
                       py_vals.loc[max_diff_dap], vba_vals.loc[max_diff_dap]))

    print(f"{'column':8} {'mismatches':12} {'max |diff|':12} {'at DAP':8} "
          f"{'python':>10} {'vba':>10}")
    for col, n_bad, n_total, max_diff, dap, py_v, vba_v in report:
        flag = "  <-- FAIL" if n_bad > 0 else ""
        print(f"{col:8} {n_bad:4}/{n_total:<7} {max_diff:12.2e} {dap:8} "
              f"{py_v:10.2f} {vba_v:10.2f}{flag}")

    n_failing_cols = sum(1 for r in report if r[1] > 0)
    print(f"\n{len(report) - n_failing_cols}/{len(report)} columns within tolerance")


if __name__ == "__main__":
    main()
