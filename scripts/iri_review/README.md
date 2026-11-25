# IRI forecast trigger review (Nov 2026)

Backtest of IRI's NextGen July–September rainfall forecast (FbF Maproom, `burkinafaso`) as a
trigger for the former Boucle du Mouhoun, Nord, Centre-Nord and Sahel regions, with thresholds
set from earlier seasons only; comparison with ECMWF SEAS5; overall return period with the
observational options in `../obs_review/`. Results are on the restricted page
`/trigger-review-2027/`, in English and French (one encrypted page with a language switch).

IRI shared its candidate table with us; it is not public. The settings taken from it live in
`config.local.json`, and the page generator in `page/`; both are gitignored. Copies are kept on
the dev blob under `pa-aa-bfa-drought/raw/iri_partner/`.

## Data

On the team's dev blob (`projects` container), never in the repo:

```bash
export BFA_DATA_DIR=$(uv run --no-project --with ocha-stratus python scripts/iri_review/blob_data.py pull)
# ... run scripts ...
uv run --no-project --with ocha-stratus python scripts/iri_review/blob_data.py push
rm -rf "$BFA_DATA_DIR"
```

## Run order

From `scripts/iri_review/`, with `BFA_DATA_DIR` set and
`uv run --no-project --with pandas --with scipy --with pyarrow --with openpyxl python <script>`:

| script | what it does |
|---|---|
| `fetch_maproom.py` | Maproom export API: forecasts v1/v4/v5 × issue month × severity for the nation and the six 2026 regions; CHIRPS series; bad-year lists |
| `fetch_db.py` | SEAS5 and ERA5 for the area from the team prod DB (read-only; needs the DB tunnel and `--with ocha-stratus --with psycopg2-binary`) |
| `reproduce.py <table.xlsx>` | searches Maproom configurations for the one behind IRI's table |
| `backtest.py` | thresholds from the whole record, the previous 10 seasons, or all earlier seasons; leakage test |
| `skill.py` | rank correlation, ROC AUC and hits for IRI and SEAS5 against CHIRPS and ERA5 |
| `compare.py` | IRI and SEAS5 through the same rule at ~1-in-6 years |
| `checks.py <obs_by_year.csv>` | national vs area, forecast level by period, chance probabilities, 2025-framework years |
| `overall.py <obs_by_year.csv>` | forecast OR observational trigger, 2003–2025 |

`compare.py` and `checks.py` also read `iri_review/chirps_aoi_jas.json`: CHIRPS v2/v3 and ERA5
July–September over the area from the 0.5° cubes of ds-precip-intercomparison, with September
2026 read from the CHC monthly COGs.

The area average is the area-weighted mean of the six 2026 regions (`cod/aoi_region_areas.csv`,
COD-AB March 2026). Their outline matches the four former regions exactly.
