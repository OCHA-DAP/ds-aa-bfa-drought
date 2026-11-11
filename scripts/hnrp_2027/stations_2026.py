"""Read the 2026 rain-gauge table (Word document, not public) into a station file with coordinates.

The document is a single table, one row per gauge: seasonal totals for the year, the previous year
and a normal, the two ratios, the onset date, the longest dry spell and the end-of-season date. The
source's assessment of each value (deficit / surplus, late / early, long / short) exists only as the
shading of the cell, so the shading is read too.

Nothing from the document is kept in this repository: the document, the description of its layout
(shading colours, class bounds), the name crosswalk and the output stay in the work directory
(archived on the dev blob with the other work files).

Usage: stations_2026.py <document.docx> <workdir>
  in : <workdir>/provinces.csv (province names and p-codes),
       <workdir>/stations_2026_format.json (layout of the document; see FMT below),
       <workdir>/stations_2026_alias.csv (station -> COD-AB commune or GeoNames place; see ALIAS below),
       COD-AB v03 (dev blob, cached in <workdir>), GeoNames BF dump (downloaded, cached in <workdir>)
  out: <workdir>/stations_2026.csv
"""

import io
import json
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import geopandas as gpd
import pandas as pd
import requests

DOCX, WORK = Path(sys.argv[1]), Path(sys.argv[2])
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# FMT keys: year; header_first_cell (text of the first cell of the last header row); shade (fill hex -> colour
# name); ratio_classes (colour name -> class, "" = unshaded); ratio_bounds ([upper bound, class, inclusive] in
# ascending order, last bound null); onset_flags, dry_spell_flags, end_flags (colour name -> flag); na (text)
FMT = json.loads((WORK / "stations_2026_format.json").read_text())
YEAR, SHADE, NA = FMT["year"], FMT["shade"], FMT["na"]
MONTHS = {"janv": 1, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "juillet": 7, "aout": 8,
          "sept": 9, "oct": 10, "nov": 11, "dec": 12}
COLS = ["region", "province", "station", "cum_2026", "cum_2025", "normal", "pct_2025", "pct_normal", "onset",
        "dry_spell", "end", "end_cmp"]
# ALIAS file columns: station, kind (commune | place), name, province
#   commune: `name` is the COD-AB v03 commune the gauge is named after (spelling differs from the document)
#   place  : `name` is a GeoNames feature (village, research station) inside the province
#   province (optional): COD-AB province when the document lists the gauge under another one


def norm(s):
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())


def cell(tc):
    """Text and shading of one table cell (the shading sits on the text runs)."""
    txt = " ".join("".join(t.text or "" for t in p.iter(W + "t")) for p in tc.iter(W + "p")).strip()
    fills, seen = set(), 0
    pr = tc.find(W + "tcPr")
    if pr is not None and pr.find(W + "shd") is not None:
        fills.add(pr.find(W + "shd").get(W + "fill"))
        seen += 1
    for r in tc.iter(W + "r"):
        rp = r.find(W + "rPr")
        if rp is None:
            continue
        for tag in ("shd", "highlight"):
            e = rp.find(W + tag)
            if e is not None:
                seen += tag == "shd"
                if "".join(t.text or "" for t in r.iter(W + "t")).strip():
                    fills.add(e.get(W + "fill") or e.get(W + "val"))
    # every shading element in the cell must be one of the two kinds read above (none on paragraphs, for instance)
    assert seen == sum(1 for _ in tc.iter(W + "shd")), ("shading in an unexpected place", txt)
    fills -= {None, "auto", "FFFFFF", "none"}
    assert len(fills) <= 1, (txt, fills)
    return txt, (SHADE[fills.pop()] if fills else "")


def to_date(s):
    if s == NA:
        return None
    d, m = s.rstrip(".").split("-")
    return f"{YEAR}-{MONTHS[norm(m)]:02d}-{int(d):02d}"


def to_num(s):
    return None if s == NA else float(s.replace("%", "").replace(",", ".").strip())


def ratio_class(v):
    """Class of an unrounded ratio, from the bounds given in the document's legend."""
    if pd.isna(v):
        return None
    for bound, name, inclusive in FMT["ratio_bounds"]:
        if bound is None or v < bound or (inclusive and v == bound):
            return name


