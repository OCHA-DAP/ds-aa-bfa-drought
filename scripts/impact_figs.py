import json, sys, html
import pandas as pd, numpy as np
from scipy import stats
S=sys.argv[1]; D=pd.read_csv(f"{S}/impact_table.csv",index_col=0); R=json.load(open(f"{S}/impact_results.json"))
INK="#1f2324"; MUTED="#5e6a6b"; FAINT="#7e8e8f"; GRID="#e2e8e8"; ACC="#1e795f"; RED="#9d372b"; AMBER="#d48f2a"; BLUE="#1862d8"
FONT='font-family="Roboto,system-ui,sans-serif"'; esc=html.escape
def head(W,H,title,tid): return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" {FONT} role="img" aria-labelledby="{tid}"><title id="{tid}">{esc(title)}</title>']
years=list(D.index); MAIN=set(R["main"]); ALT=set(R["alt"])

# ---- Fig 1: production anomaly bars with impact markers; temp & biomass strips beneath (AOI)
W=760; lx=190; cw=(W-lx-16)/len(years); ty=30; ph=150; H=ty+ph+30+3*26+40
o=head(W,H,"National millet and sorghum production anomaly 2001–2024 with impact seasons, and framework-province temperature and biomass anomalies","g1")
ymin,ymax=-22,22
def X(i): return lx+i*cw
def Y(v): return ty+ph-(v-ymin)/(ymax-ymin)*ph
for v in [-20,-10,0,10,20]: o.append(f'<line x1="{lx}" y1="{Y(v):.1f}" x2="{W-16}" y2="{Y(v):.1f}" stroke="{"#9db1b3" if v==0 else GRID}"/><text x="{lx-6}" y="{Y(v)+3.5:.1f}" text-anchor="end" font-size="9.5" fill="{FAINT}">{v:+d}%</text>')
o.append(f'<text x="{lx}" y="{ty-10}" font-size="12" font-weight="500" fill="{INK}">Millet + sorghum production, % from 2001–2024 trend (FAOSTAT)</text>')
for i,yr in enumerate(years):
    v=D.prod_anom[yr]; c=RED if v<0 else "#7dc1ad"
    o.append(f'<rect x="{X(i)+3:.1f}" y="{min(Y(v),Y(0)):.1f}" width="{cw-6:.1f}" height="{abs(Y(v)-Y(0)):.1f}" rx="2" fill="{c}"><title>{esc(f"{yr}: {v:+.1f}%")}</title></rect>')
    if yr in MAIN: o.append(f'<circle cx="{X(i)+cw/2:.1f}" cy="{ty+ph+10}" r="4.5" fill="{RED}"><title>{esc(f"{yr}: impact season (evidence-dated)")}</title></circle>')
    if yr in ALT and yr not in MAIN:
        tip=esc("%d: impact season under the framework dating (alternative)"%yr)
        o.append(f'<circle cx="{X(i)+cw/2:.1f}" cy="{ty+ph+10}" r="4.5" fill="#fff" stroke="{RED}" stroke-width="1.6"><title>{tip}</title></circle>')
o.append(f'<text x="{lx-6}" y="{ty+ph+14}" text-anchor="end" font-size="9.5" fill="{MUTED}">Impact season</text>')
def strip(row,key,label,lim,warm_is_bad):
    y0=ty+ph+30+row*26
    o.append(f'<text x="{lx-6}" y="{y0+16}" text-anchor="end" font-size="9.5" fill="{MUTED}">{esc(label)}</text>')
    for i,yr in enumerate(years):
        v=D[key][yr]
        if v!=v: continue
        f=max(-1,min(1,v/lim));
        if warm_is_bad: c="#%02x%02x%02x"%tuple(int(255+(a-255)*f) for a in (157,55,43)) if f>0 else "#%02x%02x%02x"%tuple(int(255+(a-255)*(-f)) for a in (24,98,216))
        else: c="#%02x%02x%02x"%tuple(int(255+(a-255)*f) for a in (30,121,95)) if f>0 else "#%02x%02x%02x"%tuple(int(255+(a-255)*(-f)) for a in (157,55,43))
        o.append(f'<rect x="{X(i)+1:.1f}" y="{y0+2}" width="{cw-2:.1f}" height="20" rx="3" fill="{c}"><title>{esc(f"{yr} {label}: {v:+.2f}")}</title></rect>')
        o.append(f'<text x="{X(i)+cw/2:.1f}" y="{y0+16}" text-anchor="middle" font-size="8" fill="{INK}">{v:+.1f}</text>')
