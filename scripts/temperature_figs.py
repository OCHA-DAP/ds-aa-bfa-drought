import pandas as pd, numpy as np, html, sys
from scipy import stats
S=sys.argv[1]
INK="#1f2324"; MUTED="#5e6a6b"; FAINT="#7e8e8f"; GRID="#e2e8e8"; ACC="#1e795f"; RED="#9d372b"; AMBER="#d48f2a"; BLUE="#1862d8"
FONT='font-family="Roboto,system-ui,sans-serif"'
def esc(s): return html.escape(str(s))
def head(W,H,title,tid): return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" {FONT} role="img" aria-labelledby="{tid}"><title id="{tid}">{esc(title)}</title>']
df=pd.read_csv(f"{S}/temp_seasonal.csv"); ym=pd.read_csv(f"{S}/temp_year_aoi.csv").set_index("year")
ACT=[2002,2004,2006,2009,2011]; TGT=[2011,2014,2017,2019,2022]

# ---------- Fig 1: AOI-mean seasonal temperature 1989-2026, pre-season and wet season, Theil-Sen lines
a=df.groupby("year")[["t_pre","t_jas"]].mean()
W=760; lx=54; pw=680; ph=170; gy=48; ty=30; H=ty+2*(ph+gy)+8
o=head(W,H,"Framework-province mean temperature by season, 1989–2026, with Theil-Sen trend","f1")
for k,(col,lab,rng,color) in enumerate([("t_pre","April–June (pre-season)",(30.5,34.5),AMBER),("t_jas","July–September (growing season)",(26.8,30.0),ACC)]):
    y0=ty+k*(ph+gy); ymin,ymax=rng
    def X(yr): return lx+(yr-1989)/(2026-1989)*(pw-10)+5
    def Y(v): return y0+ph-(v-ymin)/(ymax-ymin)*ph
    o.append(f'<text x="{lx}" y="{y0-9}" font-size="12.5" font-weight="500" fill="{INK}">{lab}</text>')
    for v in np.arange(np.ceil(ymin),ymax+0.01,1):
        o.append(f'<line x1="{lx}" y1="{Y(v):.1f}" x2="{lx+pw}" y2="{Y(v):.1f}" stroke="{GRID}"/><text x="{lx-6}" y="{Y(v)+3.5:.1f}" text-anchor="end" font-size="9.5" fill="{FAINT}">{v:.0f}°</text>')
    for yr in range(1990,2027,5): o.append(f'<text x="{X(yr):.1f}" y="{y0+ph+13}" text-anchor="middle" font-size="9.5" fill="{FAINT}">{yr}</text>')
    s=a[col].dropna(); fit=s.loc[1989:2025]; ts=stats.theilslopes(fit.values,fit.index.values); p=stats.kendalltau(fit.index.values,fit.values).pvalue
    yb=fit.index.values.mean(); yhat=lambda yr: fit.mean()+ts[0]*(yr-yb)
    o.append(f'<line x1="{X(1989):.1f}" y1="{Y(yhat(1989)):.1f}" x2="{X(2025):.1f}" y2="{Y(yhat(2025)):.1f}" stroke="{color}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    pts=" ".join(f'{X(yr):.1f},{Y(v):.1f}' for yr,v in fit.items()); o.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>')
    for yr,v in fit.items():
        mark=yr in ACT
        o.append(f'<circle cx="{X(yr):.1f}" cy="{Y(v):.1f}" r="{4 if mark else 2.6}" fill="{RED if mark else color}" stroke="#fff" stroke-width="{1 if mark else 0}"><title>{esc(f"{yr}: {v:.2f} °C")}</title></circle>')
    v26=s.get(2026)
    if v26==v26: o.append(f'<circle cx="{X(2026):.1f}" cy="{Y(v26):.1f}" r="5" fill="#fff" stroke="{RED}" stroke-width="2"><title>{esc(f"2026 (partial): {v26:.2f} °C")}</title></circle><text x="{X(2026)-8:.1f}" y="{Y(v26)-8:.1f}" text-anchor="end" font-size="10" font-weight="500" fill="{RED}">2026</text>')
    o.append(f'<text x="{lx+pw}" y="{y0-9}" text-anchor="end" font-size="11" fill="{MUTED}">trend {ts[0]*10:+.2f} °C per decade, p = {p:.2f}</text>')
ly=H-4; o.append(f'<circle cx="{lx+6}" cy="{ly-4}" r="4" fill="{RED}"/><text x="{lx+14}" y="{ly}" font-size="10.5" fill="{INK}">Years Trigger 2 would have activated (ASAP level 3 in ≥ 2 provinces)</text>')
o.append(f'<circle cx="{lx+400}" cy="{ly-4}" r="5" fill="#fff" stroke="{RED}" stroke-width="2"/><text x="{lx+410}" y="{ly}" font-size="10.5" fill="{INK}">2026 so far (through the 1st dekad of September)</text>')
o.append("</svg>"); open(f"{S}/tf1.svg","w").write("\n".join(o))

