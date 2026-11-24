"""Independent backtest of IRI's NextGen JAS forecast trigger over the AOI, with no look-ahead.

AOI: the old Boucle du Mouhoun, Nord, Centre-Nord and Sahel regions (see data.py).

Forecast series (Maproom, AOI area-weighted mean of the six 2026 regions):
- cfg2026:      v4 Mar + v5 Apr-Jun  (the March 2026 configuration as the Maproom serves it; 4 months)
- cfg2026+feb:  v1 Feb + v4 Mar + v5 Apr-Jun (5 months; the Maproom does not serve a v4 February
                issue, so the Feb 2025 configuration stands in for February)
- v1:           v1 Feb-Jun (the Feb 2025 configuration; 5 months)

Thresholds, per issue month and severity s: the k-th highest forecast in a reference set, with
k = round_half_up(s/100 x n) (IRI's rule).
- prior: reference = every season BEFORE the target season (expanding; what was known at the time).
  A season is scored only when at least MIN_REF earlier seasons exist.
- fixed: reference = the full record (IRI's spreadsheet method; look-ahead, for comparison).
- rolling10: reference = the 10 seasons before the target (IRI's Mali/Niger method).

The rule IRI proposed is read from config.local.json (not in git).
Writes results to $BFA_DATA_DIR/iri_review/backtest.json and prints a summary.
"""

import json

import numpy as np
import pandas as pd

import data
import trigger as T

MIN_REF = 10
SEVERITIES = list(range(5, 50, 5))
CONFIGS = {
    "cfg2026": [("prcp-v4", "mar"), ("prcp-v5", "apr"), ("prcp-v5", "may"), ("prcp-v5", "jun")],
    "cfg2026+feb": [("prcp-v1", "feb"), ("prcp-v4", "mar"), ("prcp-v5", "apr"), ("prcp-v5", "may"),
                    ("prcp-v5", "jun")],
    "v1": [("prcp-v1", m) for m in ["feb", "mar", "apr", "may", "jun"]],
}
# impact seasons (heat-and-impact page, evidence-dated): EM-DAT droughts + CERF drought allocations
IMPACT_MAIN = [2011, 2013, 2017, 2019, 2021]
IMPACT_ALT = [2011, 2014, 2017, 2019, 2022]  # the framework's target years read as growing seasons


def series(fc: pd.DataFrame, region: str, combo) -> tuple[pd.DataFrame, list[str]]:
    parts, months = [], []
    for i, (v, im) in enumerate(combo):
        lab = f"{im}_{v[-2:]}"
        s = fc[(fc.region == region) & (fc.version == v) & (fc.issue_month == im)][["year", "severity", "pnep"]].copy()
        s["issue_month"] = lab
        parts.append(s)
        months.append(lab)
    return pd.concat(parts, ignore_index=True), months


def thresholds(f: pd.DataFrame, method: str) -> pd.DataFrame:
    if method == "prior":
        mt = T.monthly_thresholds(f, method="expanding")
        mt = mt.sort_values(["issue_month", "severity", "year"]).reset_index(drop=True)
        mt["n_ref"] = mt.groupby(["issue_month", "severity"]).cumcount()  # seasons before this one
        mt.loc[mt.n_ref < MIN_REF, ["has_threshold", "exceed"]] = [False, False]
        mt.loc[mt.n_ref < MIN_REF, "threshold"] = np.nan
        return mt
    if method == "fixed":
        return T.monthly_thresholds(f, method="fixed")
    if method == "rolling10":
        return T.monthly_thresholds(f, method="rolling", window=10)
    raise ValueError(method)


def rules_for(months: list[str]) -> dict[str, str]:
    n = len(months)
    return {"single": "single month", "2in5": f"2 of {n} months", "2consec": "2 consecutive months",
            "3in5": f"3 of {n} months"}


def run(fc, region, cname, method):
    f, months = series(fc, region, CONFIGS[cname])
    f = f[f.severity.isin(SEVERITIES)]
    mt = thresholds(f, method)
    act = T.apply_rules(mt, months=months)
    return mt, act, months


def no_lookahead_check(fc, region, cname, severity, rule) -> int:
    """Recompute each season's activation from data truncated at that season; count disagreements."""
    f, months = series(fc, region, CONFIGS[cname])
    f = f[f.severity == severity]
    full = T.apply_rules(thresholds(f, "prior"), months=months).set_index("year")[rule]
    bad = 0
    for y in full.index:
        g = f[f.year <= y]
        a = T.apply_rules(thresholds(g, "prior"), months=months).set_index("year")[rule]
        bad += int(a.get(y, False) != full.loc[y])
        # scramble every later season: must not change season y
        g2 = f.copy()
        later = g2.year > y
        g2.loc[later, "pnep"] = np.random.default_rng(y).permutation(g2.loc[later, "pnep"].to_numpy().copy())
        a2 = T.apply_rules(thresholds(g2, "prior"), months=months).set_index("year")[rule]
        bad += int(a2.loc[y] != full.loc[y])
    return bad


