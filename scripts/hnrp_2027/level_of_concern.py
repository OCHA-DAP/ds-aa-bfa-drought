"""Level of concern 2026 per province (High / Moderate / Low) for the HPC 2027 analysis.

Scoring proposed by OCHA Burkina Faso (20 Oct 2026): three signals, each scored 0-2, added.
  (a) vegetation hazard, 2026 season ONLY (their 20 Oct version used the worst of 2024-2026,
      which carried 2024 deficits into a 2026-season rank): category E/TE or corroborated M = 2,
      uncorroborated M (the two satellite products diverge) = 1, F = 0. Dekad 26 (to 20 Sep):
      the category thresholds are fitted on dekad-26 history.
  (b) rainfall and heat to 20 Sep: SPI-3 <= -1 -> 1; Jul-mid-Sep temperature >= +1 C -> 1
      (spi3_2026 / temp_anom_2026 from consolidate.py, i.e. the ASAP values at the time of the run).
  (c) pasture / water deficit, regional, as coded by OCHA Burkina Faso from AGRHYMET (8 Sep),
      ANAM (Aug) and DGRE (10 Sep): severe = 2, deficit = 1, slight / normal = 0.
Total 4-6 = High, 2-3 = Moderate, 0-1 = Low.
Sensitivity: the same score with (b) taken one dekad later (SPI-3 and temperature to 30 Sep), i.e.
counting the late-September rain. Treat it as provisional: ASAP revises recent dekads (the mid-September
2026 SPI-3 moved by up to 0.44 between the 29 Sep and 21 Oct downloads).

Inputs in <workdir>: provinces.csv, by_year.csv (consolidate.py), xwalk_new_old_overlay.csv,
asap/{spi3_crop,spi3_range,temp_crop}.csv (prepare_inputs.py), and ocha_bfa_2026-10-20.csv
(adm2_pcode, level_ocha_bfa, pasture_water, a_ocha_bfa, b_ocha_bfa, spi3_29sep, temp_anom_29sep,
dry_29sep, hot_29sep -- their own flags; the values are rounded to 2 dp in their sheet) extracted from the OCHA BFA workbook -- kept on the blob with the other work files, not in this repo.

Usage: level_of_concern.py <workdir>  ->  level_of_concern.csv
"""

import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

WORK = Path(sys.argv[1])
DEKAD, LATE_DEKAD = 26, 27  # 11-20 Sep (as consolidate.py) / 21-30 Sep
ALIAS = {"bulkiemde": "boulkiemde", "kouritenga": "kourittenga", "komondjari": "komandjari",
         "koosin": "kossin", "lorum": "loroum"}
PASTURE = {"severe": 2, "deficit": 1, "slight": 0, "normal": 0}


def k2(s):
    k = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    k = re.sub(r"[^a-z0-9]+", "", k)
    return ALIAS.get(k, k)


P = pd.read_csv(WORK / "provinces.csv").set_index("adm2_pcode")
BY = pd.read_csv(WORK / "by_year.csv")
xw = pd.read_csv(WORK / "xwalk_new_old_overlay.csv")
old_by_key = {k2(n): p for n, p in zip(xw.ADM2_FR, xw.ADM2_PCODE)}
new_of_old = xw.groupby("adm2_pco_1").adm2_pcode.apply(list).to_dict()


