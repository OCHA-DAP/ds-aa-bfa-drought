"""Load the Maproom series and build the AOI average.

AOI = the old Boucle du Mouhoun, Nord, Centre-Nord and Sahel regions = the 2026 regions Bankui,
Sourou, Yaadga, Koulse, Liptako and Soum (same outline: symmetric difference 0 km2 against the
2020 COD-AB). The AOI forecast is the area-weighted mean of the six regional Maproom series
(each is a mean over the region's grid cells, so the weighted mean is the AOI mean up to edge cells).
"""

import os
from pathlib import Path

import pandas as pd

AOI_REGIONS = ["BF62", "BF61", "BF54", "BF49", "BF64", "BF59"]
ISSUE_ORDER = ["jan", "feb", "mar", "apr", "may", "jun"]


def local_config() -> dict:
    """Partner-derived settings (IRI's proposed rule, the published 2025 backtest years) kept out of git."""
    import json

    p = Path(__file__).with_name("config.local.json")
    if not p.exists():
        raise SystemExit(f"{p.name} is missing: it holds the partner-derived settings and is not in git")
    return json.loads(p.read_text())


def data_dir() -> Path:
    d = os.environ.get("BFA_DATA_DIR")
    if not d:
        raise SystemExit("set BFA_DATA_DIR to the folder holding iri_maproom/ and cod/")
    return Path(d)


def weights() -> pd.Series:
    a = pd.read_csv(data_dir() / "cod" / "aoi_region_areas.csv").set_index("adm1_pcode")["km2"]
    return a / a.sum()


def _aoi(df: pd.DataFrame, keys: list[str], value: str) -> pd.DataFrame:
    w = weights()
    x = df[df["region"].isin(AOI_REGIONS)].copy()
    x["w"] = x["region"].map(w)
    x["wv"] = x["w"] * x[value]
    g = x.groupby(keys).agg(wv=("wv", "sum"), w=("w", "sum"), n=("region", "nunique")).reset_index()
    if (g["n"] != len(AOI_REGIONS)).any():
        raise SystemExit("AOI average is missing a region for some rows")
    g[value] = g["wv"] / g["w"]
    g["region"] = "AOI"
    return g[["region"] + keys + [value]]


def forecasts() -> pd.DataFrame:
    """Long table: region (BF, the six AOI regions, AOI), version, issue_month, severity, year, pnep."""
    f = pd.read_csv(data_dir() / "iri_maproom" / "forecasts.csv")
    f = f.dropna(subset=["pne"])
    aoi = _aoi(f, ["version", "issue_month", "severity", "year"], "pne")
    return pd.concat([f, aoi], ignore_index=True).rename(columns={"pne": "pnep"})


def obs() -> pd.DataFrame:
    """Wide by variable: region, year, chirps-precip-jas, ... (AOI = area-weighted mean)."""
    o = pd.read_csv(data_dir() / "iri_maproom" / "obs.csv").dropna(subset=["value"])
    aoi = _aoi(o, ["variable", "year"], "value")
    o = pd.concat([o, aoi], ignore_index=True)
    return o.pivot_table(index=["region", "year"], columns="variable", values="value").reset_index()


def bad_years() -> pd.DataFrame:
    return pd.read_csv(data_dir() / "iri_maproom" / "bad_years.csv")


def maproom_thresholds() -> pd.DataFrame:
    return pd.read_csv(data_dir() / "iri_maproom" / "thresholds.csv")
