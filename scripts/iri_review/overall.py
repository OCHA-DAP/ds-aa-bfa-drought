"""Overall return period: forecast trigger OR observational trigger, on one common window.

Window 2003-2025 (23 seasons): the forecast backtests need 10 earlier seasons (IRI v4/v5 start in
1993) and the observational backtests end in 2025 (2026 is provisional). Funding is all-in (either
trigger releases the full envelope), so effective RP = overall RP.

Inputs: $BFA_DATA_DIR/iri_review/{backtest,compare}.json and the observational per-season table
written by scripts/obs_review/obs_by_year.py (path as the first argument).
Writes $BFA_DATA_DIR/iri_review/overall.json.
"""

import json
import sys

import pandas as pd

import data
from backtest import IMPACT_ALT, IMPACT_MAIN

WINDOW = list(range(2003, 2026))


def years_from_grid(grid, config, method, severity, rule):
    for g in grid:
        if (g["config"], g["method"], g["severity"], g["rule"]) == (config, method, severity, rule):
            return g["activations"]
    raise KeyError((config, method, severity, rule))


def years_from_compare(cmp, system, rule, severity):
    for o in cmp["systems"][system]:
        if o["rule"] == rule and o["severity"] == severity:
            return o["activations"]
    raise KeyError((system, rule, severity))


def main(obs_csv: str) -> None:
    dd = data.data_dir() / "iri_review"
    bt = json.loads((dd / "backtest.json").read_text())
    cmp = json.loads((dd / "compare.json").read_text())
    obs = pd.read_csv(obs_csv).set_index("season")
    prop = data.local_config()["iri_proposal"]
    fcst = {
        f"{prop['label']}, thresholds from all earlier seasons":
            years_from_grid(bt["grid"], "cfg2026+feb", "prior", prop["severity"], prop["rule"]),
        f"{prop['label']}, thresholds from the previous 10 seasons":
            years_from_grid(bt["grid"], "cfg2026+feb", "rolling10", prop["severity"], prop["rule"]),
        "SEAS5, same rule type (30%, 2 of 4 months Mar-Jun), thresholds from all earlier seasons":
            years_from_compare(cmp, "SEAS5", "2 of 4 months", 30),
    }
    obsopt = {
        "ASAP any warning (level 1+) in 14+ of 17 provinces, dekads 21–26":
            "O1_asap_L1_d21-26_ge14_activated",
        "Temperature +0.5 °C above trend in 3+ of 17 provinces, 1 Jul–20 Sep":
            "O3_temp_d19-26_+0.5C_ge3_activated",
        "ASAP level 3 in 8+ provinces, or the temperature rule":
            "O5_or_asapL3k8_or_tempd19-26_activated",
    }
    n = len(WINDOW)
    rows = []
    for fname, fy in fcst.items():
        f = {y for y in fy if y in WINDOW}
        for oname, col in obsopt.items():
            o = {int(y) for y in obs.index[obs[col] == 1] if int(y) in WINDOW}
            u = f | o
            r = {"forecast": fname, "observational": oname,
                 "forecast_years": sorted(f), "obs_years": sorted(o), "overall_years": sorted(u),
                 "rp_forecast": round((n + 1) / len(f), 2) if f else None,
                 "rp_obs": round((n + 1) / len(o), 2) if o else None,
                 "rp_overall": round((n + 1) / len(u), 2) if u else None,
                 "both": sorted(f & o),
                 "impact_main_hit": sorted(u & set(IMPACT_MAIN)), "impact_alt_hit": sorted(u & set(IMPACT_ALT))}
            assert r["rp_overall"] <= min(x for x in (r["rp_forecast"], r["rp_obs"]) if x), r
            rows.append(r)
    out = {"window": [WINDOW[0], WINDOW[-1]], "n": n, "rows": rows,
           "obs_2026": {k: int(obs.loc[2026, c]) for k, c in obsopt.items()} if 2026 in obs.index else {}}
    (dd / "overall.json").write_text(json.dumps(out, indent=1))
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(t[["forecast", "observational", "rp_forecast", "rp_obs", "rp_overall", "overall_years", "impact_main_hit"]].to_string(index=False))
    print("obs 2026:", out["obs_2026"])


if __name__ == "__main__":
    main(sys.argv[1])
