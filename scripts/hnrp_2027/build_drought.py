"""Drought + food-security indicators per BFA province (CODAB v03, 47 units) and year.

Hazard (vegetation):
  - GeoSahel/AGRHYMET biomass (DMP, WA_BIO_ADM2_v4, already on the 47 new provinces):
    cumulative dekads 10-26 (1 Apr - 20 Sep), as % of the 1999-2023 linear trend.
  - JRC ASAP zFPARc (cumulative FPAR z-score, growing-cycle pixels) at dekad 26
    (11-20 Sep), worst of cropland / rangeland, Theil-Sen detrended (fit 2001-2023,
    mean-preserving). Published on the 45 pre-reform provinces -> parent crosswalk.
2026-watch context: ASAP SPI-3 (dekad 26), ASAP Jul-Sep temperature anomaly.
(FAO ASIS ASI was evaluated and dropped: published on the 13 pre-reform regions only.)
Outcome: FEWS NET IPC-compatible area classification -> share of province population
living in units at Phase 3+ and the highest phase, worst CS/ML1 of the rounds published
in each year. Context: last public Cadre Harmonise (Mar 2024 / Jun-Aug 2024).

Usage: build_drought.py <workdir>  ->  drought_by_year.csv, drought_trends.csv, fews_rounds.csv
"""

import re
import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from exactextract import exact_extract
from scipy import stats

WORK = Path(sys.argv[1])
FIT_Y0, FIT_Y1 = 1999, 2023  # biomass trend fit (evaluation window 2024-2026 excluded)
ASAP_FIT = (2001, 2023)
DEKAD = 26  # last dekad available for 2026 across ASAP / GeoSahel (11-20 Sep)


def key(s):
    k = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", k)


ALIAS = {  # spelling variants seen in FEWS NET / HNRP vs CODAB
    "bulkiemde": "boulkiemde", "kouritenga": "kourittenga", "komondjari": "komandjari",
    "koosin": "kossin", "lorum": "loroum",
}


def k2(s):
    return ALIAS.get(key(s), key(s))


new2 = gpd.read_file(f"zip://{WORK}/bfa_admin_boundaries_new.shp.zip!bfa_admin2.shp")
new2 = new2.sort_values("adm2_pcode").reset_index(drop=True)
old2 = gpd.read_file(f"zip://{WORK}/bfa_old.shp.zip!bfa_adm2.shp")
xw = new2[["adm2_pcode", "adm2_pco_1"]].rename(columns={"adm2_pco_1": "old_pcode"})
children = xw.groupby("old_pcode").adm2_pcode.apply(list).to_dict()
old_by_key = {k2(n): p for n, p in zip(old2.ADM2_FR, old2.ADM2_PCODE)}
new_by_key = {k2(n): p for n, p in zip(new2.adm2_name1, new2.adm2_pcode)}
old_region = dict(zip(old2.ADM2_PCODE, old2.ADM1_FR))
pcodes = new2.adm2_pcode.tolist()


def to_new(df_old, col="old_pcode"):
    """Expand rows keyed on pre-reform provinces to the post-reform ones (splits inherit)."""
    return df_old.merge(xw, left_on=col, right_on="old_pcode", how="inner").drop(
        columns=["old_pcode"] if col == "old_pcode" else [col, "old_pcode"]
    )


