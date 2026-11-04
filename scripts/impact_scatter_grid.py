"""Scatter grid for the heat-and-impact page: harvest and impact against each indicator.

Rows: national millet + sorghum production vs trend, national yield vs trend (FAOSTAT, 2001-2024 trend
as in scripts/impact_analysis.py), and the impact seasons (main dating). Columns: detrended Jul-Sep
temperature, detrended biomass, Jul-Sep rainfall, water balance, SPI-3 (definitions as in
scripts/impact_analysis.py). One grid for the four framework provinces, one for all 45 provinces.
Each panel carries one number: R^2 for production and yield, AUC for the impact seasons, both shown
as a percentage.

Usage: uv run --with pandas --with scipy python scripts/impact_scatter_grid.py <scratch dir>
  <scratch dir> holds impact_table.csv (written by scripts/impact_analysis.py) and faostat_bfa.csv.
Writes grid_aoi.svg, grid_nat.svg and grid_stats.json into the scratch dir.
"""
import html
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats

S = sys.argv[1]
D = pd.read_csv(f"{S}/impact_table.csv", index_col=0)

# national yield anomaly, same trend window and source as the production anomaly
f = pd.read_csv(f"{S}/faostat_bfa.csv", dtype=str)
f = f[f["Item"].isin(["Millet", "Sorghum"]) & f["Element"].isin(["Production", "Area harvested"])].copy()
f["Year"] = f["Year"].astype(int)
f["Value"] = f["Value"].astype(float)
t = f[f["Year"].between(2001, 2024)].pivot_table(index="Year", columns="Element", values="Value", aggfunc="sum")
yld = t["Production"] / t["Area harvested"]
b = np.polyfit(yld.index, yld.values, 1)
D["yield_anom"] = (yld - np.polyval(b, yld.index)) / np.polyval(b, yld.index) * 100
D = D.loc[2001:2024]

INK, MUTED, FAINT, GRID = "#1f2324", "#5e6a6b", "#7e8e8f", "#e2e8e8"
RED, GREY, BAND = "#9d372b", "#9aa8a9", "#fbf4ea"
FONT = 'font-family="Roboto,system-ui,sans-serif"'
esc = html.escape

COLS = [  # key suffix, title lines, unit for ticks, tooltip unit, drought-like direction (+1: higher is worse)
    ("t_dt", ["Temperature, Jul–Sep", "detrended (°C from trend)"], "°C", " °C", +1),
    ("z_dt", ["Biomass (FPAR)", "detrended (z)"], "z", " z", -1),
    ("rain", ["Rainfall, Jul–Sep", "(mm per dekad)"], "mm", " mm/dekad", -1),
    ("wsi", ["Water balance", "(WSI, %)"], "%", "%", -1),
    ("spi", ["Rainfall index", "(SPI-3)"], "", "", -1),
]
ROWS = [
    ("prod_anom", ["Production", "vs trend (%)"], "explained"),
    ("yield_anom", ["Yield", "vs trend (%)"], "explained"),
    ("impact_main", ["Drought impact", "season"], "ranked"),
]


def auc(score, lab):
    pos, neg = score[lab == 1], score[lab == 0]
    return float(np.mean([1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg]))


def ticks(lo, hi):
    span = hi - lo
    step = next(s for s in [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50] if span / s <= 4)
    first = np.ceil(lo / step) * step
    return [round(v, 6) for v in np.arange(first, hi + 1e-9, step)]


def fmt(v, unit):
    if unit in ("°C", "z", ""):
        return f"{v:+.1f}".replace("+0.0", "0").replace("-0.0", "0")
    return f"{v:.0f}"


