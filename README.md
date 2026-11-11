# ssm-icrop

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23983023.svg)](https://doi.org/10.5281/zenodo.23983023)

A Python port of **SSM-iCrop**, a simple daily crop simulation model for wheat,
maize and grain legumes (soybean, chickpea and others), from its original
Excel/VBA implementation.

The goal is a faithful, tested port: the Python code reproduces the VBA model's
behaviour day by day, and is verified against output produced by the original
workbook: the *reference output*, also called the golden master, which is the
recorded output of the original program that the port has to reproduce.

> **Status: work in progress.** The daily model is ported: potential
> production, the soil water balance and the nitrogen balance match the
> reference output on every day of the reference season, in all four reference
> scenarios. The rule-based sowing dates and the seasonal summary output are
> not yet ported.

## The original model

SSM-iCrop is developed by Afshin Soltani. The SSM model is described in:

> Soltani, A., Maddah, V. & Sinclair, T. R. (2013). SSM-Wheat: a simulation
> model for wheat development, growth and yield. *International Journal of
> Plant Production* 7(4), 711–740.
> [doi:10.22069/ijpp.2013.1266](https://doi.org/10.22069/ijpp.2013.1266)

The model, its user manuals (wheat, chickpea) and the example weather data are
available from the **[SSM crop models site](https://sites.google.com/view/ssm-crop-models/home)**.
The manuals are the authoritative description of the model and the best place to
start if you are new to it.

## Port status

| Model section | Status |
|---|---|
| Weather | ported, verified² |
| Phenology: wheat | ported, verified¹ |
| Phenology: maize, grain legumes | ported, unit tests only |
| Leaf area, without and with N limitation | ported, verified |
| Dry-matter production | ported, verified (daily VPD method only) |
| Dry-matter distribution and yield formation | ported, verified |
| Soil water balance | ported, verified for rainfed, auto-irrigated and DAP-scheduled irrigation; other schedules unit tests only |
| Sowing date: fixed date | ported, verified |
| Sowing date: rule-based algorithms | not yet ported |
| Plant nitrogen, soil nitrogen | ported, verified for wheat; legume N fixation unit tests only |
| Seasonal summary output | not yet ported |

¹ Except the seasonal weather sums that appear only in the summary output.
² Except snow, which never occurs in the reference season, and the
climate-change adjustments of temperature and rainfall, which the reference
scenarios do not use. Both are covered by unit tests only.

"Verified" means an exact match, within floating-point tolerance, against the
daily output of the original VBA model, and only for the code paths the
reference scenarios run: one wheat cultivar, one location, one soil, one
season. "Unit tests only" means each function is tested in isolation with
hand-written inputs, which shows the code does what its author read in the VBA
but not that the reading was right. [docs/verification.md](docs/verification.md)
lists per process what is verified and what is not.

## Installation

Requires Python 3.11 or later.

```bash
git clone https://github.com/wolfgang-boku/ssm-icrop.git
cd ssm-icrop
uv sync --extra dev
source .venv/bin/activate
```

[uv](https://docs.astral.sh/uv/) installs the exact package versions recorded
in `uv.lock`, the same ones CI tests against. Without uv, pip works too, with
whatever versions it resolves:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

Scenarios are described in YAML: a location with its weather file, management
(sowing date, density, water and nitrogen mode) and a crop parameter file.

```python
from ssm_icrop.inputs import load_scenario
from ssm_icrop.model import run_simulation

result = run_simulation(load_scenario("configs/example/gorgan_wheat_potential.yaml"))
print(result.daily[["dap", "cbd", "lai", "wtop", "wgrn"]].tail())
```

`result.daily` holds one row per simulated day, `result.summary` one row per season.

Simulation modes follow the original model:

| `water` | Meaning |
|---|---|
| 0 | no water balance (potential production) |
| 1 | automatic irrigation when root-zone water falls below a threshold |
| 2 | rainfed |
| 3 | scheduled irrigation |

`nitrogen` is 0 (no N balance) or 2 (full N balance). Combinations that need
modules not yet ported raise `NotImplementedError` rather than running an
incomplete model.

## Repository layout

```
src/ssm_icrop/      the model, one module per section of the original VBA code
configs/crops/      crop parameters, extracted from the 2022 source workbook
configs/soils/      soil parameters, extracted from the 2022 source workbook
configs/example/    example scenarios
data/weather/       example daily weather (Gorgan, Isfahan, Tabriz; Iran)
data/verification/  reference output (golden master), one directory per model version
docs/               verification method, variable reference, model version notes
scripts/            parameter extraction, verification report, plotting
tests/              unit tests and the verification against the reference output
iCrop.vba           VBA source of the original model, for reference
SSM-iCrop/          2022 source workbook, its verification workbook, 2026 source workbook
```

## How the port is built

- **The VBA is the authority.** Where the original contains a bug, the port
  reproduces it, isolated in its own function and documented with the VBA line
  and the reasoning. A silent correction would make the port disagree with the
  model it claims to reproduce.
- **Every formula is traceable.** Comments cite the `iCrop.vba` line they port.
- **Parameters come from the workbook.** `scripts/extract_crop_params.py` and
  `scripts/extract_soil_params.py` read crop and soil parameters straight from
  the 2022 source workbook into YAML instead of transcribing them by hand:

  ```bash
  python scripts/extract_crop_params.py --list
  python scripts/extract_crop_params.py --column D -o configs/crops/wheat.yaml
  python scripts/extract_soil_params.py --list
  python scripts/extract_soil_params.py --row 24 -o configs/soils/danesh.yaml
  ```

- **Verification is against the original program's output**, not only against
  unit tests: the same inputs go into the VBA model and the port, and every
  daily output column is compared (back-to-back testing). This is verification,
  not validation: the port is checked against the VBA model, not against field
  observations.

Development is AI-assisted with [Claude Code](https://claude.com/claude-code).
`CLAUDE.md` and `.claude/` hold the project conventions, the porting workflow and
a fidelity-review agent that checks each ported module against the VBA source.

## Development

```bash
pytest                                  # all tests
pytest tests/test_verification.py       # verification against the reference output only
python scripts/compare_verification.py  # column-by-column verification report
ruff check src/ tests/ scripts/         # lint (enforced in CI)
```

Branching, commit messages and pull requests follow
[CONTRIBUTING.md](CONTRIBUTING.md).

## Citation

If you use this port, please cite the SSM-Wheat paper (Soltani et al., 2013,
see [The original model](#the-original-model)) as well as the port itself.
[CITATION.cff](CITATION.cff) lists these and further references; GitHub's
"Cite this repository" button formats them. Changes between releases
are recorded in [CHANGELOG.md](CHANGELOG.md).

## License

The Python code in this repository is released under the [MIT License](LICENSE).

The original SSM-iCrop model (`iCrop.vba`, the workbooks in `SSM-iCrop/`) and
the example weather data remain the work of their respective authors. They are
included as the source of the port and for its verification, and are not
covered by this repository's license. The port and its publication here are
made with the permission of the model's author, Afshin Soltani (Gorgan
University of Agricultural Sciences and Natural Resources).
