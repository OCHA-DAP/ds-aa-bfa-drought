// Checks the explorer's rule logic (pages/asap-explorer/explorer.js) against known results.
// Usage: node scripts/asap_explorer/check_rules.js
// 1. The 2026 framework's Trigger 2 rule on the four framework provinces (level 3 or above,
//    cropland or rangeland, at least 2 provinces, dekads 21-26) must give 2002, 2004, 2006,
//    2009, 2011 (the backtest of the framework, reproduced with the Nov 2026 archive).
// 2. National counts for the default settings must match an independent pandas computation
//    (level 3 or above, cropland or rangeland, dekads 21-26, any dekad).
const fs = require("fs");
const path = require("path");
const X = require(path.join(__dirname, "../../pages/asap-explorer/explorer.js"));
const data = JSON.parse(fs.readFileSync(path.join(__dirname, "../../pages/asap-explorer/data.json"), "utf8"));

let failed = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failed++;
  console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : "\n     got  " + JSON.stringify(got) + "\n     want " + JSON.stringify(want)));
}

const base = { codes: [6, 7, 8, 9], exceptional: true, cover: "or", d0: 21, d1: 26, minDek: 1 };

// 1. framework rule on the four provinces
const aoiNames = ["Loroum", "Oudalan", "Séno", "Yagha"];
const aoi = Object.assign({}, data, { provinces: data.provinces.filter((p) => aoiNames.includes(p.name)) });
check("four framework provinces found", aoi.provinces.map((p) => p.name).sort(), aoiNames.slice().sort());
const aoiRows = X.evaluate(aoi, X.decode(aoi), base);
check("framework rule, 4 provinces, >=2", X.summarise(aoiRows, 2).years, [2002, 2004, 2006, 2009, 2011]);

// 2. national counts, default settings
const dec = X.decode(data);
const rows = X.evaluate(data, dec, base);
const want = {2001: 8, 2002: 36, 2003: 2, 2004: 11, 2005: 1, 2006: 23, 2007: 14, 2008: 10, 2009: 7, 2010: 6,
  2011: 11, 2012: 0, 2013: 2, 2014: 4, 2015: 28, 2016: 1, 2017: 0, 2018: 7, 2019: 4, 2020: 8, 2021: 0,
  2022: 1, 2023: 2, 2024: 20, 2025: 3, 2026: 23};
const got = {};
rows.forEach((r) => { got[r.year] = r.count; });
check("national counts, level>=3, OR, 21-26", got, want);
check("all seasons valid for 21-26", rows.every((r) => r.valid), true);

// AND / crop-only / range-only spot checks against the same pandas table
const and3 = X.evaluate(data, dec, Object.assign({}, base, { cover: "and" }));
check("AND 2002 / 2006 / 2015", [2002, 2006, 2015].map((y) => and3.find((r) => r.year === y).count), [32, 15, 25]);
const crop3 = X.evaluate(data, dec, Object.assign({}, base, { cover: "crop" }));
check("crop 2002 / 2024 / 2026", [2002, 2024, 2026].map((y) => crop3.find((r) => r.year === y).count), [32, 18, 23]);
const range1 = X.evaluate(data, dec, Object.assign({}, base, { cover: "range", codes: [2, 3, 4, 5, 6, 7, 8, 9] }));
check("range level>=1 2017 / 2021", [2017, 2021].map((y) => range1.find((r) => r.year === y).count), [33, 16]);

// coverage: 2001 starts at dekad 15, 2026 ends at dekad 29
const early = X.evaluate(data, dec, Object.assign({}, base, { d0: 10, d1: 26 }));
check("2001 invalid when the range starts before dekad 15", early.find((r) => r.year === 2001).valid, false);
const late = X.evaluate(data, dec, Object.assign({}, base, { d0: 21, d1: 30 }));
check("2026 invalid when the range ends after dekad 29", late.find((r) => r.year === 2026).valid, false);
check("2025 valid to dekad 30", late.find((r) => r.year === 2025).valid, true);

// minimum dekads: count can only fall as the minimum rises; reached-by dekad within range
const md3 = X.evaluate(data, dec, Object.assign({}, base, { minDek: 3 }));
check("min dekads 3 never exceeds min dekads 1", md3.every((r, i) => r.count <= rows[i].count), true);
check("reached-by dekads inside the range", md3.every((r) => r.metAt.every((d) => d >= 23 && d <= 26)), true);

// a non-integer minimum (from a typed value) behaves like the next integer, never as "no province"
const mdHalf = X.evaluate(data, dec, Object.assign({}, base, { minDek: 2.5 }));
check("min dekads 2.5 equals min dekads 3", mdHalf.map((r) => r.count), md3.map((r) => r.count));

// return period
const s12 = X.summarise(rows, 12);
check("threshold 12: seasons", s12.years, [2002, 2006, 2007, 2015, 2024, 2026]);
check("threshold 12: return period (26+1)/6", s12.rp, 27 / 6);
check("suggested threshold for ~4 years", X.suggestK(rows, 45, 4), 12);

if (failed) { console.log(failed + " check(s) failed"); process.exit(1); }
console.log("all checks passed");
