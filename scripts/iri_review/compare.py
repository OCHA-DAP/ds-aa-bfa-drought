"""IRI vs SEAS5 run through the SAME trigger rule, prior-only thresholds, same AOI and seasons.

Rule family (IRI's): per issue month, the forecast "exceeds" when it is among the driest s% of the
forecasts for that issue month in all EARLIER seasons (k = round_half_up(s/100 x n)); activation =
2 of the monitored months (also: single month). Monitored months Mar-Jun (SEAS5 reaches all of JAS
only from March). IRI = the March 2026 configuration (v4 Mar, v5 Apr-Jun); SEAS5 = AOI-mean
ensemble-mean JAS rainfall (driest = lowest). SEAS5's reference starts in 1981, IRI's in 1993; both
are scored 2003-2026 (24 seasons) and need at least 10 earlier seasons.

Each activation set is scored against CHIRPS v2 JAS over the AOI (ranks within 2003-2026; 2026 from
the CHC COG) and the impact seasons. The severity for each system is chosen so that it activates
4 times (RP 6.25), the user's 1-in-6 target.

Writes $BFA_DATA_DIR/iri_review/compare.json.
"""

import json

import numpy as np
import pandas as pd

import data
import trigger as T
from backtest import IMPACT_ALT, IMPACT_MAIN
from skill import aoi_mean, seasonal

SCORE_YEARS = list(range(2003, 2027))
MIN_REF = 10


def chirps_aoi() -> pd.Series:
    d = json.loads((data.data_dir() / "iri_review" / "chirps_aoi_jas.json").read_text())
    r = d["res"]["chirps_v2"]
    s = {int(k): v for k, v in r.items() if k.isdigit()}
    if 2026 not in s:  # the cube ends in August 2026: add September from the CHC COG
        s[2026] = r["2026_JA"] + d["sep2026_chirps_v2_cog"]
    return pd.Series(s).sort_index()


def run_rule(long: pd.DataFrame, months: list[str], higher_is_drier: bool) -> pd.DataFrame:
    """long: year, issue_month, severity, pnep (score). Prior-only expanding thresholds."""
    f = long.copy()
    if not higher_is_drier:
        f["pnep"] = -f["pnep"]
    mt = T.monthly_thresholds(f, method="expanding")
    mt = mt.sort_values(["issue_month", "severity", "year"]).reset_index(drop=True)
    mt["n_ref"] = mt.groupby(["issue_month", "severity"]).cumcount()
    mt.loc[mt.n_ref < MIN_REF, ["has_threshold", "exceed"]] = [False, False]
    return T.apply_rules(mt, months=months)


def score(on: list[int], chirps: pd.Series) -> dict:
    c = chirps.loc[SCORE_YEARS]
    rank = c.rank().astype(int)  # 1 = driest of the 24
    k = len(on)
    driest_k = set(c.sort_values().index[:k])
    return {"activations": on, "k": k, "rp": round((len(SCORE_YEARS) + 1) / k, 2) if k else None,
            "chirps_rank_of_24": {int(y): int(rank[y]) for y in on},
            "hits_driest_k": sorted(int(y) for y in set(on) & driest_k),
            "hits_driest_6": sorted(int(y) for y in set(on) & set(c.sort_values().index[:6])),
            "median_chirps_pct_of_mean": round(float((c.loc[on] / c.mean() * 100).median()), 0) if k else None,
            "hits_impact_main": sorted(set(on) & set(IMPACT_MAIN)),
            "hits_impact_alt": sorted(set(on) & set(IMPACT_ALT))}


def main() -> None:
    chirps = chirps_aoi()
    fc = data.forecasts()
    iri_months = [("prcp-v4", "mar"), ("prcp-v5", "apr"), ("prcp-v5", "may"), ("prcp-v5", "jun")]
    parts = []
    for v, im in iri_months:
        s = fc[(fc.region == "AOI") & (fc.version == v) & (fc.issue_month == im)][["year", "severity", "pnep"]].copy()
        s["issue_month"] = im
        parts.append(s)
    iri = pd.concat(parts)
    dd = data.data_dir() / "db"
    poly = pd.read_csv(dd / "polygon_aoi.csv").set_index("pcode")["area"]
    s5 = aoi_mean(pd.read_parquet(dd / "seas5_aoi.parquet"), poly)
    rows = []
    for im, name in [(3, "mar"), (4, "apr"), (5, "may"), (6, "jun")]:
        sc = seasonal(s5, [7, 8, 9], issue_month=im)
        for sev in range(5, 55, 5):
            rows += [{"year": y, "issue_month": name, "severity": sev, "pnep": v} for y, v in sc.items()]
    seas5 = pd.DataFrame(rows)
    months = ["mar", "apr", "may", "jun"]
    out = {"score_years": [SCORE_YEARS[0], SCORE_YEARS[-1]], "chirps_driest_6": [int(y) for y in chirps.loc[SCORE_YEARS].sort_values().index[:6]],
           "systems": {}}
    for sysname, long, hid in [("IRI (Mar 2026 config)", iri, True), ("SEAS5", seas5, False)]:
        act = run_rule(long, months, hid)
        act = act[act.year.isin(SCORE_YEARS)]
        options = []
        for rule in ["2in5", "single"]:
            for sev, g in act.groupby("severity"):
                on = sorted(int(y) for y in g.year[g[rule]])
                options.append({"rule": "2 of 4 months" if rule == "2in5" else "single month", "severity": int(sev),
                                **score(on, chirps)})
        out["systems"][sysname] = options
    (data.data_dir() / "iri_review" / "compare.json").write_text(json.dumps(out, indent=1))
    print("CHIRPS driest 6 of 2003-2026:", out["chirps_driest_6"])
    for sysname, opts in out["systems"].items():
        print("==", sysname)
        for o in opts:
            if o["k"] and 3 <= o["k"] <= 6:
                print(f"  {o['rule']:14s} s={o['severity']:2d} k={o['k']} RP={o['rp']} {o['activations']} "
                      f"ranks={list(o['chirps_rank_of_24'].values())} driest-k hits={o['hits_driest_k']} "
                      f"driest6={o['hits_driest_6']} median%={o['median_chirps_pct_of_mean']} impact={o['hits_impact_main']}")


if __name__ == "__main__":
    main()
