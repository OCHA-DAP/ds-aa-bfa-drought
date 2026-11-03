"""Build the data file for the ASAP warning explorer (pages/asap-explorer/data.json).

Inputs (downloaded by hand, never committed):
  1. The JRC ASAP admin-2 warning archive, warnings_l2_ts.zip
       curl -sL -o warnings_l2_ts.zip \
         https://agricultural-production-hotspots.ec.europa.eu/files/warnings_l2_ts.zip
     (~56 MB; the server can be slow. Do not resume a partial download with `curl -C -`:
     it produces a corrupt archive.)
  2. FEWS NET Data Warehouse crop production for Burkina Faso (official agricultural
     statistics by province, public, no login):
       curl -sL -o bf_crop.csv \
         "https://fdw.fews.net/api/cropproductionindicatorvalue.csv?country_code=BF"
  3. FAOSTAT crops and livestock production for Burkina Faso, from HDX
     (dataset bfa-faostat-crops-livestock-production):
       curl -sL -o bfa_faostat.csv "https://data.humdata.org/dataset/739c3a73-1747-47bf-89bf-31de84df82d2/resource/8f1ef403-423d-4088-9175-c55a8c3c3e1a/download/bfa_faostat_crops_livestock_products.csv"

Usage:
  uv run --with pandas python scripts/asap_explorer/build_data.py \
      warnings_l2_ts.zip bf_crop.csv bfa_faostat.csv pages/asap-explorer/data.json

What goes into data.json:
  - provinces: the 45 ASAP admin-2 units (the provinces in place before the 2025 territorial
    reform), ordered by region from north to south.
  - warnings: per province, two strings (cropland, rangeland) of len(years) * 36 characters,
    one character per dekad, encoding the ASAP warning code (see CODE_CHARS). "." = no data
    (before the archive starts in May 2001 or after its last dekad).
  - yield: millet + sorghum, 2001-2023, with the percentage departure from each series' own
    2001-2023 trend (Theil-Sen).
      national: FAOSTAT (production / area harvested), official figures only (flag "A");
        FAOSTAT 2024 is imputed (millet) or unofficial (sorghum) and is left out.
      province: FEWS NET Data Warehouse, rainfed millet + sorghum + red sorghum, production /
        area planted. Summing the provinces does not give a usable national series: white
        sorghum is missing for Bam, Namentenga and Sanmatenga in 2008 and red sorghum is
        reported as zero in about 20 provinces in 2012. Province-years without both millet and
        (white or total) sorghum are left empty; zero production or area counts as missing.
        Red sorghum is reported separately in 2001 and from 2008 (in 2002-2007 "Sorghum" is the
        total), and only in some years for some northern provinces.
  - impacts: the drought impact records and their dating to growing seasons, copied from
    scripts/impact_analysis.py (the heat-and-impact page) so both pages use the same record;
    label_fr / recorded_fr are the French versions shown when the page is in French.
"""

import io
import json
import re
import sys
import unicodedata
import zipfile
from datetime import date

import numpy as np
import pandas as pd

ASAP0_ID_BFA = 17  # ASAP's own country id for Burkina Faso in the Nov 2026 archive (was 219 before)
YEARS = list(range(2001, 2027))
YIELD_YEARS = list(range(2001, 2024))  # FEWS NET ends 2023; FAOSTAT official figures end 2023

# ASAP warning codes seen in the archive -> one character each.
CODE_CHARS = {
    0: "a",  # no warning
    2: "b",  # level 1, WSI
    3: "c",  # level 1, SPI-3
    4: "d",  # level 1+, WSI and SPI-3
    5: "e",  # level 2, biomass (zNDVIc)
    6: "f",  # level 3, biomass and WSI
    7: "g",  # level 3, biomass and SPI-3
    8: "h",  # level 3+, biomass, SPI-3 and WSI
    9: "i",  # level 4, end-of-season biomass
    10: "j",  # no warning, exceptional (positive) conditions
    12: "k",  # level 1 (WSI) with exceptional conditions
    13: "l",  # level 1 (SPI-3) with exceptional conditions
    14: "m",  # level 1+ with exceptional conditions
    15: "n",  # level 2 with exceptional conditions
    16: "o",  # level 3 (biomass and WSI) with exceptional conditions
    17: "p",  # level 3 (biomass and SPI-3) with exceptional conditions
    18: "q",  # level 3+ with exceptional conditions
    20: "r",  # successful season
    98: "s",  # off season
    99: "t",  # insufficient cropland/rangeland area
}

