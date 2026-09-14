import json, sys, html
import pandas as pd, numpy as np
S=sys.argv[1]; R=json.load(open(f"{S}/detrend_results.json"))
T=R["T_CAL"]; PROV=["Loroum","Oudalan","Séno","Yagha"]
INK="#1f2324"; MUTED="#5e6a6b"; FAINT="#7e8e8f"; GRID="#e2e8e8"; ACC="#1e795f"; ACC2="#9d372b"; AMBER="#d48f2a"
FONT='font-family="Roboto,system-ui,sans-serif"'
def esc(s): return html.escape(str(s))
def svg_open(W,H,title,tid): return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" {FONT} role="img" aria-labelledby="{tid}"><title id="{tid}">{esc(title)}</title>']

# ---------- Fig A: slopes for all provinces, dot chart, sorted by rangeland slope
tr=pd.DataFrame(R["trend"]); piv=tr.pivot(index="name",columns="lc",values="slope_dec"); pv=tr.pivot(index="name",columns="lc",values="p")
aoi=set(tr[tr.aoi].name); piv=piv.sort_values("range")
W=760; lx=110; cw=560; rh=13; ty=44; H=ty+rh*len(piv)+62
xmin,xmax=-1.0,1.0
def X(v): return lx+(v-xmin)/(xmax-xmin)*cw
o=svg_open(W,H,"Theil-Sen trend in seasonal-mean zFPARc per province, 2001–2025, z per decade","fa")
for v in [-1,-0.5,0,0.5,1]:
    o.append(f'<line x1="{X(v):.1f}" y1="{ty-6}" x2="{X(v):.1f}" y2="{H-52}" stroke="{"#9db1b3" if v==0 else GRID}" stroke-width="{1.4 if v==0 else 1}"/>')
    o.append(f'<text x="{X(v):.1f}" y="{ty-12}" text-anchor="middle" font-size="10.5" fill="{MUTED}">{v:+.1f}</text>')
o.append(f'<text x="{X(0):.1f}" y="{H-36}" text-anchor="middle" font-size="11" fill="{MUTED}">Trend in seasonal-mean zFPARc (z-score units per decade)</text>')
for i,(name,row) in enumerate(piv.iterrows()):
    y=ty+i*rh+rh/2; isa=name in aoi
    o.append(f'<text x="{lx-8}" y="{y+3.5:.1f}" text-anchor="end" font-size="{11 if isa else 9.5}" font-weight="{500 if isa else 400}" fill="{INK if isa else FAINT}">{esc(name)}</text>')
    c=row["crop"]; r=row["range"]
    if pd.notna(c) and pd.notna(r): o.append(f'<line x1="{X(min(c,r)):.1f}" y1="{y:.1f}" x2="{X(max(c,r)):.1f}" y2="{y:.1f}" stroke="{GRID if not isa else "#bee0d6"}" stroke-width="2"/>')
    for lc,val,fill,shape in [("crop",c,ACC if isa else "#b1c1c2","circle"),("range",r,ACC2 if isa else "#c4d0d1","square")]:
        if pd.isna(val): continue
        sig=pv.loc[name,lc]<0.05
        tip=f'{name} — {lc}: {val:+.2f} z/decade (Mann-Kendall p={pv.loc[name,lc]:.3f})'
        if shape=="circle": o.append(f'<circle cx="{X(val):.1f}" cy="{y:.1f}" r="{4.5 if isa else 3.2}" fill="{fill}" stroke="#fff" stroke-width="1"><title>{esc(tip)}</title></circle>')
        else: o.append(f'<rect x="{X(val)-(4.5 if isa else 3.2):.1f}" y="{y-(4.5 if isa else 3.2):.1f}" width="{9 if isa else 6.4}" height="{9 if isa else 6.4}" fill="{fill}" stroke="#fff" stroke-width="1"><title>{esc(tip)}</title></rect>')
# legend
ly=H-8; lx0=lx
o.append(f'<circle cx="{lx0}" cy="{ly-4}" r="4.5" fill="{ACC}"/><text x="{lx0+9}" y="{ly}" font-size="10.5" fill="{INK}">Cropland</text>')
o.append(f'<rect x="{lx0+70}" y="{ly-8.5}" width="9" height="9" fill="{ACC2}"/><text x="{lx0+84}" y="{ly}" font-size="10.5" fill="{INK}">Rangeland</text>')
o.append(f'<text x="{lx0+150}" y="{ly}" font-size="10.5" fill="{MUTED}">Framework provinces in colour; others grey</text>')
o.append('</svg>'); open(f"{S}/figA.svg","w").write("\n".join(o))