# ---------------- the table ----------------
root = ET.fromstring(zipfile.ZipFile(DOCX).read("word/document.xml"))
tbl = next(el for el in root.find(W + "body") if el.tag == W + "tbl")
raw = [[cell(tc) for tc in tr.findall(W + "tc")] for tr in tbl.findall(W + "tr")]
hdr = next(i for i, r in enumerate(raw) if r[0][0] == FMT["header_first_cell"])
rows = raw[hdr + 1:]
assert all(len(r) == len(COLS) for r in rows), "unexpected table shape"
T = pd.DataFrame({c: [r[i][0] for r in rows] for i, c in enumerate(COLS)})
S = pd.DataFrame({c: [r[i][1] for r in rows] for i, c in enumerate(COLS)})
for c in ("region", "province"):
    T[c] = T[c].replace("", pd.NA).ffill()
assert not S[["region", "province", "station", "cum_2026", "cum_2025", "normal", "end"]].ne("").any().any()
assert not T.station.duplicated().any()

out = T[["region", "province", "station"]].rename(columns={"region": "region_doc", "province": "province_doc"})
for c in ("cum_2026", "cum_2025", "normal", "pct_2025", "pct_normal", "dry_spell"):
    out[c] = T[c].map(to_num)
out = out.rename(columns={"normal": "normal_1991_2020", "dry_spell": "dry_spell_days"})
out["onset"], out["end"] = T.onset.map(to_date), T.end.map(to_date)

# ratios: the printed percentages must be the rounded ratio of the totals, and the shading must be the legend's
# class of the UNROUNDED ratio (so a printed value on a class bound can sit in the class below)
for pc, den in (("pct_2025", "cum_2025"), ("pct_normal", "normal_1991_2020")):
    calc = 100 * out.cum_2026 / out[den]
    assert ((calc + 0.5).floordiv(1).fillna(-1) == out[pc].fillna(-1)).all(), pc
    shade = S[pc].map(FMT["ratio_classes"]).where(calc.notna(), None)
    assert (calc.map(ratio_class).fillna("") == shade.fillna("")).all(), f"{pc}: shading differs from the legend"
    out[pc.replace("pct", "ratio")] = calc.round(1)
    out[pc.replace("pct", "class")] = shade
# dates and dry spells: the flag is the shading
for c, flags in (("onset", "onset_flags"), ("dry_spell", "dry_spell_flags"), ("end_cmp", "end_flags")):
    assert set(S[c]) <= set(FMT[flags]) | {""}, f"unexpected shading in {c}"
out["onset_flag"] = S.onset.map(FMT["onset_flags"]).fillna("")
out["dry_spell_flag"] = S.dry_spell.map(FMT["dry_spell_flags"]).fillna("")
# the last column repeats the end date when the document compares it with a normal date, NA when it does not
assert ((T.end_cmp == NA) | (T.end_cmp == T.end)).all()
out["end_compared"] = T.end_cmp != NA
out["end_flag"] = S.end_cmp.map(FMT["end_flags"]).fillna("")
assert not (out.end_flag.ne("") & ~out.end_compared).any()

# ---------------- where the gauges are ----------------
P = pd.read_csv(WORK / "provinces.csv")[["adm2_pcode", "adm2_name", "hnrp_name_2026", "adm1_pcode", "adm1_name"]]
ALIAS = pd.read_csv(WORK / "stations_2026_alias.csv", dtype=str).fillna("").set_index("station")
cod = WORK / "bfa_admin_boundaries_new.shp.zip"
if not cod.exists():
    import ocha_stratus as stratus

    cod.write_bytes(stratus.load_blob_data("pa-aa-bfa-drought/raw/codab/bfa_admin_boundaries.shp.zip", stage="dev"))
gz = WORK / "geonames_BF.zip"
if not gz.exists():
    resp = requests.get("https://download.geonames.org/export/dump/BF.zip", timeout=120)
    resp.raise_for_status()
    gz.write_bytes(resp.content)
a2 = gpd.read_file(f"zip://{cod}!bfa_admin2.shp")[["adm2_name", "adm2_pcode", "geometry"]]
a3 = gpd.read_file(f"zip://{cod}!bfa_admin3.shp")[["adm3_name", "adm3_pcode", "adm2_pcode", "geometry"]]
caps = gpd.read_file(f"zip://{cod}!bfa_admincapitals.shp")  # seat of every commune (level 3)
caps = caps[caps.adm_p_lvl == 3].set_index("adm3_pcode")[["x_coord", "y_coord"]]
assert caps.index.is_unique and set(a3.adm3_pcode) <= set(caps.index)
gcols = ["id", "name", "ascii", "alt", "lat", "lon", "fclass", "fcode", "cc", "cc2", "a1", "a2", "a3", "a4", "pop",
         "elev", "dem", "tz", "mod"]