def asap(name):
    d = pd.read_csv(WORK / "asap" / f"{name}.csv", dtype={"date": str})
    d["date"] = pd.to_datetime(d["date"], format="%Y%m%d")
    d["year"] = d.date.dt.year
    d["dekad"] = (d.date.dt.month - 1) * 3 + np.minimum((d.date.dt.day - 1) // 10, 2) + 1
    d["old_pcode"] = d.region_name.map(k2).map(old_by_key)
    assert d.old_pcode.notna().all(), d[d.old_pcode.isna()].region_name.unique()
    d.loc[d.value <= -999, "value"] = np.nan
    return d


def to_new(s):
    """Series on pre-reform p-codes -> Series on the 47 post-reform provinces (splits inherit)."""
    return pd.Series({n: v for o, v in s.items() for n in new_of_old.get(o, [])}).reindex(P.index)


sp = [asap(f"spi3_{lc}") for lc in ("crop", "range")]
t = asap("temp_crop")
t_clim = t[t.year.between(2001, 2023)]


def rain_heat(dekad):
    spi = to_new(np.fmin(*[d[(d.year == 2026) & (d.dekad == dekad)].set_index("old_pcode").value for d in sp]))
    jul = lambda d: d[d.dekad.between(19, dekad)]  # noqa: E731
    ta = to_new(jul(t[t.year == 2026]).groupby("old_pcode").value.mean()
                - jul(t_clim).groupby(["old_pcode", "year"]).value.mean().groupby("old_pcode").mean())
    return spi, ta


# same export as consolidate.py -> the dekad-26 recomputation must match provinces.csv
spi26, ta26 = rain_heat(DEKAD)
assert np.allclose(spi26, P.spi3_2026) and np.allclose(ta26, P.temp_anom_2026, atol=1e-6)
spi27, ta27 = rain_heat(LATE_DEKAD)

v26 = BY[BY.year == 2026].set_index("adm2_pcode").reindex(P.index)
bfa = pd.read_csv(WORK / "ocha_bfa_2026-10-20.csv").set_index("adm2_pcode").reindex(P.index)
out = P[["adm1_pcode", "adm1_name", "adm2_name"]].copy()
out["veg_cat_2026"] = v26.cat_hazard
out["veg_one_product_2026"] = v26.diverge.astype(bool)
out["spi3_2026"] = P.spi3_2026  # rounded only when written, after the threshold tests
out["temp_anom_2026"] = P.temp_anom_2026
out["pasture_water"] = bfa.pasture_water
out["spi3_to_30sep"] = spi27
out["temp_anom_to_30sep"] = ta27
out["level_ocha_bfa_20oct"] = bfa.level_ocha_bfa
out["a_ocha_bfa_20oct"] = bfa.a_ocha_bfa
out["b_ocha_bfa_20oct"] = bfa.b_ocha_bfa
out["spi3_2026_29sep"] = bfa.spi3_29sep  # the values the 20 Oct sheet used, before ASAP's revision
out["temp_anom_2026_29sep"] = bfa.temp_anom_29sep
out["dry_29sep"] = bfa.dry_29sep
out["hot_29sep"] = bfa.hot_29sep
assert out.notna().all().all(), out[out.isna().any(axis=1)]


def level(score):
    return np.select([score >= 4, score >= 2], ["High", "Moderate"], "Low")


out["a_vegetation"] = np.select(
    [out.veg_cat_2026.isin(["E", "TE"]), (out.veg_cat_2026 == "M") & ~out.veg_one_product_2026,
     out.veg_cat_2026 == "M"], [2, 2, 1], default=0)
out["b_rain_heat"] = (out.spi3_2026 <= -1).astype(int) + (out.temp_anom_2026 >= 1).astype(int)
out["c_pasture_water"] = out.pasture_water.map(PASTURE)
out["score"] = out.a_vegetation + out.b_rain_heat + out.c_pasture_water
out["level_of_concern_2026"] = level(out.score)
b_late = (out.spi3_to_30sep <= -1).astype(int) + (out.temp_anom_to_30sep >= 1).astype(int)
out["score_to_30sep"] = out.a_vegetation + b_late + out.c_pasture_water
out["level_to_30sep"] = level(out.score_to_30sep)
first = ["adm2_pcode", "adm2_name", "adm1_pcode", "adm1_name", "level_of_concern_2026", "score", "a_vegetation",
         "b_rain_heat", "c_pasture_water"]  # what to join on and read, then the inputs
out = out.reset_index().sort_values(["score", "adm2_pcode"], ascending=[False, True])
out = out[first + [c for c in out.columns if c not in first]]
num = ["spi3_2026", "temp_anom_2026", "spi3_to_30sep", "temp_anom_to_30sep"]
out[num] = out[num].round(2)
out.to_csv(WORK / "level_of_concern.csv", index=False)

print(out.level_of_concern_2026.value_counts().to_dict())
print(pd.crosstab(out.level_ocha_bfa_20oct, out.level_of_concern_2026, margins=True))
cols = ["adm2_name", "level_ocha_bfa_20oct", "level_of_concern_2026", "level_to_30sep", "a_vegetation",
        "b_rain_heat", "c_pasture_water", "veg_cat_2026", "spi3_2026", "temp_anom_2026", "spi3_to_30sep"]
print(out[(out.level_ocha_bfa_20oct != out.level_of_concern_2026)
          | (out.level_to_30sep != out.level_of_concern_2026)][cols].to_string(index=False))
