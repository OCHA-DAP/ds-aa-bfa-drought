"""Search the Maproom configurations (version, issue months, region, threshold method, years) for the
one behind IRI's Burkina Faso candidate table, which IRI shared with us (not public).

The table is read at run time from a path given on the command line; none of its values are written
into this repo. Each block of the table is compared with the counts each configuration produces.

Usage: BFA_DATA_DIR=... uv run --no-project --with pandas --with openpyxl --with scipy \
           python reproduce.py <table.xlsx>
"""

import itertools
import sys

import numpy as np
import pandas as pd

import data
import trigger as T

RULES = {"rule_single": "single", "rule_2in5": "2in5", "rule_2consec": "2consec", "rule_3in5": "3in5"}
MONTH_NUM = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6}


def read_iri(path: str) -> pd.DataFrame:
    x = pd.read_excel(path, sheet_name=0, header=1)
    x = x.iloc[:, :13]
    x.columns = ["severity", "rule", "n_act", "rate", "rp", "mean_month", "accuracy", "hit_rate",
                 "far", "wa", "aiv", "fta", "wi"]
    x = x.dropna(subset=["severity"])
    x["rule"] = x["rule"].map(RULES)
    x["severity"] = x["severity"].astype(int)
    return x


def activations(fc_long, months, method, years, maproom=None):
    f = fc_long[fc_long.year.isin(years)]
    mt = T.monthly_thresholds(f, method=method, window=10, maproom=maproom)
    return T.apply_rules(mt, months=months)


def main(path: str) -> None:
    iri = read_iri(path)
    fc = data.forecasts()
    combos = {
        "v1 feb-jun": [("prcp-v1", m) for m in ["feb", "mar", "apr", "may", "jun"]],
        "v1 jan-may": [("prcp-v1", m) for m in ["jan", "feb", "mar", "apr", "may"]],
        "v1 feb,v4 mar-jun": [("prcp-v1", "feb")] + [("prcp-v4", m) for m in ["mar", "apr", "may", "jun"]],
        "v1 feb-mar,v5 apr-jun": [("prcp-v1", "feb"), ("prcp-v1", "mar")] + [("prcp-v5", m) for m in ["apr", "may", "jun"]],
        "v4 mar, v1 feb, v5 apr-jun": [("prcp-v1", "feb"), ("prcp-v4", "mar")] + [("prcp-v5", m) for m in ["apr", "may", "jun"]],
    }
    year_sets = {"1991-2025": list(range(1991, 2026)), "1991-2024": list(range(1991, 2025))}
    methods = ["fixed", "expanding_incl", "expanding", "rolling"]
    target = iri.set_index(["severity", "rule"])
    res = []
    for (cname, combo), region, (yname, yrs), method in itertools.product(
        combos.items(), ["BF", "AOI"], year_sets.items(), methods
    ):
        months = [f"{im}_{i}" for i, (_, im) in enumerate(combo)]  # unique labels when two versions share a month
        lab = {}
        for i, (v, im) in enumerate(combo):
            lab[(v, im)] = f"{im}_{i}"
        parts = []
        for i, (v, im) in enumerate(combo):
            s = fc[(fc.region == region) & (fc.version == v) & (fc.issue_month == im)][["year", "severity", "pnep"]].copy()
            s["issue_month"] = lab[(v, im)]
            parts.append(s)
        f = pd.concat(parts, ignore_index=True)
        f = f[f.severity.isin(iri.severity.unique())]
        a = activations(f, months, method, yrs)
        if a.empty:
            continue
        n_c = n_perf = n_month = 0
        for (sev, rule), row in target.iterrows():
            g = a[a.severity == sev]
            k = int(g[rule].sum())
            n_c += k == row.n_act
            n_perf += k == row.wa + row.aiv
            mm = g[f"{rule}_month"].dropna().map(lambda s: MONTH_NUM[s.split("_")[0]])
            n_month += bool(len(mm)) and abs(mm.mean() - row.mean_month) < 1e-6
        res.append({"combo": cname, "region": region, "years": yname, "method": method,
                    "match_C": n_c, "match_perf_nact": n_perf, "match_mean_month": n_month,
                    "n_scored": int(a.year.nunique())})
    r = pd.DataFrame(res).sort_values(["match_C", "match_perf_nact"], ascending=False)
    print(r.head(25).to_string(index=False))
    r.to_csv(data.data_dir() / "iri_maproom" / "reproduce_search.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1])
