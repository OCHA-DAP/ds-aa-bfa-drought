"""Population living in modelled river-flood zones (JRC/CEMS GloFAS global flood hazard maps
v2.1.2, 3 arcsec) per BFA province, for the 1-in-10 and 1-in-100-year return periods.

The categorised depth tiles (class >= 1, permanent water excluded) are averaged onto the
WorldPop 2020 1 km grid (share of each 1 km cell in the flood zone), times population.

Usage: jrc_flood_zone_pop.py <workdir>  ->  <workdir>/jrc_flood_zone_pop.csv
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject
from rasterio.windows import from_bounds

WORK = Path(sys.argv[1])
TILES = ["ID110_N20_W10", "ID111_N10_W10", "ID117_N20_W0", "ID118_N10_W0"]

adm = gpd.read_file(f"zip://{WORK}/bfa_admin_boundaries_new.shp.zip!bfa_admin2.shp")
adm = adm.sort_values("adm2_pcode").reset_index(drop=True)
with rasterio.open(WORK / "bfa_pop_2020_1km.tif") as ds:
    pop = ds.read(1).astype("float64")
    pop[(pop < 0) | ~np.isfinite(pop)] = 0
    ptr, pcrs, shape, pb = ds.transform, ds.crs, ds.shape, ds.bounds
ids = rasterize([(g, i + 1) for i, g in enumerate(adm.geometry)], out_shape=shape, transform=ptr,
                fill=0, dtype="int32")
rows = {}
for rp in ["RP10", "RP100"]:
    frac = np.zeros(shape, "float32")
    for t in TILES:
        f = WORK / "jrc" / f"{t}_{rp}_depth_reclass.tif"
        with rasterio.open(f) as ds:
            w = from_bounds(pb.left, pb.bottom, pb.right, pb.top, ds.transform)
            w = w.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
            a = ds.read(1, window=w)
            m = ((a >= 1) & (a <= 4)).astype("float32")
            part = np.zeros(shape, "float32")
            reproject(m, part, src_transform=ds.window_transform(w), src_crs=ds.crs,
                      dst_transform=ptr, dst_crs=pcrs, resampling=Resampling.average,
                      src_nodata=None, dst_nodata=0)
            frac = np.maximum(frac, part)
            del a, m
    exp = pop * frac
    rows[f"pop_floodzone_{rp.lower()}"] = pd.Series(
        np.bincount(ids.ravel(), weights=exp.ravel(), minlength=len(adm) + 1)[1:], index=adm.adm2_pcode)
out = pd.DataFrame(rows)
tot = pd.Series(np.bincount(ids.ravel(), weights=pop.ravel(), minlength=len(adm) + 1)[1:],
                index=adm.adm2_pcode)
for c in list(out.columns):
    out[c.replace("pop_", "pct_")] = 100 * out[c] / tot
out.index.name = "adm2_pcode"
out.to_csv(WORK / "jrc_flood_zone_pop.csv")
print(out.round(1).sort_values("pct_floodzone_rp100", ascending=False).head(12).to_string())
print(out[["pop_floodzone_rp10", "pop_floodzone_rp100"]].sum().round())
