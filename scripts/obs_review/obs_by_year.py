"""Per-season table (2001-2026) for the recommended ~1-in-6 observational options -> obs_by_year.csv.

Options are pre-specified (named below), not picked by the search in targets_1in6.py, except the AND
combination, which the search found and is flagged as such.

Usage: uv run --no-project --with pandas --with numpy python scripts/obs_review/obs_by_year.py <obs_out dir>
"""

import json
import sys
from pathlib import Path

import pandas as pd

import common as c
from temp_analysis import anom_prior, window_mean

YEARS = list(range(2001, 2027))


def main(d: str) -> None:
    d = Path(d)
    asap = json.load(open(d / "asap_options.json"))["counts"]
    arr, years, dks = c.temperature()

    def asap_n(key):
        return pd.Series({int(y): v for y, v in asap[key].items()}).loc[YEARS]

    def temp_n(a, b, sev):
        A = anom_prior(window_mean(arr, dks, a, b), years)
        return pd.Series((A >= sev - 1e-9).sum(axis=0), index=years).loc[YEARS]

    comp = {
        "asapL1_d21_26": (asap_n("ge1|21-26|or"), 14),  # level>=1 crop or range, dekads 21-26, >=14 of 17
        "asapL3_d21_26": (asap_n("ge3|21-26|or"), 6),  # framework style, >=6 of 17
        "asapL3_d21_26_k8": (asap_n("ge3|21-26|or"), 8),  # tightened for the OR combination
        "asapL1_d22_28": (asap_n("ge1|22-28|or"), 14),  # loosened for the AND combination
        "temp_d19_26": (temp_n(19, 26, 0.5), 3),  # 1 Jul-20 Sep, +0.5 degC, >=3 of 17
        "temp_d19_28": (temp_n(19, 28, 0.4), 5),  # 1 Jul-10 Oct, +0.4 degC, >=5 of 17
        "temp_d19_27_0.3": (temp_n(19, 27, 0.3), 5),  # 1 Jul-30 Sep, +0.3 degC, >=5 of 17 (AND arm)
    }
    out = pd.DataFrame(index=pd.Index(YEARS, name="season"))
    out["impact_main"] = [int(y in c.IMPACT_MAIN) for y in YEARS]
    out["impact_alt"] = [int(y in c.IMPACT_ALT) for y in YEARS]
    out["yield_anom_17prov_pct"] = c.province_yield_anom().mean(axis=1).round(1).reindex(YEARS)
    out["yield_anom_national_pct"] = c.national_yield_anom().round(1).reindex(YEARS)
    acts = {}
    for name, (n, k) in comp.items():
        out[f"{name}_n_prov"] = n
        acts[name] = n >= k
    options = {
        "O1_asap_L1_d21-26_ge14": acts["asapL1_d21_26"],
        "O2_asap_L3_d21-26_ge6": acts["asapL3_d21_26"],
        "O3_temp_d19-26_+0.5C_ge3": acts["temp_d19_26"],
        "O4_temp_d19-28_+0.4C_ge5": acts["temp_d19_28"],
        "O5_or_asapL3k8_or_tempd19-26": acts["asapL3_d21_26_k8"] | acts["temp_d19_26"],
        "O6_and_asapL1d22-28k14_and_tempd19-27": acts["asapL1_d22_28"] & acts["temp_d19_27_0.3"],
    }
    ev = [y for y in YEARS if y <= 2025]
    summary = {}
    for name, a in options.items():
        out[f"{name}_activated"] = a.astype(int)
        yrs = [y for y in ev if a.loc[y]]
        summary[name] = {"years_2001_2025": yrs, "n": len(yrs), "rp": round((len(ev) + 1) / len(yrs), 2),
                         "act_2026": bool(a.loc[2026]),
                         "hits_main": sorted(set(yrs) & c.IMPACT_MAIN)}
        print(name, summary[name])
    out.to_csv(d / "obs_by_year.csv")
    json.dump(summary, open(d / "obs_by_year_summary.json", "w"), indent=1)
    print("wrote", d / "obs_by_year.csv", out.shape)


if __name__ == "__main__":
    main(sys.argv[1])