# The 13 pre-reform regions, roughly north to south, for display order.
REGION_ORDER = [
    "Sahel", "Nord", "Centre-Nord", "Est", "Boucle Mouhoun", "Plateau-Central", "Centre",
    "Centre-Est", "Centre-Ouest", "Centre-Sud", "Hauts-Bassins", "Sud-Ouest", "Cascades",
]
REGION_LABEL = {"Boucle Mouhoun": "Boucle du Mouhoun"}

# FEWS NET spellings that differ from ASAP's after accent stripping.
FDW_ALIASES = {"komondjari": "komandjari", "kouritenga": "kourittenga"}

# Impact records: the dating table of scripts/impact_analysis.py (heat-and-impact page).
# season_main = growing season the record is attributed to on the evidence;
# season_alt = the season under the framework's own labelling (the year recorded).
IMPACTS = [
    {"source": "EM-DAT", "id": "2011-9524", "label_fr": "EM-DAT : sécheresse, 2.85 millions de personnes affectées (Sahel, Centre-Nord, Est, Centre-Ouest, Centre-Est)", "recorded_fr": "déc. 2011 – 2012", "label": "EM-DAT drought, 2.85M affected (Sahel, Centre-Nord, Est, Centre-Ouest, Centre-Est)",
     "short": "EM-DAT 2.85M", "recorded": "Dec 2011 – 2012", "season_main": 2011, "season_alt": 2011},
    {"source": "CERF", "id": "12-RR-BFA-13236", "label_fr": "CERF réponse rapide, sécheresse, $9.2M", "recorded_fr": "2012", "label": "CERF rapid response, drought, $9.2M",
     "short": "CERF $9.2M", "recorded": "2012", "season_main": 2011, "season_alt": 2011},
    {"source": "EM-DAT", "id": "2014-9196", "label_fr": "EM-DAT : sécheresse, 4.0 millions de personnes affectées (Sahel)", "recorded_fr": "mai 2014", "label": "EM-DAT drought, 4.0M affected (Sahel)",
     "short": "EM-DAT 4.0M", "recorded": "May 2014", "season_main": 2013, "season_alt": 2014},
    {"source": "CERF", "id": "14-UFE-BFA-10955", "label_fr": "CERF urgences sous-financées, sécheresse, $3.9M", "recorded_fr": "août 2014", "label": "CERF underfunded emergencies, drought, $3.9M",
     "short": "CERF $3.9M", "recorded": "Aug 2014", "season_main": 2013, "season_alt": 2014},
    {"source": "CERF", "id": "18-RR-BFA-30726", "label_fr": "CERF réponse rapide, sécheresse et crise pastorale, $9.0M", "recorded_fr": "mai 2018", "label": "CERF rapid response, drought and pastoral crisis, $9.0M",
     "short": "CERF $9.0M", "recorded": "May 2018", "season_main": 2017, "season_alt": 2017},
    {"source": "EM-DAT", "id": "2020-9235", "label_fr": "EM-DAT : sécheresse, 2.9 millions de personnes affectées (toutes les régions)", "recorded_fr": "janv. – juin 2020", "label": "EM-DAT drought, 2.9M affected (all regions)",
     "short": "EM-DAT 2.9M", "recorded": "Jan – Jun 2020", "season_main": 2019, "season_alt": 2019},
    {"source": "EM-DAT", "id": "2022-9781", "label_fr": "EM-DAT : sécheresse, 3.5 millions de personnes affectées", "recorded_fr": "jusqu’à nov. 2022", "label": "EM-DAT drought, 3.5M affected",
     "short": "EM-DAT 3.5M", "recorded": "to Nov 2022", "season_main": 2021, "season_alt": 2022},
    {"source": "CERF", "id": "22-RR-BFA-53665", "label_fr": "CERF réponse rapide, insécurité alimentaire (période de soudure), $6.0M", "recorded_fr": "mai 2022", "label": "CERF rapid response, food insecurity (lean season), $6.0M",
     "short": "CERF $6.0M", "recorded": "May 2022", "season_main": 2021, "season_alt": 2022},
]
FRAMEWORK_YEARS = [2011, 2014, 2017, 2019, 2022]  # target years of the 2026 trigger analysis
IMPACT_SEASONS_MAIN = [2011, 2013, 2017, 2019, 2021]
IMPACT_SEASONS_ALT = [2011, 2014, 2017, 2019, 2022]
# Seasons the impact record can speak to. The EM-DAT and CERF records run to 2024; a failed
# 2024 season would be recorded in the 2025 lean season, so with the growing-season dating
# the last season that can be scored is 2023.
IMPACT_RECORD_YEARS = {"main": [2001, 2023], "alt": [2001, 2024]}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z]", "", s)
    return FDW_ALIASES.get(s, s)


