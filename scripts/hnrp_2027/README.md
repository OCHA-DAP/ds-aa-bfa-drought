# HNRP 2027 — drought and flood baseline per province (Burkina Faso)

<!-- markdownlint-disable MD013 -->

Builds the password-protected page `pages/hnrp-2027/` requested by the OCHA Burkina Faso
office for the HPC 2027 shock analysis: province-level (47 provinces, COD-AB v03 = HNRP 2026
p-codes) drought and flood baseline data, bilingual FR/EN, with CSV/XLSX downloads embedded in
the encrypted page. Nothing but the encrypted payload (`pages/hnrp-2027/page.enc`) and the gate
page is published. **The page generator (`gen_page.py`) and its text (`page_template.html`) are
deliberately not in this public repo** — they carry the page's findings in plaintext. They live,
with the work files, research outputs and plaintext build, on the dev blob under
`projects/ds-aa-bfa-drought/hnrp_2027/` (`code/`, `work/`, `research/`, `build/`); copy `code/`
back here (gitignored) to rebuild.

## Design (reviewed)

- **No blended drought index.** Vegetation hazard (GeoSahel biomass + ASAP zFPARc, both detrended,
  scored 0 at p20 / 0.5 at p10 / 1 at p5 of the pooled historical distribution, index = mean,
  categories F < 0.1 ≤ M < 0.5 ≤ E < 0.9 ≤ TE) is shown **beside** FEWS NET phase (bivariate
  headline), because hazard and food-security outcome need not coincide and an additive index would
  attribute any food insecurity to drought.
- **Corroboration rule**: if the biomass and zFPARc scores differ by ≥ 0.5 the category is capped
  at M and flagged (guards against land-cover drift in either product).
- Three drought lenses: recent (worst year 2024–2026), structural (dry years 2001–2025, either
  source < p20), 2026 watch (SPI-3 ≤ −1, Jul–Sep temperature anomaly ≥ +1 °C; unscored).
- **Floods are not ranked.** Satellite/modelled exposure layers (FloodScan, IMERG, JRC flood zones)
  were validated against EM-DAT province lists and did not discriminate; recorded impacts (CONASUR,
  EM-DAT) are shown instead, exposure layers stay in the files flagged "non validé".

## Run order

```bash
W=work                                         # any scratch dir; research/ is expected as its sibling
eval "$(db-tunnel env)"                        # dev DB via the Databricks SSH tunnel
python prepare_inputs.py $W                    # blob, DB, GeoSahel WFS, ASAP export, JRC tiles
python flood_exposure.py $W                    # FloodScan x WorldPop per province, daily May-Nov 1998-2026 (~2 min)
python imerg_extremes.py $W                    # optional: IMERG extremes (evaluation only)
python jrc_flood_zone_pop.py $W                # population in JRC RP10/RP100 river flood zones
python build_drought.py $W                     # biomass, zFPARc, SPI-3, temperature, FEWS NET per year
python build_flood.py $W                       # FloodScan Aug-Oct 5-day peak per year
python build_context.py $W                     # HNRP 2026, CH Mar 2024, EM-DAT, population
python consolidate.py $W                       # scores, categories, per-province + per-region tables
python gen_page.py $W build                    # plaintext page + CSV/XLSX (local only!)
PAGE_PASSWORD=... python encrypt_page.py build/index.html ../../pages/hnrp-2027/page.enc
```

`gen_page.py` also reads `research/documents_fr.json` (curated document list, FR/EN notes) and
`research/conasur_flood_impacts.csv` (flood impacts read from CONASUR/OCHA/IFRC documents) from the
work directory's sibling `research/`; both are archived on the dev blob with the work files.
`gate.html` is the published `pages/hnrp-2027/index.html` (PBKDF2-SHA256 300k + AES-256-GCM,
decrypted in the browser, then `document.write`).

Python env: any env with ocha-stratus, geopandas, rasterio, exactextract, scipy, openpyxl,
cryptography (the `ds-seas5-skill` uv env was used).
