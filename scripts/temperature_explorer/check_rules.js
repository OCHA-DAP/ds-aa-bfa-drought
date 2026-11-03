// Checks the temperature explorer's logic (pages/temperature-explorer/explorer.js) against values
// computed separately with pandas + scipy.stats.theilslopes from the November 2026 ASAP export.
// Usage: node scripts/temperature_explorer/check_rules.js
// The expected values are tied to that export; update them when ASAP revises the series.
const fs = require("fs");
const path = require("path");
const X = require(path.join(__dirname, "../../pages/temperature-explorer/explorer.js"));
const data = JSON.parse(fs.readFileSync(path.join(__dirname, "../../pages/temperature-explorer/data.json"), "utf8"));

let failed = 0;
function check(name, ok, detail) {
  if (!ok) failed++;
  console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : "\n     " + detail));
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const dec = X.decode(data);
const jas = { sev: 0.3, d0: 19, d1: 27 };

// 1. the heat-and-impact indicator: mean Jul-Sep anomaly of the four framework provinces
const aoi = data.provinces.filter((p) => ["Loroum", "Oudalan", "Séno", "Yagha"].includes(p.name));
check("four framework provinces found", aoi.length === 4, aoi.map((p) => p.name));
const A = X.anomalies(data, dec, jas);
const want = { 2002: 0.69, 2003: -0.48, 2011: 0.47, 2012: -0.6, 2022: -0.14, 2026: 1.24 };
Object.entries(want).forEach(([y, v]) => {
  const yi = data.meta.years.indexOf(+y);
  const got = aoi.reduce((s, p) => s + A[p.id].anom[yi], 0) / 4;
  check("framework provinces Jul-Sep " + y + " = " + v, Math.abs(got - v) <= 0.01, "got " + got.toFixed(3));
});

// 2. national counts of provinces at or above the severity, Jul-Sep
const counts = (st) => Object.fromEntries(X.evaluate(data, dec, st).map((r) => [r.year, r.count]));
const nz = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v > 0));
check("counts, severity 0.3 degC", eq(nz(counts(jas)), {1990: 8, 1997: 42, 2000: 2, 2002: 43, 2004: 3, 2009: 14, 2011: 29, 2014: 5,
  2015: 2, 2017: 5, 2019: 10, 2021: 8, 2023: 40, 2026: 41}), JSON.stringify(nz(counts(jas))));
check("counts, severity 0.5 degC", eq(nz(counts({ ...jas, sev: 0.5 })), {1990: 1, 1997: 14, 2002: 17, 2009: 1, 2011: 9, 2021: 3,
  2023: 8, 2026: 29}), JSON.stringify(nz(counts({ ...jas, sev: 0.5 }))));
check("counts, dekads 22-26, severity 0.5 degC", eq(nz(counts({ sev: 0.5, d0: 22, d1: 26 })), {1990: 18, 1997: 16, 2000: 3, 2002: 3,
  2004: 5, 2005: 1, 2011: 18, 2017: 5, 2021: 5, 2023: 3, 2026: 39}), JSON.stringify(nz(counts({ sev: 0.5, d0: 22, d1: 26 }))));

// 3. validity, return period, suggested threshold
const rows = X.evaluate(data, dec, jas);
check("all 38 seasons valid for Jul-Sep", rows.length === 38 && rows.every((r) => r.valid), rows.length);
check("a window beyond the stored dekads is invalid", X.evaluate(data, dec, { sev: 0.3, d0: 19, d1: 30 }).every((r) => !r.valid), "");
const s8 = X.summarise(rows, 8);
check("severity 0.3, 8 provinces: seasons", eq(s8.years, [1990, 1997, 2002, 2009, 2011, 2019, 2021, 2023, 2026]), s8.years);
check("severity 0.3, 8 provinces: return period (38+1)/9", Math.abs(s8.rp - 39 / 9) < 1e-9, s8.rp);
// 6, 7 and 8 provinces give the same nine seasons; ties go to the smallest threshold
check("suggested threshold for ~4 years", X.suggestK(rows, 45, 4) === 6, X.suggestK(rows, 45, 4));

if (failed) { console.log(failed + " check(s) failed"); process.exit(1); }
console.log("all checks passed");