# ---------- Fig B: 4x2 small multiples, window-mean zFPARc, observed vs detrended, thresholds
ann=pd.DataFrame(R["annual"]); years=list(range(2001,2027))
pw,ph=300,130; gx=40; gy=44; lx=48; ty=34; W=lx+2*pw+gx+10; H=ty+4*(ph+gy)
ymin,ymax=-2.2,2.6
o=svg_open(W,H,"Window-mean zFPARc (dekads 21–26) per framework province, cropland and rangeland, 2001–2026: as published vs detrended","fb")
def px(y0,yr): return y0+ (yr-2001)/(2026-2001)*(pw-10)+5
def py(y0,v): return y0+ph-(v-ymin)/(ymax-ymin)*ph
for i,p in enumerate(PROV):
    for j,lc in enumerate(["crop","range"]):
        x0=lx+j*(pw+gx); y0=ty+i*(ph+gy)
        o.append(f'<text x="{x0}" y="{y0-8}" font-size="12" font-weight="500" fill="{INK}">{esc(p)} · {"cropland" if lc=="crop" else "rangeland"}</text>')
        for v in [-2,-1,0,1,2]:
            o.append(f'<line x1="{x0}" y1="{py(y0,v):.1f}" x2="{x0+pw}" y2="{py(y0,v):.1f}" stroke="{GRID}" stroke-width="1"/>')
            o.append(f'<text x="{x0-6}" y="{py(y0,v)+3.5:.1f}" text-anchor="end" font-size="9.5" fill="{FAINT}">{v:+d}</text>')
        # thresholds
        o.append(f'<line x1="{x0}" y1="{py(y0,T):.1f}" x2="{x0+pw}" y2="{py(y0,T):.1f}" stroke="{AMBER}" stroke-width="1.2" stroke-dasharray="4 3"/>')
        o.append(f'<line x1="{x0}" y1="{py(y0,-1):.1f}" x2="{x0+pw}" y2="{py(y0,-1):.1f}" stroke="{ACC2}" stroke-width="1.2" stroke-dasharray="4 3"/>')
        for yr in [2005,2010,2015,2020,2025]:
            o.append(f'<text x="{px(x0,yr):.1f}" y="{y0+ph+12}" text-anchor="middle" font-size="9.5" fill="{FAINT}">{yr}</text>')
        d=ann[(ann.name==p)&(ann.lc==lc)].sort_values("year")
        for col,color,wd,dash in [("value","#9db1b3",2,""),("z_det",ACC,2,"")]:
            pts=" ".join(f'{px(x0,r.year):.1f},{py(y0,getattr(r,col)):.1f}' for r in d.itertuples())
            o.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{wd}" stroke-linejoin="round" {dash}/>')
        for r in d.itertuples():
            o.append(f'<circle cx="{px(x0,r.year):.1f}" cy="{py(y0,r.value):.1f}" r="2.6" fill="#9db1b3"><title>{esc(f"{p} {lc} {r.year}: published {r.value:+.2f}, detrended {r.z_det:+.2f}")}</title></circle>')
            o.append(f'<circle cx="{px(x0,r.year):.1f}" cy="{py(y0,r.z_det):.1f}" r="2.6" fill="{ACC}"><title>{esc(f"{p} {lc} {r.year}: published {r.value:+.2f}, detrended {r.z_det:+.2f}")}</title></circle>')
ly=H-6
o.append(f'<line x1="{lx}" y1="{ly-4}" x2="{lx+22}" y2="{ly-4}" stroke="#9db1b3" stroke-width="2.5"/><text x="{lx+28}" y="{ly}" font-size="10.5" fill="{INK}">As published by ASAP</text>')
o.append(f'<line x1="{lx+150}" y1="{ly-4}" x2="{lx+172}" y2="{ly-4}" stroke="{ACC}" stroke-width="2.5"/><text x="{lx+178}" y="{ly}" font-size="10.5" fill="{INK}">Detrended (re-centred on 2001–2025 mean)</text>')
o.append(f'<line x1="{lx+400}" y1="{ly-4}" x2="{lx+422}" y2="{ly-4}" stroke="{AMBER}" stroke-width="1.5" stroke-dasharray="4 3"/><text x="{lx+428}" y="{ly}" font-size="10.5" fill="{INK}">Calibrated cut-off {T}</text>')
o.append(f'<line x1="{lx+545}" y1="{ly-4}" x2="{lx+567}" y2="{ly-4}" stroke="{ACC2}" stroke-width="1.5" stroke-dasharray="4 3"/><text x="{lx+573}" y="{ly}" font-size="10.5" fill="{INK}">ASAP −1</text>')
o.append('</svg>'); open(f"{S}/figB.svg","w").write("\n".join(o))

