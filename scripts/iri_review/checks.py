"""Checks behind the headline statements on the review page.

1. National (BF) instead of AOI for the proposed rule: does the region change the picture?
2. Forecast level by period, for IRI and SEAS5 (SEAS5 hindcasts to 2016, operational from 2017).
3. For every activation set, the chance probability of its hit counts (hypergeometric: activation
   years drawn at random from the scored seasons; impact hits only over seasons the impact record covers).
4. The published 2025-framework SEAS5 backtest years, scored the same way (they used full-record
   thresholds and the JJA / ASO targets; the pixel-area rule was not re-run prior-only).
5. Where the full-record activations of the proposed rule fall in time.

Writes $BFA_DATA_DIR/iri_review/checks.json.
"""

import json
import sys

import pandas as pd

import data
import trigger as T
from backtest import IMPACT_MAIN, run
from compare import SCORE_YEARS, chirps_aoi
from skill import aoi_mean, seasonal

IMPACT_RECORD_END = 2023  # last season the impact record can score (temperature-explorer meta: impact_record_years.main)


def chance(on, scored, targets) -> dict:
    on = [y for y in on if y in scored]
    tg = [y for y in targets if y in scored]
    hits = len(set(on) & set(tg))
    p = T.p_hits_by_chance(len(scored), len(on), len(tg), hits) if on else None
    return {"k": len(on), "n": len(scored), "targets": len(tg), "hits": hits,
            "expected_by_chance": round(len(on) * len(tg) / len(scored), 2), "p_at_least": round(p, 2) if p is not None else None}


def main(obs_csv: str) -> None:
    cfg = data.local_config()
    prop = cfg["iri_proposal"]
    fc = data.forecasts()
    out = {}
    # 1. national vs AOI
    nat = []
    for region in ["AOI", "BF"]:
        for cname in ["cfg2026", "cfg2026+feb"]:
            for method in ["prior", "fixed", "rolling10"]:
                _, act, _ = run(fc, region, cname, method)
                g = act[act.severity == prop["severity"]]
                on = sorted(int(y) for y in g.year[g[prop["rule"]]])
                n = int(g.year.nunique())
                nat.append({"region": region, "config": cname, "method": method, "n": n, "k": len(on),
                            "rp": round((n + 1) / len(on), 2) if on else None, "activations": on})
    out["national_vs_aoi"] = nat
    # 5. full-record activations by period
    for r in nat:
        if r["method"] == "fixed":
            r["by_period"] = {"1993-2001": sum(y <= 2001 for y in r["activations"]),
                              "2002-2009": sum(2002 <= y <= 2009 for y in r["activations"]),
                              "2010-2019": sum(2010 <= y <= 2019 for y in r["activations"]),
                              "2020+": sum(y >= 2020 for y in r["activations"])}
    # 2. forecast level by period
    chirps = chirps_aoi()
    dd = data.data_dir() / "db"
    poly = pd.read_csv(dd / "polygon_aoi.csv").set_index("pcode")["area"]
    s5 = aoi_mean(pd.read_parquet(dd / "seas5_aoi.parquet"), poly)
    per = {"1993-2009": (1993, 2009), "2010-2016": (2010, 2016), "2017-2019": (2017, 2019), "2020-2025": (2020, 2025), "2026": (2026, 2026)}
    lev = {"CHIRPS v2 JAS (mm)": {k: round(float(chirps.loc[a:b].mean()), 0) for k, (a, b) in per.items()}}
    for im, name in [(3, "mar"), (4, "apr"), (5, "may"), (6, "jun")]:
        sc = seasonal(s5, [7, 8, 9], issue_month=im)
        lev[f"SEAS5 {name} JAS (mm)"] = {k: round(float(sc.loc[a:b].mean()), 0) for k, (a, b) in per.items()}
    f = fc[(fc.region == "AOI") & (fc.severity == prop["severity"])]
    for (v, im), g in f[f.version.isin(["prcp-v4", "prcp-v5"])].groupby(["version", "issue_month"]):
        s = g.set_index("year")["pnep"]
        lev[f"IRI {v} {im} P(below p{prop['severity']}) %"] = {k: round(float(s.loc[a:b].mean()), 1) for k, (a, b) in per.items()}
    out["levels_by_period"] = lev
    # observed frequency of the same event the forecast is about: JAS below its 35th percentile (1991-2020 base)
    p35 = chirps.loc[1991:2020].quantile(prop["severity"] / 100)
    out["obs_below_pctl_by_period"] = {k: {"n_below": int((chirps.loc[a:b] < p35).sum()), "n": int(chirps.loc[a:b].size)}
                                       for k, (a, b) in per.items()}
    # 3/4. chance probabilities for each activation set on 2003-2026 (CHIRPS) / 2003-2025 (impact)
    driest6 = list(chirps.loc[SCORE_YEARS].sort_values().index[:6])
    cmp = json.loads((data.data_dir() / "iri_review" / "compare.json").read_text())
    obs = pd.read_csv(obs_csv).set_index("season")
    sets = {
        "IRI 40%, 2 of 4, prior": next(o for o in cmp["systems"]["IRI (Mar 2026 config)"] if o["rule"] == "2 of 4 months" and o["severity"] == 40)["activations"],
        "SEAS5 30%, 2 of 4, prior": next(o for o in cmp["systems"]["SEAS5"] if o["rule"] == "2 of 4 months" and o["severity"] == 30)["activations"],
        "SEAS5 2025 framework (published, full-record)": cfg["old_setup_2025_published_years"],
        "ASAP level 1+ in 14+ of 17": [int(y) for y in obs.index[obs["O1_asap_L1_d21-26_ge14_activated"] == 1]],
        "Temperature +0.5 C in 3+ of 17": [int(y) for y in obs.index[obs["O3_temp_d19-26_+0.5C_ge3_activated"] == 1]],
    }
    ch = {}
    for name, on in sets.items():
        if name.startswith(("ASAP", "Temp")):
            scored_c = list(range(2001, 2026))
        elif "published" in name:
            scored_c = list(range(cfg["old_setup_2025_window"][0], cfg["old_setup_2025_window"][1] + 1))
        else:
            scored_c = SCORE_YEARS
        d6 = list(chirps.loc[scored_c].sort_values().index[:6])
        ch[name] = {"activations": [y for y in on if y in scored_c],
                    "chirps_rank": {int(y): int(chirps.loc[scored_c].rank().loc[y]) for y in on if y in scored_c},
                    "driest6": d6,
                    "driest6_hits": chance(on, scored_c, d6),
                    "impact_hits": chance(on, [y for y in scored_c if y <= IMPACT_RECORD_END], IMPACT_MAIN)}
    out["chance"] = ch
    out["driest6_2003_2026"] = [int(y) for y in driest6]
    (data.data_dir() / "iri_review" / "checks.json").write_text(json.dumps(out, indent=1, default=int))
    print(pd.DataFrame(nat).to_string(index=False))
    print(pd.DataFrame(lev).T.to_string())
    for k, v in ch.items():
        print(k, v["activations"], v["chirps_rank"], "driest6", v["driest6_hits"], "impact", v["impact_hits"])


if __name__ == "__main__":
    main(sys.argv[1])
