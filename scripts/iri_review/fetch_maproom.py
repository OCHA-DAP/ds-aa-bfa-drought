"""Pull IRI's Burkina Faso FbF Maproom series (JAS rainfall forecast) for the nation and the AOI regions.

Maproom: https://iridl.ldeo.columbia.edu/fbfmaproom2/burkinafaso (season1 = JAS, issues Jan-Jun,
start 1991). One export call returns, for one forecast version, issue month, severity ("freq")
and region: the region-average forecast probability that JAS rainfall falls below its s-th
percentile for every year, the Maproom's own threshold, and the bad-year ranks.

Versions served (Nov 2026): prcp-v1 (config Feb 2025, issues Jan-Jun, 1991-2025),
prcp-v4 (config Mar 2026, issues Mar-Jun, 1991-2026), prcp-v5 (config Mar 2026, issues Apr-Jun).

Regions: national (mode 0, BF) and the six 2026 regions that make up the old Boucle du Mouhoun,
Nord, Centre-Nord and Sahel regions (mode 1): Bankui BF62, Sourou BF61, Yaadga BF54, Koulse BF49,
Liptako BF64, Soum BF59.

Writes to $BFA_DATA_DIR/iri_maproom/: forecasts.csv, thresholds.csv, obs.csv, bad_years.csv.
Usage: BFA_DATA_DIR=... uv run --with pandas --with requests python scripts/iri_review/fetch_maproom.py
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

BASE = "https://iridl.ldeo.columbia.edu/fbfmaproom2/burkinafaso/export"
VERSIONS = {
    "prcp-v1": ["jan", "feb", "mar", "apr", "may", "jun"],
    "prcp-v4": ["mar", "apr", "may", "jun"],
    "prcp-v5": ["apr", "may", "jun"],
}
REGIONS = [(0, "BF")] + [(1, k) for k in ["BF62", "BF61", "BF54", "BF49", "BF64", "BF59"]]
SEVERITIES = list(range(5, 55, 5))
OBS = ["chirps-precip-jas", "chirps-precip-jjaso", "chirp-spi-jas", "chirps-dryspell"]
PREDICTANDS = ["bad-years-humanitarian", "bad-years-emdat"]


def export(mode, region, predictor, issue_month, freq, predictand="bad-years-humanitarian"):
    params = {"mode": mode, "season": "season1", "issue_month": issue_month, "freq": freq,
              "region": region, "predictor": predictor, "predictand": predictand,
              "include_upcoming": "true"}
    for attempt in range(4):
        try:
            r = requests.get(BASE, params=params, timeout=180)
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code == 200:
            return json.loads(r.text.replace("NaN", "null"))
        if r.status_code in (400, 500):
            return None
        time.sleep(10 * (attempt + 1))
    return None


def main() -> None:
    out = Path(os.environ["BFA_DATA_DIR"]) / "iri_maproom"
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(m, reg, v, im, s) for (m, reg) in REGIONS for v, ims in VERSIONS.items()
            for im in ims for s in SEVERITIES]

    def run(job):
        m, reg, v, im, s = job
        d = export(m, reg, v, im, s)
        time.sleep(0.3)
        return job, d

    rows, thr = [], []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for i, ((m, reg, v, im, s), d) in enumerate(ex.map(run, jobs)):
            if d is None:
                print("missing", m, reg, v, im, s, flush=True)
                continue
            thr.append({"region": reg, "version": v, "issue_month": im, "severity": s,
                        "maproom_threshold": d.get("threshold"), **{f"skill_{k}": x for k, x in (d.get("skill") or {}).items()}})
            for h in d["history"]:
                rows.append({"region": reg, "version": v, "issue_month": im, "severity": s,
                             "year": h["year"], "pne": h.get(v)})
            if i % 50 == 0:
                print(i, "/", len(jobs), flush=True)
    pd.DataFrame(rows).to_csv(out / "forecasts.csv", index=False)
    pd.DataFrame(thr).to_csv(out / "thresholds.csv", index=False)

    obs = []
    for m, reg in REGIONS:
        for o in OBS:
            d = export(m, reg, o, "jun", 30)
            if d is None:
                print("missing obs", reg, o)
                continue
            for h in d["history"]:
                obs.append({"region": reg, "variable": o, "year": h["year"], "value": h.get(o)})
            time.sleep(0.3)
    pd.DataFrame(obs).to_csv(out / "obs.csv", index=False)

    bad = []
    for p in PREDICTANDS:
        d = export(0, "BF", "prcp-v1", "jun", 30, predictand=p)
        for h in d["history"]:
            bad.append({"predictand": p, "year": h["year"], "rank": h.get(p)})
    pd.DataFrame(bad).to_csv(out / "bad_years.csv", index=False)
    print("wrote", sorted(x.name for x in out.iterdir()))


if __name__ == "__main__":
    main()