# ---------- Fig C: activation matrix
per={k:pd.DataFrame(v) for k,v in R["per"].items()}
obs=pd.DataFrame(R["yr_obs"]).set_index("year")
cols=[("Observed ASAP warnings",None,"n_l3_obs"),("Proxy, as published, cut-off %.1f"%T,"trend|cal","n_l3"),("Proxy, detrended, cut-off %.1f"%T,"detrended|cal","n_l3"),
      ("Proxy, as published, −1","trend|minus1","n_l3"),("Proxy, detrended, −1","detrended|minus1","n_l3"),
      ("Biomass only, as published, cut-off %.1f"%T,"trend|cal","n_bio"),("Biomass only, detrended, cut-off %.1f"%T,"detrended|cal","n_bio")]
CNT={0:"#ebeff0",1:"#e7b5af",2:"#d06a5e",3:"#9d372b",4:"#4e1c16"}
cw,ch=92,17; lx=46; ty=74; W=lx+cw*len(cols)+70; H=ty+ch*len(years)+40
o=svg_open(W,H,"Maximum number of framework provinces meeting the criterion in any dekad 21–26, by year and method","fc")
for j,(lab,key,col) in enumerate(cols):
    x=lx+j*cw+cw/2; parts=lab.split(", ")
    for k,part in enumerate(parts): o.append(f'<text x="{x}" y="{ty-46+k*12}" text-anchor="middle" font-size="9.5" fill="{MUTED if k else INK}" font-weight="{500 if k==0 else 400}">{esc(part)}</text>')
