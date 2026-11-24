"""July-September rainfall over the area from CHIRPS v2, CHIRPS v3 and ERA5, 1981-2026.

Source: the 0.5-degree monthly cubes of ds-precip-intercomparison (`cache/packed/{chirps_v2,chirps_v3,era5}.npz`,
1981 to August 2026), each cell weighted by its overlap with the area times cos(latitude). September 2026
is read from the CHC monthly COGs (one windowed read per product) and aggregated to the same cells; the
script checks that a COG read of September 2025 reproduces the cube value.

Area outline: the four former regions (COD-AB 2020, ADM1 BF46, BF49, BF54, BF56), same outline as the six
2026 regions.

Usage: BFA_DATA_DIR=... uv run --no-project --with numpy --with geopandas --with pyogrio --with rasterio \
           --with shapely python chirps_aoi.py <ds-precip-intercomparison cache dir> <bfa_adm1.shp (2020)>
Writes $BFA_DATA_DIR/iri_review/chirps_aoi_jas.json.
"""

import json
import sys
import time

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from shapely.geometry import box

import data

COG = {
    "chirps_v2": "/vsicurl/https://data.chc.ucsb.edu/products/CHIRPS/v2.0/global_monthly/cogs/chirps-v2.0.{}.cog",
    "chirps_v3": "/vsicurl/https://data.chc.ucsb.edu/products/CHIRPS/v3.0/monthly/global/cogs/chirps-v3.0.{}.cog",
}


def main(cache: str, adm1: str) -> None:
    o1 = gpd.read_file(adm1)
    aoi = o1[o1.ADM1_PCODE.isin(["BF46", "BF49", "BF54", "BF56"])].to_crs(4326).union_all()
    cells = np.load(f"{cache}/packed/cells.npz")
    lat, lon = cells["lat"], cells["lon"]
    sel = np.where((lat > 9) & (lat < 16) & (lon > -6) & (lon < 3))[0]
    w = np.array([box(lon[i] - .25, lat[i] - .25, lon[i] + .25, lat[i] + .25).intersection(aoi).area / 0.25 for i in sel])
    keep = w > 0
    sel, w = sel[keep], w[keep] * np.cos(np.deg2rad(lat[sel[keep]]))

    def cog_mean(url):
        with rasterio.open(url) as src:
            win = from_bounds(-6, 9, 3, 16, src.transform)
            a = src.read(1, window=win).astype(float)
            tr = src.window_transform(win)
        a[a < 0] = np.nan
        ys = tr.f + tr.e * (np.arange(a.shape[0]) + .5)
        xs = tr.c + tr.a * (np.arange(a.shape[1]) + .5)
        v = [np.nanmean(a[np.ix_((ys <= lat[i] + .25) & (ys > lat[i] - .25), (xs >= lon[i] - .25) & (xs < lon[i] + .25))]) for i in sel]
        return float((np.array(v) * w).sum() / w.sum())

    res, out = {}, {}
    for prod in ["chirps_v2", "chirps_v3", "era5"]:
        z = np.load(f"{cache}/packed/{prod}.npz", allow_pickle=True)
        t = z["time"].astype(str)
        p = z["precip"][:, sel]
        s = {}
        for y in range(1981, 2027):
            idx = [np.where(np.char.startswith(t, f"{y}-{m:02d}"))[0] for m in (7, 8, 9)]
            if all(len(i) for i in idx):
                s[y] = float(sum((p[i[0]] * w).sum() / w.sum() for i in idx))
            elif y == 2026 and len(idx[0]) and len(idx[1]):  # July and August in the cube, September from the COG
                s["2026_JA"] = float(sum((p[i[0]] * w).sum() / w.sum() for i in idx[:2]))
        res[prod] = s
        if prod in COG:
            k = np.where(np.char.startswith(t, "2025-09"))[0][0]
            cube25 = float((p[k] * w).sum() / w.sum())
            cog25 = cog_mean(COG[prod].format("2025.09"))
            if abs(cube25 - cog25) > 0.01:
                raise SystemExit(f"{prod}: COG September 2025 {cog25:.3f} differs from the cube {cube25:.3f}")
            time.sleep(3)
            out[f"sep2026_{prod}_cog"] = cog_mean(COG[prod].format("2026.09"))
            out[f"sep2025_{prod}_cog_check"] = [cube25, cog25]
            time.sleep(3)
    out["res"] = res
    (data.data_dir() / "iri_review" / "chirps_aoi_jas.json").write_text(json.dumps(out))
    print({k: v for k, v in out.items() if k != "res"})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
