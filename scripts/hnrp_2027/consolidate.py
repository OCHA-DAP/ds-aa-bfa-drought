"""Consolidate per-year indicators into the per-province HNRP 2027 tables (+ region rollup).

Design (reviewed): no blended drought index. Three drought lenses + FEWS NET beside them,
floods as impact records + descriptive, unranked exposure layers.
  - Vegetation hazard per year: biomass (% of trend) and zFPARc (detrended z) each scored
    piecewise-linearly on their pooled historical percentiles (0 at p20, 0.5 at p10, 1 at p5);
    index = mean of the two; categories Faible <0.1, Modere 0.1-0.5, Eleve 0.5-0.9,
    Tres eleve >=0.9. Corroboration rule: if the two scores differ by >= 0.5 the category is
    capped at Modere and flagged (zFPARc drifts negative around Ouagadougou 2024-26 while
    biomass does not).
  - Recent = worst year of the per-year index over 2024-2026 (+ which year, + each year).
  - Structural = number of dry years 2001-2025 (either source below its p20).
  - 2026 watch = SPI-3 (dekad 26) <= -1 and/or Jul-Sep temperature anomaly >= +1 C; unscored.
  - FEWS NET = highest phase (and share of population in Phase 3+ units) per year; latest
    projection; assistance ("!") flag. Not combined with the hazard index.

Usage: consolidate.py <workdir>  ->  provinces.csv, regions.csv, by_year.csv, config.json
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

WORK = Path(sys.argv[1])
WINDOW = (2024, 2026)
BIO_BASE, ZF_BASE = (1999, 2023), (2001, 2023)
SPLIT_CHILDREN = {"BF5901", "BF5902", "BF6001", "BF6002"}  # Soum, Tapoa splits (2024 reform)
CATS = [(0.9, "TE"), (0.5, "E"), (0.1, "M"), (-1, "F")]

dr = pd.read_csv(WORK / "drought_by_year.csv")
fl = pd.read_csv(WORK / "flood_by_year.csv")
ctx = pd.read_csv(WORK / "context.csv")
jrc = pd.read_csv(WORK / "jrc_flood_zone_pop.csv")

# ---------------- percentile anchors ----------------
hb = dr[dr.year.between(*BIO_BASE)].bio_det.dropna()
hz = dr[dr.year.between(*ZF_BASE)].zfparc_det.dropna()
A = {"bio": [float(np.percentile(hb, q)) for q in (20, 10, 5)],
     "zf": [float(np.percentile(hz, q)) for q in (20, 10, 5)]}


def pscore(v, a):
    """0 at p20, 0.5 at p10, 1 at p5 (low values = dry), linear between, clipped."""
    p20, p10, p5 = a
    return np.where(np.isnan(v), np.nan,
                    np.where(v >= p20, 0.0,
                             np.where(v >= p10, 0.5 * (p20 - v) / (p20 - p10),
                                      np.clip(0.5 + 0.5 * (p10 - v) / (p10 - p5), 0.5, 1.0))))


def cat(v):
    return None if pd.isna(v) else next(c for t, c in CATS if v >= t)


by = dr.merge(fl[["adm2_pcode", "year", "flood_exp_pk5", "flood_exp_pct"]], on=["adm2_pcode", "year"],
              how="left")
by["score_bio"] = pscore(by.bio_det.to_numpy(float), A["bio"])
by["score_zf"] = pscore(by.zfparc_det.to_numpy(float), A["zf"])
by["idx_hazard"] = by[["score_bio", "score_zf"]].mean(axis=1, skipna=False)
by["diverge"] = (by.score_bio - by.score_zf).abs() >= 0.5
by["cat_raw"] = by.idx_hazard.map(cat)
by["cat_hazard"] = np.where(by.diverge & by.cat_raw.isin(["E", "TE"]), "M", by.cat_raw)
by.loc[by.idx_hazard.isna(), "cat_hazard"] = None
by["dry_year"] = ((by.bio_det < A["bio"][0]) | (by.zfparc_det < A["zf"][0])).astype(float)
by.loc[by.bio_det.isna() & by.zfparc_det.isna(), "dry_year"] = np.nan

# realised historical category frequencies (pooled province-years, both sources present)
hist = by[by.year.between(2001, 2023) & by.idx_hazard.notna()]
freq = (hist.cat_hazard.value_counts(normalize=True) * 100).round(1).to_dict()
print("realised 2001-2023 category frequency (%):", freq)
keep = ["adm1_pcode", "adm1_name", "adm2_pcode", "adm2_name", "year", "bio_det", "bio_raw", "zfparc_det",
        "zfparc_raw", "score_bio", "score_zf", "idx_hazard", "cat_hazard", "diverge", "spi3", "temp_anom",
        "fews_max_phase", "fews_p3_share", "fews_n_rounds", "flood_exp_pk5", "flood_exp_pct"]
by[keep].to_csv(WORK / "by_year.csv", index=False)

# ---------------- per province ----------------
out = ctx.set_index("adm2_pcode").copy()
w = by[by.year.between(*WINDOW)]
for y in range(WINDOW[0], WINDOW[1] + 1):
    wy = w[w.year == y].set_index("adm2_pcode")
    for c in ["bio_det", "zfparc_det", "idx_hazard", "cat_hazard", "fews_max_phase", "fews_p3_share"]:
        out[f"{c}_{y}"] = wy[c]
g = w.dropna(subset=["idx_hazard"]).sort_values(["idx_hazard", "year"], ascending=[False, False])
worst = g.groupby("adm2_pcode").first()
out["hazard_worst_year"] = worst.year
out["idx_hazard_recent"] = worst.idx_hazard
out["score_bio_recent"] = worst.score_bio
out["score_zf_recent"] = worst.score_zf
out["cat_hazard_recent"] = worst.cat_hazard
out["diverge_recent"] = worst.diverge
out["bio_min_2024_2026"] = w.groupby("adm2_pcode").bio_det.min()
out["zf_min_2024_2026"] = w.groupby("adm2_pcode").zfparc_det.min()
st = by[by.year.between(2001, 2025)].groupby("adm2_pcode")
out["dry_years_2001_2025"] = st.dry_year.sum().astype(int)
out["dry_years_list"] = st.apply(lambda x: ", ".join(str(y) for y in x.loc[x.dry_year == 1, "year"]),
                                 include_groups=False)
w26 = by[by.year == 2026].set_index("adm2_pcode")
out["spi3_2026"] = w26.spi3
out["temp_anom_2026"] = w26.temp_anom
out["watch_2026"] = np.select(
    [(w26.spi3 <= -1) & (w26.temp_anom >= 1), w26.spi3 <= -1, w26.temp_anom >= 1],
    ["sec+chaud", "sec", "chaud"], default="")

# FEWS NET: worst 2024-2026, latest projection, assistance flag
fw = w.groupby("adm2_pcode")
out["fews_max_phase_2024_2026"] = fw.fews_max_phase.max()
out["fews_p3_share_2024_2026"] = fw.fews_p3_share.max()
c = pd.read_parquet(WORK / "fews_bfa_classification.parquet")
c = c[(c.unit_type == "fsc_admin_lhz") & (c.scale != "IPC Highest Household") & c.fnid.str.startswith("BF2026")]
c["reporting_date"] = pd.to_datetime(c.reporting_date)
last = c.reporting_date.max()
parts = c.unit_full_name.str.rsplit(", ", n=3)
c["prov"] = parts.str[1]
def nkey(n):
    k = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", k)


name2pc = {nkey(n): pc for n, pc in zip(out.hnrp_name_2026.fillna(out.adm2_name), out.index)}
name2pc.update({nkey(n): pc for n, pc in zip(out.adm2_name, out.index)})
name2pc.update({"koosin": "BF6101", "lorum": "BF5401", "komondjari": "BF5802"})
c["adm2_pcode"] = c.prov.map(lambda n: name2pc.get(nkey(n)))
assert c.adm2_pcode.notna().all(), c[c.adm2_pcode.isna()].prov.unique()
cl = c[c.reporting_date == last]
ml2 = cl[cl.scenario == "ML2"]
out["fews_proj_phase"] = ml2.groupby("adm2_pcode").phase.max()
out["fews_proj_period"] = f"{ml2.projection_start.min()}/{ml2.projection_end.max()}"
out["fews_assistance_2026"] = c[c.scenario.isin(["CS", "ML1"])].groupby("adm2_pcode").assistance.any()
out["fews_latest_round"] = str(last.date())

# floods (descriptive; not validated -> never ranked)
ff = fl.set_index(["adm2_pcode", "year"])
out["flood_exp_median_2002_2023"] = fl[fl.year.between(2002, 2023)].groupby("adm2_pcode").flood_exp_pk5.median()
for y in range(2024, 2027):
    out[f"flood_exp_{y}"] = fl[fl.year == y].set_index("adm2_pcode").flood_exp_pk5
out = out.join(jrc.set_index("adm2_pcode"))
out["inherited_pre2026"] = out.index.isin(SPLIT_CHILDREN)
out = out.sort_index()
out.reset_index().to_csv(WORK / "provinces.csv", index=False)

# ---------------- regions (admin 1) ----------------
pw = out.pop_worldpop_2020


def wavg(s):
    m = s.notna()
    return np.average(s[m], weights=pw[s.index][m]) if m.any() else np.nan


reg = []
for (pc1, n1), gg in out.groupby(["adm1_pcode", "adm1_name"]):
    r = {"adm1_pcode": pc1, "adm1_name": n1, "n_provinces": len(gg), "pop_worldpop_2020": gg.pop_worldpop_2020.sum()}
    for y in range(2024, 2027):
        r[f"idx_hazard_{y}"] = wavg(gg[f"idx_hazard_{y}"].astype(float))
    r["idx_hazard_recent_popw"] = wavg(gg.idx_hazard_recent.astype(float))
    r["n_prov_hazard_E_plus"] = int(gg.cat_hazard_recent.isin(["E", "TE"]).sum())
    r["dry_years_popw"] = wavg(gg.dry_years_2001_2025.astype(float))
    r["fews_max_phase_2024_2026"] = gg.fews_max_phase_2024_2026.max()
    r["fews_p3_share_2024_popw"] = wavg(gg.fews_p3_share_2024.astype(float))
    r["fews_p3_share_2026_popw"] = wavg(gg.fews_p3_share_2026.astype(float))
    r["fews_proj_phase"] = gg.fews_proj_phase.max()
    r["watch_2026_n_prov"] = int((gg.watch_2026 != "").sum())
    r["jiaf_severity_2026_max"] = gg.jiaf_severity_2026.max()
    r["pin_2026_total"] = gg.pin_2026_total.sum()
    r["emdat_flood_years_n_max"] = gg.emdat_flood_years_n.max()
    for col in ["flood_exp_median_2002_2023", "flood_exp_2024", "flood_exp_2025", "flood_exp_2026",
                "pop_floodzone_rp10", "pop_floodzone_rp100"]:
        r[col] = gg[col].sum()
    reg.append(r)
reg = pd.DataFrame(reg)
reg.to_csv(WORK / "regions.csv", index=False)
json.dump({"anchors": A, "window": WINDOW, "cats": CATS, "freq_2001_2023": freq,
           "fews_latest_round": str(last.date())}, open(WORK / "config.json", "w"), indent=1)
print(out[["adm1_name", "adm2_name", "bio_min_2024_2026", "zf_min_2024_2026", "idx_hazard_recent",
           "hazard_worst_year", "cat_hazard_recent", "diverge_recent", "dry_years_2001_2025",
           "fews_max_phase_2024_2026", "fews_max_phase_2026", "fews_proj_phase", "watch_2026"]]
      .sort_values("idx_hazard_recent", ascending=False).round(2).head(20).to_string())
print(out.cat_hazard_recent.value_counts().to_dict(), "anchors", {k: np.round(v, 2).tolist() for k, v in A.items()})
print(pd.crosstab(out.cat_hazard_recent, out.fews_max_phase_2024_2026))
