"""Run one potential-production scenario and plot the daily output.

Dev tool for plausibility checks — not part of the installable package.
Params below are real values extracted from the 2022 source workbook
(SSM_iCrop__2022_05_29.xlsm): wheat cultivar "Zagros" (Crop sheet, column
C) sown at Gorgan (Location sheet, row 7), management row 13 (FixFind=0,
Fyear=2005, SimDoy=340, Pdoy=348, Pden=386).

Usage:
    .venv/bin/python scripts/plot_scenario.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ssm_icrop.crop_lai import LAIParams
from ssm_icrop.dm_distribution import DMDistributionParams
from ssm_icrop.dm_production import DMProductionParams
from ssm_icrop.model import run_potential_production
from ssm_icrop.phenology import WheatParams
from ssm_icrop.weather import load_weather

REPO_ROOT = Path(__file__).parent.parent

# --- Wheat "Zagros", Crop sheet column C ---
phenology_params = WheatParams(
    tbd=0.0, tp1d=27.5, tp2d=30.0, tcd=40.0,  # tp2d unused (blank in sheet)
    tbver=-1.0, tp1ver=0.0, tp2ver=8.0, tcver=12.0,
    vdsat=50.0, vsen=0.00305,
    cpp=21.0, ppsen=0.001649,
    bd_sowemr=4.0, bd_emrtil=5.5, bd_tilsel=8.04, bd_selbot=7.0,
    bd_botear=2.0, bd_earant=7.0, bd_antpm=34.0, bd_pmhm=8.0,
)

lai_params = LAIParams(
    phyl=91.0, placon=1.0, plapow=2.34,
    a_pla_den=1.1718, b_pla_den=-0.0006,
    sla=0.021, frztkil=-5.0, frzldr=0.01, htlth=30.0, htldr=0.1,
)

dm_production_params = DMProductionParams(
    irue=2.2, kpar=0.65,
    tbrue=0.0, tp1rue=15.0, tp2rue=22.0, tcrue=35.0,
    vpd_type=0, vpd_threshold=2.0, vpdf=0.63,
    co2=385.0, co2_ref=385.0, co2_res=0.8,
    tec_ref=5.8,
)

dm_distribution_params = DMDistributionParams(
    flf1a=0.6, flf1b=0.3, wtopl=160.0, flf2=0.1,
    frtrl=0.22, gcc=1.0, pdhi=0.014,
    wdhi1=0.0, wdhi2=600.0, wdhi3=1200.0, wdhi4=3200.0,
    sncs=0.005, mc=14.0,
    heat=1, tp2h=31.0, tch=40.0, tp1f=0.0, tbf=-5.0, rfmax=0.3,
)

LAT = 36.85
PDEN = 386.0
PYEAR = 2005
SIMDOY = 340
PDOY = 348


def main() -> None:
    weather_df = load_weather(REPO_ROOT / "data" / "weather" / "gorgan.csv")

    daily = run_potential_production(
        weather_df=weather_df,
        lat=LAT,
        pyear=PYEAR,
        simdoy=SIMDOY,
        pdoy=PDOY,
        crop_type="WHEAT",
        phenology_params=phenology_params,
        lai_params=lai_params,
        dm_production_params=dm_production_params,
        dm_distribution_params=dm_distribution_params,
        pden=PDEN,
    )

    last = daily.iloc[-1]
    print(f"Simulated {len(daily)} days, DAP {daily['dap'].min()}-{daily['dap'].max()}")
    print(f"Final: CBD={last['cbd']:.1f}, LAI={daily['lai'].max():.2f} (max), "
          f"WTOP={last['wtop']:.1f}, WGRN={last['wgrn']:.1f}, "
          f"HI={last['hi']:.3f}, matured={last['mat'] == 1} (matyp={last['matyp']})")

    fig, axes = plt.subplots(4, 1, figsize=(9, 11), sharex=True)

    axes[0].plot(daily["dap"], daily["cbd"], label="CBD")
    axes[0].set_ylabel("Biological days (CBD)")
    axes[0].legend()

    axes[1].plot(daily["dap"], daily["lai"], color="green")
    axes[1].set_ylabel("LAI (m² m⁻²)")

    axes[2].plot(daily["dap"], daily["wlf"], label="Leaf")
    axes[2].plot(daily["dap"], daily["wst"], label="Stem")
    axes[2].plot(daily["dap"], daily["wgrn"], label="Grain")
    axes[2].plot(daily["dap"], daily["wtop"], label="Total",
                linestyle="--", color="black")
    axes[2].set_ylabel("Dry matter (g m⁻²)")
    axes[2].legend()

    axes[3].plot(daily["dap"], daily["ddmp"], label="DDMP", color="orange")
    axes[3].set_ylabel("Daily DM production\n(g m⁻² d⁻¹)")
    axes[3].set_xlabel("Days after sowing (DAP)")
    axes[3].legend()

    fig.suptitle("Wheat 'Zagros' @ Gorgan, sown DOY 348 2005 — potential production")
    fig.tight_layout()

    out_path = REPO_ROOT / "scripts" / "output" / "wheat_gorgan_potential.png"
    out_path.parent.mkdir(exist_ok=True)
    fig.savefig(out_path, dpi=120)
    print(f"Saved plot to {out_path}")


if __name__ == "__main__":
    main()
