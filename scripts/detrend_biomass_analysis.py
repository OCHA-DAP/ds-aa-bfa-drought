import pandas as pd, numpy as np, json, sys
from scipy import stats
S=sys.argv[1]
AOI={3820:"Loroum",3824:"Oudalan",3825:"Séno",3827:"Yagha"}
BIO={5,6,7,8,9}; MET={2,3,4,6,7,8,12,13,14}; L3={6,7,8,9}
WIN=range(21,27); SEASON=range(19,31)   # framework window; generic season window for national trends
YRS=range(2001,2026)

def load(name):
    d=pd.read_csv(f"{S}/asap_bfa/{name}.csv", dtype={"date":str}); d["date"]=pd.to_datetime(d["date"],format="%Y%m%d")
    d["year"]=d["date"].dt.year; d["dekad"]=(d["date"].dt.month-1)*3+np.minimum((d["date"].dt.day-1)//10,2)+1
    return d[["region_id","region_name","year","dekad","date","value"]]
z={lc:load(f"zfparc_{lc}") for lc in ["crop","range"]}
w=pd.read_csv(f"{S}/aoi.csv", sep=";"); w["date"]=pd.to_datetime(w["date"]); w["year"]=w["date"].dt.year
w["dekad"]=(w["date"].dt.month-1)*3+(w["date"].dt.day-1)//10+1

# ---------- 1. trends: seasonal-mean zFPARc per province x lc (dekads 19-30), 2001-2025
trend_rows=[]
for lc,d in z.items():
    dd=d[d["dekad"].isin(SEASON)&d["year"].isin(YRS)]
    ann=dd.groupby(["region_id","region_name","year"])["value"].mean().reset_index()
    for (rid,rn),g in ann.groupby(["region_id","region_name"]):
        if len(g)<15: continue
        ts=stats.theilslopes(g["value"],g["year"]); tau=stats.kendalltau(g["year"],g["value"])
        trend_rows.append(dict(region_id=rid,name=rn,lc=lc,slope_dec=ts[0]*10,lo=ts[2]*10,hi=ts[3]*10,p=tau.pvalue,
            first5=g[g["year"]<=2005]["value"].mean(),last5=g[g["year"]>=2021]["value"].mean(),n=len(g),aoi=rid in AOI))
trend=pd.DataFrame(trend_rows)
print("national median slope/decade crop %.2f range %.2f; share p<0.05: crop %.0f%% range %.0f%%"%(
    trend[trend.lc=="crop"].slope_dec.median(),trend[trend.lc=="range"].slope_dec.median(),
    100*(trend[trend.lc=="crop"].p<0.05).mean(),100*(trend[trend.lc=="range"].p<0.05).mean()))
print(trend[trend.aoi].round(3).to_string())

# ---------- 2. detrend AOI series per province x lc x dekad (Theil-Sen slope, mean preserved), fit 2001-2025, applied to all years incl 2026
det=[]
for lc,d in z.items():
    dd=d[d["region_id"].isin(AOI)].copy()
    for (rid,dk),g in dd.groupby(["region_id","dekad"]):
        fit=g[g["year"].isin(YRS)]
        slope=stats.theilslopes(fit["value"],fit["year"])[0]; ybar=fit["year"].mean()
        g=g.assign(lc=lc,slope=slope,z_det=g["value"]-slope*(g["year"]-ybar))
        det.append(g)
det=pd.concat(det); det["name"]=det["region_id"].map(AOI)
# per-dekad slope summary in window
sl=det[det.dekad.isin(WIN)].groupby(["name","lc"])["slope"].mean().unstack()*10
print("mean per-dekad slope/decade in window:\n", sl.round(2))

# ---------- 3. join warnings, calibrate threshold on in-season province-dekads (both lc)
m=det.merge(w[["asap2_id","date","w_crop","w_range"]], left_on=["region_id","date"], right_on=["asap2_id","date"], how="left")
m["code"]=np.where(m["lc"]=="crop", m["w_crop"], m["w_range"])
ins=m.dropna(subset=["code"]); ins=ins[ins["code"]!=98].copy(); ins["code"]=ins["code"].astype(int)
ins["bio"]=ins["code"].isin(BIO); ins["met"]=ins["code"].isin(MET); ins["l3"]=ins["code"].isin(L3)
cal=ins[ins["year"].isin(YRS)]
best=None
for t in np.arange(-1.5,0.01,0.05):
    p=cal["value"]<t; tp=(p&cal.bio).sum(); fp=(p&~cal.bio).sum(); fn=(~p&cal.bio).sum(); f1=2*tp/(2*tp+fp+fn)
    if best is None or f1>best[1]: best=(round(t,2),f1,tp,fp,fn)
T_CAL=best[0]; print("calibrated threshold",best)
def conf(t,col="value"):
    p=cal[col]<t; tp=(p&cal.bio).sum(); fp=(p&~cal.bio).sum(); fn=(~p&cal.bio).sum(); return dict(t=t,tp=int(tp),fp=int(fp),fn=int(fn),f1=round(2*tp/(2*tp+fp+fn),3),obs=int(cal.bio.sum()))
CONF={"cal":conf(T_CAL),"minus1":conf(-1.0)}
print(CONF)

# ---------- 4. simulate per year: biomass flag & level>=3 proxy, in window; count provinces per dekad; activation if >=2 in same dekad
def simulate(col,t):
    d=ins[ins.dekad.isin(WIN)].copy(); d["bio_sim"]=d[col]<t; d["l3_sim"]=d["bio_sim"]&d["met"]
    # province-level per dekad: crop OR range
    pd_=d.groupby(["year","dekad","name"]).agg(bio=("bio_sim","max"),l3=("l3_sim","max"),bio_obs=("bio","max"),l3_obs=("l3","max")).reset_index()
    per=pd_.groupby(["year","dekad"]).agg(n_bio=("bio","sum"),n_l3=("l3","sum"),n_l3_obs=("l3_obs","sum"),n_bio_obs=("bio_obs","sum")).reset_index()
    yr=per.groupby("year").agg(max_bio=("n_bio","max"),max_l3=("n_l3","max"),max_l3_obs=("n_l3_obs","max"),max_bio_obs=("n_bio_obs","max")).reset_index()
    prov=pd_.groupby(["year","name"]).agg(bio=("bio","max"),l3=("l3","max"),bio_obs=("bio_obs","max"),l3_obs=("l3_obs","max")).reset_index()
    return yr,prov,per
RES={}
for label,col in [("trend","value"),("detrended","z_det")]:
    for tl,t in [("cal",T_CAL),("minus1",-1.0)]:
        yr,prov,per=simulate(col,t); RES[(label,tl)]=(yr,prov,per)
yr_obs=RES[("trend","cal")][0][["year","max_l3_obs","max_bio_obs"]]
print("\nobserved (from warnings) years with >=2 provinces at L3 in window:", yr_obs[yr_obs.max_l3_obs>=2].year.tolist())
summary={}
for k,(yr,prov,per) in RES.items():
    act=yr[yr.max_l3>=2].year.tolist(); actb=yr[yr.max_bio>=2].year.tolist()
    hist=[y for y in act if y<=2025]; histb=[y for y in actb if y<=2025]
    summary[k]=dict(l3_years=act,bio_years=actb,rp_l3=round(26/len(hist),1) if hist else None,rp_bio=round(26/len(histb),1) if histb else None)
    print(k, "L3>=2 prov:",act, "RP",summary[k]["rp_l3"], "| biomass>=2 prov:",actb,"RP",summary[k]["rp_bio"])

# ---------- 5. 2026 detail (dekads 19-25), both lc, trend vs detrended
d26=det[(det.year==2026)&(det.dekad>=19)].merge(ins[["region_id","date","lc","code"]],on=["region_id","date","lc"],how="left")
print("\n2026:\n", d26.pivot_table(index=["name","lc"],columns="dekad",values=["value","z_det"]).round(2).to_string())

# ---------- 6. export
out={"T_CAL":T_CAL,"conf":CONF,"summary":{f"{a}|{b}":v for (a,b),v in summary.items()},
     "trend":trend.round(3).to_dict(orient="records"),
     "window_slope":sl.round(3).reset_index().to_dict(orient="records"),
     "annual":{}, "prov":{}, "per":{}, "y2026":d26[["name","lc","dekad","value","z_det","code"]].round(3).to_dict(orient="records")}
# annual window-mean series per province x lc: trend & detrended (for fig 1)
ann=det[det.dekad.isin(WIN)].groupby(["name","lc","year"])[["value","z_det"]].mean().reset_index()
out["annual"]=ann.round(3).to_dict(orient="records")
for k,(yr,prov,per) in RES.items():
    out["prov"][f"{k[0]}|{k[1]}"]=prov.to_dict(orient="records"); out["per"][f"{k[0]}|{k[1]}"]=per.to_dict(orient="records")
out["yr_obs"]=yr_obs.to_dict(orient="records")
json.dump(out,open(f"{S}/detrend_results.json","w"),default=lambda o: bool(o) if isinstance(o,np.bool_) else (float(o) if isinstance(o,(np.floating,)) else int(o)))
print("saved")
