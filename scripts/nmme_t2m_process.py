"""NMME 2 m temperature forecasts for the framework-province box, September 2026 start.

For each model with a September 2026 forecast on the IRI Data Library: box-mean per member
and lead (Sep, Oct, Nov), climatology and member distribution from the 1991-2020
September-start hindcasts, anomaly of the ensemble mean (degC and hindcast sd), probability
of the upper/lower tercile. Writes nmme_summary.json.
"""
import glob
import json
import sys

import numpy as np
import xarray as xr

S = sys.argv[1]
MONTH = {0.5: "September", 1.5: "October", 2.5: "November"}


def box(path_or_paths):
    ds = xr.open_mfdataset(path_or_paths, combine="nested", concat_dim="S", decode_times=False) if isinstance(path_or_paths, list) else xr.open_dataset(path_or_paths, decode_times=False)
    da = ds["tref"]
    w = np.cos(np.deg2rad(da["Y"]))
    b = da.weighted(w).mean(dim=["X", "Y"])
    if "Z" in b.dims:
        b = b.squeeze("Z", drop=True)
    return b.load() - 273.15


out = {}
for fc_path in sorted(glob.glob(f"{S}/nmme/fc_*.nc")):
    m = fc_path.split("fc_")[1][:-3]
    hc_files = sorted(glob.glob(f"{S}/nmme/hc_{m}/*.nc"))
    if hc_files:
        hc = box(hc_files)
    elif glob.glob(f"{S}/nmme/hc_{m}.nc"):
        hc = box(f"{S}/nmme/hc_{m}.nc")
        # keep September starts only: S is months since 1960-01-01; Sep => (S - 8) % 12 == 0
        hc = hc.sel(S=[s for s in hc["S"].values if (int(round(s)) - 8) % 12 == 0])
    else:
        print(m, "no hindcast, skipping")
        continue
    fc = box(fc_path)
    rows = []
    for L in fc["L"].values:
        f = fc.sel(L=L).values.ravel()
        f = f[~np.isnan(f)]
        h = hc.sel(L=L).values.ravel()
        h = h[~np.isnan(h)]
        hm = hc.sel(L=L).mean(dim="M").values.ravel()  # hindcast ensemble means, one per year
        lo, hi = np.percentile(h, [100 / 3, 200 / 3])
        clim = h.mean()
        rows.append(
            dict(
                lead=float(L), month=MONTH[float(L)], n_members=int(len(f)), n_hc_years=int(hc.sizes["S"]),
                clim=float(clim), ens_mean=float(f.mean()), anom=float(f.mean() - clim),
                anom_sd_members=float((f.mean() - clim) / h.std()),
                anom_sd_ensmeans=float((f.mean() - clim) / hm.std()),
                spread=float(f.std()), hc_member_sd=float(h.std()), hc_ensmean_sd=float(hm.std()),
                p_upper=float((f > hi).mean()), p_lower=float((f < lo).mean()),
                p_above_median=float((f > np.median(h)).mean()),
                rank_of_ensmean_among_hc_ensmeans=int((hm > f.mean()).sum() + 1),
                terciles=[float(lo), float(hi)],
            )
        )
        print(f"{m:14s} {MONTH[float(L)]:9s} clim {clim:.2f} ens {f.mean():.2f} anom {f.mean()-clim:+.2f} °C "
              f"({(f.mean()-clim)/hm.std():+.1f} sd of hindcast means) P(upper) {(f>hi).mean():.0%} P(lower) {(f<lo).mean():.0%} "
              f"rank {rows[-1]['rank_of_ensmean_among_hc_ensmeans']}/{hc.sizes['S']+1}")
    out[m] = rows
json.dump(out, open(f"{S}/nmme_summary.json", "w"), indent=1)
print("saved", list(out))
