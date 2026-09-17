"""Does heat add to biomass in explaining drought IMPACT (not just the biomass proxy)?

Targets: (1) national millet+sorghum production anomaly from a 2001-2024 linear trend (FAOSTAT);
(2) binary impact seasons from EM-DAT drought events, CERF drought allocations (dated to the
rainfall-deficit season) and the framework's target years.
Predictors: ASAP province series (zFPARc, WSI, SPI-3, rainfall, temperature) aggregated to the
four framework provinces (AOI) and to the unweighted national mean of all provinces.
"""
import json, sys
import numpy as np, pandas as pd
from scipy import stats
S=sys.argv[1]; AOI={3820,3824,3825,3827}
JAS=range(19,28); WIN=range(21,27)
def load(name):
    d=pd.read_csv(f"{S}/asap_bfa/{name}.csv",dtype={"date":str}); d["date"]=pd.to_datetime(d["date"],format="%Y%m%d")
    d["year"]=d.date.dt.year; d["dekad"]=(d.date.dt.month-1)*3+np.minimum((d.date.dt.day-1)//10,2)+1
    return d[["region_id","year","dekad","value"]].rename(columns={"value":name})
def seas(d,col,dks): return d[d.dekad.isin(dks)].groupby(["region_id","year"])[col].mean()
t,r,z,zr,w,s3=(load(n) for n in ["temp_crop","rain_crop","zfparc_crop","zfparc_range","wsi_crop","spi3_crop"])
prov=pd.concat([seas(t,"temp_crop",JAS).rename("t_jas"),seas(r,"rain_crop",JAS).rename("rain"),seas(z,"zfparc_crop",WIN).rename("z_crop"),
                seas(zr,"zfparc_range",WIN).rename("z_range"),seas(w,"wsi_crop",WIN).rename("wsi"),seas(s3,"spi3_crop",WIN).rename("spi")],axis=1).reset_index()
# per-province detrending of temp (1989-2025) and biomass (2001-2025)
out=[]
for rid,g in prov.groupby("region_id"):
    g=g.sort_values("year").copy()
    f=g[g.year.between(1989,2025)].dropna(subset=["t_jas"]); sl=stats.theilslopes(f.t_jas,f.year); g["t_dt"]=g.t_jas-sl[0]*(g.year-f.year.mean())-f.t_jas.mean()
    for col in ["z_crop","z_range"]:
        f=g[g.year.between(2001,2025)].dropna(subset=[col])
        if len(f)>=15: sl=stats.theilslopes(f[col],f.year); g[col+"_dt"]=g[col]-sl[0]*(g.year-f.year.mean())
        else: g[col+"_dt"]=np.nan
    out.append(g)
prov=pd.concat(out); prov["z_dt"]=prov[["z_crop_dt","z_range_dt"]].mean(axis=1); prov["z_pub"]=prov[["z_crop","z_range"]].mean(axis=1)
def agg(sel,label):
    a=prov[prov.region_id.isin(sel)].groupby("year")[["t_dt","rain","z_dt","z_pub","wsi","spi"]].mean(); a.columns=[f"{c}_{label}" for c in a.columns]; return a
X=pd.concat([agg(AOI,"aoi"),agg(set(prov.region_id),"nat")],axis=1)

# ---------------- targets
rows=[r for r in pd.read_csv(f"{S}/faostat_bfa.csv",dtype=str).to_dict("records") if not str(r.get("Year","")).startswith("#")]
fa=pd.DataFrame(rows); fa=fa[fa.Item.isin(["Millet","Sorghum"])&(fa.Element=="Production")]; fa["Year"]=fa.Year.astype(int); fa["Value"]=fa.Value.astype(float)
prod=fa.groupby("Year").Value.sum(); prod=prod.loc[2001:2024]
b=np.polyfit(prod.index,prod.values,1); prod_an=(prod.values-np.polyval(b,prod.index))/np.polyval(b,prod.index)*100
Y=pd.DataFrame({"prod_anom":prod_an},index=prod.index)
# impact seasons: evidence-dated (main) and framework-labelled (alt)
DATING=[  # (record, raw date, season assigned, alt season, basis)
 ("EM-DAT 2011-9524 (2.85M affected, Sahel/Centre-Nord/Est)","Dec 2011–2012",2011,None,"event starts Dec 2011 = failed 2011 season; CERF supplement dates the 2012 allocation to Jun–Sep 2011"),
 ("EM-DAT 2014-9196 (4.0M affected, Sahel)","May 2014",2013,2014,"May start = 2014 lean season, i.e. the 2013 harvest; but the framework lists 2014 and AOI biomass was poor in 2014, so 2014 is the alternative"),
 ("CERF 14-UFE-BFA-10955 ($3.9M, drought, Aug 2014)","Aug 2014",2013,2014,"underfunded-window allocation mid-2014 funds the 2014 lean-season response (2013 harvest); alternative 2014 as above"),
 ("CERF 12-RR-BFA-13236 ($9.2M, drought)","2012",2011,None,"CERF supplement: rainfall deficit Jun–Sep 2011, confidence 0.85"),
 ("CERF 18-RR-BFA-30726 ($9.0M, drought / pastoral crisis)","May 2018",2017,None,"CERF supplement: poor, early-ending Jun–Sep 2017 season, confidence 0.80"),
 ("EM-DAT 2020-9235 (2.9M affected, all regions)","Jan–Jun 2020",2019,None,"lean-season 2020 event = 2019 harvest"),
 ("EM-DAT 2022-9781 (3.5M affected)","–Nov 2022",2021,2022,"3.5M matches the Jun–Aug 2022 CH lean-season figure = 2021 harvest (national millet+sorghum −14% from trend in 2021); framework lists 2022, so 2022 is the alternative"),
 ("CERF 22-RR-BFA-53665 ($6.0M, food security, May 2022)","May 2022",2021,2022,"allocated for the 2022 lean season = 2021 harvest; typed 'economic disruption', conflict-related"),
 ("Framework target years","—",None,None,"2011, 2014, 2017, 2019, 2022 as listed in exploration/asap_adm2.md; read here as impact years (2014→2013 season, 2022→2021 season) in the main dating and as growing seasons in the alternative"),
]
MAIN={2011,2013,2017,2019,2021}; ALT={2011,2014,2017,2019,2022}
UF={2005,2006,2007,2008}  # 2006-2009 UF drought allocations, undated, mapped to previous seasons; 2008 RR excluded (food-price crisis)
Y["impact_main"]=Y.index.isin(MAIN).astype(int); Y["impact_alt"]=Y.index.isin(ALT).astype(int); Y["impact_main_plus_uf"]=Y.index.isin(MAIN|UF).astype(int)
D=Y.join(X,how="left"); D=D.loc[2001:2024]
D.to_csv(f"{S}/impact_table.csv")

# ---------------- stats helpers
def zs(s): return (s-s.mean())/s.std()
def ols(y,X):
    X=np.column_stack([np.ones(len(y))]+X); b=np.linalg.lstsq(X,y,rcond=None)[0]; yhat=X@b; r2=1-((y-yhat)**2).sum()/((y-y.mean())**2).sum()
    n,k=X.shape; s2=((y-yhat)**2).sum()/(n-k); se=np.sqrt(np.diag(s2*np.linalg.inv(X.T@X))); p=2*(1-stats.t.cdf(abs(b/se),n-k)); return b,p,r2
def loo_r2(y,Xc):
    n=len(y); pred=np.zeros(n)
    for i in range(n):
        m=np.ones(n,bool); m[i]=False; Xtr=np.column_stack([np.ones(m.sum())]+[c[m] for c in Xc]); b=np.linalg.lstsq(Xtr,y[m],rcond=None)[0]
        pred[i]=np.array([1]+[c[i] for c in Xc])@b
    return 1-((y-pred)**2).sum()/((y-y.mean())**2).sum()
def auc(score,label):  # higher score = more drought-like
    from itertools import product
    pos=score[label==1]; neg=score[label==0]; return float(np.mean([1.0 if p>n else 0.5 if p==n else 0.0 for p,n in product(pos,neg)]))

RES={"dating":DATING,"main":sorted(MAIN),"alt":sorted(ALT),"uf":sorted(UF),"cont":{},"bin":{},"quad":{}}
for scope in ["aoi","nat"]:
    d=D.dropna(subset=[f"z_dt_{scope}",f"t_dt_{scope}","prod_anom"]).copy()
    y=d.prod_anom.values; Z=zs(d[f"z_dt_{scope}"]).values; T=zs(d[f"t_dt_{scope}"]).values; W=zs(d[f"wsi_{scope}"]).values; R=zs(d[f"rain_{scope}"]).values; Sp=zs(d[f"spi_{scope}"]).values; Zp=zs(d[f"z_pub_{scope}"]).values
    specs={"biomass (detrended)":[Z],"biomass (published)":[Zp],"temperature":[T],"water balance":[W],"SPI-3":[Sp],"rainfall":[R],
           "biomass + temperature":[Z,T],"biomass + water balance":[Z,W],"biomass + water balance + temperature":[Z,W,T],"biomass × temperature (interaction)":[Z,T,Z*T]}
    RES["cont"][scope]={}
    for k,Xc in specs.items():
        b,p,r2=ols(y,Xc); RES["cont"][scope][k]=dict(r2=round(r2,3),loo_r2=round(loo_r2(y,Xc),3),coefs=[round(x,2) for x in b[1:]],p=[round(x,3) for x in p[1:]],n=int(len(y)))
    # binary: AUC of single scores and of a fitted combination (LOO logistic-free: use OLS-score of impact on predictors, LOO)
    RES["bin"][scope]={}
    for tgt in ["impact_main","impact_alt","impact_main_plus_uf"]:
        for period,yrs in [("2001-2024",(2001,2024)),("2001-2018",(2001,2018))]:
            dd=d[d.index.to_series().between(*yrs)]; lab=dd[tgt].values
            if lab.sum()<2: continue
            Zd=zs(dd[f"z_dt_{scope}"]).values; Td=zs(dd[f"t_dt_{scope}"]).values; Wd=zs(dd[f"wsi_{scope}"]).values; Pd=-dd.prod_anom.values
            # LOO combination score
            n=len(lab); comb=np.zeros(n)
            for i in range(n):
                m=np.ones(n,bool); m[i]=False; Xtr=np.column_stack([np.ones(m.sum()),Zd[m],Td[m]]); bb=np.linalg.lstsq(Xtr,lab[m].astype(float),rcond=None)[0]; comb[i]=np.array([1,Zd[i],Td[i]])@bb
            RES["bin"][scope][f"{tgt}|{period}"]=dict(n=int(n),n_pos=int(lab.sum()),pos_years=[int(x) for x in dd.index[lab==1]],
                auc=dict(biomass=round(auc(-Zd,lab),3),temperature=round(auc(Td,lab),3),water_balance=round(auc(-Wd,lab),3),production=round(auc(Pd,lab),3),
                         biomass_plus_temp_loo=round(auc(comb,lab),3),biomass_minus_temp_sum=round(auc(-Zd+Td,lab),3)))
    # quadrants: hot (t_dt > median) x low biomass (z_dt < median): mean production anomaly and impact rate
    hot=d[f"t_dt_{scope}"]>d[f"t_dt_{scope}"].median(); low=d[f"z_dt_{scope}"]<d[f"z_dt_{scope}"].median()
    q={}
    for hn,hm in [("hot",hot),("cool",~hot)]:
        for ln,lm in [("low biomass",low),("high biomass",~low)]:
            m=hm&lm; q[f"{hn} / {ln}"]=dict(n=int(m.sum()),years=[int(x) for x in d.index[m]],prod_mean=round(float(d.prod_anom[m].mean()),1),impact_rate=round(float(d.impact_main[m].mean()),2),impact_years=[int(x) for x in d.index[m&(d.impact_main==1)]])
    RES["quad"][scope]=q
    # within low-biomass years: hot vs cool production
    lowd=d[low]; RES["quad"][scope]["low_biomass_hot_vs_cool"]=dict(hot_prod=round(float(lowd.prod_anom[lowd[f"t_dt_{scope}"]>d[f"t_dt_{scope}"].median()].mean()),1),cool_prod=round(float(lowd.prod_anom[lowd[f"t_dt_{scope}"]<=d[f"t_dt_{scope}"].median()].mean()),1))
json.dump(RES,open(f"{S}/impact_results.json","w"),indent=1,default=float)
pd.set_option("display.width",250)
print(D[["prod_anom","impact_main","impact_alt","z_dt_aoi","t_dt_aoi","wsi_aoi","z_dt_nat","t_dt_nat","wsi_nat"]].round(2).to_string())
for scope in ["aoi","nat"]:
    print(f"\n== {scope} continuous (production anomaly):");
    for k,v in RES["cont"][scope].items(): print(f"  {k:40s} R2={v['r2']:.2f} LOO={v['loo_r2']:+.2f} coefs={v['coefs']} p={v['p']}")
    print(f"== {scope} binary AUC:");
    for k,v in RES["bin"][scope].items(): print(f"  {k:32s} n+={v['n_pos']} {v['pos_years']} {v['auc']}")
    print(f"== {scope} quadrants:"); [print("  ",k,v) for k,v in RES["quad"][scope].items()]