strip(0,"t_dt_aoi","Temp, Jul–Sep, from trend (°C)",0.7,True); strip(1,"z_dt_aoi","Biomass, window, detrended (z)",1.0,False); strip(2,"t_dt_nat","Temp, national (°C)",0.5,True)
for i,yr in enumerate(years): o.append(f'<text x="{X(i)+cw/2:.1f}" y="{H-10}" text-anchor="middle" font-size="8.5" fill="{MUTED}" transform="rotate(-60 {X(i)+cw/2:.1f} {H-10})">{yr}</text>')
o.append("</svg>"); open(f"{S}/ig1.svg","w").write("\n".join(o))

# ---- Fig 2: scatter temp (AOI, detrended) vs production anomaly, colour = biomass tercile, impact years ringed; national temp as second panel
def scatter(o,x0,tkey,zkey,title):
    pw,ph=320,260; ty=36; xmin,xmax=-0.8,0.9; ymin,ymax=-22,22
    def X(v): return x0+(v-xmin)/(xmax-xmin)*pw
    def Y(v): return ty+ph-(v-ymin)/(ymax-ymin)*ph
    o.append(f'<text x="{x0}" y="{ty-14}" font-size="12" font-weight="500" fill="{INK}">{esc(title)}</text>')
    for v in [-20,-10,0,10,20]: o.append(f'<line x1="{x0}" y1="{Y(v):.1f}" x2="{x0+pw}" y2="{Y(v):.1f}" stroke="{"#9db1b3" if v==0 else GRID}"/><text x="{x0-5}" y="{Y(v)+3.5:.1f}" text-anchor="end" font-size="9" fill="{FAINT}">{v:+d}%</text>')
    for v in [-0.5,0,0.5]: o.append(f'<line x1="{X(v):.1f}" y1="{ty}" x2="{X(v):.1f}" y2="{ty+ph}" stroke="{"#9db1b3" if v==0 else GRID}"/><text x="{X(v):.1f}" y="{ty+ph+13}" text-anchor="middle" font-size="9" fill="{FAINT}">{v:+.1f} °C</text>')
    d=D.dropna(subset=[tkey,zkey]); q1,q2=d[zkey].quantile([1/3,2/3])
    sl,ic,r,p,_=stats.linregress(d[tkey],d.prod_anom); xa,xb=d[tkey].min(),d[tkey].max(); o.append(f'<line x1="{X(xa):.1f}" y1="{Y(ic+sl*xa):.1f}" x2="{X(xb):.1f}" y2="{Y(ic+sl*xb):.1f}" stroke="{INK}" opacity="0.6"/>')
    o.append(f'<text x="{x0+pw}" y="{ty-2}" text-anchor="end" font-size="10" fill="{INK}">{sl:+.1f}% per °C, r = {r:.2f}</text>')
    for yr,rw in d.iterrows():
        c=RED if rw[zkey]<q1 else BLUE if rw[zkey]>q2 else "#9db1b3"; imp=yr in MAIN
        o.append(f'<circle cx="{X(rw[tkey]):.1f}" cy="{Y(rw.prod_anom):.1f}" r="{5.5 if imp else 4.5}" fill="{c}" stroke="{RED if imp else "#fff"}" stroke-width="{2 if imp else 0.8}"><title>{esc(f"{yr}: temp {rw[tkey]:+.2f} °C, biomass {rw[zkey]:+.2f} z, production {rw.prod_anom:+.1f}%")}</title></circle>')
        if imp or abs(rw.prod_anom)>13: o.append(f'<text x="{X(rw[tkey])+7:.1f}" y="{Y(rw.prod_anom)+3.5:.1f}" font-size="9" fill="{INK}">{yr}</text>')