def dekad_of(d: pd.Series) -> pd.Series:
    return (d.dt.month - 1) * 3 + np.minimum((d.dt.day - 1) // 10, 2) + 1


def load_asap(zip_path: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        chunks = []
        with z.open(csv_name) as f:
            for chunk in pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), sep=";", chunksize=500_000):
                chunks.append(chunk[chunk["asap0_id"] == ASAP0_ID_BFA])
    df = pd.concat(chunks, ignore_index=True)
    if df.empty or (df["asap0_name"] != "Burkina Faso").any():
        raise SystemExit(f"asap0_id {ASAP0_ID_BFA} is not (only) Burkina Faso in this archive: ids have changed again")
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["dekad"] = dekad_of(df["date"])
    unknown = set(df["w_crop"]) | set(df["w_range"])
    unknown -= set(CODE_CHARS)
    if unknown:
        raise SystemExit(f"unknown ASAP warning codes {sorted(unknown)}: extend CODE_CHARS")
    return df


def encode_warnings(df: pd.DataFrame, provinces: list[dict]) -> dict:
    out = {}
    for p in provinces:
        g = df[df["asap2_id"] == p["id"]].set_index(["year", "dekad"])
        if g.index.duplicated().any():
            raise SystemExit(f"duplicate dekads for {p['name']}")
        enc = {}
        for col, key in (("w_crop", "c"), ("w_range", "r")):
            chars = []
            for y in YEARS:
                for dk in range(1, 37):
                    v = g[col].get((y, dk))
                    chars.append("." if v is None or pd.isna(v) else CODE_CHARS[int(v)])
            enc[key] = "".join(chars)
        out[str(p["id"])] = enc
    return out