for i,yr in enumerate(years):
    y=ty+i*ch
    o.append(f'<text x="{lx-6}" y="{y+ch/2+4}" text-anchor="end" font-size="11" fill="{INK}">{yr}</text>')
    for j,(lab,key,col) in enumerate(cols):
        x=lx+j*cw
        if key is None:
            v=obs.loc[yr,"max_l3_obs"] if yr in obs.index else None
        else:
            d=per[key]; d=d[d.year==yr]; v=int(d[col].max()) if len(d) else None
        if v is None or yr==2026 and False: continue
        v=int(v); fill=CNT[min(v,4)]
        o.append(f'<rect x="{x+1}" y="{y+1}" width="{cw-2}" height="{ch-2}" rx="3" fill="{fill}"><title>{esc(f"{yr} · {lab}: {v} province(s)")}</title></rect>')
        if v>0: o.append(f'<text x="{x+cw/2}" y="{y+ch/2+4}" text-anchor="middle" font-size="10" font-weight="500" fill="{"#fff" if v>=2 else INK}">{v}</text>')
        if v>=2: o.append(f'<rect x="{x+1}" y="{y+1}" width="{cw-2}" height="{ch-2}" rx="3" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    if yr==2026: o.append(f'<text x="{lx+cw*len(cols)+4}" y="{y+ch/2+4}" font-size="9" fill="{FAINT}">to dek 25</text>')
ly=H-8; xx=lx
o.append(f'<text x="{xx}" y="{ly-2}" font-size="10.5" fill="{INK}">Provinces meeting the criterion in the same dekad:</text>'); xx+=290
for n in range(0,5):
    o.append(f'<rect x="{xx}" y="{ly-11}" width="14" height="11" rx="2" fill="{CNT[n]}"/><text x="{xx+18}" y="{ly-2}" font-size="10.5" fill="{INK}">{n}</text>'); xx+=38
o.append(f'<rect x="{xx+10}" y="{ly-11}" width="14" height="11" rx="2" fill="none" stroke="{INK}" stroke-width="1.2"/><text x="{xx+28}" y="{ly-2}" font-size="10.5" fill="{INK}">≥ 2 = would activate</text>')
o.append('</svg>'); open(f"{S}/figC.svg","w").write("\n".join(o))

# ---------- Fig D: 2026 dekads 19-25, published vs detrended, per province (range & crop), thresholds
d26=pd.DataFrame(R["y2026"]); deks=list(range(19,26)); DEK={19:"1 Jul",20:"2 Jul",21:"3 Jul",22:"1 Aug",23:"2 Aug",24:"3 Aug",25:"1 Sep"}
pw,ph=200,120; gx=30; lx=44; ty=30; W=lx+4*(pw+gx); H=ty+ph+70
ymin,ymax=-1.4,2.6
o=svg_open(W,H,"2026 season: zFPARc by dekad for each framework province, as published vs detrended","fd")
def px2(x0,dk): return x0+(dk-19)/(25-19)*(pw-16)+8
def py2(v): return ty+ph-(v-ymin)/(ymax-ymin)*ph
for i,p in enumerate(PROV):
    x0=lx+i*(pw+gx)
    o.append(f'<text x="{x0}" y="{ty-10}" font-size="12" font-weight="500" fill="{INK}">{esc(p)}</text>')
    for v in [-1,0,1,2]:
        o.append(f'<line x1="{x0}" y1="{py2(v):.1f}" x2="{x0+pw}" y2="{py2(v):.1f}" stroke="{GRID}"/>')
        if i==0: o.append(f'<text x="{x0-6}" y="{py2(v)+3.5:.1f}" text-anchor="end" font-size="9.5" fill="{FAINT}">{v:+d}</text>')
    o.append(f'<line x1="{x0}" y1="{py2(T):.1f}" x2="{x0+pw}" y2="{py2(T):.1f}" stroke="{AMBER}" stroke-width="1.2" stroke-dasharray="4 3"/>')
    o.append(f'<line x1="{x0}" y1="{py2(-1):.1f}" x2="{x0+pw}" y2="{py2(-1):.1f}" stroke="{ACC2}" stroke-width="1.2" stroke-dasharray="4 3"/>')
    o.append(f'<rect x="{px2(x0,21)-4:.1f}" y="{ty}" width="{px2(x0,25)-px2(x0,21)+8:.1f}" height="{ph}" fill="{ACC}" opacity="0.06"/>')
    for dk in deks: o.append(f'<text x="{px2(x0,dk):.1f}" y="{ty+ph+13}" text-anchor="middle" font-size="9" fill="{FAINT}">{DEK[dk]}</text>')
    for lc,dash in [("crop",""),("range",'stroke-dasharray="5 3"')]:
        d=d26[(d26.name==p)&(d26.lc==lc)].sort_values("dekad")
        for col,color in [("value","#9db1b3"),("z_det",ACC)]:
            pts=" ".join(f'{px2(x0,r.dekad):.1f},{py2(getattr(r,col)):.1f}' for r in d.itertuples())
            o.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" {dash}/>')
            for r in d.itertuples(): o.append(f'<circle cx="{px2(x0,r.dekad):.1f}" cy="{py2(getattr(r,col)):.1f}" r="2.4" fill="{color}"><title>{esc(f"{p} {lc} {DEK[r.dekad]}: published {r.value:+.2f}, detrended {r.z_det:+.2f}")}</title></circle>')
ly=H-8
o.append(f'<line x1="{lx}" y1="{ly-4}" x2="{lx+22}" y2="{ly-4}" stroke="#9db1b3" stroke-width="2.5"/><text x="{lx+28}" y="{ly}" font-size="10.5" fill="{INK}">As published</text>')
o.append(f'<line x1="{lx+110}" y1="{ly-4}" x2="{lx+132}" y2="{ly-4}" stroke="{ACC}" stroke-width="2.5"/><text x="{lx+138}" y="{ly}" font-size="10.5" fill="{INK}">Detrended</text>')
o.append(f'<line x1="{lx+210}" y1="{ly-4}" x2="{lx+232}" y2="{ly-4}" stroke="{INK}" stroke-width="2"/><text x="{lx+238}" y="{ly}" font-size="10.5" fill="{INK}">solid = cropland</text>')
o.append(f'<line x1="{lx+340}" y1="{ly-4}" x2="{lx+362}" y2="{ly-4}" stroke="{INK}" stroke-width="2" stroke-dasharray="5 3"/><text x="{lx+368}" y="{ly}" font-size="10.5" fill="{INK}">dashed = rangeland</text>')
o.append(f'<text x="{lx+500}" y="{ly}" font-size="10.5" fill="{MUTED}">Shaded = Trigger 2 window</text>')
o.append('</svg>'); open(f"{S}/figD.svg","w").write("\n".join(o))
print("figs ok")
