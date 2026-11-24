"""Trigger logic for IRI's FbF Maproom forecast candidates (copied from ds-aa-mli-drought/scripts/trigger.py,
where it reproduces IRI's published Mali analysis exactly).

Terms (IRI's): *severity* s (%) picks both the forecast quantity — the probability that JAS
rainfall falls below its s-th percentile — and the per-month threshold, the top-s% of a
reference set of past forecasts for the same issue month and severity. A *rule* combines
the monthly exceedances over the Feb–Jun monitoring months.

Threshold variants:
- ``fixed``: reference = every year in the record, k by the rule below.
- ``fixed_maproom``: the Maproom's own fixed threshold (its rank rule differs at some
  severities: with 35 years it takes the 1st, 3rd and 10th highest at 5, 10 and 30%).
- ``rolling``: reference = the ``window`` years before the target year.
- ``expanding``: reference = every year from the start of the record to the year before.

In a reference set of n values the threshold is the k-th highest value, with
k = round_half_up(s/100 * n) (IRI's "top-k ranking"; k = 0 means the month cannot
trigger).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

MONITOR_MONTHS = ["feb", "mar", "apr", "may", "jun"]
RULES = ["single", "2consec", "2in5", "3in5"]
TOL = 1e-9  # the Maproom serves thresholds that differ from the forecast values by ~1e-14
RULE_LABEL = {
    "single": "Single month",
    "2consec": "2 consecutive months",
    "2in5": "2 of 5 months",
    "3in5": "3 of 5 months",
}


def top_k(severity: float, n: int) -> int:
    return int(math.floor(severity / 100 * n + 0.5))


def kth_highest(values: np.ndarray, k: int) -> float:
    if k <= 0 or len(values) < k:
        return np.inf
    return float(np.sort(values)[::-1][k - 1])


def monthly_thresholds(
    fc: pd.DataFrame, method: str = "rolling", window: int = 10, base_years=None, maproom=None
) -> pd.DataFrame:
    """Per (year, issue_month, severity) threshold and exceedance flag.

    ``fc`` columns: year, issue_month, severity, pnep (one version only).
    ``base_years``: for ``fixed``, the years the threshold is computed over
    (default: all years present).
    """
    out = []
    for (im, sev), g in fc.groupby(["issue_month", "severity"]):
        g = g.sort_values("year")
        years, vals = g["year"].to_numpy(), g["pnep"].to_numpy()
        if method == "fixed":
            mask = np.isin(years, base_years) if base_years is not None else np.ones_like(years, bool)
            ref = vals[mask & ~np.isnan(vals)]
            thr_all = kth_highest(ref, top_k(sev, len(ref)))
        if method == "fixed_maproom":  # thresholds as served by the Maproom export
            thr_all = float(maproom.loc[(im, sev)])
        for y, v in zip(years, vals):
            if method in ("fixed", "fixed_maproom"):
                thr = thr_all
            elif method == "rolling":
                ref = vals[(years >= y - window) & (years <= y - 1)]
                thr = kth_highest(ref, top_k(sev, window)) if len(ref) == window else np.nan
            elif method == "expanding":
                ref = vals[years <= y - 1]
                thr = kth_highest(ref, top_k(sev, len(ref))) if len(ref) else np.nan
            elif method == "expanding_incl":
                # IRI's "dynamic" section: the target year is part of its own reference set
                ref = vals[years <= y]
                thr = kth_highest(ref, top_k(sev, len(ref)))
            else:
                raise ValueError(method)
            out.append({"year": y, "issue_month": im, "severity": sev, "pnep": v,
                        "threshold": thr, "exceed": bool(v >= thr - TOL) if np.isfinite(thr) else False,
                        "has_threshold": bool(np.isfinite(thr))})
    return pd.DataFrame(out)


def apply_rules(mt: pd.DataFrame, months=MONITOR_MONTHS) -> pd.DataFrame:
    """Annual activation and activation month for each rule, per (year, severity)."""
    rows = []
    for (y, sev), g in mt[mt["issue_month"].isin(months)].groupby(["year", "severity"]):
        g = g.set_index("issue_month").reindex(months)
        if not g["has_threshold"].fillna(False).all():
            continue
        e = g["exceed"].fillna(False).to_numpy()
        res = {"year": y, "severity": sev, "n_months": int(e.sum())}
        cum = np.cumsum(e)
        # single month / 2 of 5 / 3 of 5: month where the cumulative count first reaches 1/2/3
        for rule, need in [("single", 1), ("2in5", 2), ("3in5", 3)]:
            idx = np.argmax(cum >= need) if cum[-1] >= need else None
            res[rule] = idx is not None
            res[f"{rule}_month"] = months[idx] if idx is not None else None
        consec = [i for i in range(1, len(e)) if e[i] and e[i - 1]]
        res["2consec"] = bool(consec)
        res["2consec_month"] = months[consec[0]] if consec else None
        rows.append(res)
    return pd.DataFrame(rows)


def drought_years(obs: pd.Series, n: int) -> set:
    """The n driest years of ``obs`` (index = year)."""
    return set(obs.sort_values(kind="mergesort").index[:n])


def score(activated: set, years: list, obs: pd.Series, n_bench: int | None = None) -> dict:
    """IRI-style contingency: benchmark = the driest N years, N = number of activations."""
    n = len(years)
    n_act = len(activated)
    nb = n_act if n_bench is None else n_bench
    dry = drought_years(obs.loc[years], nb) if nb else set()
    wa = len(activated & dry)
    aiv = n_act - wa
    fta = len(dry - activated)
    wi = n - wa - aiv - fta
    return {
        "n_years": n, "n_act": n_act, "rate": n_act / n,
        "rp_weibull": (n + 1) / n_act if n_act else np.inf,
        "worthy_action": wa, "act_in_vain": aiv, "fail_to_act": fta, "worthy_inaction": wi,
        "hit_rate": wa / len(dry) if dry else np.nan,
        "far": aiv / n_act if n_act else np.nan,
        "accuracy": (wa + wi) / n,
        "drought_years": sorted(dry),
    }


def p_hits_by_chance(n: int, n_act: int, n_dry: int, hits: int) -> float:
    """P(at least ``hits`` overlaps) if the ``n_act`` activation years were drawn at random."""
    from scipy.stats import hypergeom

    return float(hypergeom.sf(hits - 1, n, n_dry, n_act))
