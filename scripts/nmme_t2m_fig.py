"""Figure: NMME temperature forecast for Sep-Nov 2026 over the framework-province box."""
import html
import json
import sys

S = sys.argv[1]
R = json.load(open(f"{S}/nmme_summary.json"))
INK = "#1f2324"; MUTED = "#5e6a6b"; FAINT = "#7e8e8f"; GRID = "#e2e8e8"; RED = "#9d372b"; BLUE = "#1862d8"; ACC = "#1e795f"
LABEL = {"CanSIPS-IC4": "CanSIPS-IC4 (Canada)", "NASA-GEOSS2S": "NASA GEOS-S2S", "NCEP-CFSv2": "NCEP CFSv2"}
models = [m for m in ["CanSIPS-IC4", "NASA-GEOSS2S", "NCEP-CFSv2"] if m in R]
months = ["September", "October", "November"]
esc = html.escape

# Panel A: anomaly of ensemble mean (degC) with hindcast ensemble-mean sd as whisker; Panel B: P(upper tercile)
W = 760; lx = 150; pw = 250; gx = 60; ty = 40; rh = 22; mh = 18; H = ty + len(months) * (len(models) * rh + mh + 12) + 60
o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" font-family="Roboto,system-ui,sans-serif" role="img" aria-labelledby="ff"><title id="ff">NMME 2 m temperature forecast for the framework provinces, September 2026 start</title>']
xa0 = lx; xb0 = lx + pw + gx; pwb = W - xb0 - 50
amin, amax = -1.0, 3.6
def XA(v): return xa0 + (v - amin) / (amax - amin) * pw
def XB(v): return xb0 + v * pwb
o.append(f'<text x="{xa0 + pw / 2}" y="{ty - 24}" text-anchor="middle" font-size="11.5" font-weight="500" fill="{INK}">Ensemble-mean anomaly vs the model\'s own hindcast (°C)</text>')
o.append(f'<text x="{xb0 + pwb / 2}" y="{ty - 24}" text-anchor="middle" font-size="11.5" font-weight="500" fill="{INK}">Share of members in the warm tercile</text>')
for v in [-1, 0, 1, 2, 3]:
    o.append(f'<line x1="{XA(v):.1f}" y1="{ty - 6}" x2="{XA(v):.1f}" y2="{H - 50}" stroke="{"#9db1b3" if v == 0 else GRID}"/><text x="{XA(v):.1f}" y="{ty - 10}" text-anchor="middle" font-size="9.5" fill="{FAINT}">{v:+d}</text>')
for v in [0, 1 / 3, 0.5, 2 / 3, 1]:
    o.append(f'<line x1="{XB(v):.1f}" y1="{ty - 6}" x2="{XB(v):.1f}" y2="{H - 50}" stroke="{"#9db1b3" if abs(v - 1 / 3) < 0.01 else GRID}" stroke-dasharray="{"" if abs(v - 1 / 3) < 0.01 else "2 3"}"/><text x="{XB(v):.1f}" y="{ty - 10}" text-anchor="middle" font-size="9.5" fill="{FAINT}">{v * 100:.0f}%</text>')
o.append(f'<text x="{XB(1 / 3):.1f}" y="{H - 38}" text-anchor="middle" font-size="9.5" fill="{MUTED}">33% = climatology</text>')
y = ty
for mo in months:
    o.append(f'<text x="{lx - 8}" y="{y + 12}" text-anchor="end" font-size="12" font-weight="700" fill="{INK}">{mo}</text>')
    y += mh
    for m in models:
        r = [x for x in R[m] if x["month"] == mo]
        if not r:
            y += rh; continue
        r = r[0]
        o.append(f'<text x="{lx - 8}" y="{y + rh - 6}" text-anchor="end" font-size="10.5" fill="{MUTED}">{esc(LABEL[m])}</text>')
        a = r["anom"]; sd = r["hc_ensmean_sd"]
        c = RED if a > 0 else BLUE
        tip_a = esc("%s %s: ensemble mean %.1f °C, climatology %.1f °C, anomaly %+.2f °C = %+.1f sd of hindcast means; %d members, rank %d of %d" % (LABEL[m], mo, r["ens_mean"], r["clim"], a, r["anom_sd_ensmeans"], r["n_members"], r["rank_of_ensmean_among_hc_ensmeans"], r["n_hc_years"] + 1))
        o.append(f'<rect x="{min(XA(0), XA(a)):.1f}" y="{y + 5}" width="{abs(XA(a) - XA(0)):.1f}" height="{rh - 10}" fill="{c}" opacity="0.85"><title>{tip_a}</title></rect>')
        o.append(f'<line x1="{XA(a - sd):.1f}" y1="{y + rh / 2:.1f}" x2="{XA(a + sd):.1f}" y2="{y + rh / 2:.1f}" stroke="{INK}" stroke-width="1"/>')
        lab_x = XA(max(a + sd, a, 0)) + 5
        o.append(f'<text x="{lab_x:.1f}" y="{y + rh - 7}" font-size="10" fill="{INK}">{a:+.1f} °C</text>')
        p = r["p_upper"]
        tip_b = esc("%s %s: %.0f%% of members above the warm-tercile boundary, %.0f%% below the cool one" % (LABEL[m], mo, p * 100, r["p_lower"] * 100))
        fill_b = RED if p > 1 / 3 else "#9db1b3"
        o.append(f'<rect x="{XB(0):.1f}" y="{y + 5}" width="{XB(p) - XB(0):.1f}" height="{rh - 10}" fill="{fill_b}" opacity="0.85"><title>{tip_b}</title></rect>')
        o.append(f'<text x="{XB(p) + 5:.1f}" y="{y + rh - 7}" font-size="10" fill="{INK}">{p:.0%}</text>')
        y += rh
    y += 12
o.append(f'<text x="{lx}" y="{H - 24}" font-size="10" fill="{MUTED}">Bars: ensemble-mean anomaly. Whisker: ± one standard deviation of the hindcast ensemble means.</text>')
o.append(f'<text x="{lx}" y="{H - 10}" font-size="10" fill="{MUTED}">Box 13–16 °N, 3 °W–1 °E. Hindcasts 1991–2020 (CFSv2: 1991–2010).</text>')
o.append("</svg>")
open(f"{S}/tf4.svg", "w").write("\n".join(o))
print("ok")
