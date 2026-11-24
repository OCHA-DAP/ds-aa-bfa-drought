"""How well do IRI's NextGen JAS forecasts and ECMWF SEAS5 predict AOI rainfall?

Same AOI (old Boucle du Mouhoun, Nord, Centre-Nord, Sahel), same target (JAS total), same years.
Observations: CHIRPS JAS (Maproom, AOI area-weighted) and ERA5 (team DB, AOI area-weighted).
IRI score: probability of JAS below its s-th percentile (higher = drier); SEAS5 score: AOI-mean
ensemble-mean JAS rainfall (lower = drier). Both are oriented so that "drier forecast" = higher.

Metrics: Spearman rho between the dryness score and observed dryness (minus rainfall) with a
90% bootstrap interval; ROC AUC for the observed driest 30% of seasons; hits at a 1-in-5 frequency
(top 20% of forecasts vs driest 20% of seasons); and the same rho after removing each season's
prior-10-season mean from both forecast and observation (the view a rolling or prior-only
threshold sees).

Also scores the old SEAS5 framework set-ups on their own targets (2025: Mar issue for JJA, Jul
issue for ASO; 2026: Apr issue for JJASO) against ERA5 (and CHIRPS where the Maproom has the season).

Writes $BFA_DATA_DIR/iri_review/skill.json.
"""

import json

import numpy as np
import pandas as pd
from scipy import stats

import data

YEARS = list(range(1993, 2026))  # v4/v5 start in 1993; CHIRPS in the Maproom ends in 2025
SEV = 30
AOI1 = ["BF46", "BF49", "BF54", "BF56"]
rng = np.random.default_rng(0)


def aoi_mean(df: pd.DataFrame, area: pd.Series) -> pd.DataFrame:
    x = df[df.adm_level == 1].copy()
    x["w"] = x.pcode.map(area)
    keys = [c for c in df.columns if c not in ("pcode", "adm_level", "mean", "w")]
    return x.assign(wm=x["mean"] * x.w).groupby(keys).agg(wm=("wm", "sum"), w=("w", "sum")).assign(
        mean=lambda g: g.wm / g.w)[["mean"]].reset_index()


def seasonal(df, months, issue_month=None):
    d = df.copy()
    d["vm"] = pd.to_datetime(d.valid_date).dt.month
    d["year"] = pd.to_datetime(d.valid_date).dt.year
    if issue_month is not None:
        d = d[pd.to_datetime(d.issued_date).dt.month == issue_month]
    d = d[d.vm.isin(months)]
    g = d.groupby("year")["mean"].agg(["mean", "count"])
    return g.loc[g["count"] == len(months), "mean"] * 30.4 * len(months)  # mm per season (approx.)


def prior_anom(s: pd.Series, w=10) -> pd.Series:
    return pd.Series({y: s.loc[y] - s.loc[[x for x in s.index if y - w <= x < y]].mean()
                      for y in s.index if sum(1 for x in s.index if y - w <= x < y) == w})


def metrics(score: pd.Series, obs: pd.Series, years) -> dict:
    yrs = [y for y in years if y in score.index and y in obs.index and pd.notna(score.loc[y]) and pd.notna(obs.loc[y])]
    f, o = score.loc[yrs].to_numpy(float), -obs.loc[yrs].to_numpy(float)  # o: higher = drier
    rho = stats.spearmanr(f, o).statistic
    boots = []
    for _ in range(2000):
        i = rng.integers(0, len(f), len(f))
        boots.append(stats.spearmanr(f[i], o[i]).statistic)
    dry = o >= np.quantile(o, 0.7)
    auc = stats.mannwhitneyu(f[dry], f[~dry]).statistic / (dry.sum() * (~dry).sum())
    k = round(len(f) / 5)
    top_f = set(np.argsort(-f)[:k])
    top_o = set(np.argsort(-o)[:k])
    # year-to-year skill without the shared trend: Spearman of residuals from a linear fit on year
    yy = np.array(yrs, float)
    rf = f - np.polyval(np.polyfit(yy, f, 1), yy)
    ro = o - np.polyval(np.polyfit(yy, o, 1), yy)
    rho_dt = stats.spearmanr(rf, ro).statistic
    fa, oa = prior_anom(score.loc[yrs]), prior_anom(obs.loc[yrs])
    common = fa.index.intersection(oa.index)
    rho_anom = stats.spearmanr(fa.loc[common], -oa.loc[common]).statistic
    return {"n": len(yrs), "years": [yrs[0], yrs[-1]], "rho": round(float(rho), 2),
            "rho_ci90": [round(float(np.nanquantile(boots, q)), 2) for q in (0.05, 0.95)],
            "auc_dry30": round(float(auc), 2), "hits_1in5": f"{len(top_f & top_o)} of {k}",
            "rho_detrended": round(float(rho_dt), 2),
            "rho_prior10_anom": round(float(rho_anom), 2), "n_anom": int(len(common))}


