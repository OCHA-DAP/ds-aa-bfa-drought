"""Temperature observational trigger for the 17 provinces of the old Boucle du Mouhoun, Nord,
Centre-Nord and Sahel regions.

Indicator: ASAP temperature over cropland (as the temperature explorer), mean over dekads s..d.
(a) Dekad scan: correlation of the season-to-date anomaly (from each province's Theil-Sen trend)
    with millet+sorghum yield anomalies; year-block bootstrap; earliest end dekad on the plateau.
(b) Trigger "at least K of 17 provinces at least Y degC above their own trend", with the trend
    fitted PRIOR-ONLY (years before the target season, expanding, burn-in >= 12 seasons) and,
    for comparison, on the full record 1989-2025 (the explorer's choice).
(c) Absolute variant: AOI-mean window temperature >= T degC, and a fixed-baseline variant
    (province above its own 1991-2020 mean by Y); activation rates by period show the drift.

Usage: uv run --no-project --with pandas --with numpy --with scipy python scripts/obs_review/temp_analysis.py <out.json>
"""

import json
import sys

import numpy as np
import pandas as pd

import common as c

RNG = np.random.default_rng(20261124)
N_BOOT = 4000
BURN_IN = 12  # seasons 1989-2000 before the first scored season 2001


def theil_sen(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Slope and value of the line at mean(x) (line through the means, as the explorer)."""
    i, j = np.triu_indices(len(x), 1)
    slope = float(np.median((y[j] - y[i]) / (x[j] - x[i])))
    return slope, float(y.mean())


def window_mean(arr, dks, s, d):
    i0, i1 = dks.index(s), dks.index(d)
    return arr[:, :, i0 : i1 + 1].mean(axis=2)  # [province, year]


def anom_full(m: np.ndarray, years: list[int], fit=(1989, 2025)) -> np.ndarray:
    yrs = np.array(years)
    f = (yrs >= fit[0]) & (yrs <= fit[1])
    out = np.empty_like(m)
    for p in range(m.shape[0]):
        sl, mu = theil_sen(yrs[f].astype(float), m[p, f])
        out[p] = m[p] - (mu + sl * (yrs - yrs[f].mean()))
    return out


def anom_prior(m: np.ndarray, years: list[int], burn_in=BURN_IN) -> np.ndarray:
    """Anomaly of season Y from the Theil-Sen line fitted on seasons 1989..Y-1 only."""
    yrs = np.array(years)
    out = np.full_like(m, np.nan)
    for yi, y in enumerate(yrs):
        f = yrs < y
        if f.sum() < burn_in:
            continue
        for p in range(m.shape[0]):
            sl, mu = theil_sen(yrs[f].astype(float), m[p, f])
            out[p, yi] = m[p, yi] - (mu + sl * (y - yrs[f].mean()))
    return out


def corr(a, b):
    ok = ~(np.isnan(a) | np.isnan(b))
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def dekad_scan(arr, years, dks, yld_prov: pd.DataFrame, nat: pd.Series) -> dict:
    yidx = {y: i for i, y in enumerate(years)}
    yy = list(yld_prov.index)  # 2001-2023
    Y = yld_prov.to_numpy().T  # [province, year]
    nat_years = [y for y in nat.index if y in yidx]
    boots = [RNG.integers(0, len(yy), len(yy)) for _ in range(N_BOOT)]
    boots_nat = [RNG.integers(0, len(nat_years), len(nat_years)) for _ in range(N_BOOT)]
    res = {}
    for s in (17, 19):
        ends = [d for d in dks if d >= max(s, 19)]
        stats = {"pooled": {}, "aoi": {}, "national": {}}
        draws = {k: [] for k in stats}
        for d in ends:
            A = anom_full(window_mean(arr, dks, s, d), years)
            T = A[:, [yidx[y] for y in yy]]  # [province, year] 2001-2023
            Tn = A.mean(axis=0)[[yidx[y] for y in nat_years]]
            n_v = nat.loc[nat_years].to_numpy()
            aoi_t, aoi_y = T.mean(axis=0), np.nanmean(Y, axis=0)
            stats["pooled"][d] = corr(T.ravel(), Y.ravel())
            stats["aoi"][d] = corr(aoi_t, aoi_y)
            stats["national"][d] = corr(Tn, n_v)
            draws["pooled"].append([corr(T[:, b].ravel(), Y[:, b].ravel()) for b in boots])
            draws["aoi"].append([corr(aoi_t[b], aoi_y[b]) for b in boots])
            draws["national"].append([corr(Tn[b], n_v[b]) for b in boots_nat])
        out = {}
        for k in stats:
            r = np.array([stats[k][d] for d in ends])
            D = np.array(draws[k])  # [end, boot]
            best = int(np.argmin(r))  # most negative: hotter -> lower yield
            lo, hi = np.percentile(D, [5, 95], axis=1)
            diff = D - D[best]
            dlo, dhi = np.percentile(diff, [5, 95], axis=1)
            plateau = [ends[i] for i in range(len(ends)) if dlo[i] <= 0 <= dhi[i]]
            out[k] = {"ends": ends, "r": r.round(3).tolist(), "lo90": lo.round(3).tolist(), "hi90": hi.round(3).tolist(),
                      "best_end": ends[best], "plateau": plateau, "earliest_on_plateau": plateau[0],
                      "n": {"pooled": int((~np.isnan(Y)).sum()), "aoi": len(yy), "national": len(nat_years)}[k]}
        res[str(s)] = out
    return res


def counts_table(A: np.ndarray, years, ys, ks) -> dict:
    yrs = np.array(years)
    return {(y_, k): set(yrs[(A >= y_ - 1e-9).sum(axis=0) >= k]) for y_ in ys for k in ks}


def evaluate_rules(A: np.ndarray, years, label: str, aoi_y, nat_y, eval_years=c.EVAL_YEARS) -> list[dict]:
    rows = []
    yrs = np.array(years)
    ev = np.isin(yrs, eval_years)
    if np.isnan(A[:, ev]).any():
        raise ValueError(f"{label}: missing anomalies in scored seasons")
    for y_ in np.round(np.arange(0.1, 1.01, 0.05), 2):
        cnt = (A >= y_ - 1e-9).sum(axis=0)
        for k in range(1, 18):
            act = set(int(v) for v in yrs[ev & (cnt >= k)])
            if not act:
                break
            r = {"variant": label, "sev": float(y_), "k": k, "n_years": int(ev.sum()), "n_act": len(act),
                 "rp": round(c.weibull_rp(int(ev.sum()), len(act)), 2), "years": sorted(act),
                 "count_2026": int(cnt[years.index(2026)]), "act_2026": bool(cnt[years.index(2026)] >= k)}
            r.update(c.score(act, aoi_y, nat_y))
            rows.append(r)
    return rows


def main(out_path: str) -> None:
    arr, years, dks = c.temperature()
    yld_prov = c.province_yield_anom()
    aoi_y = yld_prov.mean(axis=1)
    nat_y = c.national_yield_anom()
    nat_long = c.national_yield_anom(start=1989)
    out = {"provinces": [c.NAMES[p] for p in c.PIDS]}

    # (a) dekad scan
    scan = dekad_scan(arr, years, dks, yld_prov, nat_long)
    out["dekad_scan"] = scan
    for s, v in scan.items():
        for k, x in v.items():
            print(f"start {s} {k:9s} n={x['n']:3d} best end {x['best_end']} r={min(x['r']):+.2f}  plateau {x['plateau']}"
                  f"  earliest {x['earliest_on_plateau']}")
            print("   ", dict(zip(x["ends"], x["r"])))
    # (b) count-of-provinces rules, prior-only vs full-record trend, two windows
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 500)
    cols = ["variant", "sev", "k", "n_act", "rp", "years", "hits_main", "hits_alt", "aoi_yield_act", "aoi_yield_other",
            "nat_yield_act", "nat_yield_other", "count_2026", "act_2026"]
    rules, anoms = [], {}
    for (s, d) in [(19, 28), (19, 27)]:
        m = window_mean(arr, dks, s, d)
        for lab, A in [("prior", anom_prior(m, years)), ("full", anom_full(m, years)),
                       ("prior15", anom_prior(m, years, burn_in=15))]:
            ev = c.EVAL_YEARS if lab != "prior15" else list(range(2004, 2026))
            name = f"{lab}|{s}-{d}"
            anoms[name] = A
            rules += evaluate_rules(A, years, name, aoi_y, nat_y, eval_years=ev)
        # (c) absolute: AOI-mean window temperature >= T, and fixed 1991-2020 baseline per province
        aoi_m = m.mean(axis=0)
        yrs = np.array(years)
        base = m[:, (yrs >= 1991) & (yrs <= 2020)].mean(axis=1, keepdims=True)
        anoms[f"fixed|{s}-{d}"] = m - base
        rules += evaluate_rules(m - base, years, f"fixed|{s}-{d}", aoi_y, nat_y)
        sl, _ = theil_sen(yrs[yrs <= 2025].astype(float), aoi_m[yrs <= 2025])
        out.setdefault("aoi_mean_temp", {})[f"{s}-{d}"] = {"values": dict(zip(years, aoi_m.round(3).tolist())),
                                                         "trend_per_decade": round(sl * 10, 3)}
    R = pd.DataFrame(rules)
    out["rules"] = R.to_dict("records")
    band = R[(R.rp >= 3.0) & (R.rp <= 5.5)]
    for v in sorted(R.variant.unique()):
        print("\n==", v)
        print(band[band.variant == v][cols].to_string(index=False))

    # absolute AOI-mean threshold: activation share by period for thresholds giving RP ~3-5 over 2001-2025
    for key, vals in out["aoi_mean_temp"].items():
        s_ = pd.Series(vals["values"])
        ev = s_.loc[c.EVAL_YEARS].sort_values(ascending=False)
        print(f"\nAOI-mean temperature {key}: trend {vals['trend_per_decade']:+.2f} degC/decade (1989-2025, Theil-Sen)")
        tab = []
        for n_act in (5, 6, 7, 8):
            T = float(ev.iloc[n_act - 1])
            per = {f"{a}-{b}": f"{int((s_.loc[a:b] >= T - 1e-9).sum())}/{b - a + 1}"
                   for a, b in [(1989, 2000), (2001, 2012), (2013, 2025)]}
            act = set(s_.index[(s_ >= T - 1e-9)]) & set(c.EVAL_YEARS)
            row = {"T": round(T, 2), "n_act": len(act), "rp": round(c.weibull_rp(25, len(act)), 2),
                   "years": sorted(act), **per, "2026": round(float(s_.loc[2026]), 2)}
            row.update(c.score(act, aoi_y, nat_y))
            tab.append(row)
            print(row)
        out.setdefault("absolute", {})[key] = tab
    out["anoms"] = {k: {c.NAMES[p]: dict(zip(years, np.round(A[i], 3).tolist())) for i, p in enumerate(c.PIDS)}
                    for k, A in anoms.items()}
    json.dump(out, open(out_path, "w"), default=str)


if __name__ == "__main__":
    main(sys.argv[1])
