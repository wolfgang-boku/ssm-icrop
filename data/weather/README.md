# Weather data

Place CSV weather files here. Format (no header row needed, or use these names):

```
year, doy, srad, tmax, tmin, rain
```

| Column | Unit | Description |
|--------|------|-------------|
| year   | —    | Calendar year |
| doy    | 1–366 | Day of year |
| srad   | MJ m⁻² d⁻¹ | Solar radiation |
| tmax   | °C   | Daily maximum temperature |
| tmin   | °C   | Daily minimum temperature |
| rain   | mm   | Daily precipitation |

The bundled files (`gorgan.csv`, `isfahan.csv`, `tabriz.csv`) are converted from the
example `.xls` weather files distributed with SSM-iCrop on the
[SSM crop models site](https://sites.google.com/view/ssm-crop-models/home).
Convert further files with `pandas.read_excel`; local originals go in
`SSM-iCrop/Weather/` (git-ignored).