def main() -> None:
    dd = data.data_dir() / "db"
    poly = pd.read_csv(dd / "polygon_aoi.csv").set_index("pcode")["area"]
    s5 = aoi_mean(pd.read_parquet(dd / "seas5_aoi.parquet"), poly)
    e5 = aoi_mean(pd.read_parquet(dd / "era5_aoi.parquet"), poly)
    ob = data.obs()
    chirps = ob[ob.region == "AOI"].set_index("year")["chirps-precip-jas"]
    chirps5 = ob[ob.region == "AOI"].set_index("year")["chirps-precip-jjaso"]
    era_jas = seasonal(e5, [7, 8, 9])
    obs_sets = {"CHIRPS": chirps, "ERA5": era_jas}
    out = {"years": [YEARS[0], YEARS[-1]], "severity": SEV, "obs_agreement": {}, "jas": [], "old_setups": [], "2026": {}}
    out["obs_agreement"]["chirps_vs_era5_jas_rho"] = round(float(stats.spearmanr(
        chirps.loc[YEARS], era_jas.loc[YEARS]).statistic), 2)

    fc = data.forecasts()
    fc = fc[(fc.region == "AOI") & (fc.severity == SEV)]
    for (v, im), g in fc.groupby(["version", "issue_month"]):
        sc = g.set_index("year")["pnep"]
        for oname, o in obs_sets.items():
            out["jas"].append({"system": f"IRI {v}", "issue": im, "obs": oname, **metrics(sc, o, YEARS)})
    for im, name in [(2, "feb"), (3, "mar"), (4, "apr"), (5, "may"), (6, "jun")]:
        sc = seasonal(s5, [7, 8, 9], issue_month=im)
        if sc.empty:
            continue
        for oname, o in obs_sets.items():
            out["jas"].append({"system": "SEAS5", "issue": name, "obs": oname, **metrics(-sc, o, YEARS)})
    # the old framework set-ups on their own target seasons (ERA5; CHIRPS where available)
    for label, im, months in [("2025 T1: Mar issue, JJA", 3, [6, 7, 8]), ("2025 T2: Jul issue, ASO", 7, [8, 9, 10]),
                              ("2026 T1: Apr issue, JJASO", 4, [6, 7, 8, 9, 10])]:
        sc = seasonal(s5, months, issue_month=im)
        o = seasonal(e5, months)
        row = {"setup": label, "obs": "ERA5", **metrics(-sc, o, YEARS)}
        out["old_setups"].append(row)
        if months == [6, 7, 8, 9, 10]:
            out["old_setups"].append({"setup": label, "obs": "CHIRPS", **metrics(-sc, chirps5, YEARS)})
    # 2026: what each system said, and how the season came out on ERA5 (CHIRPS 2026 not in the Maproom)
    era_all = era_jas.dropna()
    out["2026"]["era5_jas_rank_driest"] = int((era_all.rank(method="min")).loc[2026]) if 2026 in era_all else None
    out["2026"]["era5_n_seasons"] = int(len(era_all))
    out["2026"]["era5_jas_pct_of_1991_2020"] = round(float(era_all.loc[2026] / era_all.loc[1991:2020].mean() * 100), 1)
    for im, name in [(3, "mar"), (4, "apr"), (5, "may"), (6, "jun")]:
        sc = seasonal(s5, [7, 8, 9], issue_month=im)
        out["2026"][f"seas5_{name}_pct_of_1993_2025"] = round(float(sc.loc[2026] / sc.loc[1993:2025].mean() * 100), 1)
        out["2026"][f"seas5_{name}_rank_driest_of_{int(sc.loc[1993:2026].size)}"] = int(sc.loc[1993:2026].rank(method="min").loc[2026])
    for (v, im), g in fc[fc.version.isin(["prcp-v4", "prcp-v5"])].groupby(["version", "issue_month"]):
        s = g.set_index("year")["pnep"]
        if 2026 in s:
            out["2026"][f"iri_{v}_{im}_p_below_p{SEV}"] = round(float(s.loc[2026]), 1)
            out["2026"][f"iri_{v}_{im}_rank_driest_of_{s.size}"] = int(s.rank(ascending=False, method="min").loc[2026])
    od = data.data_dir() / "iri_review"
    od.mkdir(exist_ok=True)
    (od / "skill.json").write_text(json.dumps(out, indent=1))
    t = pd.DataFrame(out["jas"])
    print("CHIRPS vs ERA5 JAS rho", out["obs_agreement"])
    print(t.pivot_table(index=["system", "issue"], columns="obs", values=["rho", "auc_dry30", "rho_prior10_anom"]).round(2).to_string())
    print(t[t.obs == "CHIRPS"][["system", "issue", "rho", "rho_ci90", "auc_dry30", "hits_1in5"]].to_string(index=False))
    print(pd.DataFrame(out["old_setups"]).to_string(index=False))
    print(json.dumps(out["2026"], indent=0))


if __name__ == "__main__":
    main()
