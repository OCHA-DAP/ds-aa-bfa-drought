"""Heat and drought in the Burkina Faso framework provinces.

Builds the seasonal table and prints the statistics quoted on pages/temperature/:
trends in pre-season and growing-season temperature, correlations and regressions of
detrended biomass on rainfall and detrended temperature, composites for the Trigger 2
activation years, dekadal lead/lag between heat and rain, and the 2026 anomalies.

Inputs (in the directory given as argv[1]):
  asap_bfa/{temp_crop,temp_crop_all,rain_crop,wsi_crop,spi3_crop,zfparc_crop,zfparc_range}.csv
    -- JRC ASAP indicator-statistics export, Burkina Faso, GAUL level 2 (see pages/README.md)
Outputs: temp_seasonal.csv (province x year), temp_year_aoi.csv (AOI means by year),
  temp_2026.csv (2026 dekadal anomalies), temp_dekadal.csv (dekadal z-anomalies 1991-2025).

Usage: uv run python scripts/temperature_analysis.py <scratch dir>
"""
import sys

import numpy as np
import pandas as pd
from scipy import stats

S = sys.argv[1]
AOI = {3820: "Loroum", 3824: "Oudalan", 3825: "Séno", 3827: "Yagha"}
JAS, WIN, PRE = range(19, 28), range(21, 27), range(10, 19)
ACT = [2002, 2004, 2006, 2009, 2011]
TGT = [2011, 2014, 2017, 2019, 2022]


