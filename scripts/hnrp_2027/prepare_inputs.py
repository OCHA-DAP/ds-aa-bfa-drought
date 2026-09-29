"""Fetch every raw input for the HNRP 2027 Burkina Faso baseline into a work directory.

Needs: ocha-stratus with dev + prod blob access and the dev DB (fewsnet, hpc, ipc schemas).
Usage: prepare_inputs.py <workdir>
"""

import io
import sys
import time
from pathlib import Path

import ocha_stratus as stratus
import pandas as pd
import requests

WORK = Path(sys.argv[1])
(WORK / "asap").mkdir(parents=True, exist_ok=True)
(WORK / "jrc").mkdir(exist_ok=True)


def save_blob(name, out, **kw):
    (WORK / out).write_bytes(stratus.load_blob_data(name, **kw))
    print("blob ->", out)


# boundaries: COD-AB v03 (post-2024 reform, 47 provinces) + pre-reform FieldMaps copy (45)
save_blob("pa-aa-bfa-drought/raw/codab/bfa_admin_boundaries.shp.zip", "bfa_admin_boundaries_new.shp.zip")
save_blob("pa-aa-bfa-drought/raw/codab/bfa.shp.zip", "bfa_old.shp.zip")
# population: WorldPop 2020 1 km UN-adjusted (same raster as ds-floodexposure-monitoring)
save_blob("ds-floodexposure-monitoring/raw/worldpop/bfa_ppp_2020_1km_Aggregated_UNadj.tif", "bfa_pop_2020_1km.tif")
# FEWS NET 2026 unit geometry (ds-fewsnet-mirror)
save_blob("ds-fewsnet-mirror/processed/units/BFA.geojson", "fews_units_bfa_2026.geojson")
import geopandas as gpd  # noqa: E402

gpd.read_file(WORK / "fews_units_bfa_2026.geojson").to_file(WORK / "fews_units_bfa_2026.gpkg")

# FEWS NET classifications (dev DB mirror)
eng = stratus.get_engine(stage="dev")
pd.read_sql("select * from fewsnet.classification where iso3='BFA' and unit_type='fsc_admin_lhz' "
            "and scale<>'IPC Highest Household'", eng).to_parquet(WORK / "fews_bfa_classification.parquet")
# EM-DAT snapshot
stratus.emdat.load_emdat_from_blob(iso3="BFA").to_parquet(WORK / "emdat_bfa.parquet")

# GeoSahel / AGRHYMET biomass (DMP) at ADM2 (already on the 47 new provinces)
url = ("http://213.206.230.89:8080/geoserver/Biomass/wfs?service=WFS&version=1.0.0&request=GetFeature"
       "&typeName=Biomass:WA_BIO_ADM2_v4&outputFormat=csv&CQL_FILTER=adm0_pcode%3D%27BF%27")
b = pd.read_csv(io.StringIO(requests.get(url, timeout=600).text)).drop(columns=["the_geom"])
b.set_index("adm2_pcode").to_parquet(WORK / "bio_adm2_bfa.parquet")
print("GeoSahel biomass:", b.shape)

# JRC ASAP per-province indicator export (GAUL level 2 = the 45 pre-reform provinces).
# Export country id for Burkina Faso is 17 (the warnings files use asap0_id 219).
ASAP = "https://agricultural-production-hotspots.ec.europa.eu/export/rum/export.php"
IND = {"zfparc_crop": (240, 1, 1, 3), "zfparc_range": (240, 2, 1, 3), "spi3_crop": (40, 1, 1, 4),
       "spi3_range": (40, 2, 1, 4), "temp_crop": (140, 1, 1, 4), "rain_crop": (10, 1, 1, 4)}
for k, (v, c, cs, s) in IND.items():
    for attempt in range(3):
        r = requests.get(ASAP, params=dict(gaul_level=2, country_id=17, variable_id=v, class_id=c,
                                           classesset_id=cs, sensor_id=s), timeout=600)
        if r.ok and r.text.lstrip().startswith("country_id,") and len(r.text) > 1000:
            (WORK / "asap" / f"{k}.csv").write_text(r.text)
            print("ASAP", k, len(r.text))
            break
        time.sleep(10 * (attempt + 1))
    else:
        raise RuntimeError(f"ASAP export failed for {k}")

# JRC/CEMS GloFAS river flood hazard maps v2.1.2, categorised depth, RP10 + RP100
JRC = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard"
for rp in ["RP10", "RP100"]:
    for t in ["ID110_N20_W10", "ID111_N10_W10", "ID117_N20_W0", "ID118_N10_W0"]:
        f = WORK / "jrc" / f"{t}_{rp}_depth_reclass.tif"
        if not f.exists():
            f.write_bytes(requests.get(f"{JRC}/{rp}/{t}_{rp}_depth_reclass.tif", timeout=900).content)
print("done")
