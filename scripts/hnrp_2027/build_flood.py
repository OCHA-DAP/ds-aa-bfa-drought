"""Flood indicators per BFA province (CODAB v03, 47 units) and year.

FloodScan (SFED x WorldPop 2020, see flood_exposure.py):
  - flood_exp_pk5: annual peak of the 5-day running mean of daily exposed population,
    Aug-Oct (5-day smoothing removes the one-day SFED spikes common over the Sahel);
    also as % of province population.
  - flood_exp_rp: Weibull return period of that peak against the 2002-2023 record
    (1998-2001 excluded: a sensor-era step change inflates those years ~5x nationally).
IMERG Late v7 (see imerg_extremes.py), May-Oct:
  - rain_rx3_pop: population-weighted mean of the pixel seasonal max 3-day rainfall (mm).
  - rain_ext_share: share of province population whose pixel Rx3day reached its own
    1-in-5-year value (2001-2023 Weibull, i.e. rank 5 of 23).
  - rain_n50_pop: population-weighted mean number of days >= 50 mm.

Usage: build_flood.py <workdir>  ->  flood_by_year.csv
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio.features import rasterize
from scipy import sparse

WORK = Path(sys.argv[1])
BASE = (2002, 2023)
IM_BASE = (2001, 2023)

adm = gpd.read_file(f"zip://{WORK}/bfa_admin_boundaries_new.shp.zip!bfa_admin2.shp")
adm = adm.sort_values("adm2_pcode").reset_index(drop=True)
pcodes = adm.adm2_pcode.tolist()
pop = pd.read_csv(WORK / "prov_pop_worldpop2020.csv").set_index("adm2_pcode").pop_worldpop_2020


def weibull_rp(hist, x):
    """Return period of value x against a sample of annual maxima (Weibull plotting position)."""
    h = np.sort(np.asarray(hist)[~np.isnan(hist)])[::-1]
    n = len(h)
    rank = (h >= x).sum()  # x's rank if inserted (ties count as exceedances)
    if rank == 0:
        return (n + 1) / 1.0 * 1.0 if n else np.nan  # beyond record -> > n+1
    return (n + 1) / rank


# ---------------- FloodScan ----------------
d = pd.read_parquet(WORK / "flood_daily_adm2.parquet")
d = d[d.date.dt.month.between(8, 10)]
wide = d.pivot_table(index="date", columns="adm2_pcode", values="exposed_f05")
wide = wide.asfreq("D")
r5 = wide.rolling(5, min_periods=4).mean()
pk5 = r5.groupby(r5.index.year).max().T  # adm2 x year
pk1 = wide.groupby(wide.index.year).max().T
rows = []
for pc in pcodes:
    hist = pk5.loc[pc, [y for y in pk5.columns if BASE[0] <= y <= BASE[1]]].values
    for y in pk5.columns:
        v = pk5.at[pc, y]
        rows.append(dict(adm2_pcode=pc, year=y, flood_exp_pk5=v, flood_exp_pk1=pk1.at[pc, y],
                         flood_exp_pct=100 * v / pop[pc],
                         flood_exp_rp=weibull_rp(hist, v) if v > 0 else 1.0))
fl = pd.DataFrame(rows).set_index(["adm2_pcode", "year"])

# ---------------- IMERG (evaluated and dropped; kept optional for the validation) ----------------
im = None
if (WORK / "imerg_season_extremes.npz").exists():
    z = np.load(WORK / "imerg_season_extremes.npz")
    years = z["years"].tolist()
    tr = Affine(*z["transform"])
    H, Wd = z["rx1"].shape[1:]
    with rasterio.open(WORK / "bfa_pop_2020_1km.tif") as ds:
        p = ds.read(1).astype("float64")
        p[(p < 0) | ~np.isfinite(p)] = 0
        ptr = ds.transform
        ids = rasterize([(g, i + 1) for i, g in enumerate(adm.geometry)], out_shape=p.shape,
                        transform=ptr, fill=0, dtype="int32")
    rr, cc = np.indices(p.shape)
    xc, yc = ptr.c + (cc + 0.5) * ptr.a, ptr.f + (rr + 0.5) * ptr.e
    icol = np.floor((xc - tr.c) / tr.a).astype(int)
    irow = np.floor((yc - tr.f) / tr.e).astype(int)
    m = (ids > 0) & (p > 0)
    Wm = sparse.csr_matrix((p[m], (ids[m] - 1, irow[m] * Wd + icol[m])), shape=(len(adm), H * Wd))
    wsum = np.asarray(Wm.sum(1)).ravel()

    rx3 = z["rx3"].reshape(len(years), -1)
    base_idx = [i for i, y in enumerate(years) if IM_BASE[0] <= y <= IM_BASE[1]]
    nb = len(base_idx)
    k = max(1, round((nb + 1) / 5))  # rank of the 1-in-5-year value
    thr5 = -np.sort(-rx3[base_idx], axis=0)[k - 1]
    im_rows = []
    for i, y in enumerate(years):
        ext = (rx3[i] >= thr5).astype(float)
        rx3m = Wm @ np.nan_to_num(rx3[i]) / wsum
        exs = 100 * (Wm @ ext) / wsum
        n50 = Wm @ z["n50"][i].reshape(-1).astype(float) / wsum
        rx1m = Wm @ np.nan_to_num(z["rx1"][i].reshape(-1)) / wsum
        for j, pc in enumerate(pcodes):
            im_rows.append(dict(adm2_pcode=pc, year=y, rain_rx3_pop=rx3m[j], rain_rx1_pop=rx1m[j],
                                rain_ext_share=exs[j], rain_n50_pop=n50[j]))
    im = pd.DataFrame(im_rows).set_index(["adm2_pcode", "year"])
out = (fl.join(im, how="outer") if im is not None else fl).reset_index()
out = adm[["adm1_pcode", "adm1_name1", "adm2_pcode", "adm2_name1"]].rename(
    columns={"adm1_name1": "adm1_name", "adm2_name1": "adm2_name"}).merge(out, on="adm2_pcode")
out.to_csv(WORK / "flood_by_year.csv", index=False)
print(out.groupby("year")[["flood_exp_pk5", "flood_exp_pct"]].agg({"flood_exp_pk5": "sum", "flood_exp_pct": "mean"})
      .round(2).tail(8).to_string())