def grid(scope, title):
    lx, top, pw, ph, gx, gy = 112, 54, 108, 104, 12, 30
    W = lx + len(COLS) * (pw + gx) + 4
    H = top + len(ROWS) * (ph + gy) + 30
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" {FONT} '
         f'role="img" aria-labelledby="sg-{scope}"><title id="sg-{scope}">{esc(title)}</title>']
    # highlight the temperature column
    o.append(f'<rect x="{lx - 8}" y="4" width="{pw + 14}" height="{H - 8}" rx="6" fill="{BAND}"/>')
    out = {}
    for ci, (key, tl, unit, tunit, sign) in enumerate(COLS):
        col = f"{key}_{scope}"
        x0 = lx + ci * (pw + gx)
        for li, line in enumerate(tl):
            o.append(f'<text x="{x0 + pw / 2:.1f}" y="{18 + li * 13}" text-anchor="middle" font-size="{12 if li == 0 else 10}" '
                     f'font-weight="{700 if li == 0 else 400}" fill="{INK if li == 0 else MUTED}">{esc(line)}</text>')
        xs = D[col]
        pad = (xs.max() - xs.min()) * 0.08
        xlo, xhi = xs.min() - pad, xs.max() + pad

        def X(v):
            return x0 + (v - xlo) / (xhi - xlo) * pw

        for ri, (tgt, rl, kind) in enumerate(ROWS):
            y0 = top + ri * (ph + gy)
            if ci == 0:
                for li, line in enumerate(rl):
                    o.append(f'<text x="4" y="{y0 + ph / 2 - 4 + li * 14}" font-size="{12.5 if li == 0 else 10}" '
                             f'font-weight="{700 if li == 0 else 400}" fill="{INK if li == 0 else MUTED}">{esc(line)}</text>')
            o.append(f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="#fff" stroke="{GRID}"/>')
            imp = D["impact_main"].values
            if kind == "explained":
                ys = D[tgt]
                ylo, yhi = -24, 24

                def Y(v):
                    return y0 + ph - (min(max(v, ylo), yhi) - ylo) / (yhi - ylo) * ph

                o.append(f'<line x1="{x0}" y1="{Y(0):.1f}" x2="{x0 + pw}" y2="{Y(0):.1f}" stroke="{GRID}"/>')
                if ci == 0:
                    for v in (-20, 0, 20):
                        o.append(f'<text x="{x0 - 4}" y="{Y(v) + 3:.1f}" text-anchor="end" font-size="9.5" fill="{FAINT}">{v:+d}%</text>'.replace("+0%", "0%"))
                sl, ic, r, p, _ = stats.linregress(xs, ys)
                o.append(f'<line x1="{X(xs.min()):.1f}" y1="{Y(ic + sl * xs.min()):.1f}" x2="{X(xs.max()):.1f}" '
                         f'y2="{Y(ic + sl * xs.max()):.1f}" stroke="{INK}" stroke-width="1.2" opacity="0.55"/>')
                for yr in D.index:
                    isimp = D.at[yr, "impact_main"] == 1
                    tip = f"{yr}: {xs[yr]:+.2f}{tunit}, {rl[0].lower()} {ys[yr]:+.1f}%" + (" (impact season)" if isimp else "")
                    o.append(f'<circle cx="{X(xs[yr]):.1f}" cy="{Y(ys[yr]):.1f}" r="{3.6 if isimp else 3}" fill="{RED if isimp else GREY}" '
                             f'stroke="#fff" stroke-width="0.6"><title>{esc(tip)}</title></circle>')
                val = r * r
                out[(tgt, key)] = dict(r2=round(val, 3), r=round(r, 3), p=round(p, 3))
            else:
                lanes = {1: y0 + ph * 0.3, 0: y0 + ph * 0.72}
                if ci == 0:
                    o.append(f'<text x="{x0 - 4}" y="{lanes[1] + 3:.1f}" text-anchor="end" font-size="9.5" fill="{RED}">yes</text>')
                    o.append(f'<text x="{x0 - 4}" y="{lanes[0] + 3:.1f}" text-anchor="end" font-size="9.5" fill="{FAINT}">no</text>')
                for lab in (1, 0):
                    o.append(f'<line x1="{x0 + 4}" y1="{lanes[lab]:.1f}" x2="{x0 + pw - 4}" y2="{lanes[lab]:.1f}" stroke="{GRID}"/>')
                    m = xs[D["impact_main"] == lab].mean()
                    o.append(f'<line x1="{X(m):.1f}" y1="{lanes[lab] - 11:.1f}" x2="{X(m):.1f}" y2="{lanes[lab] + 11:.1f}" '
                             f'stroke="{RED if lab else MUTED}" stroke-width="2"><title>{esc(("Impact seasons" if lab else "Other seasons") + f" average: {m:+.2f}{tunit}")}</title></line>')
                rng = np.random.default_rng(7)
                for yr in D.index:
                    lab = int(D.at[yr, "impact_main"])
                    jit = rng.uniform(-6, 6)
                    tip = f"{yr}: {xs[yr]:+.2f}{tunit}" + (" (impact season)" if lab else "")
                    o.append(f'<circle cx="{X(xs[yr]):.1f}" cy="{lanes[lab] + jit:.1f}" r="{3.6 if lab else 3}" fill="{RED if lab else GREY}" '
                             f'stroke="#fff" stroke-width="0.6" opacity="0.9"><title>{esc(tip)}</title></circle>')
                val = auc(sign * xs.values, imp)
                out[(tgt, key)] = dict(auc=round(val, 3))
            o.append(f'<text x="{x0 + pw - 5}" y="{y0 + 15}" text-anchor="end" font-size="15" font-weight="700" '
                     f'stroke="#fff" stroke-width="3" paint-order="stroke" '
                     f'fill="{INK if ci == 0 else MUTED}">{val * 100:.0f}%</text>')
        # x ticks under the last row
        yb = top + (len(ROWS) - 1) * (ph + gy) + ph
        for v in ticks(xlo, xhi):
            o.append(f'<line x1="{X(v):.1f}" y1="{yb}" x2="{X(v):.1f}" y2="{yb + 3}" stroke="{FAINT}"/>'
                     f'<text x="{X(v):.1f}" y="{yb + 13}" text-anchor="middle" font-size="9.5" fill="{FAINT}">{fmt(v, unit)}</text>')
    o.append("</svg>")
    return "\n".join(o), out


res = {}
for scope, label in [("aoi", "framework provinces"), ("nat", "all 45 provinces")]:
    svg, st = grid(scope, f"Production, yield and impact seasons against each indicator, {label}, 2001–2024")
    open(f"{S}/grid_{scope}.svg", "w").write(svg)
    res[scope] = {f"{t}|{k}": v for (t, k), v in st.items()}
json.dump(res, open(f"{S}/grid_stats.json", "w"), indent=1)
for scope, st in res.items():
    print(scope)
    for k, v in st.items():
        print("  ", k, v)