G = pd.read_csv(io.BytesIO(zipfile.ZipFile(gz).read("BF.txt")), sep="\t", names=gcols, dtype=str, keep_default_na=False)
G = G.assign(lat=lambda d: d.lat.astype(float), lon=lambda d: d.lon.astype(float), key=lambda d: d.ascii.map(norm))
G = gpd.GeoDataFrame(G, geometry=gpd.points_from_xy(G.lon, G.lat), crs=4326).sjoin(a3[["adm3_pcode", "geometry"]], how="left")
pkey = {norm(n): pc for n, pc in zip(P.adm2_name, P.adm2_pcode)}  # COD-AB v03 and HNRP 2026 spellings
pkey.update({norm(n): pc for n, pc in zip(P.hnrp_name_2026, P.adm2_pcode) if isinstance(n, str)})
pkey.update({norm(n): pc for n, pc in zip(a2.adm2_name, a2.adm2_pcode)})

loc = []
for r in out.itertuples():
    al = ALIAS.loc[r.station] if r.station in ALIAS.index else None
    prov = al.province if al is not None and al.province else r.province_doc
    pc = pkey[norm(prov)]
    key = norm(al["name"] if al is not None else r.station)
    communes = a3[a3.adm2_pcode == pc]
    if al is not None and al.kind == "place":  # a village or research station: the gazetteer feature of that name
        hit = G[G.adm3_pcode.isin(communes.adm3_pcode) & (G.key == key)]
        assert len(hit) == 1, (r.station, len(hit))
        h = hit.iloc[0]
        com = communes[communes.adm3_pcode == h.adm3_pcode].iloc[0]
        loc.append((pc, com.adm3_name, com.adm3_pcode, h.lat, h.lon, "place"))
        continue
    com = communes[communes.adm3_name.map(norm) == key]  # a gauge named after its commune: the commune seat
    assert len(com) == 1, (r.station, prov, len(com))
    com = com.iloc[0]
    seat = caps.loc[com.adm3_pcode]
    loc.append((pc, com.adm3_name, com.adm3_pcode, float(seat.y_coord), float(seat.x_coord), "commune_seat"))
L = pd.DataFrame(loc, columns=["adm2_pcode", "adm3_name", "adm3_pcode", "lat", "lon", "coord_source"])
out = pd.concat([out, L], axis=1).merge(P.drop(columns="hnrp_name_2026"), on="adm2_pcode", how="left")
out["province_differs"] = [pkey[norm(a)] != pc for a, pc in zip(out.province_doc, out.adm2_pcode)]
out["lat"], out["lon"] = out.lat.round(4), out.lon.round(4)
for c in ("cum_2026", "cum_2025", "normal_1991_2020", "pct_2025", "pct_normal", "dry_spell_days"):
    out[c] = out[c].astype("Int64")
out = out[["adm1_pcode", "adm1_name", "adm2_pcode", "adm2_name", "station", "adm3_pcode", "adm3_name", "lat", "lon",
           "coord_source", "cum_2026", "cum_2025", "normal_1991_2020", "pct_2025", "ratio_2025", "class_2025",
           "pct_normal", "ratio_normal", "class_normal", "onset", "onset_flag", "dry_spell_days", "dry_spell_flag",
           "end", "end_compared", "end_flag", "region_doc", "province_doc", "province_differs"]]
# every gauge must fall inside the province it is attributed to
pts = gpd.GeoDataFrame(out[["adm2_pcode"]], geometry=gpd.points_from_xy(out.lon, out.lat), crs=4326)
inside = pts.sjoin(a2[["adm2_pcode", "geometry"]], how="left", lsuffix="st", rsuffix="geo")
assert (inside.adm2_pcode_st == inside.adm2_pcode_geo).all(), "a gauge falls outside its province"
assert out[["lat", "lon", "adm2_name"]].notna().all().all()
out.to_csv(WORK / "stations_2026.csv", index=False)
print(f"{len(out)} gauges in {out.adm2_pcode.nunique()} provinces -> {WORK / 'stations_2026.csv'}")
print(out.coord_source.value_counts().to_string())
print("listed under another province in the document:", int(out.province_differs.sum()))