def trend_anomaly(years: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Percentage departure from the series' own linear trend.

    Theil-Sen (median of pairwise slopes, intercept through the medians) rather than least
    squares, because the province statistics contain isolated implausible values (e.g. Houet
    2014 at 3.8 t/ha) that would otherwise tilt the trend for every other year.
    """
    ok = ~np.isnan(values)
    if ok.sum() < 10:
        return np.full_like(values, np.nan)
    x, y = years[ok], values[ok]
    i, j = np.triu_indices(len(x), k=1)
    slope = np.median((y[j] - y[i]) / (x[j] - x[i]))
    intercept = np.median(y - slope * x)
    fit = intercept + slope * years
    return (values - fit) / fit * 100


def rounded(values, digits=0):
    return [None if np.isnan(v) else (round(v) if digits == 0 else round(v, digits)) for v in values]


def load_national_yield(fao_path: str, years: list[int] | None = None) -> dict:
    f = pd.read_csv(fao_path, dtype=str)
    f = f[f["Iso3"] == "BFA"]
    f = f[f["Item"].isin(["Millet", "Sorghum"]) & f["Element"].isin(["Production", "Area harvested"])].copy()
    f["Year"] = f["Year"].astype(int)
    f["Value"] = f["Value"].astype(float)
    years = years or YIELD_YEARS
    f = f[f["Year"].isin(years)]
    if (f["Flag"] != "A").any():
        bad = f[f["Flag"] != "A"][["Item", "Element", "Year", "Flag"]].to_dict("records")
        raise SystemExit(f"FAOSTAT values in {years[0]}-{years[-1]} that are not official: {bad}")
    t = f.pivot_table(index="Year", columns="Element", values="Value", aggfunc="sum").reindex(years)
    if t.isna().any().any() or (f.groupby(["Year", "Element"]).size() != 2).any():
        raise SystemExit("FAOSTAT millet/sorghum production or area missing for some year")
    yrs = np.array(years, dtype=float)
    prod, area = t["Production"].to_numpy(dtype=float), t["Area harvested"].to_numpy(dtype=float)
    ny = prod / area * 1000  # t/ha -> kg/ha
    return {
        "kg_ha": rounded(ny),
        "anom": rounded(trend_anomaly(yrs, ny), 1),
        "prod_kt": rounded(prod / 1000),
        "prod_anom": rounded(trend_anomaly(yrs, prod), 1),
    }


def load_yield(fdw_path: str, fao_path: str, provinces: list[dict]) -> dict:
    d = pd.read_csv(fdw_path, low_memory=False, encoding="utf-8-sig")
    d = d[d["value"].notna() & (d["value"] > 0) & d["admin_2"].notna() & d["admin_3"].isna()].copy()
    d["year"] = pd.to_datetime(d["period_date"]).dt.year
    d = d[
        d["product"].isin(["Millet", "Sorghum", "Sorghum (Red)"])
        & d["indicator"].isin(["Quantity Produced", "Area Planted"])
        & (d["crop_production_system"] == "Rainfed (PS)")
        & d["year"].isin(YIELD_YEARS)
    ]
    d["key"] = d["admin_2"].map(norm)
    if d.duplicated(["key", "year", "product", "indicator"]).any():
        raise SystemExit("duplicate FEWS NET rows for a province, year, product and indicator")
    # a product counts for a province-year only with both production and area
    both = d.groupby(["key", "year", "product"])["indicator"].transform("nunique") == 2
    d = d[both]
    have = d.groupby(["key", "year"])["product"].agg(set)
    complete = have.apply(lambda s: "Millet" in s and "Sorghum" in s)
    t = d.pivot_table(index=["key", "year"], columns="indicator", values="value", aggfunc="sum")
    t = t.rename(columns={"Area Planted": "area", "Quantity Produced": "prod"})
    t.loc[~complete.reindex(t.index, fill_value=False), ["area", "prod"]] = np.nan

    asap_keys = {norm(p["name"]): p for p in provinces}
    fdw_keys = set(t.index.get_level_values("key"))
    if fdw_keys != set(asap_keys):
        raise SystemExit(f"province crosswalk failed: only FEWS NET {sorted(fdw_keys - set(asap_keys))}, "
                         f"only ASAP {sorted(set(asap_keys) - fdw_keys)}")

    yrs = np.array(YIELD_YEARS, dtype=float)
    prov_out, gaps = {}, []
    for key, p in asap_keys.items():
        g = t.loc[key].reindex(YIELD_YEARS)
        y = (g["prod"] / g["area"]).to_numpy(dtype=float) * 1000  # t/ha -> kg/ha
        gaps += [f"{p['name']} {yr}" for yr, v in zip(YIELD_YEARS, y) if np.isnan(v)]
        if np.isnan(y).sum() > 3:
            raise SystemExit(f"more than 3 missing yield years for {p['name']}")
        prov_out[str(p["id"])] = {"kg_ha": rounded(y), "anom": rounded(trend_anomaly(yrs, y), 1)}
    print(f"province-years without complete millet and sorghum statistics ({len(gaps)}): {', '.join(gaps)}")
    return {"years": YIELD_YEARS, "national": load_national_yield(fao_path), "province": prov_out}


def main(zip_path: str, fdw_path: str, fao_path: str, out_path: str) -> None:
    df = load_asap(zip_path)
    units = df[["asap1_name", "asap2_id", "asap2_name"]].drop_duplicates()
    if len(units) != 45 or units["asap2_id"].duplicated().any():
        raise SystemExit(f"expected 45 provinces, got {len(units)}")
    if set(units["asap1_name"]) != set(REGION_ORDER):
        raise SystemExit(f"region names changed: {sorted(set(units['asap1_name']) ^ set(REGION_ORDER))}")
    units["r"] = units["asap1_name"].map(REGION_ORDER.index)
    units = units.sort_values(["r", "asap2_name"])
    provinces = [
        {"id": int(u.asap2_id), "name": u.asap2_name, "region": REGION_LABEL.get(u.asap1_name, u.asap1_name)}
        for u in units.itertuples()
    ]
    first, last = df["date"].min(), df["date"].max()
    data = {
        "meta": {
            "built": date.today().isoformat(),
            "asap_first_dekad": first.date().isoformat(),
            "asap_last_dekad": last.date().isoformat(),
            "years": YEARS,
            "code_chars": {ch: code for code, ch in CODE_CHARS.items()},
            "framework_years": FRAMEWORK_YEARS,
            "impact_seasons_main": IMPACT_SEASONS_MAIN,
            "impact_seasons_alt": IMPACT_SEASONS_ALT,
            "impact_record_years": IMPACT_RECORD_YEARS,
        },
        "provinces": provinces,
        "warnings": encode_warnings(df, provinces),
        "yield": load_yield(fdw_path, fao_path, provinces),
        "impacts": IMPACTS,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out_path}: {len(provinces)} provinces, ASAP {first.date()} to {last.date()}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
