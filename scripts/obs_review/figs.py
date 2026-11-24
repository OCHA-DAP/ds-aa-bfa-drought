"""Figures for the observational-trigger review (static PNG, light surface).

Usage: uv run --no-project --with pandas --with numpy --with matplotlib python scripts/obs_review/figs.py <obs_out dir>
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as c  # noqa: E402

SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
BLUE, ORANGE, AQUA, BASE = "#2a78d6", "#eb6834", "#1baf7a", "#c9c8c2"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def dek(d):
    return f"{MONTHS[(d - 1) // 3]} {(d - 1) % 3 + 1}"


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def fig_scan(d: Path, scan: dict) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.4), facecolor=SURF)
    style(ax)
    for key, s, col, ls, lab in [("aoi", "19", BLUE, "-", "17-province mean (n = 23 seasons), from 1 July"),
                                 ("pooled", "19", AQUA, "-", "province-seasons pooled (n = 388), from 1 July"),
                                 ("aoi", "17", BLUE, (0, (3, 2)), "17-province mean, from mid-June")]:
        x = scan[s][key]
        e = np.array(x["ends"])
        ax.plot(e, x["r"], color=col, lw=2, ls=ls, marker="o", ms=4, label=lab)
        if ls == "-":
            ax.fill_between(e, x["lo90"], x["hi90"], color=col, alpha=0.12, lw=0)
    ax.axhline(0, color=MUTED, lw=1)
    ax.axvline(28, color=INK2, lw=1, ls=":")
    ax.annotate("chosen end: 1–10 Oct", (28, 0.25), ha="right", va="top", fontsize=9, color=INK2, xytext=(-4, 0),
                textcoords="offset points")
    ax.set_xticks(range(19, 30), [dek(v) for v in range(19, 30)], rotation=45, ha="right")
    ax.set_ylabel("Correlation with yield anomaly", color=INK2, fontsize=9)
    ax.set_title("Season-to-date heat vs millet and sorghum yield, by last dekad included", loc="left", color=INK, fontsize=11)
    ax.text(0, -0.42, "Temperature: mean over cropland from the start dekad to the dekad shown, minus the province's own\n"
            "trend (1989–2025). Yield: FEWS NET province yield, % from trend, 2001–2023. Shading: 90% bootstrap\n"
            "interval (resampling seasons). Negative = hotter seasons had lower yields.", transform=ax.transAxes,
            fontsize=8, color=INK2)
    ax.legend(frameon=False, fontsize=8.5, loc="lower left", labelcolor=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(d / "fig1_dekad_scan.png", dpi=170, facecolor=SURF)
    plt.close(fig)


def fig_temp(d: Path, T: dict) -> None:
    a = pd.DataFrame(T["anoms"]["prior|19-28"])
    a.index = a.index.astype(int)
    yrs = list(range(2001, 2027))
    cnt = (a.loc[yrs] >= 0.3 - 1e-9).sum(axis=1)
    yld = c.province_yield_anom().mean(axis=1)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 5.6), sharex=True, facecolor=SURF,
                                   gridspec_kw={"height_ratios": [1.3, 1]})
    for ax in (ax1, ax2):
        style(ax)
    col = [ORANGE if v >= 5 else BASE for v in cnt]
    ax1.bar(yrs, cnt, width=0.6, color=col)
    ax1.axhline(5, color=INK2, lw=1, ls="--")
    ax1.text(2000.4, 5.3, "threshold: 5 of 17", fontsize=8, color=INK2)
    for y in yrs:
        if y in c.IMPACT_MAIN:
            ax1.text(y, cnt.loc[y] + 0.4, "impact", ha="center", fontsize=7.5, color=INK2, rotation=90, va="bottom")
    ax1.set_ylim(0, 21)
    ax1.set_ylabel("Provinces ≥ +0.3 °C\nabove own trend", color=INK2, fontsize=9)
    ax1.set_title("Proposed temperature rule, 1 July–10 October, 17 provinces (trend fitted on earlier seasons only)",
                  loc="left", color=INK, fontsize=10.5)
    from matplotlib.patches import Patch
    ax1.legend(handles=[Patch(color=ORANGE, label="threshold reached (5 of 25 seasons 2001–2025, plus 2026*)"),
                        Patch(color=BASE, label="not reached")], frameon=False, fontsize=8, loc="upper left",
               labelcolor=INK2)
    ax1.set_yticks(range(0, 21, 5))
    yv = yld.reindex(yrs)
    ax2.bar(yrs, yv, width=0.6, color=[ORANGE if cnt.loc[y] >= 5 else BASE for y in yrs])
    ax2.axhline(0, color=MUTED, lw=1)
    ax2.set_ylabel("Yield, % from trend\n(17-province mean)", color=INK2, fontsize=9)
    ax2.text(2024, 1, "no data\n2024–26", fontsize=7.5, color=MUTED)
    ax2.set_xticks(yrs[::2])
    fig.text(0.01, 0.01, "Impact = season dated to an EM-DAT drought event or CERF drought allocation (2011, 2013, 2017, "
             "2019, 2021). *2026 provisional (ASAP data to 11 Oct).", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(d / "fig2_temperature_rule.png", dpi=170, facecolor=SURF)
    plt.close(fig)


def fig_asap(d: Path, counts: dict) -> None:
    opts = [("ge3|21-26|or", 5, "Level 3+ (biomass with rainfall or water deficit), dekads 21–26, crop or rangeland"),
            ("ge1|22-28|or", 15, "Level 1+ (any rainfall or water-balance deficit), dekads 22–28, crop or rangeland")]
    yrs = list(range(2001, 2027))
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 5.4), sharex=True, facecolor=SURF)
    for ax, (key, k, title) in zip(axes, opts):
        style(ax)
        v = [counts[key][str(y)] for y in yrs]
        ax.bar(yrs, v, width=0.6, color=[ORANGE if x >= k else BASE for x in v])
        ax.axhline(k, color=INK2, lw=1, ls="--")
        ax.text(2000.4, k + 0.4, f"threshold: {k} of 17", fontsize=8, color=INK2)
        for y, x in zip(yrs, v):
            if y in c.IMPACT_MAIN:
                ax.text(y, x + 0.4, "impact", ha="center", fontsize=7.5, color=INK2, rotation=90, va="bottom")
        ax.set_ylim(0, 24)
        ax.set_title(title, loc="left", color=INK, fontsize=10)
        ax.set_ylabel("Provinces with warning", color=INK2, fontsize=9)
    axes[1].set_xticks(yrs[::2])
    fig.text(0.01, 0.01, "ASAP warning archive of Nov 2026 (past warnings revised). Orange = threshold reached. "
             "Impact seasons as in Figure 2. 2026 provisional.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(d / "fig3_asap_options.png", dpi=170, facecolor=SURF)
    plt.close(fig)


def main(d: str) -> None:
    d = Path(d)
    T = json.load(open(d / "temp_results.json"))
    fig_scan(d, T["dekad_scan"])
    fig_temp(d, T)
    fig_asap(d, json.load(open(d / "asap_options.json"))["counts"])
    print(sorted(p.name for p in d.glob("fig*.png")))


if __name__ == "__main__":
    main(sys.argv[1])