# ---------- Fig 2: scatter detrended JAS temp anomaly vs detrended window biomass z, per province-year 2001-2025; colour = rain tercile; 2026 marked
h=df[df.year.between(2001,2025)].dropna(subset=["t_jas_dt","z_win_dt"]).copy()
q1,q2=h.rain_jas.quantile([1/3,2/3]); h["rt"]=np.where(h.rain_jas<q1,"dry",np.where(h.rain_jas>q2,"wet","mid"))
COL={"dry":AMBER,"mid":"#9db1b3","wet":BLUE}
W=760; lx=56; pw=660; ph=330; ty=26; H=ty+ph+70
xmin,xmax=-1.0,1.7; ymin,ymax=-2.4,2.4
def X(v): return lx+(v-xmin)/(xmax-xmin)*pw
def Y(v): return ty+ph-(v-ymin)/(ymax-ymin)*ph
o=head(W,H,"Growing-season temperature anomaly vs biomass anomaly, framework provinces, 2001–2025","f2")
for v in [-2,-1,0,1,2]: o.append(f'<line x1="{lx}" y1="{Y(v):.1f}" x2="{lx+pw}" y2="{Y(v):.1f}" stroke="{GRID if v else "#9db1b3"}"/><text x="{lx-6}" y="{Y(v)+3.5:.1f}" text-anchor="end" font-size="9.5" fill="{FAINT}">{v:+d}</text>')
for v in [-1,-0.5,0,0.5,1,1.5]: o.append(f'<line x1="{X(v):.1f}" y1="{ty}" x2="{X(v):.1f}" y2="{ty+ph}" stroke="{GRID if v else "#9db1b3"}"/><text x="{X(v):.1f}" y="{ty+ph+14}" text-anchor="middle" font-size="9.5" fill="{FAINT}">{v:+.1f} °C</text>')
o.append(f'<text x="{X(0.1):.1f}" y="{ty+ph+30}" text-anchor="middle" font-size="11" fill="{MUTED}">July–September temperature, anomaly from the province\'s own trend line (°C)</text>')
o.append(f'<text transform="translate(14,{ty+ph/2:.0f}) rotate(-90)" text-anchor="middle" font-size="11" fill="{MUTED}">Cumulative-FPAR anomaly, Trigger 2 window, detrended (z)</text>')
o.append(f'<line x1="{lx}" y1="{Y(-0.6):.1f}" x2="{lx+pw}" y2="{Y(-0.6):.1f}" stroke="{RED}" stroke-width="1.2" stroke-dasharray="4 3"/><text x="{lx+pw-4}" y="{Y(-0.6)+11:.1f}" text-anchor="end" font-size="9.5" fill="{RED}">biomass-warning cut-off (−0.6)</text>')
# regression line (pooled)
sl,ic,r,p,_=stats.linregress(h.t_jas_dt,h.z_win_dt)
o.append(f'<line x1="{X(-0.9):.1f}" y1="{Y(ic+sl*-0.9):.1f}" x2="{X(1.1):.1f}" y2="{Y(ic+sl*1.1):.1f}" stroke="{INK}" stroke-width="1.2" opacity="0.6"/>')
o.append(f'<text x="{X(-0.95):.1f}" y="{Y(2.2):.1f}" font-size="10.5" fill="{INK}">Pooled fit 2001–2025: {sl:+.2f} z per °C, r = {r:.2f}</text>')
for rr in h.itertuples():
    mark=rr.year in ACT
    o.append(f'<circle cx="{X(rr.t_jas_dt):.1f}" cy="{Y(rr.z_win_dt):.1f}" r="{5 if mark else 4}" fill="{COL[rr.rt]}" stroke="{RED if mark else "#fff"}" stroke-width="{1.8 if mark else 0.8}" opacity="0.9"><title>{esc(f"{rr.name} {rr.year}: temp {rr.t_jas_dt:+.2f} °C, biomass {rr.z_win_dt:+.2f} z, rain {rr.rain_jas:.0f} mm/dekad ({rr.rt} tercile)")}</title></circle>')
# 2026 points: observed temp so far detrended, biomass so far (published, detrended not available for 2026 z? we have z_win_dt via extrapolated slope)
d26=df[df.year==2026]
for rr in d26.itertuples():
    if rr.t_jas_dt!=rr.t_jas_dt or rr.z_win_dt!=rr.z_win_dt: continue
    o.append(f'<circle cx="{X(rr.t_jas_dt):.1f}" cy="{Y(rr.z_win_dt):.1f}" r="6" fill="#fff" stroke="{RED}" stroke-width="2.2"><title>{esc(f"{rr.name} 2026 so far: temp {rr.t_jas_dt:+.2f} °C, biomass {rr.z_win_dt:+.2f} z")}</title></circle>')
    o.append(f'<text x="{X(rr.t_jas_dt):.1f}" y="{Y(rr.z_win_dt)-9:.1f}" text-anchor="middle" font-size="9.5" font-weight="500" fill="{RED}">{esc(rr.name)} 2026</text>')
