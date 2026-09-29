"""Context columns per BFA province: HNRP 2026 (JIAF severity, PiN by group), last public
Cadre Harmonise (Mar 2024 analysis), EM-DAT flood history, population.

Usage: build_context.py <workdir>  ->  context.csv
Needs the dev DB (hpc, ipc schemas) -- run with the DB tunnel env set.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

WORK = Path(sys.argv[1])
eng = stratus.get_engine(stage="dev")


def key(s):
    k = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", k)


AL = {"bulkiemde": "boulkiemde", "kouritenga": "kourittenga", "komondjari": "komandjari"}
new2 = gpd.read_file(f"zip://{WORK}/bfa_admin_boundaries_new.shp.zip!bfa_admin2.shp")
old2 = gpd.read_file(f"zip://{WORK}/bfa_old.shp.zip!bfa_adm2.shp")
xw = new2[["adm2_pcode", "adm2_pco_1"]].rename(columns={"adm2_pco_1": "old_pcode"})
ch_ = xw.groupby("old_pcode").adm2_pcode.apply(list).to_dict()
old_by_key = {AL.get(key(n), key(n)): p for n, p in zip(old2.ADM2_FR, old2.ADM2_PCODE)}

ctx = new2[["adm1_pcode", "adm1_name1", "adm2_pcode", "adm2_name1"]].rename(
    columns={"adm1_name1": "adm1_name", "adm2_name1": "adm2_name"}).set_index("adm2_pcode")
ctx["pop_worldpop_2020"] = pd.read_csv(WORK / "prov_pop_worldpop2020.csv").set_index(
    "adm2_pcode").pop_worldpop_2020.round()

# ---- HNRP 2026 ----
sev = pd.read_sql("select admin2_code, admin2_name, final_severity from hpc.severity_admin "
                  "where iso3='BFA' and year=2026", eng).set_index("admin2_code")
pin = pd.read_sql("select admin2_code, population_group, population, final_pin from hpc.pin_admin "
                  "where iso3='BFA' and year=2026", eng)
pw = pin.pivot_table(index="admin2_code", columns="population_group", values="final_pin", aggfunc="sum")
pw.columns = ["pin_2026_" + {"Non deplaces": "non_deplaces", "PDI": "pdi", "Retournes": "retournes"}[c]
              for c in pw.columns]
ctx["hnrp_name_2026"] = sev.admin2_name
ctx["jiaf_severity_2026"] = sev.final_severity
ctx = ctx.join(pw)
ctx["pin_2026_total"] = pw.sum(axis=1)
ctx["pop_hnrp_2026"] = pin.groupby("admin2_code").population.sum()

# ---- last public Cadre Harmonise (Mar 2024 analysis), pre-reform provinces ----
ch = pd.read_sql("""select admin2_code, admin2_name, ipc_type, ipc_phase, population_in_phase,
                    population_fraction_in_phase, reference_period_start
                    from ipc.population_admin where location_code='BFA' and admin_level=2
                    and reference_period_start in ('2024-03-01','2024-06-01')""", eng)
ch["old_pcode"] = ch.admin2_code
bad = ~ch.old_pcode.isin(xw.old_pcode)
ch.loc[bad, "old_pcode"] = ch.loc[bad, "admin2_name"].map(lambda n: old_by_key.get(AL.get(key(n), key(n))))
print("CH rows unmatched:", ch.old_pcode.isna().sum())
p3 = ch[ch.ipc_phase.isin(["3+"])]
if p3.empty:
    p3 = ch[ch.ipc_phase.astype(str).isin(["3", "4", "5"])].groupby(
        ["old_pcode", "ipc_type"]).population_fraction_in_phase.sum().reset_index()
else:
    p3 = p3.groupby(["old_pcode", "ipc_type"]).population_fraction_in_phase.sum().reset_index()
p3w = p3.pivot_table(index="old_pcode", columns="ipc_type", values="population_fraction_in_phase")
p3w = 100 * p3w.rename(columns={"current": "ch_p3_pct_mar2024", "first projection": "ch_p3_pct_jja2024"})
chn = xw.merge(p3w, left_on="old_pcode", right_index=True, how="left").set_index("adm2_pcode")
ctx = ctx.join(chn[[c for c in chn.columns if c.startswith("ch_")]])

# ---- EM-DAT flood history (event-years naming the province, 2000-2025) ----
e = pd.read_parquet(WORK / "emdat_bfa.parquet")
e = e[(e["Disaster Type"] == "Flood") & (e["Start Year"] >= 2000)]
hits, national = {}, []
for _, r in e.iterrows():
    if not isinstance(r["Admin Units"], str):
        national.append(int(r["Start Year"]))
        continue
    au = json.loads(r["Admin Units"])
    a2 = [x["adm2_name"] for x in au if "adm2_name" in x]
    if len([x for x in au if "adm1_name" in x]) >= 13 or not a2:
        national.append(int(r["Start Year"]))
        continue
    for n in a2:
        op = old_by_key.get(AL.get(key(n), key(n)))
        for npc in ch_.get(op, []):
            hits.setdefault(npc, set()).add(int(r["Start Year"]))
ctx["emdat_flood_years_n"] = pd.Series({k: len(v) for k, v in hits.items()})
ctx["emdat_flood_years"] = pd.Series({k: ", ".join(map(str, sorted(v))) for k, v in hits.items()})
ctx["emdat_flood_years_n"] = ctx.emdat_flood_years_n.fillna(0).astype(int)
print("EM-DAT national/unlocated flood years:", sorted(set(national)))

# ---- long-term flood exposure (FloodScan 2002-2025, Jun-Oct peak 5-day mean) ----
f = pd.read_csv(WORK / "flood_by_year.csv")
lt = f[f.year.between(2002, 2025)].groupby("adm2_pcode")
ctx["flood_exp_pct_mean_2002_2025"] = lt.flood_exp_pct.mean()
ctx["flood_exp_pk5_mean_2002_2025"] = lt.flood_exp_pk5.mean()
ctx.reset_index().to_csv(WORK / "context.csv", index=False)
print(ctx.drop(columns=["emdat_flood_years"]).round(1).head(8).to_string())
print(ctx[["jiaf_severity_2026"]].value_counts())
