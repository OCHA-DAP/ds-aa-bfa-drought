"""FloodScan x WorldPop flood exposure per BFA province (post-2024 reform, 47 units).

Daily exposed population = sum over FloodScan cells of SFED(cell) x WorldPop 2020
population in (cell n province) -- the same definition as ds-floodexposure-monitoring
(SFED nearest-neighbour onto the WorldPop grid, multiplied, summed per admin unit),
computed here on the new CODAB v03 provinces. Season May-Nov, 1998-2026.

Also keeps the per-pixel seasonal max SFED per year (BFA window) for recurrence maps.

Usage: flood_exposure.py <workdir>
  in : <workdir>/bfa_admin_boundaries_new.shp.zip, <workdir>/bfa_pop_2020_1km.tif
  out: <workdir>/flood_daily_adm2.parquet, <workdir>/flood_seasonmax_sfed.npz
"""

import io
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import ocha_stratus as stratus
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from scipy import sparse
from tqdm import tqdm

WORK = Path(sys.argv[1])
MONTHS = range(5, 12)  # May-Nov
FS_X0, FS_Y0, FS_RES = -30.0, 40.0, 1 / 12  # FloodScan Africa grid origin / res
DATE_RE = re.compile(r"aer_area_300s_v(\d{4}-\d{2}-\d{2})_v05r01\.tif$")

adm = gpd.read_file(f"zip://{WORK}/bfa_admin_boundaries_new.shp.zip!bfa_admin2.shp")
adm = adm.sort_values("adm2_pcode").reset_index(drop=True)
pcodes = adm.adm2_pcode.tolist()

# ---- population weights W[province, floodscan cell in the BFA window] ----
with rasterio.open(WORK / "bfa_pop_2020_1km.tif") as ds:
    pop = ds.read(1).astype("float64")
    pop[(pop < 0) | ~np.isfinite(pop)] = 0
    tr = ds.transform
    ids = rasterize(
        [(g, i + 1) for i, g in enumerate(adm.geometry)],
        out_shape=pop.shape, transform=tr, fill=0, dtype="int32",
    )
rows, cols = np.indices(pop.shape)
xc = tr.c + (cols + 0.5) * tr.a
yc = tr.f + (rows + 0.5) * tr.e
fcol = np.floor((xc - FS_X0) / FS_RES).astype(int)
frow = np.floor((FS_Y0 - yc) / FS_RES).astype(int)
c0, c1, r0, r1 = fcol.min(), fcol.max() + 1, frow.min(), frow.max() + 1
win = Window(c0, r0, c1 - c0, r1 - r0)
cell = (frow - r0) * (c1 - c0) + (fcol - c0)
m = (ids > 0) & (pop > 0)
W = sparse.csr_matrix(
    (pop[m], (ids[m] - 1, cell[m])), shape=(len(adm), (r1 - r0) * (c1 - c0))
)
prov_pop = np.asarray(W.sum(axis=1)).ravel()
print(f"window rows {r0}:{r1} cols {c0}:{c1}; pop assigned {prov_pop.sum():,.0f}")
pd.DataFrame({"adm2_pcode": pcodes, "pop_worldpop_2020": prov_pop}).to_csv(
    WORK / "prov_pop_worldpop2020.csv", index=False
)

# ---- FloodScan daily list ----
blobs = []
for y in range(1998, 2027):
    for b in stratus.list_container_blobs(
        name_starts_with=f"floodscan/daily/v5/processed/aer_area_300s_v{y}-",
        container_name="raster", stage="prod",
    ):
        mm = DATE_RE.search(b)
        if mm and int(mm.group(1)[5:7]) in MONTHS:
            blobs.append((mm.group(1), b))
blobs.sort()
print(len(blobs), "daily rasters", blobs[0][0], "->", blobs[-1][0])

cc = stratus.get_container_client(container_name="raster", stage="prod")


def read(item):
    date, name = item
    for a in range(4):
        try:
            data = cc.get_blob_client(name).download_blob().readall()
            with rasterio.open(io.BytesIO(data)) as ds:
                arr = ds.read(1, window=win).astype("float64")  # band 1 = SFED
            arr[~np.isfinite(arr) | (arr < 0)] = 0
            return date, arr
        except Exception as e:  # noqa: BLE001
            err = e
    raise RuntimeError(f"{name}: {err}")


daily, seasonmax = [], {}
with ThreadPoolExecutor(16) as ex:
    for date, arr in tqdm(ex.map(read, blobs), total=len(blobs), mininterval=20):
        v = arr.ravel()
        daily.append(pd.DataFrame({
            "date": date, "adm2_pcode": pcodes, "exposed": W @ v,
            "exposed_f05": W @ np.where(v >= 0.05, v, 0),
            "exposed_f10": W @ np.where(v >= 0.10, v, 0),
        }))
        y = int(date[:4])
        seasonmax[y] = arr if y not in seasonmax else np.maximum(seasonmax[y], arr)

df = pd.concat(daily)
df["date"] = pd.to_datetime(df["date"])
df.to_parquet(WORK / "flood_daily_adm2.parquet", index=False)
yrs = sorted(seasonmax)
np.savez_compressed(
    WORK / "flood_seasonmax_sfed.npz",
    years=np.array(yrs), sfed=np.stack([seasonmax[y] for y in yrs]),
    window=np.array([r0, r1, c0, c1]),
)
# ever-flooded-in-season population per province-year (pixelwise max SFED)
ev = pd.DataFrame(
    [{"year": y, "adm2_pcode": p, "exposed_seasonmax": v}
     for y in yrs for p, v in zip(pcodes, W @ seasonmax[y].ravel())]
)
ev.to_csv(WORK / "flood_seasonmax_adm2.csv", index=False)
print("done", len(df))