ly=H-6; xx=lx
for k,lab in [("dry","Driest third of seasons (rain)"),("mid","Middle third"),("wet","Wettest third")]:
    o.append(f'<circle cx="{xx+5}" cy="{ly-4}" r="4.5" fill="{COL[k]}"/><text x="{xx+13}" y="{ly}" font-size="10.5" fill="{INK}">{lab}</text>'); xx+=len(lab)*6.3+30
o.append(f'<circle cx="{xx+5}" cy="{ly-4}" r="5" fill="#fff" stroke="{RED}" stroke-width="1.8"/><text x="{xx+13}" y="{ly}" font-size="10.5" fill="{INK}">Trigger 2 activation year</text>')
o.append("</svg>"); open(f"{S}/tf2.svg","w").write("\n".join(o))

# ---------- Fig 3: year strip 2001-2026: rows temp anomaly (detrended), rain, biomass, WSI; AOI mean
rows=[("t","Temperature, Jul–Sep, anomaly from trend (°C)","div_t"),("rain","Rainfall, Jul–Sep (mm per dekad)","seq_r"),("zdt","Biomass (zFPARc), window, detrended","div_z"),("wsi","Water satisfaction index, window (%)","seq_w")]
years=list(range(2001,2027)); ym26=ym.copy()
# add 2026 partial values
d26=df[df.year==2026]; ym26.loc[2026]=[d26.t_jas_dt.mean(),d26.t_jas_an.mean(),d26.t_pre_dt.mean(),d26.rain_jas.mean(),d26.z_win.mean(),d26.z_win_dt.mean(),d26.wsi_win.mean()]
cw,ch=26,30; lx=290; ty=36; W=lx+cw*len(years)+10; H=ty+ch*len(rows)+34
def lerp(c1,c2,f):
    a=[int(c1[i:i+2],16) for i in (1,3,5)]; b=[int(c2[i:i+2],16) for i in (1,3,5)]; return "#%02x%02x%02x"%tuple(int(a[i]+(b[i]-a[i])*f) for i in range(3))
def col_div(v,lim,warm_is_high=True):
    f=max(-1,min(1,v/lim));
    if warm_is_high: return lerp("#ffffff","#9d372b",f) if f>0 else lerp("#ffffff","#1862d8",-f)
    return lerp("#ffffff","#1e795f",f) if f>0 else lerp("#ffffff","#9d372b",-f)
o=head(W,H,"Framework-province means by year, 2001–2026: temperature anomaly, rainfall, biomass and water balance","f3")
for j,yr in enumerate(years):
    x=lx+j*cw+cw/2; mark=yr in ACT
    o.append(f'<text x="{x}" y="{ty-8}" text-anchor="middle" font-size="9.5" font-weight="{700 if mark else 400}" fill="{RED if mark else MUTED}" transform="rotate(-60 {x} {ty-8})">{yr}</text>')
for i,(key,lab,kind) in enumerate(rows):
    y=ty+i*ch; o.append(f'<text x="{lx-8}" y="{y+ch/2+4}" text-anchor="end" font-size="11" fill="{INK}">{lab}</text>')
    s=ym26[key];
    for j,yr in enumerate(years):
        v=s.get(yr); x=lx+j*cw
        if v!=v: continue
        if key=="t": c=col_div(v,0.7); txt=f"{v:+.1f}"
        elif key=="zdt": c=col_div(v,1.0,False); txt=f"{v:+.1f}"
        elif key=="rain": f=(v-35)/(62-35); c=lerp("#f6e9d4","#1862d8",max(0,min(1,f))); txt=f"{v:.0f}"
        else: f=(v-88)/(100-88); c=lerp("#e7b5af","#ffffff",max(0,min(1,f))); txt=f"{v:.0f}"
        o.append(f'<rect x="{x+1}" y="{y+1}" width="{cw-2}" height="{ch-2}" rx="3" fill="{c}"><title>{esc(f"{yr} — {lab}: {v:.2f}")}</title></rect>')
        o.append(f'<text x="{x+cw/2}" y="{y+ch/2+3.5}" text-anchor="middle" font-size="8.5" fill="{INK}">{txt}</text>')
for j,yr in enumerate(years):
    if yr in ACT: o.append(f'<rect x="{lx+j*cw+1}" y="{ty+1}" width="{cw-2}" height="{ch*len(rows)-2}" rx="3" fill="none" stroke="{RED}" stroke-width="1.5"/>')
o.append(f'<text x="{lx}" y="{H-8}" font-size="10.5" fill="{MUTED}">Outlined: Trigger 2 activation years. 2026 partial (to 1 Sep). Red = hot, low biomass, low water balance; blue = wet, cool.</text>')
o.append("</svg>"); open(f"{S}/tf3.svg","w").write("\n".join(o))
print("ok")
