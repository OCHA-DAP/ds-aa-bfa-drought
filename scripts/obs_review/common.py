"""Shared inputs for the observational-trigger review of the 17 provinces of the old
Boucle du Mouhoun, Nord, Centre-Nord and Sahel regions (scripts/obs_review/)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OLD_REGIONS = ["Boucle du Mouhoun", "Nord", "Centre-Nord", "Sahel"]
EVAL_YEARS = list(range(2001, 2026))  # complete seasons scored; 2026 reported separately


def load_json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


ASAP = load_json("pages/asap-explorer/data.json")
TEMP = load_json("pages/temperature-explorer/data.json")
PROVINCES = [p for p in TEMP["provinces"] if p["region"] in OLD_REGIONS]
assert len(PROVINCES) == 17, len(PROVINCES)
PIDS = [str(p["id"]) for p in PROVINCES]
NAMES = {str(p["id"]): p["name"] for p in PROVINCES}

IMPACT_MAIN = set(TEMP["meta"]["impact_seasons_main"])  # 2011, 2013, 2017, 2019, 2021
IMPACT_ALT = set(TEMP["meta"]["impact_seasons_alt"])  # 2011, 2014, 2017, 2019, 2022
SCORE_MAIN = range(TEMP["meta"]["impact_record_years"]["main"][0], TEMP["meta"]["impact_record_years"]["main"][1] + 1)
SCORE_ALT = range(TEMP["meta"]["impact_record_years"]["alt"][0], TEMP["meta"]["impact_record_years"]["alt"][1] + 1)


def province_yield_anom() -> pd.DataFrame:
    """FDW rainfed millet+sorghum yield, % from each province's Theil-Sen trend (2001-2023);
    rows = year, columns = province id (17 AOI provinces)."""
    y = TEMP["yield"]
    df = pd.DataFrame({pid: y["province"][pid]["anom"] for pid in PIDS if pid in y["province"]}, index=y["years"])
    return df.astype(float)


def national_yield_anom(start: int = 2001) -> pd.Series:
    """FAOSTAT national millet+sorghum yield anomaly (%). From 2001 the ASAP explorer series
    (trend 2001-2023); from 1989 the temperature explorer series (trend 1989-2023)."""
    if start >= 2001:
        n = ASAP["yield"]
        return pd.Series(n["national"]["anom"], index=n["years"], dtype=float)
    n = TEMP["yield"]
    return pd.Series(n["national"]["anom"], index=n["national_years"], dtype=float)


def temperature() -> tuple[np.ndarray, list[int], list[int]]:
    """Dekadal crop temperature (degC), array [province, year, dekad] for the 17 provinces."""
    years, dks = TEMP["meta"]["years"], TEMP["meta"]["dekads"]
    arr = np.array([np.array(TEMP["temp"][pid], dtype=float).reshape(len(years), len(dks)) / 1000 for pid in PIDS])
    return arr, years, dks


def weibull_rp(n_years: int, n_act: int) -> float | None:
    return (n_years + 1) / n_act if n_act else None


def score(act_years: set, aoi_yield: pd.Series, nat_yield: pd.Series) -> dict:
    """Hits on impact seasons (each dating scored on its own record years) and yield anomalies."""
    main = [y for y in SCORE_MAIN if y in act_years]
    alt = [y for y in SCORE_ALT if y in act_years]
    yrs_y = [y for y in aoi_yield.index if y in EVAL_YEARS]
    act_y = [y for y in yrs_y if y in act_years]
    oth_y = [y for y in yrs_y if y not in act_years]
    return {
        "hits_main": sorted(set(main) & IMPACT_MAIN), "n_impact_main": len(IMPACT_MAIN),
        "false_main": sorted(set(main) - IMPACT_MAIN),
        "hits_alt": sorted(set(alt) & IMPACT_ALT), "n_impact_alt": len(IMPACT_ALT),
        "aoi_yield_act": round(float(aoi_yield.loc[act_y].mean()), 1) if act_y else None,
        "aoi_yield_other": round(float(aoi_yield.loc[oth_y].mean()), 1) if oth_y else None,
        "nat_yield_act": round(float(nat_yield.reindex(act_y).mean()), 1) if act_y else None,
        "nat_yield_other": round(float(nat_yield.reindex(oth_y).mean()), 1) if oth_y else None,
        "n_act_with_yield": len(act_y),
    }
