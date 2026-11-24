// Scan ASAP warning rules over the 17 provinces of the old Boucle du Mouhoun, Nord, Centre-Nord and
// Sahel regions, reusing the explorer's rule logic (pages/asap-explorer/explorer.js) unchanged.
// Writes per-setting province counts by season for scripts/obs_review/analysis.py.
// Usage: node scripts/obs_review/asap_scan.js <out.json>
const fs = require("fs");
const path = require("path");
const X = require(path.join(__dirname, "../../pages/asap-explorer/explorer.js"));
const data = JSON.parse(fs.readFileSync(path.join(__dirname, "../../pages/asap-explorer/data.json"), "utf8"));

const OLD_REGIONS = ["Boucle du Mouhoun", "Nord", "Centre-Nord", "Sahel"];

function subset(names) {
  return Object.assign({}, data, { provinces: data.provinces.filter((p) => names(p)) });
}

// Reproduction check: the 2026 framework rule on its four provinces must give the known backtest.
const fw = subset((p) => ["Loroum", "Oudalan", "Séno", "Yagha"].includes(p.name));
const base = { codes: [6, 7, 8, 9], exceptional: true, cover: "or", d0: 21, d1: 26, minDek: 1 };
const fwYears = X.summarise(X.evaluate(fw, X.decode(fw), base), 2).years;
const want = [2002, 2004, 2006, 2009, 2011];
if (JSON.stringify(fwYears) !== JSON.stringify(want)) {
  console.error("framework backtest not reproduced:", fwYears);
  process.exit(1);
}
console.log("framework backtest reproduced:", fwYears.join(", "));

const aoi = subset((p) => OLD_REGIONS.includes(p.region));
if (aoi.provinces.length !== 17) throw new Error("expected 17 provinces, got " + aoi.provinces.length);
const dec = X.decode(aoi);

const LEVELS = { ge1: [2, 3, 4, 5, 6, 7, 8, 9], ge2: [5, 6, 7, 8, 9], ge3: [6, 7, 8, 9], eq4: [9] };
const WINDOWS = [[21, 26], [19, 27], [22, 28]];
const COVERS = ["or", "and", "crop", "range"];
const out = { provinces: aoi.provinces, years: aoi.meta.years, settings: [] };
for (const [lv, codes] of Object.entries(LEVELS)) {
  for (const [d0, d1] of WINDOWS) {
    for (const cover of COVERS) {
      const st = { codes, exceptional: true, cover, d0, d1, minDek: 1 };
      const rows = X.evaluate(aoi, dec, st);
      out.settings.push({
        level: lv, d0, d1, cover,
        rows: rows.map((r) => ({ year: r.year, valid: r.valid, count: r.count, metAt: r.metAt })),
      });
    }
  }
}
fs.writeFileSync(process.argv[2], JSON.stringify(out));
console.log("wrote", out.settings.length, "settings for", aoi.provinces.length, "provinces");
