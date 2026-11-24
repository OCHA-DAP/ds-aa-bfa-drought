"""ASAP warning-trigger options for the 17 provinces: RP, activation years, impact hits, yields.

Input: the scan written by scripts/obs_review/asap_scan.js (explorer rule logic, unchanged).
Usage: uv run --no-project --with pandas --with numpy python scripts/obs_review/asap_options.py <asap_scan.json> <out.json>
"""

import json
import sys

import pandas as pd

import common as c


def main(scan_path: str, out_path: str) -> None:
    scan = json.loads(open(scan_path, encoding="utf-8").read())
    aoi_y = c.province_yield_anom().mean(axis=1)
    nat_y = c.national_yield_anom()
    rows = []
    for s in scan["settings"]:
        r = pd.DataFrame(s["rows"]).set_index("year")
        ev = r.loc[c.EVAL_YEARS]
        if not ev["valid"].all():
            continue
        n = len(ev)
        for k in range(1, 18):
            act = set(ev.index[ev["count"] >= k])
            if not act:
                break
            rp = c.weibull_rp(n, len(act))
            row = {"level": s["level"], "window": f"{s['d0']}-{s['d1']}", "cover": s["cover"], "k": k,
                   "n_years": n, "n_act": len(act), "rp": round(rp, 2), "years": sorted(act),
                   "count_2026": int(r.loc[2026, "count"]) if bool(r.loc[2026, "valid"]) else None,
                   "act_2026": bool(r.loc[2026, "valid"]) and int(r.loc[2026, "count"]) >= k}
            row.update(c.score(act, aoi_y, nat_y))
            rows.append(row)
    df = pd.DataFrame(rows)
    counts = {f"{s['level']}|{s['d0']}-{s['d1']}|{s['cover']}": {r["year"]: r["count"] for r in s["rows"]}
              for s in scan["settings"]}
    band = df[(df.rp >= 2.9) & (df.rp <= 5.5)].copy()
    band["n_hits_main"] = band.hits_main.map(len)
    band["n_hits_alt"] = band.hits_alt.map(len)
    band["yield_gap"] = band.aoi_yield_act - band.aoi_yield_other
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 400)
    cols = ["level", "window", "cover", "k", "n_act", "rp", "years", "hits_main", "hits_alt", "aoi_yield_act",
            "aoi_yield_other", "nat_yield_act", "nat_yield_other", "act_2026", "count_2026"]
    print(band.sort_values(["level", "window", "cover", "k"])[cols].to_string(index=False))
    json.dump({"options": df.to_dict("records"), "counts": counts}, open(out_path, "w"), default=str)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
