/* Temperature explorer: national drought trigger options from growing-season heat, Burkina Faso.
 *
 * Indicator (as on the heat-and-impact page): ASAP temperature over cropland, averaged over the chosen
 * dekads, minus the province's own Theil-Sen trend fitted over 1989-2025 (line through the mean of the
 * fit years). The rule logic is pure and exported for Node (scripts/temperature_explorer/check_rules.js).
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- rule logic
  function decode(data) {
    const out = {};
    data.provinces.forEach(function (p) {
      out[p.id] = Float64Array.from(data.temp[String(p.id)], function (v) { return v / 100; });
    });
    return out;
  }

  // Window mean per province and season, then the anomaly from the province's trend.
  function anomalies(data, dec, st) {
    const years = data.meta.years, dks = data.meta.dekads, nD = dks.length;
    const i0 = dks.indexOf(st.d0), i1 = dks.indexOf(st.d1);
    const fit = years.map(function (y) { return y >= data.meta.fit_years[0] && y <= data.meta.fit_years[1]; });
    const fy = years.filter(function (_, i) { return fit[i]; });
    const meanYear = fy.reduce(function (a, b) { return a + b; }, 0) / fy.length;
    const out = {};
    data.provinces.forEach(function (p) {
      const v = dec[p.id];
      const m = years.map(function (_, yi) {
        let s = 0;
        for (let i = i0; i <= i1; i++) s += v[yi * nD + i];
        return s / (i1 - i0 + 1);
      });
      const fm = m.filter(function (_, i) { return fit[i]; });
      const slopes = [];
      for (let a = 0; a < fy.length; a++) {
        for (let b = a + 1; b < fy.length; b++) slopes.push((fm[b] - fm[a]) / (fy[b] - fy[a]));
      }
      slopes.sort(function (a, b) { return a - b; });
      const h = slopes.length;
      const slope = h % 2 ? slopes[(h - 1) / 2] : (slopes[h / 2 - 1] + slopes[h / 2]) / 2;
      const meanFit = fm.reduce(function (a, b) { return a + b; }, 0) / fm.length;
      out[p.id] = {
        mean: m,
        anom: m.map(function (t, yi) { return t - slope * (years[yi] - meanYear) - meanFit; }),
        slope: slope,
      };
    });
    return out;
  }

  function evaluate(data, dec, st) {
    const A = anomalies(data, dec, st);
    const valid = st.d0 >= data.meta.dekads[0] && st.d1 <= data.meta.dekads[data.meta.dekads.length - 1] && st.d0 <= st.d1;
    return data.meta.years.map(function (year, yi) {
      const hot = [];
      let sum = 0;
      data.provinces.forEach(function (p) {
        const a = A[p.id].anom[yi];
        sum += a;
        if (a >= st.sev - 1e-9) hot.push(p.id);
      });
      return { year: year, valid: valid, count: hot.length, hot: hot, natMean: sum / data.provinces.length };
    });
  }

  function summarise(rows, k) {
    const v = rows.filter(function (r) { return r.valid; });
    const act = v.filter(function (r) { return r.count >= k; });
    return { n: v.length, k: act.length, years: act.map(function (r) { return r.year; }),
             rp: act.length ? (v.length + 1) / act.length : null };
  }

  function suggestK(rows, nProv, target) {
    let best = null;
    for (let k = 1; k <= nProv; k++) {
      const s = summarise(rows, k);
      if (!s.rp) continue;
      const diff = Math.abs(s.rp - target);
      if (best === null || diff < best.diff - 1e-9) best = { k: k, diff: diff };
    }
    return best ? best.k : 1;
  }

  const api = { decode: decode, anomalies: anomalies, evaluate: evaluate, summarise: summarise, suggestK: suggestK };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }

  // ---------------------------------------------------------------- page
  let LANG = "en";
  function t(en, fr) { return LANG === "fr" ? fr : en; }
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  const MONTHS_FR_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
                          "novembre", "décembre"];
  const PART = ["1st", "2nd", "3rd"], PART_FR = ["1re", "2e", "3e"];
  function dekadLabel(dk) { return (LANG === "fr" ? MONTHS_FR : MONTHS)[Math.floor((dk - 1) / 3)] + " " + ((dk - 1) % 3 + 1); }
  function dekadLong(dk) {
    const m = Math.floor((dk - 1) / 3);
    if (LANG !== "fr") return PART[(dk - 1) % 3] + " dekad of " + MONTHS[m];
    const name = MONTHS_FR_LONG[m];
    return PART_FR[(dk - 1) % 3] + " décade " + (/^[aeiouy]/.test(name) || name === "août" ? "d’" : "de ") + name;
  }
  function of_(a, b) { return a + t(" of ", " sur ") + b; }
  function nWord(n, en1, enN, fr1, frN) { return n + " " + (LANG === "fr" ? (n > 1 ? frN : fr1) : (n === 1 ? en1 : enN)); }

  const COL = { act: "#9d372b", base: "#b9c4c5", none: "#eef1f1", ink: "#1f2324", ink2: "#5e6a6b", grid: "#e2e8e8",
                band: "#e9f5f1" };
  // diverging blue-neutral-red for anomalies (degC), clamped at +-1.2
  const DIV = [[-1.2, [33, 102, 172]], [-0.6, [103, 169, 207]], [-0.2, [209, 229, 240]], [0, [242, 242, 242]],
               [0.2, [253, 219, 199]], [0.6, [239, 138, 98]], [1.2, [178, 24, 43]]];
  function divColor(v) {
    v = Math.max(DIV[0][0], Math.min(DIV[DIV.length - 1][0], v));
    for (let i = 1; i < DIV.length; i++) {
      if (v <= DIV[i][0]) {
        const a = DIV[i - 1], b = DIV[i], f = (v - a[0]) / (b[0] - a[0]);
        const c = a[1].map(function (x, j) { return Math.round(x + f * (b[1][j] - x)); });
        return "rgb(" + c.join(",") + ")";
      }
    }
    return "rgb(" + DIV[DIV.length - 1][1].join(",") + ")";
  }
  const DEFAULTS = { sev: 0.3, d0: 19, d1: 27, k: null, imp: "main", yt: 20, nat: "yield", year: null };
  const SEV_MAX = 1.5, SEV_GRID = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2];

  let DATA, DEC, ST, ROWS, ANOM;
  const $ = function (id) { return document.getElementById(id); };
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  function pct(v) {
    if (v === null || v === undefined || isNaN(v)) return "–";
    const r = Math.abs(v).toFixed(0);
    if (+r === 0) return "0%";
    return (v > 0 ? "+" : "−") + r + "%";
  }
  function degC(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return "–";
    const r = Math.abs(v).toFixed(digits === undefined ? 2 : digits);
    if (+r === 0) return (0).toFixed(digits === undefined ? 2 : digits) + " °C";
    return (v > 0 ? "+" : "−") + r + " °C";
  }
  function fmtRp(rp) { return rp ? t("1 in " + rp.toFixed(1) + " years", "tous les " + rp.toFixed(1) + " ans") : t("never", "jamais"); }
  function recLabel(rec) { return (LANG === "fr" && rec.label_fr) || rec.label; }
  function recDate(rec) { return (LANG === "fr" && rec.recorded_fr) || rec.recorded; }
  function lastYear() { return DATA.meta.years[DATA.meta.years.length - 1]; }

  // ---------------- state <-> URL
  function readState() {
    const q = new URLSearchParams(location.search);
    const st = JSON.parse(JSON.stringify(DEFAULTS));
    const dks = DATA.meta.dekads;
    const int = function (name) { const v = Math.round(Number(q.get(name))); return isFinite(v) ? v : 0; };
    const sev = Number(q.get("sev"));
    if (q.has("sev") && isFinite(sev)) st.sev = Math.max(0, Math.min(SEV_MAX, Math.round(sev * 20) / 20));
    const d0 = int("d0"), d1 = int("d1");
    if (dks.indexOf(d0) >= 0) st.d0 = d0;
    if (dks.indexOf(d1) >= 0) st.d1 = d1;
    if (st.d1 < st.d0) { const x = st.d0; st.d0 = st.d1; st.d1 = x; }
    const k = int("k");
    if (k >= 1 && k <= DATA.provinces.length) st.k = k;
    if (q.get("imp") === "alt") st.imp = "alt";
    const yt = int("yt");
    if ([10, 15, 20, 25, 30].indexOf(yt) >= 0) st.yt = yt;
    if (q.get("nat") === "prod") st.nat = "prod";
    const y = int("y");
    st.year = DATA.meta.years.indexOf(y) >= 0 ? y : lastYear();
    return st;
  }
  function writeState() {
    const q = new URLSearchParams();
    q.set("sev", ST.sev.toFixed(2)); q.set("d0", ST.d0); q.set("d1", ST.d1); q.set("k", ST.k);
    q.set("imp", ST.imp); q.set("yt", ST.yt); q.set("nat", ST.nat); q.set("y", ST.year);
    if (LANG === "fr") q.set("lang", "fr");
    history.replaceState(null, "", "?" + q.toString());
  }

  // ---------------- controls
  function buildDekadOptions() {
    const opts = DATA.meta.dekads.map(function (dk) { return '<option value="' + dk + '">' + dk + " · " + dekadLabel(dk) + "</option>"; });
    $("d0").innerHTML = opts.join(""); $("d1").innerHTML = opts.join("");
  }
  function buildYearOptions() {
    $("year").innerHTML = DATA.meta.years.map(function (y) {
      return '<option value="' + y + '">' + y + (y === lastYear() ? "*" : "") + "</option>";
    }).join("");
  }
  function buildControls() {
    buildDekadOptions();
    buildYearOptions();
    $("sev").addEventListener("input", function (e) { ST.sev = +e.target.value; update(); });
    $("sevn").addEventListener("change", function (e) {
      const v = Number(e.target.value);
      ST.sev = isFinite(v) ? Math.max(0, Math.min(SEV_MAX, Math.round(v * 20) / 20)) : ST.sev; update();
    });
    $("d0").addEventListener("change", function (e) { ST.d0 = +e.target.value; if (ST.d1 < ST.d0) ST.d1 = ST.d0; update(); });
    $("d1").addEventListener("change", function (e) { ST.d1 = +e.target.value; if (ST.d0 > ST.d1) ST.d0 = ST.d1; update(); });
    $("k").addEventListener("change", function (e) {
      ST.k = Math.max(1, Math.min(Math.round(+e.target.value) || 1, DATA.provinces.length)); update(true);
    });
    $("kslider").addEventListener("input", function (e) { ST.k = +e.target.value; update(true); });
    $("suggest").addEventListener("click", function () { ST.k = suggestK(ROWS, DATA.provinces.length, 4); update(true); });
    $("imp").addEventListener("change", function (e) { ST.imp = e.target.value; update(true); });
    $("yt").addEventListener("change", function (e) { ST.yt = +e.target.value; update(true); });
    document.querySelectorAll('input[name="nat"]').forEach(function (el) {
      el.addEventListener("change", function (e) { ST.nat = e.target.value; update(true); });
    });
    $("year").addEventListener("change", function (e) { ST.year = +e.target.value; update(true); });
    $("yprev").addEventListener("click", function () { stepYear(-1); });
    $("ynext").addEventListener("click", function () { stepYear(1); });
    $("csv").addEventListener("click", downloadCsv);
    $("rpgrid").addEventListener("click", function (e) {
      const c = e.target.closest("[data-sev]");
      if (c) { ST.sev = +c.dataset.sev; ST.k = +c.dataset.k; update(); }
    });
    $("chart-counts").addEventListener("click", function (e) {
      const c = e.target.closest("[data-year]");
      if (c) { ST.year = +c.dataset.year; update(true); $("map-section").scrollIntoView({ behavior: "smooth", block: "start" }); }
    });
    $("chart-grid").addEventListener("click", function (e) {
      const c = e.target.closest("[data-year]");
      if (c) { ST.year = +c.dataset.year; update(true); $("map-section").scrollIntoView({ behavior: "smooth", block: "start" }); }
    });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (en) { $("panel").classList.toggle("stuck", !en[0].isIntersecting); })
        .observe($("panel-top"));
    }
  }
  function stepYear(d) {
    const ys = DATA.meta.years, i = ys.indexOf(ST.year) + d;
    if (i >= 0 && i < ys.length) { ST.year = ys[i]; update(true); }
  }
  function syncControls() {
    $("sev").value = ST.sev; $("sevn").value = ST.sev.toFixed(2);
    $("d0").value = ST.d0; $("d1").value = ST.d1;
    $("k").value = ST.k; $("kslider").value = ST.k;
    $("kunit").textContent = ST.k > 1 ? "provinces" : "province";
    $("imp").value = ST.imp; $("yt").value = ST.yt; $("year").value = ST.year;
    document.querySelectorAll('input[name="nat"]').forEach(function (el) { el.checked = el.value === ST.nat; });
    document.querySelectorAll(".ytlabel").forEach(function (el) { el.textContent = ST.yt; });
    document.querySelectorAll(".sevlabel").forEach(function (el) { el.textContent = degC(ST.sev, 2); });
    $("klabel").textContent = nWord(ST.k, "province", "provinces", "province", "provinces");
    document.querySelectorAll(".known-by").forEach(function (el) { el.textContent = dekadLong(ST.d1); });
  }

  // ---------------- derived values
  function impactSeasons() { return ST.imp === "alt" ? DATA.meta.impact_seasons_alt : DATA.meta.impact_seasons_main; }
  function impactRecordYears() { return DATA.meta.impact_record_years[ST.imp]; }
  function inImpactRecord(y) { const r = impactRecordYears(); return y >= r[0] && y <= r[1]; }
  function nationalYield(y) {
    const i = DATA.yield.national_years.indexOf(y);
    if (i < 0) return null;
    const n = DATA.yield.national;
    return { kg: n.kg_ha[i], anom: n.anom[i], prod: n.prod_kt[i], prodAnom: n.prod_anom[i] };
  }
  function provYield(pid, y) {
    const i = DATA.yield.years.indexOf(y);
    if (i < 0) return null;
    const p = DATA.yield.province[pid];
    return p.anom[i] === null ? { missing: true } : { kg: p.kg_ha[i], anom: p.anom[i] };
  }
  function poorYield(y) {
    const i = DATA.yield.years.indexOf(y);
    if (i < 0) return null;
    let poor = 0, withData = 0;
    DATA.provinces.forEach(function (p) {
      const a = DATA.yield.province[p.id].anom[i];
      if (a === null) return;
      withData++;
      if (a <= -ST.yt) poor++;
    });
    return { poor: poor, withData: withData };
  }
  function impactRecords(y) {
    const key = ST.imp === "alt" ? "season_alt" : "season_main";
    return DATA.impacts.filter(function (r) { return r[key] === y; });
  }
  function impactStatus(y) {
    if (y < impactRecordYears()[0]) return "none";
    if (!inImpactRecord(y)) return "unknown";
    return impactSeasons().indexOf(y) >= 0 ? "yes" : "no";
  }

  // ---------------- rendering helpers
  function svgOpen(w, h, label) {
    return '<svg viewBox="0 0 ' + w + " " + h + '" width="' + w + '" height="' + h + '" role="img" aria-label="' + esc(label) + '">';
  }
  function chartWidth(el) { return Math.max(560, Math.min(el.clientWidth || 900, 1040)); }
  function yearX(w, padL, padR) {
    const ys = DATA.meta.years, step = (w - padL - padR) / ys.length;
    return { step: step, x: function (y) { return padL + (ys.indexOf(y) + 0.5) * step; } };
  }
  // label every fifth season plus the first and last, dropping a label that would collide with its neighbour
  function yearTick(y) {
    const first = DATA.meta.years[0], last = lastYear();
    if (y === last) return true;
    if (y === first) return (5 - (first % 5)) % 5 >= 3;
    return y % 5 === 0 && last - y >= 3;
  }

  // ---------------- summary
  function renderSummary(sum) {
    const imp = impactSeasons();
    const act = new Set(sum.years);
    const scored = ROWS.filter(function (r) { return r.valid && inImpactRecord(r.year); });
    const hits = imp.filter(function (y) { return act.has(y); });
    const misses = imp.filter(function (y) { return !act.has(y) && scored.some(function (r) { return r.year === y; }); });
    const fa = scored.filter(function (r) { return act.has(r.year) && imp.indexOf(r.year) < 0; }).map(function (r) { return r.year; });
    const nImp = hits.length + misses.length;
    const yA = [], yN = [];
    ROWS.forEach(function (r) {
      const ny = r.valid ? nationalYield(r.year) : null;
      if (!ny) return;
      (act.has(r.year) ? yA : yN).push(ST.nat === "prod" ? ny.prodAnom : ny.anom);
    });
    const mean = function (a) { return a.length ? a.reduce(function (s, v) { return s + v; }, 0) / a.length : null; };
    let metPoor = 0, met = 0, notPoor = 0, notMet = 0;
    ROWS.forEach(function (r, yi) {
      if (!r.valid) return;
      const hot = new Set(r.hot);
      DATA.provinces.forEach(function (p) {
        const py = provYield(p.id, r.year);
        if (!py || py.missing) return;
        const poor = py.anom <= -ST.yt;
        if (hot.has(p.id)) { met++; if (poor) metPoor++; } else { notMet++; if (poor) notPoor++; }
      });
    });
    const tiles = [
      { v: of_(sum.k, sum.n), l: t("seasons reach the threshold", "saisons atteignent le seuil") },
      { v: fmtRp(sum.rp), l: t("return period", "période de retour") },
      { v: of_(hits.length, nImp), l: t("impact seasons reached", "saisons avec impact où le seuil est atteint") },
      { v: String(fa.length), l: t("seasons reached without a recorded impact", "saisons où le seuil est atteint sans impact enregistré") },
    ];
    $("tiles").innerHTML = tiles.map(function (x) {
      return '<div class="tile"><div class="tv">' + esc(x.v) + '</div><div class="tl">' + esc(x.l) + "</div></div>";
    }).join("");
    $("live").innerHTML = "<b>" + sum.k + "</b>" + t(" of ", " sur ") + sum.n + " · <b>" +
      (sum.rp ? t("1 in " + sum.rp.toFixed(1) + " yrs", "tous les " + sum.rp.toFixed(1) + " ans") : t("never", "jamais")) +
      "</b> · impact <b>" + hits.length + "</b>" + t(" of ", " sur ") + nImp;
    $("live").setAttribute("data-tip", t(
      sum.k + " of " + sum.n + " seasons reach the threshold; return period " + fmtRp(sum.rp) + "; " + hits.length + " of " + nImp +
        " impact seasons reached",
      nWord(sum.k, "", "", "saison", "saisons") + " sur " + sum.n + (sum.k > 1 ? " atteignent" : " atteint") +
        " le seuil ; période de retour : " + fmtRp(sum.rp) + " ; seuil atteint pour " +
        nWord(hits.length, "", "", "saison", "saisons") + " avec impact sur " + nImp));

    const list = function (a) { return a.length ? a.join(", ") : t("none", "aucune"); };
    const provNote = act.has(lastYear()) ? " (" + lastYear() + t(" provisional", " provisoire") + ")" : "";
    const ny0 = DATA.yield.national_years[0], ny1 = DATA.yield.national_years[DATA.yield.national_years.length - 1];
    const ir = impactRecordYears().join("–");
    const mA = mean(yA), mN = mean(yN);
    let s;
    if (LANG === "fr") {
      s = "<p>Saisons qui atteignent le seuil : <strong>" + list(sum.years) + "</strong>" + provNote + ". Période de retour calculée sur " +
          sum.n + " saisons (" + DATA.meta.years[0] + "–" + lastYear() + ").</p>";
      s += "<p>Saisons avec impact (" + (ST.imp === "alt" ? "libellés du cadre" : "datées par saison de culture") +
           ") où le seuil est atteint : " + list(hits) + " ; où il n’est pas atteint : " + list(misses) +
           ". Saisons où le seuil est atteint sans impact de sécheresse enregistré (" + ir + ") : " + list(fa) +
           ". Avant " + impactRecordYears()[0] + ", les impacts enregistrés utilisés ici ne couvrent pas les saisons.</p>";
      s += "<p>" + (ST.nat === "prod" ? "Production" : "Rendement") + " national de mil et de sorgho, " + ny0 + "–" + ny1 + " : " +
           pct(mA) + " par rapport à la tendance en moyenne pour les saisons qui atteignent le seuil (" + yA.length + "), " + pct(mN) +
           " pour les autres (" + yN.length + ").";
      if (met && notMet) {
        s += " Par province (" + DATA.yield.years[0] + "–" + DATA.yield.years[DATA.yield.years.length - 1] +
             ") : quand une province atteignait le seuil de chaleur, son rendement était au moins " + ST.yt +
             "% sous la tendance dans " + Math.round(100 * metPoor / met) + "% des cas (" + metPoor + " sur " + met +
             "), contre " + Math.round(100 * notPoor / notMet) + "% sinon.";
      }
    } else {
      s = "<p>Seasons that reach the threshold: <strong>" + list(sum.years) + "</strong>" + provNote + ". Return period from " +
          sum.n + " seasons (" + DATA.meta.years[0] + "–" + lastYear() + ").</p>";
      s += "<p>Impact seasons (" + (ST.imp === "alt" ? "framework labelling" : "dated to the growing season") + "): reached " +
           list(hits) + "; not reached " + list(misses) + ". Seasons reached with no recorded drought impact (" + ir + "): " +
           list(fa) + ". The impact records used here do not cover seasons before " + impactRecordYears()[0] + ".</p>";
      s += "<p>National millet and sorghum " + (ST.nat === "prod" ? "production" : "yield") + ", " + ny0 + "–" + ny1 + ": " +
           pct(mA) + " from trend on average in seasons that reach the threshold (" + yA.length + "), " + pct(mN) +
           " in the others (" + yN.length + ").";
      if (met && notMet) {
        s += " By province (" + DATA.yield.years[0] + "–" + DATA.yield.years[DATA.yield.years.length - 1] +
             "): when a province reached the heat threshold, its yield was at least " + ST.yt + "% below trend in " +
             Math.round(100 * metPoor / met) + "% of cases (" + metPoor + " of " + met + "), against " +
             Math.round(100 * notPoor / notMet) + "% otherwise.";
      }
    }
    $("summary").innerHTML = s + "</p>";
  }

  // ---------------- map
  function renderMap() {
    const m = DATA.map, yi = DATA.meta.years.indexOf(ST.year);
    const w = m.width, h = m.height;
    let s = '<svg viewBox="-4 -4 ' + (w + 8) + " " + (h + 8) + '" role="img" aria-label="' +
            esc(t("Temperature anomaly by province, ", "Anomalie de température par province, ") + ST.year) + '">';
    let outlines = "";
    DATA.provinces.forEach(function (p) {
      const a = ANOM[p.id].anom[yi], tm = ANOM[p.id].mean[yi], hot = a >= ST.sev - 1e-9;
      const tip = p.name + " (" + p.region + "), " + ST.year + (ST.year === lastYear() ? t(" (provisional)", " (provisoire)") : "") +
        t("\nMean temperature over the window: ", "\nTempérature moyenne sur la plage : ") + tm.toFixed(1) + " °C" +
        t("\nAnomaly from the province trend: ", "\nAnomalie par rapport à la tendance de la province : ") + degC(a) +
        (hot ? t("\nAt or above the severity threshold", "\nAtteint le seuil de sévérité") : "") +
        t("\nProvince trend: ", "\nTendance de la province : ") + degC(ANOM[p.id].slope * 10) + t(" per decade", " par décennie");
      s += '<path d="' + m.provinces[String(p.id)] + '" fill="' + divColor(a) + '" stroke="#fff" stroke-width="0.8" data-tip="' + esc(tip) + '"/>';
      if (hot) outlines += '<path d="' + m.provinces[String(p.id)] + '" fill="none" stroke="' + COL.ink + '" stroke-width="2" pointer-events="none"/>';
    });
    m.regions.forEach(function (d) { s += '<path d="' + d + '" fill="none" stroke="#7e8e8f" stroke-width="0.9" pointer-events="none"/>'; });
    s += outlines + "</svg>";
    $("map").innerHTML = s;

    // legend
    const lw = 260, lh = 10;
    let lg = '<svg viewBox="0 0 ' + (lw + 20) + ' 34" width="' + (lw + 20) + '" height="34" aria-hidden="true"><defs><linearGradient id="dg">';
    DIV.forEach(function (d) { lg += '<stop offset="' + ((d[0] + 1.2) / 2.4 * 100).toFixed(1) + '%" stop-color="rgb(' + d[1].join(",") + ')"/>'; });
    lg += '</linearGradient></defs><rect x="10" y="2" width="' + lw + '" height="' + lh + '" fill="url(#dg)" rx="2"/>';
    [-1.2, -0.6, 0, 0.6, 1.2].forEach(function (v) {
      const x = 10 + (v + 1.2) / 2.4 * lw;
      lg += '<line x1="' + x + '" x2="' + x + '" y1="' + (2 + lh) + '" y2="' + (5 + lh) + '" stroke="#5e6a6b"/>';
      lg += '<text x="' + x + '" y="' + (16 + lh) + '" text-anchor="middle" class="ax">' + (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "</text>";
    });
    $("map-legend").innerHTML = lg + "</svg>";

    // side panel for the selected year
    const r = ROWS[yi], ny = nationalYield(ST.year), act = r.valid && r.count >= ST.k, st = impactStatus(ST.year);
    const recs = impactRecords(ST.year);
    let info = '<div class="yr">' + ST.year + (ST.year === lastYear() ? '<span class="muted">*</span>' : "") + "</div>";
    info += '<div class="kv"><span>' + t("National mean anomaly", "Anomalie moyenne nationale") + "</span><b>" + degC(r.natMean) + "</b></div>";
    info += '<div class="kv"><span>' + t("Provinces at or above ", "Provinces à ") + degC(ST.sev, 2) + t("", " ou plus") + "</span><b>" + r.count + "</b></div>";
    info += '<div class="kv"><span>' + t("Threshold", "Seuil") + " (" + nWord(ST.k, "province", "provinces", "province", "provinces") + ")</span><b>" +
            (act ? '<span class="tag on">' + t("reached", "atteint") + "</span>" : '<span class="tag off">' + t("not reached", "non atteint") + "</span>") + "</b></div>";
    info += '<div class="kv"><span>' + t("National yield vs trend", "Rendement national, écart à la tendance") + "</span><b>" + (ny ? pct(ny.anom) : "–") + "</b></div>";
    info += '<div class="kv"><span>' + t("National production vs trend", "Production nationale, écart à la tendance") + "</span><b>" + (ny ? pct(ny.prodAnom) : "–") + "</b></div>";
    info += '<div class="kv"><span>' + t("Impact season", "Saison avec impact") + "</span><b>" + statusLabel(st) + "</b></div>";
    if (recs.length) info += '<ul class="recs-list">' + recs.map(function (x) { return "<li>" + esc(recLabel(x)) + " <span class=\"muted\">(" + esc(recDate(x)) + ")</span></li>"; }).join("") + "</ul>";
    $("map-info").innerHTML = info;
    $("year").value = ST.year;
    $("yprev").disabled = ST.year === DATA.meta.years[0];
    $("ynext").disabled = ST.year === lastYear();
  }
  function statusLabel(st) {
    if (st === "yes") return '<span class="tag imp">' + t("Yes", "Oui") + "</span>";
    if (st === "no") return t("No", "Non");
    if (st === "none") return '<span class="muted">' + t("no impact record", "pas de données d’impact") + "</span>";
    return '<span class="muted">' + t("not yet known", "pas encore connu") + "</span>";
  }

  // ---------------- chart: provinces per season
  function renderCounts(sum) {
    const el = $("chart-counts"), w = chartWidth(el), h = 300, padL = 44, padR = 14, padT = 18, padB = 52;
    const X = yearX(w, padL, padR), maxY = DATA.provinces.length;
    const y = function (v) { return padT + (h - padT - padB) * (1 - v / maxY); };
    const imp = new Set(impactSeasons()), act = new Set(sum.years);
    let s = svgOpen(w, h, t("Number of provinces at or above the severity threshold in each season",
                            "Nombre de provinces atteignant le seuil de sévérité par saison"));
    [0, 10, 20, 30, 40].forEach(function (v) {
      s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + COL.grid + '"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end" class="ax">' + v + "</text>";
    });
    const bw = Math.min(18, X.step * 0.7);
    ROWS.forEach(function (r) {
      const cx = X.x(r.year), on = act.has(r.year);
      if (r.year === ST.year) {
        s += '<rect x="' + (cx - X.step / 2) + '" y="' + padT + '" width="' + X.step + '" height="' + (h - padT - padB) + '" fill="' + COL.band + '"/>';
      }
      if (r.count > 0) {
        const top = y(r.count);
        s += '<rect x="' + (cx - bw / 2) + '" y="' + top + '" width="' + bw + '" height="' + (y(0) - top) + '" rx="2" fill="' +
             (on ? COL.act : COL.base) + '"' + (r.year === lastYear() ? ' fill-opacity="0.6"' : "") + "/>";
        if (on) s += '<text x="' + cx + '" y="' + (top - 4) + '" text-anchor="middle" class="lab">' + r.count + "</text>";
      }
      const ny = nationalYield(r.year);
      const tip = r.year + (r.year === lastYear() ? t(" (provisional)", " (provisoire)") : "") + "\n" +
        nWord(r.count, "province", "provinces", "province", "provinces") + t(" at or above ", " à ") + degC(ST.sev, 2) + t("", " ou plus") +
        t("\nNational mean anomaly ", "\nAnomalie moyenne nationale ") + degC(r.natMean) +
        (ny ? t("\nNational millet and sorghum yield ", "\nRendement national mil et sorgho ") + pct(ny.anom) +
              t(" from trend", " par rapport à la tendance") : "") +
        impactRecords(r.year).map(function (rec) { return "\n" + recLabel(rec); }).join("") +
        t("\nClick to show this season on the map", "\nCliquez pour afficher cette saison sur la carte");
      s += '<rect class="hit" data-year="' + r.year + '" x="' + (cx - X.step / 2) + '" y="' + padT + '" width="' + X.step + '" height="' +
           (h - padT - 8) + '" fill="transparent" style="cursor:pointer" data-tip="' + esc(tip) + '"/>';
      if (yearTick(r.year)) s += '<text x="' + cx + '" y="' + (h - padB + 16) + '" text-anchor="middle" class="ax">' + r.year + (r.year === lastYear() ? "*" : "") + "</text>";
      else s += '<line x1="' + cx + '" x2="' + cx + '" y1="' + (h - padB + 2) + '" y2="' + (h - padB + 6) + '" stroke="' + COL.ink2 + '"/>';
      const stt = impactStatus(r.year);
      if (stt === "yes") {
        const my = h - padB + 30;
        s += '<path d="M' + cx + " " + (my - 6) + " L" + (cx + 6) + " " + my + " L" + cx + " " + (my + 6) + " L" + (cx - 6) + " " + my + ' Z" fill="' + COL.ink + '"/>';
      }
    });
    // shade the seasons outside the impact record
    const r0 = impactRecordYears()[0];
    if (DATA.meta.years[0] < r0) {
      const x1 = X.x(r0) - X.step / 2;
      s += '<rect x="' + padL + '" y="' + (h - padB + 22) + '" width="' + (x1 - padL) + '" height="16" fill="' + COL.none + '"/>';
      s += '<text x="' + ((padL + x1) / 2) + '" y="' + (h - padB + 34) + '" text-anchor="middle" class="ax na">' +
           t("no impact record", "pas de données d’impact") + "</text>";
    }
    s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(0) + '" y2="' + y(0) + '" stroke="' + COL.ink2 + '"/>';
    const ty = y(ST.k);
    s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + ty + '" y2="' + ty + '" stroke="' + COL.ink + '" stroke-width="1.5" stroke-dasharray="5 4"/>';
    s += '<text x="' + (padL - 6) + '" y="' + (h - padB + 34) + '" text-anchor="end" class="ax">impact</text>';
    el.innerHTML = s + "</svg>";
  }

  // ---------------- chart: return period for every severity x count threshold
  function renderRpGrid() {
    const el = $("rpgrid"), w = chartWidth(el), padL = 64, padR = 14, padT = 8, padB = 34, cellH = 15;
    const nP = DATA.provinces.length, cw = (w - padL - padR) / nP, h = padT + SEV_GRID.length * cellH + padB;
    const nYears = ROWS.filter(function (r) { return r.valid; }).length;
    let s = svgOpen(w, h, t("Return period for each severity threshold and number of provinces",
                            "Période de retour pour chaque seuil de sévérité et nombre de provinces"));
    SEV_GRID.forEach(function (sev, ri) {
      const cy = padT + ri * cellH;
      const counts = ROWS.map(function (r, yi) {
        let c = 0;
        DATA.provinces.forEach(function (p) { if (ANOM[p.id].anom[yi] >= sev - 1e-9) c++; });
        return { year: r.year, c: c };
      });
      s += '<text x="' + (padL - 6) + '" y="' + (cy + cellH - 4) + '" text-anchor="end" class="ax">' + degC(sev, 1).replace(" °C", "") + "</text>";
      for (let k = 1; k <= nP; k++) {
        const yrs = counts.filter(function (x) { return x.c >= k; }).map(function (x) { return x.year; });
        const rp = yrs.length ? (nYears + 1) / yrs.length : null;
        const fill = !rp ? "#fff" : rp < 2 ? "#d8dede" : rp < 3 ? "#bfe0d6" : rp <= 5 ? "#269777" : rp <= 10 ? "#7cc2ad" : "#d4eae4";
        const x = padL + (k - 1) * cw;
        const cur = Math.abs(sev - ST.sev) < 1e-9 && k === ST.k;
        s += '<rect x="' + (x + 0.5) + '" y="' + (cy + 0.5) + '" width="' + (cw - 1) + '" height="' + (cellH - 1) + '" fill="' + fill + '"' +
             (cur ? ' stroke="' + COL.ink + '" stroke-width="2"' : !rp ? ' stroke="' + COL.grid + '"' : "") + "/>";
        const tip = t("Severity ", "Sévérité ") + degC(sev, 1) + t(", threshold ", ", seuil de ") +
                    nWord(k, "province", "provinces", "province", "provinces") + "\n" + yrs.length + t(" of ", " sur ") + nYears +
                    t(" seasons, ", " saisons, ") + fmtRp(rp) + (yrs.length && yrs.length <= 12 ? "\n" + yrs.join(", ") : "") +
                    t("\nClick to use these settings", "\nCliquez pour utiliser ces paramètres");
        s += '<rect class="hit" data-sev="' + sev + '" data-k="' + k + '" x="' + x + '" y="' + cy + '" width="' + cw + '" height="' + cellH +
             '" fill="transparent" style="cursor:pointer" data-tip="' + esc(tip) + '"/>';
      }
    });
    const by = padT + SEV_GRID.length * cellH;
    for (let k = 1; k <= nP; k++) {
      if (k === 1 || k % 5 === 0) s += '<text x="' + (padL + (k - 0.5) * cw) + '" y="' + (by + 13) + '" text-anchor="middle" class="ax">' + k + "</text>";
    }
    s += '<text x="' + ((w + padL) / 2) + '" y="' + (h - 4) + '" text-anchor="middle" class="ax">' +
         t("number of provinces required", "nombre de provinces requis") + "</text>";
    s += '<text x="12" y="' + (padT + SEV_GRID.length * cellH / 2) + '" text-anchor="middle" class="ax" transform="rotate(-90 12 ' +
         (padT + SEV_GRID.length * cellH / 2) + ')">' + t("severity, °C", "sévérité, °C") + "</text>";
    el.innerHTML = s + "</svg>";
  }

  // ---------------- chart: national yield or production
  function renderYield(sum) {
    const el = $("chart-yield"), w = chartWidth(el), h = 230, padL = 44, padR = 14, padT = 14, padB = 30;
    const X = yearX(w, padL, padR), lim = 35;
    const y = function (v) { return padT + (h - padT - padB) * (lim - Math.max(-lim, Math.min(lim, v))) / (2 * lim); };
    const act = new Set(sum.years), prodMode = ST.nat === "prod";
    let s = svgOpen(w, h, t("National millet and sorghum " + (prodMode ? "production" : "yield") + ", percentage from trend, by season",
                            (prodMode ? "Production" : "Rendement") + " national de mil et de sorgho, écart à la tendance en pourcentage, par saison"));
    [-30, -20, -10, 0, 10, 20, 30].forEach(function (v) {
      s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + (v === 0 ? COL.ink2 : COL.grid) + '"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end" class="ax">' + (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v) + "%</text>";
    });
    const bw = Math.min(18, X.step * 0.7);
    DATA.meta.years.forEach(function (yr) {
      const cx = X.x(yr), ny = nationalYield(yr);
      if (ny) {
        const v = prodMode ? ny.prodAnom : ny.anom, y0 = y(0), y1 = y(v);
        s += '<rect x="' + (cx - bw / 2) + '" y="' + Math.min(y0, y1) + '" width="' + bw + '" height="' + Math.abs(y1 - y0) + '" rx="2" fill="' +
             (act.has(yr) ? COL.act : COL.base) + '"/>';
        const tip = t(yr + "\nYield " + ny.kg + " kg/ha, " + pct(ny.anom) + " from trend\nProduction " + ny.prod + " thousand t, " +
                      pct(ny.prodAnom) + " from trend" + (act.has(yr) ? "\nThreshold reached" : ""),
                      yr + "\nRendement " + ny.kg + " kg/ha, " + pct(ny.anom) + " par rapport à la tendance\nProduction " + ny.prod +
                      " milliers de t, " + pct(ny.prodAnom) + " par rapport à la tendance" + (act.has(yr) ? "\nSeuil atteint" : ""));
        s += '<rect class="hit" x="' + (cx - X.step / 2) + '" y="' + padT + '" width="' + X.step + '" height="' + (h - padT - padB) +
             '" fill="transparent" data-tip="' + esc(tip) + '"/>';
      } else {
        s += '<text x="' + cx + '" y="' + (y(0) - 5) + '" text-anchor="middle" class="ax na">' + t("n/a", "n.d.") + "</text>";
      }
      if (yearTick(yr)) s += '<text x="' + cx + '" y="' + (h - padB + 16) + '" text-anchor="middle" class="ax">' + yr + "</text>";
    });
    el.innerHTML = s + "</svg>";
  }

  // ---------------- chart: provinces x seasons
  function renderGrid() {
    const el = $("chart-grid"), w = chartWidth(el), padL = 210, padR = 14, padT = 22, rowH = 13, gap = 6;
    const ys = DATA.meta.years, step = (w - padL - padR) / ys.length;
    const regions = [];
    DATA.provinces.forEach(function (p) {
      if (!regions.length || regions[regions.length - 1].name !== p.region) regions.push({ name: p.region, provs: [] });
      regions[regions.length - 1].provs.push(p);
    });
    const h = padT + DATA.provinces.length * rowH + (regions.length - 1) * gap + 8;
    let s = svgOpen(w, h, t("Provinces at or above the severity threshold by season, with poor-yield provinces marked",
                            "Provinces atteignant le seuil de sévérité par saison, avec les provinces à rendement faible marquées"));
    ys.forEach(function (yr, i) {
      if (yearTick(yr)) s += '<text x="' + (padL + (i + 0.5) * step) + '" y="' + (padT - 8) + '" text-anchor="middle" class="ax">' + yr + "</text>";
    });
    let top = padT;
    regions.forEach(function (rg) {
      s += '<text x="4" y="' + (top + 9) + '" class="rg">' + esc(rg.name) + "</text>";
      rg.provs.forEach(function (p, j) {
        const ry = top + j * rowH;
        s += '<text x="' + (padL - 6) + '" y="' + (ry + 10) + '" text-anchor="end" class="pv">' + esc(p.name) + "</text>";
        ys.forEach(function (yr, i) {
          const x = padL + i * step, a = ANOM[p.id].anom[i], hot = a >= ST.sev - 1e-9;
          s += '<rect x="' + (x + 1) + '" y="' + (ry + 1) + '" width="' + (step - 2) + '" height="' + (rowH - 2) + '" fill="' +
               (hot ? COL.act : COL.none) + '"' + (yr === ST.year ? ' stroke="' + COL.ink2 + '" stroke-width="0.8"' : "") + "/>";
          const py = provYield(p.id, yr);
          if (py && !py.missing && py.anom <= -ST.yt) {
            s += '<circle cx="' + (x + step / 2) + '" cy="' + (ry + rowH / 2) + '" r="2.4" fill="' + COL.ink + '" stroke="#fff" stroke-width="1"/>';
          }
          const tip = p.name + " (" + p.region + "), " + yr + t("\nAnomaly from trend: ", "\nAnomalie par rapport à la tendance : ") + degC(a) +
            (py ? (py.missing ? t("\nNo complete millet and sorghum statistics", "\nPas de statistiques complètes pour le mil et le sorgho") :
                   t("\nMillet and sorghum yield ", "\nRendement mil et sorgho ") + py.kg + " kg/ha, " + pct(py.anom) +
                   t(" from trend", " par rapport à la tendance")) : "");
          s += '<rect class="hit" data-year="' + yr + '" x="' + x + '" y="' + ry + '" width="' + step + '" height="' + rowH +
               '" fill="transparent" style="cursor:pointer" data-tip="' + esc(tip) + '"/>';
        });
      });
      top += rg.provs.length * rowH + gap;
    });
    el.innerHTML = s + "</svg>";
  }

  // ---------------- table
  function tableRows(sum) {
    const act = new Set(sum.years), fw = new Set(DATA.meta.framework_years);
    return ROWS.slice().reverse().map(function (r) {
      const ny = nationalYield(r.year), pyl = poorYield(r.year), recs = impactRecords(r.year);
      return {
        year: r.year, provisional: r.year === lastYear(), natMean: r.natMean, count: r.count,
        reached: act.has(r.year) ? "Yes" : "No",
        yieldKg: ny ? ny.kg : null, yieldAnom: ny ? ny.anom : null, prodAnom: ny ? ny.prodAnom : null,
        poor: pyl ? pyl.poor : null, withYield: pyl ? pyl.withData : null,
        impact: impactStatus(r.year), recs: recs, framework: fw.has(r.year),
      };
    });
  }
  function renderTable(sum) {
    const YES = t("Yes", "Oui"), NO = t("No", "Non");
    let s = "";
    tableRows(sum).forEach(function (row) {
      s += "<tr" + (row.reached === "Yes" ? ' class="hit-row"' : "") + "><td>" + row.year + (row.provisional ? "*" : "") + "</td>" +
           '<td class="num">' + degC(row.natMean) + "</td>" +
           '<td class="num">' + row.count + "</td>" +
           '<td class="nw">' + (row.reached === "Yes" ? '<span class="tag on">' + YES + "</span>" : '<span class="tag off">' + NO + "</span>") + "</td>" +
           '<td class="num">' + (row.yieldKg === null ? "–" : row.yieldKg) + "</td>" +
           '<td class="num">' + pct(row.yieldAnom) + "</td>" +
           '<td class="num">' + pct(row.prodAnom) + "</td>" +
           '<td class="num">' + (row.poor === null ? "–" : row.poor + (row.withYield < DATA.provinces.length ? t(" of ", " sur ") + row.withYield : "")) + "</td>" +
           '<td class="nw">' + statusLabel(row.impact) + "</td>" +
           '<td class="recs">' + row.recs.map(function (x) {
             return '<span data-tip="' + esc(recLabel(x) + t("\nRecorded ", "\nDate : ") + recDate(x) + " (" + x.source + " " + x.id + ")") + '">' +
                    esc(x.short) + "</span>";
           }).join("<br>") + "</td>" +
           "<td>" + (row.framework ? YES : "") + "</td></tr>";
    });
    $("tbody").innerHTML = s;
    $("th-count").textContent = t("Provinces at or above ", "Provinces à ") + degC(ST.sev, 2) + t("", " ou plus");
    $("th-poor").textContent = t("Provinces with yield ≥" + ST.yt + "% below trend", "Provinces avec un rendement ≥" + ST.yt + "% sous la tendance");
  }
  function downloadCsv() {
    const rows = tableRows(summarise(ROWS, ST.k));
    const head = ["season", "provisional", "national_mean_anomaly_degC", "provinces_at_or_above_severity", "threshold_reached",
                  "national_millet_sorghum_yield_kg_ha", "national_yield_pct_from_trend", "national_production_pct_from_trend",
                  "provinces_yield_" + ST.yt + "pct_below_trend", "provinces_with_yield_data", "impact_season", "impact_records",
                  "framework_target_year"];
    const q = function (v) { v = v === null || v === undefined ? "" : String(v); return /[",;\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const IMP = { yes: "Yes", no: "No", none: "No impact record", unknown: "Not yet known" };
    const lines = [head.join(",")];
    rows.forEach(function (row) {
      lines.push([row.year, row.provisional ? "yes" : "", row.natMean.toFixed(2), row.count, row.reached, row.yieldKg, row.yieldAnom,
                  row.prodAnom, row.poor, row.poor === null ? "" : row.withYield, IMP[row.impact],
                  row.recs.map(function (x) { return x.label + " [" + x.id + ", " + x.recorded + "]"; }).join("; "),
                  row.framework ? "yes" : ""].map(q).join(","));
    });
    const settings = "# settings: temperature over cropland, mean of dekads " + ST.d0 + "-" + ST.d1 + ", anomaly from province Theil-Sen trend " +
                     DATA.meta.fit_years.join("-") + "; severity " + ST.sev.toFixed(2) + " degC; threshold " + ST.k + " provinces; impact dating " +
                     ST.imp + "; national yield trend " + DATA.yield.national_years[0] + "-" +
                     DATA.yield.national_years[DATA.yield.national_years.length - 1] + "; " + location.href;
    const blob = new Blob([settings + "\n" + lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "bfa_temperature_trigger_explorer.csv";
    document.body.appendChild(a); a.click(); a.remove();
  }

  // ---------------- tooltip
  function initTooltip() {
    const tip = $("tip");
    document.addEventListener("mouseover", function (e) {
      const el = e.target.closest && e.target.closest("[data-tip]");
      if (!el) { tip.hidden = true; return; }
      tip.textContent = (LANG === "fr" && el.getAttribute("data-tip-fr")) || el.getAttribute("data-tip");
      tip.hidden = false;
    });
    document.addEventListener("mousemove", function (e) {
      if (tip.hidden) return;
      const pad = 14, r = tip.getBoundingClientRect();
      let x = e.clientX + pad, y = e.clientY + pad;
      if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - pad;
      if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
      tip.style.left = x + "px"; tip.style.top = y + "px";
    });
  }

  // ---------------- main loop
  function update(kOnly) {
    if (!kOnly) {
      ANOM = anomalies(DATA, DEC, ST);
      ROWS = evaluate(DATA, DEC, ST);
    }
    if (ST.k === null) ST.k = suggestK(ROWS, DATA.provinces.length, 4);
    syncControls();
    writeState();
    const sum = summarise(ROWS, ST.k);
    renderSummary(sum);
    renderMap();
    renderCounts(sum);
    renderRpGrid();
    renderYield(sum);
    renderGrid();
    renderTable(sum);
  }

  // ---------------- language
  const TITLES = {
    en: "Burkina Faso drought — temperature explorer for a national trigger",
    fr: "Sécheresse au Burkina Faso — explorateur des températures pour un déclencheur national",
  };
  function staticDynamicText() {
    if (!DATA) return;
    const last = new Date(DATA.meta.asap_last_dekad + "T00:00:00Z");
    const lastDk = last.getUTCMonth() * 3 + Math.min(Math.floor((last.getUTCDate() - 1) / 10), 2) + 1;
    const lastTxt = dekadLong(lastDk) + " " + last.getUTCFullYear();
    const longMonth = LANG === "fr" ? MONTHS_FR_LONG[last.getUTCMonth()] : MONTHS[last.getUTCMonth()];
    document.querySelectorAll(".last-dekad").forEach(function (el) {
      el.textContent = last.getUTCDate() + " " + longMonth + " " + last.getUTCFullYear() + " (" + lastTxt + ")";
    });
    $("vintage").textContent = t("ASAP temperature to " + DATA.meta.asap_last_dekad + " (" + lastTxt + "); built " + DATA.meta.built + ".",
                                 "Températures ASAP jusqu’au " + DATA.meta.asap_last_dekad + " (" + lastTxt + ") ; générée le " + DATA.meta.built + ".");
  }
  function setLang(l) {
    LANG = l === "fr" ? "fr" : "en";
    const html = document.documentElement;
    html.lang = LANG; html.setAttribute("data-lang", LANG);
    try { localStorage.setItem("aa-lang", LANG); } catch (e) { /* private mode */ }
    document.title = TITLES[LANG];
    document.querySelectorAll(".aa-lang button").forEach(function (b) { b.classList.toggle("on", b.dataset.l === LANG); });
    document.querySelectorAll("option[data-fr]").forEach(function (o) {
      if (!o.dataset.en) o.dataset.en = o.textContent;
      o.textContent = LANG === "fr" ? o.dataset.fr : o.dataset.en;
    });
    document.querySelectorAll("[data-aria-fr]").forEach(function (el) {
      if (!el.dataset.ariaEn) el.dataset.ariaEn = el.getAttribute("aria-label") || "";
      el.setAttribute("aria-label", LANG === "fr" ? el.dataset.ariaFr : el.dataset.ariaEn);
    });
    if (DATA) { buildDekadOptions(); staticDynamicText(); update(true); }
  }
  function initLang() {
    const q = new URLSearchParams(location.search).get("lang");
    let stored = null;
    try { stored = localStorage.getItem("aa-lang"); } catch (e) { /* private mode */ }
    document.querySelectorAll(".aa-lang button").forEach(function (b) { b.addEventListener("click", function () { setLang(b.dataset.l); }); });
    setLang(q === "fr" || q === "en" ? q : stored === "fr" ? "fr" : "en");
  }

  function init() {
    initLang();
    fetch("data.json", { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (data) {
      DATA = data;
      DEC = decode(data);
      ST = readState();
      buildControls();
      initTooltip();
      staticDynamicText();
      $("app").hidden = false; $("loading").hidden = true;
      update();
      let timer;
      window.addEventListener("resize", function () { clearTimeout(timer); timer = setTimeout(function () { update(true); }, 150); });
    }).catch(function (err) {
      $("loading").textContent = t("Could not load the data (", "Impossible de charger les données (") + err + ").";
    });
  }
  root.TempExplorer = api;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})(this);