W=760; H=36+260+58
o=head(W,H,"Growing-season temperature anomaly vs national production anomaly, 2001–2024","g2")
scatter(o,50,"t_dt_aoi","z_dt_aoi","Framework provinces"); scatter(o,420,"t_dt_nat","z_dt_nat","All provinces (national mean)")
ly=H-8; xx=50
for c,l in [(RED,"Lowest-third biomass"),("#9db1b3","Middle third"),(BLUE,"Highest third")]: o.append(f'<circle cx="{xx+5}" cy="{ly-4}" r="4.5" fill="{c}"/><text x="{xx+13}" y="{ly}" font-size="10" fill="{INK}">{l}</text>'); xx+=len(l)*6+30
o.append(f'<circle cx="{xx+5}" cy="{ly-4}" r="5" fill="#fff" stroke="{RED}" stroke-width="2"/><text x="{xx+13}" y="{ly}" font-size="10" fill="{INK}">Impact season</text>')
o.append("</svg>"); open(f"{S}/ig2.svg","w").write("\n".join(o))

# ---- Fig 3: quadrants (AOI and national)
W=760; H=300
o=head(W,H,"Mean production anomaly and impact rate by heat and biomass quadrant","g3")
for k,(x0,scope,title) in enumerate([(70,"aoi","Framework provinces"),(420,"nat","All provinces")]):
    Q=R["quad"][scope]; cw,ch=150,95; ty=44
    o.append(f'<text x="{x0+cw}" y="{ty-24}" text-anchor="middle" font-size="12" font-weight="500" fill="{INK}">{title}</text>')
    o.append(f'<text x="{x0+cw/2}" y="{ty-8}" text-anchor="middle" font-size="9.5" fill="{MUTED}">low biomass</text><text x="{x0+cw*1.5}" y="{ty-8}" text-anchor="middle" font-size="9.5" fill="{MUTED}">high biomass</text>')
    for i,hn in enumerate(["hot","cool"]):
        o.append(f'<text x="{x0-6}" y="{ty+i*ch+ch/2+3}" text-anchor="end" font-size="9.5" fill="{MUTED}">{hn}</text>')
        for j,ln in enumerate(["low biomass","high biomass"]):
            q=Q[f"{hn} / {ln}"]; v=q["prod_mean"]; f=max(-1,min(1,v/12))
            c="#%02x%02x%02x"%tuple(int(255+(a-255)*(-f)) for a in (157,55,43)) if f<0 else "#%02x%02x%02x"%tuple(int(255+(a-255)*f) for a in (30,121,95))
            x=x0+j*cw; y=ty+i*ch
            tip=esc("%s / %s: %d seasons %s; mean production %+.1f%%; impact seasons %s"%(hn,ln,q["n"],q["years"],v,q["impact_years"]))
            o.append(f'<rect x="{x+2}" y="{y+2}" width="{cw-4}" height="{ch-4}" rx="5" fill="{c}"><title>{tip}</title></rect>')
            o.append(f'<text x="{x+cw/2}" y="{y+ch/2-14}" text-anchor="middle" font-size="18" font-weight="700" fill="{INK}">{v:+.1f}%</text>')
            n_=q["n"]; nimp=len(q["impact_years"]); yrs_=esc(", ".join(str(yy) for yy in q["years"]))
            o.append(f'<text x="{x+cw/2}" y="{y+ch/2+10}" text-anchor="middle" font-size="9.5" fill="{INK}">production, {n_} seasons</text>')
            o.append(f'<text x="{x+cw/2}" y="{y+ch/2+25}" text-anchor="middle" font-size="9.5" fill="{INK}">{nimp} of {n_} impact seasons</text>')
            pass
o.append(f'<text x="{70}" y="{H-22}" font-size="10" fill="{MUTED}">Splits at the 2001–2024 median of detrended Jul–Sep temperature and window biomass. Cell colour: mean production anomaly.</text>')
o.append(f'<text x="{70}" y="{H-8}" font-size="10" fill="{MUTED}">Hover a cell for the seasons in it.</text>')
o.append("</svg>"); open(f"{S}/ig3.svg","w").write("\n".join(o))
print("figs ok")