def load(name):
    d = pd.read_csv(f"{S}/asap_bfa/{name}.csv", dtype={"date": str})
    d["date"] = pd.to_datetime(d["date"], format="%Y%m%d")
    d["year"] = d["date"].dt.year
    d["dekad"] = (d["date"].dt.month - 1) * 3 + np.minimum((d["date"].dt.day - 1) // 10, 2) + 1
    return d[d.region_id.isin(AOI)][["region_id", "year", "dekad", "value"]].rename(
        columns={"value": name}
    )


def seas(d, col, dks):
    return d[d.dekad.isin(dks)].groupby(["region_id", "year"])[col].mean()


def ols(y, X):
    X = np.column_stack([np.ones(len(y))] + X)
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    yhat = X @ b
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    n, k = X.shape
    s2 = ((y - yhat) ** 2).sum() / (n - k)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    p = 2 * (1 - stats.t.cdf(abs(b / se), n - k))
    return b, p, r2


# ---------------------------------------------------------------- seasonal table
t, r, z, zr, w, s3 = (load(n) for n in ["temp_crop", "rain_crop", "zfparc_crop", "zfparc_range", "wsi_crop", "spi3_crop"])
df = pd.concat(
    [
        seas(t, "temp_crop", JAS).rename("t_jas"),
        seas(t, "temp_crop", PRE).rename("t_pre"),
        seas(t, "temp_crop", WIN).rename("t_win"),
        seas(r, "rain_crop", JAS).rename("rain_jas"),
        seas(z, "zfparc_crop", WIN).rename("z_win"),
        seas(zr, "zfparc_range", WIN).rename("zr_win"),
        seas(w, "wsi_crop", WIN).rename("wsi_win"),
        seas(s3, "spi3_crop", WIN).rename("spi_win"),
    ],
    axis=1,
).reset_index()
df["name"] = df.region_id.map(AOI)
out = []
for rid, g in df.groupby("region_id"):
    g = g.sort_values("year").copy()
    for col in ["t_jas", "t_pre", "t_win"]:
        fit = g[g.year.between(1989, 2025)].dropna(subset=[col])
        sl = stats.theilslopes(fit[col], fit.year)
        p = stats.kendalltau(fit.year, fit[col]).pvalue
        g[col + "_dt"] = g[col] - sl[0] * (g.year - fit.year.mean()) - fit[col].mean()
        g[col + "_an"] = g[col] - fit[fit.year.between(1991, 2020)][col].mean()
        print(f"trend {col} {AOI[rid]}: {sl[0]*10:+.2f} °C/decade p={p:.3f}; "
              f"1989-98 {fit[fit.year<=1998][col].mean():.2f} -> 2016-25 {fit[fit.year>=2016][col].mean():.2f}")
    h = g[g.year.between(2001, 2025)]
    for col in ["z_win", "zr_win"]:
        sl = stats.theilslopes(h[col], h.year)
        g[col + "_dt"] = g[col] - sl[0] * (g.year - h.year.mean())
    out.append(g)
df = pd.concat(out)
df.to_csv(f"{S}/temp_seasonal.csv", index=False)

# ---------------------------------------------------------------- relationships 2001-2025
h = df[df.year.between(2001, 2025)].dropna(subset=["t_jas_dt", "z_win_dt", "rain_jas"]).copy()
print("\ncorrelations, pooled:")
for a in ["t_jas_dt", "t_win_dt", "t_pre_dt"]:
    for b in ["z_win_dt", "rain_jas", "spi_win", "wsi_win"]:
        rr, p = stats.pearsonr(h[a], h[b])
        print(f"  {a} vs {b}: r={rr:+.2f} p={p:.3f}")
print("  rain_jas vs z_win_dt: r=%+.2f" % stats.pearsonr(h.rain_jas, h.z_win_dt)[0])

print("\nz_win_dt ~ rain_std + temp_std:")
for rid, g in h.groupby("region_id"):
    rs = (g.rain_jas - g.rain_jas.mean()) / g.rain_jas.std()
    ts = g.t_jas_dt / g.t_jas_dt.std()
    b, p, r2 = ols(g.z_win_dt.values, [rs.values, ts.values])
    _, _, r20 = ols(g.z_win_dt.values, [rs.values])
    print(f"  {AOI[rid]}: rain {b[1]:+.2f} (p={p[1]:.3f}) temp {b[2]:+.2f} (p={p[2]:.3f}) "
          f"per °C {b[2]/g.t_jas_dt.std():+.2f}; R2 {r20:.2f} -> {r2:.2f}")
rs = (h.rain_jas - h.rain_jas.mean()) / h.rain_jas.std()
ts = h.t_jas_dt / h.t_jas_dt.std()
for col in ["z_win_dt", "zr_win_dt", "wsi_win"]:
    b, p, r2 = ols(h[col].values, [rs.values, ts.values])
    _, _, r20 = ols(h[col].values, [rs.values])
    print(f"  pooled {col}: rain {b[1]:+.2f} (p={p[1]:.4f}) temp {b[2]:+.2f} (p={p[2]:.4f}); R2 {r20:.2f} -> {r2:.2f}")
b, p, r2 = ols(h.z_win_dt.values, [rs.values, (h.t_pre_dt / h.t_pre_dt.std()).values])
print(f"  pre-season temp: {b[2]:+.2f} (p={p[2]:.4f}); pre vs JAS r={stats.pearsonr(h.t_pre_dt, h.t_jas_dt)[0]:.2f}")

print("\ncomposites:")
for lab, yrs in [("activation", ACT), ("target", TGT)]:
    a, o = h[h.year.isin(yrs)], h[~h.year.isin(yrs)]
    print(f"  {lab}: JAS temp dt {a.t_jas_dt.mean():+.2f} vs {o.t_jas_dt.mean():+.2f} "
          f"(p={stats.ttest_ind(a.t_jas_dt, o.t_jas_dt).pvalue:.3f}); rain {a.rain_jas.mean():.1f} vs {o.rain_jas.mean():.1f}")
ym = h.groupby("year").agg(t=("t_jas_dt", "mean"), ta=("t_jas_an", "mean"), tpre=("t_pre_dt", "mean"),
                           rain=("rain_jas", "mean"), z=("z_win", "mean"), zdt=("z_win_dt", "mean"), wsi=("wsi_win", "mean")).round(2)
ym.to_csv(f"{S}/temp_year_aoi.csv")

# ---------------------------------------------------------------- dekadal lead/lag
def dek_z(name, col):
    d = load(name)
    d = d[d.year.between(1991, 2025)].copy()
    g = d.groupby(["region_id", "dekad"])[name]
    d[col] = (d[name] - g.transform("mean")) / g.transform("std")
    return d[["region_id", "year", "dekad", col]]

dk = dek_z("temp_crop", "tz").merge(dek_z("rain_crop", "rz"), on=["region_id", "year", "dekad"])
dk = dk[dk.dekad.between(16, 30)].sort_values(["region_id", "year", "dekad"])
print("\ndekadal temp(t) vs rain(t+lag):")
for lag in [-2, -1, 0, 1, 2]:
    d = dk.assign(rz_l=dk.groupby(["region_id", "year"])["rz"].shift(-lag)).dropna()
    print(f"  lag {lag:+d}: r={stats.pearsonr(d.tz, d.rz_l)[0]:+.2f}")
hot = dk[dk.tz > 1]
print(f"  P(rain<-0.5 | temp>+1)={(hot.rz < -0.5).mean():.0%} base {(dk.rz < -0.5).mean():.0%}")
dk.to_csv(f"{S}/temp_dekadal.csv", index=False)

# ---------------------------------------------------------------- 2026
clim = t[t.year.between(1991, 2020)].groupby(["region_id", "dekad"])["temp_crop"].agg(["mean", "std"]).reset_index()
x = t[t.year == 2026].merge(clim, on=["region_id", "dekad"])
x["anom"] = x["temp_crop"] - x["mean"]
x["name"] = x.region_id.map(AOI)
print("\n2026 anomaly by dekad (AOI mean):", x.groupby("dekad").anom.mean().round(2).to_dict())
for lab, dks in [("pre-season", range(10, 19)), ("dekads 19-25", range(19, 26))]:
    allx = t[t.dekad.isin(dks)].groupby("year")["temp_crop"].mean()
    print(f"  {lab}: 2026 rank {(allx > allx.loc[2026]).sum() + 1} of {len(allx)}; "
          f"{allx.loc[2026]:.2f} vs 1991-2020 {allx.loc[1991:2020].mean():.2f}")
x[["name", "dekad", "temp_crop", "anom"]].to_csv(f"{S}/temp_2026.csv", index=False)
