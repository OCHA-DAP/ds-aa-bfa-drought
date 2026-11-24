"""Observational options at about 1-in-6 years (4 activations in 2001-2025 -> RP 6.5; 5 -> RP 5.2).

1. ASAP rules with 4-5 activations, preferring K >= 2 (not one province).
2. Temperature rules (prior-only trend) with 4-5 activations, windows ending 10 Sep (dekad 25),
   20 Sep (26, when the ASAP window closes), 30 Sep (27) and 10 Oct (28).
3. One combined observational trigger: ASAP OR temperature (each tightened) and ASAP AND temperature
   (each loosened), at 4-5 activations.
4. Per-season table 2001-2026 for the recommended options -> obs_by_year.csv.

Usage: uv run --no-project --with pandas --with numpy python scripts/obs_review/targets_1in6.py <obs_out dir>
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import common as c
from temp_analysis import anom_prior, window_mean

EV = c.EVAL_YEARS
N = len(EV)
WINDOWS_T = [(19, 25), (19, 26), (19, 27), (19, 28)]
SEVS = [round(x, 2) for x in np.arange(0.1, 1.01, 0.05)]


def hits(years):
    return sorted(set(years) & c.IMPACT_MAIN & set(c.SCORE_MAIN))


def main(d: str) -> None:
    d = Path(d)
    asap_counts = json.load(open(d / "asap_options.json"))["counts"]
    scan = json.load(open(d / "temp_results.json"))["dekad_scan"]["19"]
    aoi_y = c.province_yield_anom().mean(axis=1)
    nat_y = c.national_yield_anom()

    # ---- candidate rules: name -> (count series 2001-2026, k)
    asap_rules = {}
    for key, cnt in asap_counts.items():
        s = pd.Series({int(y): v for y, v in cnt.items()})
        for k in range(1, 18):
            asap_rules[f"ASAP {key} K>={k}"] = (s, k)
    arr, years, dks = c.temperature()
    temp_rules, temp_counts = {}, {}
    for (a, b) in WINDOWS_T:
        A = anom_prior(window_mean(arr, dks, a, b), years)
        for sev in SEVS:
            s = pd.Series((A >= sev - 1e-9).sum(axis=0), index=years)
            temp_counts[(a, b, sev)] = s
            for k in range(1, 18):
                temp_rules[f"TEMP d{a}-{b} +{sev:.2f}C K>={k}"] = (s, k)

    def act(rule):
        s, k = rule
        return frozenset(y for y in EV if s.loc[y] >= k)

    def row(name, yrs, extra=None):
        r = {"rule": name, "n_act": len(yrs), "rp": round(c.weibull_rp(N, len(yrs)), 2) if yrs else None,
             "years": sorted(yrs)}
        r.update(c.score(set(yrs), aoi_y, nat_y))
        r["yield_gap"] = (r["aoi_yield_act"] - r["aoi_yield_other"]) if r["aoi_yield_act"] is not None else None
        if extra:
            r.update(extra)
        return r

    A_act = {n: act(r) for n, r in asap_rules.items()}
    T_act = {n: act(r) for n, r in temp_rules.items()}

    def stable(rule_name, rules, acts):
        """Same activation set at K-1 or K+1 (not resting on one province)."""
        s, k = rules[rule_name]
        nb = [acts.get(rule_name.rsplit("K>=", 1)[0] + f"K>={kk}") for kk in (k - 1, k + 1)]
        return any(x == acts[rule_name] for x in nb if x is not None)

    pd.set_option("display.width", 260, "display.max_colwidth", 70, "display.max_rows", 200)
    cols = ["rule", "n_act", "rp", "years", "hits_main", "hits_alt", "aoi_yield_act", "aoi_yield_other", "yield_gap"]

    # ---- 1. ASAP at 4-5 activations, K >= 2
    rowsA = [row(n, y, {"k": asap_rules[n][1], "stable": stable(n, asap_rules, A_act)})
             for n, y in A_act.items() if len(y) in (4, 5) and asap_rules[n][1] >= 2]
    RA = pd.DataFrame(rowsA)
    RA["n_hits"] = RA.hits_main.map(len)
    RA = RA.sort_values(["n_act", "n_hits", "yield_gap"], ascending=[True, False, True])
    print("== ASAP, 4-5 activations, K>=2 (best 12 per n_act)")
    for n_act, g in RA.groupby("n_act"):
        print(g.head(12)[cols + ["stable"]].to_string(index=False))

    # ---- 2. temperature at 4-5 activations, by window
    rowsT = [row(n, y, {"k": temp_rules[n][1], "stable": stable(n, temp_rules, T_act)})
             for n, y in T_act.items() if len(y) in (4, 5)]
    RT = pd.DataFrame(rowsT)
    RT["n_hits"] = RT.hits_main.map(len)
    RT["window"] = RT.rule.str.extract(r"d(\d+-\d+)")[0]
    print("\n== TEMPERATURE (prior-only), 4-5 activations, stable rules only, best 6 per window x n_act")
    for (w, n_act), g in RT[RT.stable].sort_values(["n_hits", "yield_gap"], ascending=[False, True]).groupby(["window", "n_act"]):
        print(f"-- window {w}, {n_act} activations, r with yield (17-prov mean) = "
              f"{dict(zip(scan['aoi']['ends'], scan['aoi']['r']))[int(w.split('-')[1])]:+.2f}")
        print(g.head(6)[cols].to_string(index=False))

    # ---- 3. combined single trigger
    combos = []
    A_items = [(n, y) for n, y in A_act.items() if asap_rules[n][1] >= 2 and 1 <= len(y) <= 8]
    T_items = [(n, y) for n, y in T_act.items() if 1 <= len(y) <= 8 and stable(n, temp_rules, T_act)]
    for an, ay in A_items:
        for tn, ty in T_items:
            u, i = ay | ty, ay & ty
            if len(u) in (4, 5):
                combos.append(("OR", an, tn, u, ay, ty))
            if len(i) in (4, 5):
                combos.append(("AND", an, tn, i, ay, ty))
    rowsC = []
    for op, an, tn, yrs, ay, ty in combos:
        r = row(f"{an} {op} {tn}", yrs, {"op": op, "asap": an, "temp": tn, "asap_years": sorted(ay),
                                           "temp_years": sorted(ty), "overlap": sorted(ay & ty)})
        rowsC.append(r)
    RC = pd.DataFrame(rowsC)
    RC["n_hits"] = RC.hits_main.map(len)
    print(f"\n== COMBINED: {len(RC)} combinations at 4-5 activations (searched: best are optimistic)")
    for (op, n_act), g in RC.groupby(["op", "n_act"]):
        g = g.sort_values(["n_hits", "yield_gap"], ascending=[False, True])
        print(f"-- {op}, {n_act} activations: best hits = {g.n_hits.max()}, share of combos with that = "
              f"{(g.n_hits == g.n_hits.max()).mean():.2f}")
        print(g.head(6)[["rule", "years", "hits_main", "hits_alt", "yield_gap", "overlap"]].to_string(index=False))

    json.dump({"asap": RA.to_dict("records"), "temp": RT.to_dict("records"), "combined": RC.to_dict("records")},
              open(d / "targets_1in6.json", "w"), default=str)


if __name__ == "__main__":
    main(sys.argv[1])