def summarise(act: pd.DataFrame, rule: str, sev: int, obs: pd.Series, bad_rank: pd.Series) -> dict:
    g = act[act.severity == sev].set_index("year")
    yrs = sorted(g.index)
    on = sorted(int(y) for y in g.index[g[rule]])
    n, k = len(yrs), len(on)
    o = obs.reindex(yrs).dropna()
    dry_k = set(o.sort_values().index[:k]) if k else set()
    dry30 = set(o[o <= o.quantile(0.3)].index)
    br = bad_rank.reindex(yrs)
    ranked = br[br < 30].dropna()
    bad_k = set(ranked.sort_values().index[:k]) if k else set()
    return {
        "years_scored": [int(yrs[0]), int(yrs[-1])], "n": n, "k": k, "activations": on,
        "rp_weibull": round((n + 1) / k, 2) if k else None, "rp_n_over_k": round(n / k, 2) if k else None,
        "month": {int(y): g.loc[y, f"{rule}_month"] for y in on},
        "hits_driest_k_chirps": sorted(int(y) for y in set(on) & dry_k),
        "hits_driest30pct_chirps": sorted(int(y) for y in set(on) & dry30),
        "n_driest30pct": len(dry30),
        "hits_impact_main": sorted(set(on) & set(IMPACT_MAIN)),
        "hits_impact_alt": sorted(set(on) & set(IMPACT_ALT)),
        "hits_iri_bad_years_top_k": sorted(int(y) for y in set(on) & bad_k),
        "by_period": {p: sum(1 for y in on if lo <= y <= hi) for p, (lo, hi) in
                      {"to2009": (0, 2009), "2010-19": (2010, 2019), "2020+": (2020, 2100)}.items()},
        "n_by_period": {p: sum(1 for y in yrs if lo <= y <= hi) for p, (lo, hi) in
                        {"to2009": (0, 2009), "2010-19": (2010, 2019), "2020+": (2020, 2100)}.items()},
    }


def main() -> None:
    global PROP
    PROP = data.local_config()["iri_proposal"]
    fc = data.forecasts()
    ob = data.obs()
    chirps = ob[ob.region == "AOI"].set_index("year")["chirps-precip-jas"]
    bad = data.bad_years()
    bad_rank = bad[bad.predictand == "bad-years-humanitarian"].set_index("year")["rank"]
    out = {"min_ref": MIN_REF, "configs": {k: [f"{v} {m}" for v, m in c] for k, c in CONFIGS.items()},
           "results": [], "grid": [], "thresholds_2026": {}}
    for cname in CONFIGS:
        for method in ["prior", "fixed", "rolling10"]:
            mt, act, months = run(fc, "AOI", cname, method)
            for sev in SEVERITIES:
                for rule in ["single", "2in5", "2consec", "3in5"]:
                    s = summarise(act, rule, sev, chirps, bad_rank)
                    out["grid"].append({"config": cname, "method": method, "severity": sev, "rule": rule,
                                        "rule_label": rules_for(months)[rule], **{k: s[k] for k in
                                        ["n", "k", "rp_weibull", "rp_n_over_k", "activations"]}})
                    if sev == PROP["severity"] and rule == PROP["rule"]:
                        out["results"].append({"config": cname, "method": method, "severity": sev,
                                               "rule": rules_for(months)[rule], **s})
            if method == "prior":
                t = mt[(mt.severity == PROP["severity"]) & (mt.year >= 2020)][["year", "issue_month", "pnep", "threshold", "exceed"]]
                out["thresholds_2026"][cname] = t.round(2).to_dict("records")
    out["no_lookahead_disagreements"] = {c: no_lookahead_check(fc, "AOI", c, PROP["severity"], PROP["rule"])
                                         for c in CONFIGS}
    od = data.data_dir() / "iri_review"
    od.mkdir(exist_ok=True)
    (od / "backtest.json").write_text(json.dumps(out, indent=1, default=str))
    for r in out["results"]:
        print(f"{r['config']:12s} {r['method']:9s} {r['rule']:16s} n={r['n']:2d} k={r['k']:2d} RP={r['rp_weibull']} "
              f"(n/k {r['rp_n_over_k']}) {r['activations']} impact={r['hits_impact_main']} periods={r['by_period']}")
    print("no-lookahead disagreements:", out["no_lookahead_disagreements"])


if __name__ == "__main__":
    main()
