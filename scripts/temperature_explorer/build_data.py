"""Build the data file for the temperature explorer (pages/temperature-explorer/data.json).

The indicator is the one used on the heat-and-impact page (scripts/impact_analysis.py): JRC ASAP
temperature over cropland (variable 140, "crop during growing cycle" mask, ECMWF), averaged over
a window of dekads per province and season, expressed as the departure from the province's own
Theil-Sen trend fitted over 1989-2025. The window mean and the anomaly are computed in the
browser, so this file stores the dekadal temperatures (0.001 degC) for the dekads the explorer offers.

Inputs (downloaded by hand, never committed):
  1. ASAP indicator statistics, temperature over cropland, all Burkina Faso provinces:
       curl -s -o temp_crop.csv "https://agricultural-production-hotspots.ec.europa.eu/export/rum/export.php?gaul_level=2&country_id=17&variable_id=140&class_id=1&classesset_id=1&sensor_id=4"
  2. FEWS NET crop production CSV and 3. FAOSTAT CSV: see scripts/asap_explorer/build_data.py.
  4. Province boundaries: OCHA COD-AB for Burkina Faso, 2020 edition (45 provinces, before the
     2025 reform), e.g. bfa_adm2.shp from pa-aa-bfa-drought/temp/ (EPSG:4326).
  5. pages/asap-explorer/data.json (province list and display order, shared with the ASAP explorer).

Usage:
  uv run --with pandas --with geopandas --with pyogrio python scripts/temperature_explorer/build_data.py \\
      temp_crop.csv bf_crop.csv bfa_faostat.csv bfa_adm2.shp pages/temperature-explorer/data.json
"""

import importlib.util
import json
import math
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("asap_build", HERE.parent / "asap_explorer" / "build_data.py")
asap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asap)

YEARS = list(range(1989, 2027))
DEKADS = list(range(17, 30))  # 2nd dekad of June to 2nd dekad of October: complete for every province and year
FIT_YEARS = [1989, 2025]  # trend fitted on complete seasons only, as in the analysis
NATIONAL_YIELD_YEARS = list(range(1989, 2024))  # FAOSTAT official figures; 2024 is imputed/unofficial
ASAP_EXPLORER_DATA = HERE.parent.parent / "pages" / "asap-explorer" / "data.json"
MAP_WIDTH = 600  # SVG user units


def load_temperature(path: str, provinces: list[dict]) -> tuple[dict, str]:
    d = pd.read_csv(path, dtype={"date": str})
    if not {"region_id", "variable_id", "class_id", "date", "value"} <= set(d.columns):
        raise SystemExit("unexpected ASAP export columns")
    if set(d["variable_id"]) != {140} or set(d["class_id"]) != {1} or set(d["class_name"]) != {"Crop during growing cycle"}:
        raise SystemExit("expected temperature (variable 140) over cropland during the growing cycle (classesset 1)")
    d["date"] = pd.to_datetime(d["date"], format="%Y%m%d")
    d["year"] = d["date"].dt.year
    d["dekad"] = asap.dekad_of(d["date"])
    ids = {p["id"] for p in provinces}
    if set(d["region_id"]) != ids:
        raise SystemExit(f"province ids differ from the ASAP explorer: {sorted(set(d['region_id']) ^ ids)}")
    last = d["date"].max().date().isoformat()
    d = d[d["year"].isin(YEARS) & d["dekad"].isin(DEKADS)]
    if d.duplicated(["region_id", "year", "dekad"]).any():
        raise SystemExit("duplicate province-dekads")
    out = {}
    for p in provinces:
        g = d[d["region_id"] == p["id"]].set_index(["year", "dekad"])["value"]
        vals = []
        for y in YEARS:
            for dk in DEKADS:
                v = g.get((y, dk))
                if v is None or pd.isna(v):
                    raise SystemExit(f"missing temperature: {p['name']} {y} dekad {dk}")
                vals.append(int(round(float(v) * 1000)))  # 0.001 degC, the precision of the export
        out[str(p["id"])] = vals
    return out, last


def build_map(shp_path: str, provinces: list[dict]) -> dict:
    g = gpd.read_file(shp_path).to_crs(4326)
    g["key"] = g["ADM2_FR"].map(asap.norm)
    by_key = {asap.norm(p["name"]): p for p in provinces}
    if set(g["key"]) != set(by_key) or g["key"].duplicated().any():
        raise SystemExit(f"boundary crosswalk failed: {sorted(set(g['key']) ^ set(by_key))}")
    # simplify as a coverage so neighbouring provinces keep shared edges
    g["geometry"] = shapely.coverage_simplify(g.geometry.values, tolerance=0.02)
    minx, miny, maxx, maxy = g.total_bounds
    lat0 = math.radians((miny + maxy) / 2)
    sx = MAP_WIDTH / ((maxx - minx) * math.cos(lat0))
    height = (maxy - miny) * sx

    def path(geom):
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        parts = []
        for poly in polys:
            for ring in [poly.exterior, *poly.interiors]:
                pts = [((x - minx) * math.cos(lat0) * sx, (maxy - y) * sx) for x, y in ring.coords]
                parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts[:-1]) + "Z")
        return "".join(parts)

    prov_paths = {str(by_key[k]["id"]): path(geom) for k, geom in zip(g["key"], g.geometry)}
    regions = g.dissolve(by="ADM1_FR").geometry
    return {"width": MAP_WIDTH, "height": round(height, 1), "provinces": prov_paths,
            "regions": [path(geom) for geom in regions]}


def main(temp_path: str, fdw_path: str, fao_path: str, shp_path: str, out_path: str) -> None:
    asap_data = json.loads(ASAP_EXPLORER_DATA.read_text(encoding="utf-8"))
    provinces = asap_data["provinces"]
    temp, last = load_temperature(temp_path, provinces)
    yld = asap.load_yield(fdw_path, fao_path, provinces)
    yld["national_years"] = NATIONAL_YIELD_YEARS
    yld["national"] = asap.load_national_yield(fao_path, NATIONAL_YIELD_YEARS)
    data = {
        "meta": {
            "built": date.today().isoformat(),
            "asap_last_dekad": last,
            "years": YEARS,
            "dekads": DEKADS,
            "fit_years": FIT_YEARS,
            "framework_years": asap.FRAMEWORK_YEARS,
            "impact_seasons_main": asap.IMPACT_SEASONS_MAIN,
            "impact_seasons_alt": asap.IMPACT_SEASONS_ALT,
            "impact_record_years": asap.IMPACT_RECORD_YEARS,
        },
        "provinces": provinces,
        "temp": temp,
        "map": build_map(shp_path, provinces),
        "yield": yld,
        "impacts": asap.IMPACTS,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out_path}: {len(provinces)} provinces, {YEARS[0]}-{YEARS[-1]}, dekads {DEKADS[0]}-{DEKADS[-1]}, "
          f"ASAP to {last}, {Path(out_path).stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    if len(sys.argv) != 6:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
