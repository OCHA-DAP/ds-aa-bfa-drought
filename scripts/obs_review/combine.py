"""Combined return periods (ASAP option OR temperature rule) and drift of the temperature rules by period.

Usage: uv run --no-project --with pandas --with numpy python scripts/obs_review/combine.py <obs_out dir>
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import common as c


def asap_years(opts, level, window, cover, k):
    m = [o for o in opts if o["level"] == level and o["window"] == window and o["cover"] == cover and o["k"] == k]
    return set(m[0]["years"]), m[0]


def temp_years(anoms, variant, sev, k, years=c.EVAL_YEARS):
    a = pd.DataFrame(anoms[variant])
    a.index = a.index.astype(int)
    cnt = (a >= sev - 1e-9).sum(axis=1)
    ok = a.notna().all(axis=1)
    return {int(y) for y in cnt.index if y in years and ok.loc[y] and cnt.loc[y] >= k}, cnt


def main(d: str) -> None:
    d = Path(d)
    A = json.load(open(d / "asap_options.json"))["options"]
    T = json.load(open(d / "temp_results.json"))
    aoi_y = c.province_yield_anom().mean(axis=1)
    nat_y = c.national_yield_anom()
    n = len(c.EVAL_YEARS)

    asap = {
        "A1 L>=3 OR d21-26 K>=5": ("ge3", "21-26", "or", 5),
        "A2 L>=1 OR d22-28 K>=15": ("ge1", "22-28", "or", 15),
        "A3 L4 rangeland d22-28 K>=1": ("eq4", "22-28", "range", 1),
        "A4 L>=2 OR d21-26 K>=8": ("ge2", "21-26", "or", 8),
    }
    temp = {
        "T1 prior-trend +0.3C K>=5 d19-28": ("prior|19-28", 0.3, 5),
        "T1b prior-trend +0.3C K>=4 d19-28": ("prior|19-28", 0.3, 4),
        "T2 fixed 1991-2020 +0.5C K>=3 d19-28": ("fixed|19-28", 0.5, 3),
    }
    out = {"combined": [], "drift": {}, "fixed_thresholds": {}}
    for an, a in asap.items():
        ya, _ = asap_years(A, *a)
        for tn, t in temp.items():
            yt, _ = temp_years(T["anoms"], *t)
            u = ya | yt
            row = {"asap": an, "temp": tn, "asap_rp": round(c.weibull_rp(n, len(ya)), 2),
                   "temp_rp": round(c.weibull_rp(n, len(yt)), 2), "overall_rp": round(c.weibull_rp(n, len(u)), 2),
                   "both": sorted(ya & yt), "years": sorted(u)}
            assert row["overall_rp"] <= min(row["asap_rp"], row["temp_rp"]) + 1e-9
            row.update(c.score(u, aoi_y, nat_y))
            out["combined"].append(row)
    pd.set_option("display.width", 250, "display.max_colwidth", 80)
    print(pd.DataFrame(out["combined"])[["asap", "temp", "asap_rp", "temp_rp", "overall_rp", "both", "years",
                                          "hits_main", "hits_alt", "aoi_yield_act", "aoi_yield_other"]].to_string(index=False))

    # drift: activation share by period (full-record and fixed variants can be scored from 1989)
    periods = [(1989, 2000), (2001, 2012), (2013, 2025)]
    for name, (variant, sev, k) in {"T1 full-record trend +0.3C K>=5": ("full|19-28", 0.3, 5),
                                    "T1 prior-only trend +0.3C K>=5": ("prior|19-28", 0.3, 5),
                                    "T2 fixed 1991-2020 +0.5C K>=3": ("fixed|19-28", 0.5, 3)}.items():
        res = {}
        for a, b in periods:
            ys = list(range(a, b + 1))
            yt, cnt = temp_years(T["anoms"], variant, sev, k, years=ys)
            valid = [y for y in ys if not np.isnan(pd.DataFrame(T["anoms"][variant]).rename(index=int).loc[y]).any()]
            res[f"{a}-{b}"] = {"activated": sorted(yt), "n_valid": len(valid)}
        res["2026_count"] = int(temp_years(T["anoms"], variant, sev, k, years=[2026])[1].loc[2026])
        out["drift"][name] = res
        print(name, res)

    # T2 as absolute numbers: each province's 1991-2020 mean (dekads 19-28) + 0.5 degC
    arr, years, dks = c.temperature()
    yrs = np.array(years)
    m = arr[:, :, dks.index(19): dks.index(28) + 1].mean(axis=2)
    base = m[:, (yrs >= 1991) & (yrs <= 2020)].mean(axis=1)
    out["fixed_thresholds"] = {c.NAMES[p]: round(float(base[i] + 0.5), 2) for i, p in enumerate(c.PIDS)}
    print("T2 province thresholds (degC):", out["fixed_thresholds"])
    json.dump(out, open(d / "combined.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1])