def dekad_of(dt):
    return (dt.dt.month - 1) * 3 + np.minimum((dt.dt.day - 1) // 10, 2) + 1


rows = {}

# ---------------- GeoSahel biomass ----------------
b = pd.read_parquet(WORK / "bio_adm2_bfa.parquet")


def cum(y, d1=10, d2=DEKAD):
    cols = [f"DMP_{y}{k:02d}" for k in range(d1, d2 + 1)]
    return b[cols].where(b[cols] > -9000).sum(axis=1, min_count=len(cols))


bio = pd.DataFrame({y: cum(y) for y in range(1999, 2027)})
fy = [y for y in bio.columns if FIT_Y0 <= y <= FIT_Y1]
X = np.array(fy, float)
Y = bio[fy].to_numpy(float)
slope = ((X - X.mean()) * (Y - Y.mean(1, keepdims=True))).sum(1) / ((X - X.mean()) ** 2).sum()
icpt = Y.mean(1) - slope * X.mean()
fit = pd.DataFrame(np.outer(slope, bio.columns.astype(float)) + icpt[:, None],
                   index=bio.index, columns=bio.columns)
bmean = bio[fy].mean(1)
fit = fit.clip(lower=0.1 * bmean.to_numpy()[:, None])
bio_det = 100 * bio / fit
bio_raw = 100 * bio.div(bmean, axis=0)
bio_trend = pd.Series(100 * slope / bmean.to_numpy(), index=bio.index)  # %/yr
for name, df in [("bio_det", bio_det), ("bio_raw", bio_raw)]:
    rows[name] = df.stack().rename(name)

# ---------------- ASAP (GAUL-2 = pre-reform provinces) ----------------
def asap(name):
    d = pd.read_csv(WORK / "asap" / f"{name}.csv", dtype={"date": str})
    d["date"] = pd.to_datetime(d["date"], format="%Y%m%d")
    d["year"] = d.date.dt.year
    d["dekad"] = dekad_of(d.date)
    d["old_pcode"] = d.region_name.map(k2).map(old_by_key)
    assert d.old_pcode.notna().all(), d[d.old_pcode.isna()].region_name.unique()
    d.loc[d.value <= -999, "value"] = np.nan
    return d


def theil_detrend(wide, y0, y1):
    out, sl = wide.copy(), {}
    for idx, r in wide.iterrows():
        f = r[[c for c in wide.columns if y0 <= c <= y1]].dropna()
        fx = np.asarray(f.index, dtype=float)
        s = stats.theilslopes(f.values, fx)[0]
        sl[idx] = s
        out.loc[idx] = r - s * (np.array(wide.columns, float) - fx.mean())
    return out, pd.Series(sl)


zf = {}
for lc in ["crop", "range"]:
    d = asap(f"zfparc_{lc}")
    w = d[d.dekad == DEKAD].pivot_table(index="old_pcode", columns="year", values="value")
    det, sl = theil_detrend(w, *ASAP_FIT)
    zf[lc] = (w, det, sl)
z_raw = np.fmin(zf["crop"][0], zf["range"][0])
z_det = np.fmin(zf["crop"][1], zf["range"][1])
for name, df in [("zfparc_raw", z_raw), ("zfparc_det", z_det),
                 ("zfparc_crop_det", zf["crop"][1]), ("zfparc_range_det", zf["range"][1])]:
    s = df.stack().rename(name).reset_index().rename(columns={"level_1": "year"})
    s = to_new(s).set_index(["adm2_pcode", "year"])[name]
    rows[name] = s
zslope = to_new(pd.DataFrame({
    "old_pcode": zf["crop"][2].index,
    "zfparc_crop_trend_dec": 10 * zf["crop"][2].values,
    "zfparc_range_trend_dec": 10 * zf["range"][2].reindex(zf["crop"][2].index).values,
})).set_index("adm2_pcode")

# SPI-3 at dekad 26 (worst of crop/range) -- rainfall context
sp = {lc: asap(f"spi3_{lc}") for lc in ["crop", "range"]}
spw = np.fmin(*[s[s.dekad == DEKAD].pivot_table(index="old_pcode", columns="year", values="value")
                for s in sp.values()])
s = spw.stack().rename("spi3").reset_index().rename(columns={"level_1": "year"})
rows["spi3"] = to_new(s).set_index(["adm2_pcode", "year"]).spi3

# Jul-Sep (dekads 19-26) mean temperature over cropland, anomaly vs 2001-2023
t = asap("temp_crop")
tw = t[t.dekad.between(19, DEKAD)].pivot_table(index="old_pcode", columns="year", values="value")
ta = tw.sub(tw[[c for c in tw.columns if 2001 <= c <= 2023]].mean(1), axis=0)
s = ta.stack().rename("temp_anom").reset_index().rename(columns={"level_1": "year"})
rows["temp_anom"] = to_new(s).set_index(["adm2_pcode", "year"]).temp_anom

# ---------------- FEWS NET ----------------
c = pd.read_parquet(WORK / "fews_bfa_classification.parquet")
c = c[(c.unit_type == "fsc_admin_lhz") & (c.scale != "IPC Highest Household")]
c = c[c.scenario.isin(["CS", "ML1"]) & c.phase.between(1, 5)].copy()
parts = c.unit_full_name.str.rsplit(", ", n=3)
c["lhz"] = parts.str[0].str.replace("transhuman ", "transhumant ", regex=False)
c["prov"] = parts.str[1]
c["vint"] = c.fnid.str[:6]
c["reporting_date"] = pd.to_datetime(c.reporting_date)
new_rows = c[c.vint == "BF2026"].assign(adm2_pcode=lambda x: x.prov.map(k2).map(new_by_key))
old_rows = c[c.vint != "BF2026"].assign(old_pcode=lambda x: x.prov.map(k2).map(old_by_key))
assert new_rows.adm2_pcode.notna().all() and old_rows.old_pcode.notna().all()
old_rows = to_new(old_rows)
f = pd.concat([new_rows, old_rows], ignore_index=True)

# population per (province, livelihood zone) from the 2026 unit geometry x WorldPop
u = gpd.read_file(WORK / "fews_units_bfa_2026.gpkg")
u["adm2_pcode"] = u.admin2.map(k2).map(new_by_key)
u["lhz"] = u.lzname
ex = exact_extract(str(WORK / "bfa_pop_2020_1km.tif"), u, "sum", include_cols=["adm2_pcode", "lhz"],
                   output="pandas")
wpl = ex.groupby(["adm2_pcode", "lhz"])["sum"].sum()
f["w"] = [wpl.get((p, l), np.nan) for p, l in zip(f.adm2_pcode, f.lhz)]
miss = f[f.w.isna()][["vint", "adm2_pcode", "lhz"]].drop_duplicates()
print(f"FEWS rows w/o 2026 (province, LHZ) pop weight: {len(miss)} combos")
f["w"] = f.w.fillna(1.0)  # LHZ absent from 2026 geometry: tiny weight, still counts in max phase
f["p3"] = (f.phase >= 3).astype(float)
g = f.groupby(["reporting_date", "scenario", "adm2_pcode"])
fr = pd.DataFrame({
    "fews_p3_share": 100 * g.apply(lambda x: np.average(x.p3, weights=x.w), include_groups=False),
    "fews_max_phase": g.phase.max(),
}).reset_index()
fr.to_csv(WORK / "fews_rounds.csv", index=False)
fr["year"] = fr.reporting_date.dt.year
fy_ = fr.groupby(["adm2_pcode", "year"]).agg(fews_p3_share=("fews_p3_share", "max"),
                                             fews_max_phase=("fews_max_phase", "max"),
                                             fews_n_rounds=("reporting_date", "nunique"))
for col in fy_.columns:
    rows[col] = fy_[col]

# ---------------- long table ----------------
long = pd.concat(rows.values(), axis=1)
long.index.names = ["adm2_pcode", "year"]
long = long.reset_index()
long = long[long.year.between(1999, 2026)]
long = new2[["adm1_pcode", "adm1_name1", "adm2_pcode", "adm2_name1"]].rename(
    columns={"adm1_name1": "adm1_name", "adm2_name1": "adm2_name"}).merge(long, on="adm2_pcode")
long.to_csv(WORK / "drought_by_year.csv", index=False)
meta = pd.DataFrame({"bio_trend_pct_per_yr": bio_trend, "bio_baseline_cum": bmean}).join(zslope)
meta.index.name = "adm2_pcode"
meta.to_csv(WORK / "drought_trends.csv")
print(long.groupby("year")[["bio_det", "zfparc_det", "spi3", "temp_anom", "fews_p3_share"]]
      .mean().round(2).tail(8))
print(long.shape)
