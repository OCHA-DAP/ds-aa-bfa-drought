"""IMERG (Late Run v7, daily, 0.1 deg) rainfall extremes over Burkina Faso, May-Oct 1998-2026.

Per pixel and season: Rx1day, Rx3day (max 3-day running total) and the number of days
>= 50 mm. Windowed HTTP range reads of the global daily COGs on the prod raster blob.

Usage: imerg_extremes.py <workdir>  ->  <workdir>/imerg_season_extremes.npz
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import ocha_stratus as stratus
import pandas as pd
import rasterio
from rasterio.windows import from_bounds
from tqdm import tqdm

WORK = Path(sys.argv[1])
BOX = (-5.6, 9.3, 2.5, 15.2)
PREFIX = "imerg/daily/late/v7/processed/imerg-daily-late-"

cc = stratus.get_container_client(container_name="raster", stage="prod")
base, sas = cc.url.split("?", 1)
days = [d for d in pd.date_range("1998-05-01", "2026-09-28") if 5 <= d.month <= 10]

with rasterio.open(f"/vsicurl/{base}/{PREFIX}{days[0]:%Y-%m-%d}.tif?{sas}") as ds:
    win = from_bounds(*BOX, ds.transform).round_offsets(op="floor").round_lengths(op="ceil")
    wtr = ds.window_transform(win)
    nod = ds.nodata


def read(d):
    url = f"/vsicurl/{base}/{PREFIX}{d:%Y-%m-%d}.tif?{sas}"
    for _ in range(4):
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
                with rasterio.open(url) as ds:
                    a = ds.read(1, window=win).astype("float32")
            a[(a == nod) | (a < 0) | ~np.isfinite(a)] = np.nan
            return d, a
        except Exception:  # noqa: BLE001 -- retry, then report the day as missing
            continue
    return d, None


arrs = {}
with ThreadPoolExecutor(24) as ex:
    for d, a in tqdm(ex.map(read, days), total=len(days), mininterval=20):
        if a is not None:
            arrs[d] = a
missing = [d for d in days if d not in arrs]
print("read", len(arrs), "missing", len(missing), missing[:5])

years = sorted({d.year for d in arrs})
rx1, rx3, n50, ndays = [], [], [], []
for y in years:
    ds_ = sorted(d for d in arrs if d.year == y)
    st = np.stack([arrs[d] for d in ds_])
    rx1.append(np.nanmax(st, axis=0))
    s3 = np.nansum(np.stack([st[i:len(st) - 2 + i] for i in range(3)]), axis=0)
    rx3.append(s3.max(axis=0))
    n50.append((st >= 50).sum(axis=0))
    ndays.append(len(ds_))
np.savez_compressed(
    WORK / "imerg_season_extremes.npz", years=np.array(years), rx1=np.stack(rx1),
    rx3=np.stack(rx3), n50=np.stack(n50), ndays=np.array(ndays),
    transform=np.array(wtr)[:6],
)
print("done", years[0], years[-1], rx1[0].shape)
