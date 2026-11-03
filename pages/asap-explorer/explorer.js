/* ASAP warning explorer: national drought trigger options for Burkina Faso.
 *
 * The rule logic (decode, evaluate, summarise) is pure and exported for Node so it can be
 * tested without a browser; the rest renders the page from data.json. No dependencies.
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- rule logic
  // Base ASAP warning codes, grouped by warning level. Codes 12-18 are the same warnings
  // "with exceptional conditions" (part of the area also has an exceptionally good biomass
  // anomaly): base code + 10.
  const WARNING_TYPES = [
    { code: 2, level: 1, label: "Water balance (WSI)", fr: "Bilan hydrique (WSI)" },
    { code: 3, level: 1, label: "Rainfall (SPI-3)", fr: "Précipitations (SPI-3)" },
    { code: 4, level: 1, label: "Water balance and rainfall", fr: "Bilan hydrique et précipitations" },
    { code: 5, level: 2, label: "Biomass (zNDVIc)", fr: "Biomasse (zNDVIc)" },
    { code: 6, level: 3, label: "Biomass and water balance", fr: "Biomasse et bilan hydrique" },
    { code: 7, level: 3, label: "Biomass and rainfall", fr: "Biomasse et précipitations" },
    { code: 8, level: 3, label: "Biomass, water balance and rainfall", fr: "Biomasse, bilan hydrique et précipitations" },
    { code: 9, level: 4, label: "End-of-season biomass", fr: "Biomasse en fin de saison" },
  ];
  const LEVEL_NAMES = {
    1: "Level 1: rainfall or water-balance deficit",
    2: "Level 2: poor biomass",
    3: "Level 3: poor biomass with rainfall or water-balance deficit",
    4: "Level 4: poor biomass at the end of the season",
  };
  const LEVEL_NAMES_FR = {
    1: "Niveau 1\u00a0: déficit de précipitations ou de bilan hydrique",
    2: "Niveau 2\u00a0: biomasse faible",
    3: "Niveau 3\u00a0: biomasse faible avec déficit de précipitations ou de bilan hydrique",
    4: "Niveau 4\u00a0: biomasse faible en fin de saison",
  };
  const EXCEPTIONAL_OFFSET = 10;
  const CODE_LEVEL = { 0: 0, 10: 0, 20: 0, 98: -1, 99: -1 };
  WARNING_TYPES.forEach(function (t) {
    CODE_LEVEL[t.code] = t.level;
    if (t.code <= 8) CODE_LEVEL[t.code + EXCEPTIONAL_OFFSET] = t.level;
  });

  function decode(data) {
    const map = {};
    Object.keys(data.meta.code_chars).forEach(function (ch) { map[ch] = data.meta.code_chars[ch]; });
    const nY = data.meta.years.length;
    const out = {};
    data.provinces.forEach(function (p) {
      const w = data.warnings[String(p.id)];
      const crop = new Int16Array(nY * 36), range = new Int16Array(nY * 36);
      for (let i = 0; i < nY * 36; i++) {
        crop[i] = w.c[i] === "." ? -1 : map[w.c[i]];
        range[i] = w.r[i] === "." ? -1 : map[w.r[i]];
      }
      out[p.id] = { crop: crop, range: range };
    });
    return out;
  }

  function selectedCodes(st) {
    const sel = new Uint8Array(100);
    st.codes.forEach(function (c) {
      sel[c] = 1;
      if (st.exceptional && c <= 8) sel[c + EXCEPTIONAL_OFFSET] = 1;
    });
    return sel;
  }

  // One row per season: whether the dekad range has data, which provinces met the condition
  // (with how many dekads), and the first dekad by which `k` provinces had met it.
  function evaluate(data, dec, st) {
    const sel = selectedCodes(st);
    const years = data.meta.years;
    const rows = [];
    years.forEach(function (year, yi) {
      let valid = true;
      const perProv = {};
      const metAt = []; // dekad at which each province first met the condition
      data.provinces.forEach(function (p) {
        const d = dec[p.id];
        let n = 0, first = null;
        for (let dk = st.d0; dk <= st.d1; dk++) {
          const i = yi * 36 + dk - 1;
          const c = d.crop[i], r = d.range[i];
          if (c === -1 || r === -1) { valid = false; continue; }
          let ok;
          if (st.cover === "crop") ok = sel[c] === 1;
          else if (st.cover === "range") ok = sel[r] === 1;
          else if (st.cover === "and") ok = sel[c] === 1 && sel[r] === 1;
          else ok = sel[c] === 1 || sel[r] === 1;
          if (ok) {
            n++;
            if (n >= st.minDek && first === null) first = dk;
          }
        }
        perProv[p.id] = n;
        if (first !== null) metAt.push(first);
      });
      metAt.sort(function (a, b) { return a - b; });
      rows.push({
        year: year,
        valid: valid,
        count: metAt.length,
        dekadsMet: perProv,
        metAt: metAt, // sorted; metAt[k-1] = dekad the k-th province met the condition
      });
    });
    return rows;
  }

  function summarise(rows, k) {
    const valid = rows.filter(function (r) { return r.valid; });
    const act = valid.filter(function (r) { return r.count >= k; });
    return {
      n: valid.length,
      k: act.length,
      years: act.map(function (r) { return r.year; }),
      rp: act.length ? (valid.length + 1) / act.length : null,
    };
  }

  // K whose return period is closest to `target` years (ties -> smallest K).
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

  const api = {
    WARNING_TYPES: WARNING_TYPES, CODE_LEVEL: CODE_LEVEL, EXCEPTIONAL_OFFSET: EXCEPTIONAL_OFFSET,
    decode: decode, evaluate: evaluate, summarise: summarise, suggestK: suggestK,
  };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }

  // ---------------------------------------------------------------- page
  // ---- language: English or French. Static text carries both (.lv-en / .lv-fr, switched by CSS on
  // <html data-lang>); everything built here goes through t(en, fr) and is re-rendered on a switch.
  let LANG = "en";
  function t(en, fr) { return LANG === "fr" ? fr : en; }
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  const MONTHS_FR_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
                          "novembre", "décembre"];
  const PART = ["1st", "2nd", "3rd"], PART_FR = ["1re", "2e", "3e"];
  function monthAbbr(m) { return LANG === "fr" ? MONTHS_FR[m] : MONTHS[m]; }
  function dekadLabel(dk) { return monthAbbr(Math.floor((dk - 1) / 3)) + " " + ((dk - 1) % 3 + 1); }
  function dekadLong(dk) {
    const m = Math.floor((dk - 1) / 3);
    if (LANG !== "fr") return PART[(dk - 1) % 3] + " dekad of " + MONTHS[m];
    const name = MONTHS_FR_LONG[m];
    return PART_FR[(dk - 1) % 3] + " décade " + (/^[aeiouy]/.test(name) || name === "août" ? "d’" : "de ") + name;
  }
  function of_(a, b) { return a + t(" of ", " sur ") + b; }
  // "1 province", "2 provinces"; French also takes the singular after 0
  function nWord(n, en1, enN, fr1, frN) { return n + " " + (LANG === "fr" ? (n > 1 ? frN : fr1) : (n === 1 ? en1 : enN)); }

  const COL = {
    act: "#9d372b", actSoft: "#f2d9d6", base: "#b9c4c5", none: "#eef1f1", ink: "#1f2324",
    ink2: "#5e6a6b", grid: "#e2e8e8", band: "#e9f5f1", brand: "#1e795f",
  };
  const DEFAULTS = { codes: [6, 7, 8, 9], exceptional: true, cover: "or", d0: 21, d1: 26, minDek: 1, k: null,
                     imp: "main", yt: 20, nat: "yield", year: null, mapDk: null };
  // ASAP warning levels on the map: ordinal, light to dark
  const LEVEL_FILL = { "-1": "#ffffff", 0: "#eef1f1", 1: "#f5d77e", 2: "#ee9a45", 3: "#cf4f2e", 4: "#7c2a1f" };
  const PRESETS = [
    { id: "ge1", label: "≥1", tip: "Level 1 or above", tipFr: "Niveau 1 ou plus", codes: [2, 3, 4, 5, 6, 7, 8, 9] },
    { id: "ge2", label: "≥2", tip: "Level 2 or above", tipFr: "Niveau 2 ou plus", codes: [5, 6, 7, 8, 9] },
    { id: "ge3", label: "≥3", tip: "Level 3 or above", tipFr: "Niveau 3 ou plus", codes: [6, 7, 8, 9] },
    { id: "eq4", label: "4", tip: "Level 4 only", tipFr: "Niveau 4 seulement", codes: [9] },
  ];

  let DATA, DEC, ST, ROWS;
  const $ = function (id) { return document.getElementById(id); };
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  function pct(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return "–";
    const r = Math.abs(v).toFixed(digits || 0);
    if (+r === 0) return "0%";
    return (v > 0 ? "+" : "−") + r + "%";
  }
  function fmtRp(rp) { return rp ? t("1 in " + rp.toFixed(1) + " years", "tous les " + rp.toFixed(1) + " ans") : t("never", "jamais"); }
  function recLabel(rec) { return (LANG === "fr" && rec.label_fr) || rec.label; }
  function recDate(rec) { return (LANG === "fr" && rec.recorded_fr) || rec.recorded; }

  // ---------------- state <-> URL
  function readState() {
    const q = new URLSearchParams(location.search);
    const st = JSON.parse(JSON.stringify(DEFAULTS));
    if (q.has("w")) st.codes = q.get("w").split(",").map(Number).filter(function (c) { return CODE_LEVEL[c] > 0 && c <= 9; });
    if (q.has("x")) st.exceptional = q.get("x") !== "0";
    if (["crop", "range", "or", "and"].indexOf(q.get("lc")) >= 0) st.cover = q.get("lc");
    const int = function (name) { const v = Math.round(Number(q.get(name))); return isFinite(v) ? v : 0; };
    const d0 = int("d0"), d1 = int("d1");
    if (d0 >= 1 && d0 <= 36) st.d0 = d0;
    if (d1 >= 1 && d1 <= 36) st.d1 = d1;
    if (st.d1 < st.d0) { const t = st.d0; st.d0 = st.d1; st.d1 = t; }
    const md = int("md");
    if (md >= 1) st.minDek = md;
    const k = int("k");
    if (k >= 1 && k <= DATA.provinces.length) st.k = k;
    if (q.get("imp") === "alt") st.imp = "alt";
    const yt = int("yt");
    if ([10, 15, 20, 25, 30].indexOf(yt) >= 0) st.yt = yt;
    if (q.get("nat") === "prod") st.nat = "prod";
    const y = int("y");
    st.year = DATA.meta.years.indexOf(y) >= 0 ? y : DATA.meta.years[DATA.meta.years.length - 1];
    const mdk = int("mdk");
    st.mapDk = mdk >= st.d0 && mdk <= st.d1 ? mdk : null;
    return st;
  }
  function writeState() {
    const q = new URLSearchParams();
    q.set("w", ST.codes.slice().sort(function (a, b) { return a - b; }).join(","));
    q.set("x", ST.exceptional ? "1" : "0");
    q.set("lc", ST.cover); q.set("d0", ST.d0); q.set("d1", ST.d1); q.set("md", ST.minDek);
    q.set("k", ST.k); q.set("imp", ST.imp); q.set("yt", ST.yt); q.set("nat", ST.nat); q.set("y", ST.year);
    if (ST.mapDk) q.set("mdk", ST.mapDk);
    if (LANG === "fr") q.set("lang", "fr");
    history.replaceState(null, "", "?" + q.toString());
  }

  // ---------------- controls
  function buildControls() {
    const lv = $("levels");
    let html = "";
    [1, 2, 3, 4].forEach(function (L) {
      html += '<fieldset class="lvl"><legend><span class="lv lv-en">' + esc(LEVEL_NAMES[L]) + '</span><span class="lv lv-fr">' +
              esc(LEVEL_NAMES_FR[L]) + "</span></legend>";
      WARNING_TYPES.filter(function (w) { return w.level === L; }).forEach(function (w) {
        html += '<label><input type="checkbox" data-code="' + w.code + '"> <span class="lv lv-en">' + esc(w.label) +
                '</span><span class="lv lv-fr">' + esc(w.fr) + "</span></label>";
      });
      html += "</fieldset>";
    });
    lv.innerHTML = html;
    $("presets").innerHTML = PRESETS.map(function (p) {
      return '<button type="button" class="preset" data-preset="' + p.id + '" data-tip="' + esc(p.tip) + '" data-tip-fr="' +
             esc(p.tipFr) + '">' + esc(p.label) + "</button>";
    }).join("");
    buildDekadOptions();

    lv.addEventListener("change", function (e) {
      const c = +e.target.dataset.code;
      if (!c) return;
      ST.codes = ST.codes.filter(function (x) { return x !== c; });
      if (e.target.checked) ST.codes.push(c);
      update();
    });
    $("presets").addEventListener("click", function (e) {
      const p = PRESETS.find(function (x) { return x.id === e.target.dataset.preset; });
      if (!p) return;
      ST.codes = p.codes.slice();
      update();
    });
    $("exc").addEventListener("change", function (e) { ST.exceptional = e.target.checked; update(); });
    $("cover").addEventListener("change", function (e) { ST.cover = e.target.value; update(); });
    // close the warning-types menu on a click outside it or on Escape
    document.addEventListener("click", function (e) {
      if ($("types").open && !$("types").contains(e.target)) $("types").open = false;
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") $("types").open = false; });
    // shadow under the settings bar once it is stuck to the top of the window
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (en) { $("panel").classList.toggle("stuck", !en[0].isIntersecting); })
        .observe($("panel-top"));
    }
    $("d0").addEventListener("change", function (e) {
      ST.d0 = +e.target.value; if (ST.d1 < ST.d0) ST.d1 = ST.d0; update();
    });
    $("d1").addEventListener("change", function (e) {
      ST.d1 = +e.target.value; if (ST.d0 > ST.d1) ST.d0 = ST.d1; update();
    });
    $("mindek").addEventListener("change", function (e) {
      ST.minDek = Math.round(+e.target.value) || 1; update();
    });
    $("k").addEventListener("change", function (e) {
      ST.k = Math.max(1, Math.min(Math.round(+e.target.value) || 1, DATA.provinces.length)); update(true);
    });
    $("kslider").addEventListener("input", function (e) { ST.k = +e.target.value; update(true); });
    $("suggest").addEventListener("click", function () {
      ST.k = suggestK(ROWS, DATA.provinces.length, 4); update(true);
    });
    $("imp").addEventListener("change", function (e) { ST.imp = e.target.value; update(true); });
    $("yt").addEventListener("change", function (e) { ST.yt = +e.target.value; update(true); });
    document.querySelectorAll('input[name="nat"]').forEach(function (el) {
      el.addEventListener("change", function (e) { ST.nat = e.target.value; update(true); });
    });
    $("csv").addEventListener("click", downloadCsv);
    $("krp").addEventListener("click", function (e) {
      const k = e.target.closest("[data-k]");
      if (k) { ST.k = +k.dataset.k; update(true); }
    });
    // map: season and dekad
    $("year").innerHTML = DATA.meta.years.map(function (y) {
      return '<option value="' + y + '">' + y + (y === DATA.meta.years[DATA.meta.years.length - 1] ? "*" : "") + "</option>";
    }).join("");
    $("year").addEventListener("change", function (e) { ST.year = +e.target.value; update(true); });
    $("yprev").addEventListener("click", function () { stepYear(-1); });
    $("ynext").addEventListener("click", function () { stepYear(1); });
    $("mapdk").addEventListener("change", function (e) { ST.mapDk = e.target.value === "all" ? null : +e.target.value; update(true); });
    ["chart-counts", "chart-grid"].forEach(function (id) {
      $(id).addEventListener("click", function (e) {
        const c = e.target.closest("[data-year]");
        if (c) { ST.year = +c.dataset.year; update(true); $("map-section").scrollIntoView({ behavior: "smooth", block: "start" }); }
      });
    });
  }
  function stepYear(d) {
    const ys = DATA.meta.years, i = ys.indexOf(ST.year) + d;
    if (i >= 0 && i < ys.length) { ST.year = ys[i]; update(true); }
  }
  function buildMapDekadOptions() {
    let o = '<option value="all">' + esc(t("Highest level, dekads " + ST.d0 + "–" + ST.d1, "Niveau le plus élevé, décades " + ST.d0 + "–" + ST.d1)) + "</option>";
    for (let dk = ST.d0; dk <= ST.d1; dk++) o += '<option value="' + dk + '">' + esc(t("Dekad ", "Décade ") + dk + " · " + dekadLabel(dk)) + "</option>";
    $("mapdk").innerHTML = o;
  }

  function buildDekadOptions() {
    const opts = [];
    for (let dk = 1; dk <= 36; dk++) opts.push('<option value="' + dk + '">' + dk + " · " + dekadLabel(dk) + "</option>");
    $("d0").innerHTML = opts.join(""); $("d1").innerHTML = opts.join("");
  }

  function syncControls() {
    document.querySelectorAll("#levels input[data-code]").forEach(function (el) {
      el.checked = ST.codes.indexOf(+el.dataset.code) >= 0;
    });
    const key = ST.codes.slice().sort().join(",");
    let preset = null;
    document.querySelectorAll(".preset").forEach(function (b) {
      const p = PRESETS.find(function (x) { return x.id === b.dataset.preset; });
      const on = p.codes.slice().sort().join(",") === key;
      if (on) preset = p;
      b.classList.toggle("on", on);
    });
    $("types-sum").textContent = (preset ? "Types" : t("Custom", "Personnalisé")) + " (" + of_(ST.codes.length, WARNING_TYPES.length) + ")" +
                                 (ST.exceptional ? "" : t(", no exceptional", ", sans conditions exceptionnelles"));
    $("exc").checked = ST.exceptional;
    $("cover").value = ST.cover;
    $("d0").value = ST.d0; $("d1").value = ST.d1;
    $("mindek").max = ST.d1 - ST.d0 + 1;
    $("mindek").value = ST.minDek;
    $("k").value = ST.k; $("kslider").value = ST.k;
    document.querySelectorAll('input[name="nat"]').forEach(function (el) { el.checked = el.value === ST.nat; });
    $("imp").value = ST.imp; $("yt").value = ST.yt;
    document.querySelectorAll(".ytlabel").forEach(function (el) { el.textContent = ST.yt; });
    $("klabel").textContent = nWord(ST.k, "province", "provinces", "province", "provinces");
    $("kunit").textContent = ST.k > 1 ? "provinces" : "province";
    if (ST.mapDk !== null && (ST.mapDk < ST.d0 || ST.mapDk > ST.d1)) ST.mapDk = null;
    buildMapDekadOptions();
    $("mapdk").value = ST.mapDk === null ? "all" : String(ST.mapDk);
    $("year").value = ST.year;
  }

  // ---------------- derived values
  function impactSeasons() { return ST.imp === "alt" ? DATA.meta.impact_seasons_alt : DATA.meta.impact_seasons_main; }
  function impactRecordYears() { return DATA.meta.impact_record_years[ST.imp]; }
  function inImpactRecord(y) { const r = impactRecordYears(); return y >= r[0] && y <= r[1]; }
  function yieldIdx(y) { const i = DATA.yield.years.indexOf(y); return i; }
  function nationalYield(y) {
    const i = yieldIdx(y);
    if (i < 0) return null;
    const n = DATA.yield.national;
    return { kg: n.kg_ha[i], anom: n.anom[i], prod: n.prod_kt[i], prodAnom: n.prod_anom[i] };
  }
  function provincesWithYield(y) {
    const i = yieldIdx(y);
    if (i < 0) return 0;
    return DATA.provinces.filter(function (p) { return DATA.yield.province[p.id].anom[i] !== null; }).length;
  }
  function poorYieldProvinces(y) {
    const i = yieldIdx(y);
    if (i < 0) return null;
    return DATA.provinces.filter(function (p) {
      const a = DATA.yield.province[p.id].anom[i];
      return a !== null && a <= -ST.yt;
    });
  }
  function impactRecords(y) {
    const key = ST.imp === "alt" ? "season_alt" : "season_main";
    return DATA.impacts.filter(function (r) { return r[key] === y; });
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

  // ---------------- summary
  function renderSummary(sum) {
    const imp = impactSeasons();
    const scored = ROWS.filter(function (r) { return r.valid && inImpactRecord(r.year); });
    const act = new Set(sum.years);
    const hits = imp.filter(function (y) { return act.has(y); });
    const misses = imp.filter(function (y) { return !act.has(y) && scored.some(function (r) { return r.year === y; }); });
    const fa = scored.filter(function (r) { return act.has(r.year) && imp.indexOf(r.year) < 0; }).map(function (r) { return r.year; });
    const yA = [], yN = [];
    ROWS.forEach(function (r) {
      const ny = r.valid ? nationalYield(r.year) : null;
      if (!ny) return;
      (act.has(r.year) ? yA : yN).push(ST.nat === "prod" ? ny.prodAnom : ny.anom);
    });
    const mean = function (a) { return a.length ? a.reduce(function (s, v) { return s + v; }, 0) / a.length : null; };

    // province-level agreement with poor yields
    let metPoor = 0, met = 0, notPoor = 0, notMet = 0;
    ROWS.forEach(function (r) {
      const i = yieldIdx(r.year);
      if (!r.valid || i < 0) return;
      DATA.provinces.forEach(function (p) {
        const a = DATA.yield.province[p.id].anom[i];
        if (a === null) return;
        const isMet = r.dekadsMet[p.id] >= ST.minDek;
        const poor = a <= -ST.yt;
        if (isMet) { met++; if (poor) metPoor++; } else { notMet++; if (poor) notPoor++; }
      });
    });

    const nImp = hits.length + misses.length;
    const tiles = [
      { v: of_(sum.k, sum.n), l: t("seasons reach the threshold", "saisons atteignent le seuil") },
      { v: fmtRp(sum.rp), l: t("return period", "période de retour") },
      { v: of_(hits.length, nImp), l: t("impact seasons reached", "saisons avec impact où le seuil est atteint") },
      { v: String(fa.length), l: t("seasons reached without a recorded impact", "saisons où le seuil est atteint sans impact enregistré") },
    ];
    $("live").innerHTML = "<b>" + sum.k + "</b>" + t(" of ", " sur ") + sum.n + " · <b>" +
                          (sum.rp ? t("1 in " + sum.rp.toFixed(1) + " yrs", "tous les " + sum.rp.toFixed(1) + " ans") : t("never", "jamais")) +
                          "</b> · impact <b>" + hits.length + "</b>" + t(" of ", " sur ") + nImp;
    $("live").setAttribute("data-tip", t(
      sum.k + " of " + sum.n + " seasons reach the threshold; return period " + fmtRp(sum.rp) + "; " + hits.length + " of " + nImp +
        " impact seasons reached",
      nWord(sum.k, "", "", "saison", "saisons") + " sur " + sum.n + (sum.k > 1 ? " atteignent" : " atteint") +
        " le seuil\u00a0; période de retour\u00a0: " + fmtRp(sum.rp) + "\u00a0; seuil atteint pour " +
        nWord(hits.length, "", "", "saison", "saisons") + " avec impact sur " + nImp));
    $("tiles").innerHTML = tiles.map(function (t) {
      return '<div class="tile"><div class="tv">' + esc(t.v) + '</div><div class="tl">' + esc(t.l) + "</div></div>";
    }).join("");

    const list = function (a) { return a.length ? a.join(", ") : t("none", "aucune"); };
    const prov = ROWS.find(function (r) { return r.year === DATA.meta.years[DATA.meta.years.length - 1]; });
    const provNote = prov && prov.valid && act.has(prov.year) ? " (" + prov.year + t(" provisional", " provisoire") + ")" : "";
    const yr0 = DATA.yield.years[0], yr1 = DATA.yield.years[DATA.yield.years.length - 1];
    const mA = mean(yA), mN = mean(yN);
    let s;
    if (LANG === "fr") {
      s = "<p>Saisons qui atteignent le seuil\u00a0: <strong>" + list(sum.years) + "</strong>" + provNote +
          ". Période de retour calculée sur " + sum.n + " saisons avec des données pour toute la plage de décades.</p>";
      s += "<p>Saisons avec impact (" + (ST.imp === "alt" ? "libellés du cadre" : "datées par saison de culture") +
           ") où le seuil est atteint\u00a0: " + list(hits) + "\u00a0; où il n’est pas atteint\u00a0: " + list(misses) +
           ". Saisons où le seuil est atteint sans impact de sécheresse enregistré (" + impactRecordYears().join("–") + ")\u00a0: " + list(fa) + ".</p>";
      s += "<p>" + (ST.nat === "prod" ? "Production" : "Rendement") + " national de mil et de sorgho, " + yr0 + "–" + yr1 + " : " +
           pct(mA) + " par rapport à la tendance en moyenne pour les saisons qui atteignent le seuil (" + yA.length + "), " + pct(mN) +
           " pour les autres (" + yN.length + ").";
      if (met && notMet) {
        s += " Par province\u00a0: quand une province était en alerte, son rendement était au moins " + ST.yt +
             "% sous la tendance dans " + Math.round(100 * metPoor / met) + "% des cas (" + metPoor + " sur " + met +
             "), contre " + Math.round(100 * notPoor / notMet) + "% quand elle ne l’était pas.";
      }
    } else {
      s = "<p>Seasons that reach the threshold: <strong>" + list(sum.years) + "</strong>" + provNote +
          ". Return period from " + sum.n + " seasons with data for the whole dekad range.</p>";
      s += "<p>Impact seasons (" + (ST.imp === "alt" ? "framework labelling" : "dated to the growing season") + "): reached " +
           list(hits) + "; not reached " + list(misses) + ". Seasons reached with no recorded drought impact (" +
           impactRecordYears().join("–") + "): " + list(fa) + ".</p>";
      s += "<p>National millet and sorghum " + (ST.nat === "prod" ? "production" : "yield") + ", " + yr0 + "–" + yr1 +
           ": " + pct(mA) + " from trend on average in seasons that reach the threshold (" + yA.length + "), " + pct(mN) +
           " in the others (" + yN.length + ").";
      if (met && notMet) {
        s += " By province: when a province met the warning condition, its yield was at least " + ST.yt +
             "% below trend in " + Math.round(100 * metPoor / met) + "% of cases (" + metPoor + " of " + met +
             "), against " + Math.round(100 * notPoor / notMet) + "% when it did not.";
      }
    }
    s += "</p>";
    $("summary").innerHTML = s;
  }

  // ---------------- chart 1: provinces per season
  function renderCounts(sum) {
    const el = $("chart-counts"), w = chartWidth(el), h = 300, padL = 44, padR = 14, padT = 18, padB = 52;
    const X = yearX(w, padL, padR), maxY = DATA.provinces.length;
    const y = function (v) { return padT + (h - padT - padB) * (1 - v / maxY); };
    const imp = new Set(impactSeasons()), act = new Set(sum.years);
    const last = DATA.meta.years[DATA.meta.years.length - 1];
    let s = svgOpen(w, h, t("Number of provinces meeting the warning condition in each season", "Nombre de provinces en alerte par saison"));
    [0, 10, 20, 30, 40].forEach(function (v) {
      s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + COL.grid + '"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end" class="ax">' + v + "</text>";
    });
    const bw = Math.min(22, X.step * 0.7);
    ROWS.forEach(function (r) {
      const cx = X.x(r.year);
      if (r.year === ST.year) {
        s += '<rect x="' + (cx - X.step / 2) + '" y="' + padT + '" width="' + X.step + '" height="' + (h - padT - padB) +
             '" fill="' + COL.band + '" fill-opacity="0.8"/>';
      }
      if (!r.valid) {
        s += '<text x="' + cx + '" y="' + (y(0) - 5) + '" text-anchor="middle" class="ax na">' + t("n/a", "n.d.") + "</text>";
      } else {
        const on = act.has(r.year);
        const top = y(r.count), hh = Math.max(0, y(0) - top);
        if (r.count > 0) {
          s += '<rect x="' + (cx - bw / 2) + '" y="' + top + '" width="' + bw + '" height="' + hh + '" rx="2" fill="' +
               (on ? COL.act : COL.base) + '"' + (r.year === last ? ' fill-opacity="0.6"' : "") + "/>";
        }
        if (on) s += '<text x="' + cx + '" y="' + (top - 4) + '" text-anchor="middle" class="lab">' + r.count + "</text>";
      }
      const tip = tipForYear(r, act.has(r.year));
      s += '<rect class="hit" data-year="' + r.year + '" x="' + (cx - X.step / 2) + '" y="' + padT + '" width="' + X.step + '" height="' + (h - padT - 8) +
           '" fill="transparent" style="cursor:pointer" data-tip="' + esc(tip + t("\nClick to show this season on the map", "\nCliquez pour afficher cette saison sur la carte")) + '"/>';
      const lab = (r.year % 5 === 0 || r.year === DATA.meta.years[0] || r.year === last) ? String(r.year) + (r.year === last ? "*" : "") : "";
      if (lab) s += '<text x="' + cx + '" y="' + (h - padB + 16) + '" text-anchor="middle" class="ax">' + lab + "</text>";
      else s += '<line x1="' + cx + '" x2="' + cx + '" y1="' + (h - padB + 2) + '" y2="' + (h - padB + 6) + '" stroke="' + COL.ink2 + '"/>';
      if (imp.has(r.year)) {
        const my = h - padB + 30;
        s += '<path d="M' + cx + " " + (my - 6) + " L" + (cx + 6) + " " + my + " L" + cx + " " + (my + 6) + " L" + (cx - 6) + " " + my +
             ' Z" fill="' + COL.ink + '"/>';
      }
    });
    s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(0) + '" y2="' + y(0) + '" stroke="' + COL.ink2 + '"/>';
    const ty = y(ST.k);
    s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + ty + '" y2="' + ty + '" stroke="' + COL.ink + '" stroke-width="1.5" stroke-dasharray="5 4"/>';
    s += '<text x="' + (padL - 6) + '" y="' + (h - padB + 34) + '" text-anchor="end" class="ax">impact</text>';
    s += "</svg>";
    el.innerHTML = s;
  }

  function tipForYear(r, on) {
    const lines = [String(r.year) + (r.year === DATA.meta.years[DATA.meta.years.length - 1] ? t(" (provisional)", " (provisoire)") : "")];
    if (!r.valid) {
      lines.push(t("No ASAP data for the whole dekad range", "Pas de données ASAP pour toute la plage de décades"));
    } else {
      lines.push(nWord(r.count, "province met the condition", "provinces met the condition", "province en alerte", "provinces en alerte") +
                 (on ? t(" (threshold reached by ", " (seuil atteint dès ") + dekadLabel(r.metAt[ST.k - 1]) + ")" : ""));
      const names = DATA.provinces.filter(function (p) { return r.dekadsMet[p.id] >= ST.minDek; }).map(function (p) { return p.name; });
      if (names.length && names.length <= 14) lines.push(names.join(", "));
    }
    const ny = nationalYield(r.year);
    if (ny) lines.push(t("National millet and sorghum yield ", "Rendement national mil et sorgho ") + pct(ny.anom) +
                       t(" from trend", " par rapport à la tendance"));
    impactRecords(r.year).forEach(function (rec) { lines.push(recLabel(rec)); });
    return lines.join("\n");
  }

  // ---------------- chart 2: return period by count threshold
  function renderKStrip() {
    const el = $("krp"), w = chartWidth(el), h = 170, padL = 44, padR = 14, padT = 14, padB = 34;
    const nP = DATA.provinces.length, step = (w - padL - padR) / nP;
    const stats = [];
    let maxK = 1;
    for (let k = 1; k <= nP; k++) { const s = summarise(ROWS, k); stats.push(s); maxK = Math.max(maxK, s.k); }
    const y = function (v) { return padT + (h - padT - padB) * (1 - v / maxK); };
    let s = svgOpen(w, h, t("Number of seasons reaching the threshold, for each count threshold",
                            "Nombre de saisons qui atteignent le seuil, pour chaque nombre de provinces possible"));
    // band where the return period is 3 to 5 years
    stats.forEach(function (st, i) {
      if (st.rp && st.rp >= 3 && st.rp <= 5) {
        s += '<rect x="' + (padL + i * step) + '" y="' + padT + '" width="' + step + '" height="' + (h - padT - padB) + '" fill="' + COL.band + '"/>';
      }
    });
    const ticks = maxK <= 10 ? [0, 5, 10] : [0, 10, 20];
    ticks.filter(function (t) { return t <= maxK; }).forEach(function (v) {
      s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + COL.grid + '"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end" class="ax">' + v + "</text>";
    });
    const bw = Math.max(3, step * 0.62);
    stats.forEach(function (st, i) {
      const k = i + 1, cx = padL + (i + 0.5) * step, on = k === ST.k;
      if (st.k > 0) {
        s += '<rect x="' + (cx - bw / 2) + '" y="' + y(st.k) + '" width="' + bw + '" height="' + (y(0) - y(st.k)) + '" rx="1.5" fill="' +
             (on ? COL.act : COL.base) + '"/>';
      }
      const tip = t("Threshold " + nWord(k, "province", "provinces") + ": " + st.k + " of " + st.n + " seasons, " + fmtRp(st.rp),
                    "Seuil de " + nWord(k, "", "", "province", "provinces") + "\u00a0: " + nWord(st.k, "", "", "saison", "saisons") + " sur " +
                    st.n + ", " + fmtRp(st.rp)) +
                  (st.years.length && st.years.length <= 12 ? "\n" + st.years.join(", ") : "") +
                  t("\nClick to use this threshold", "\nCliquez pour utiliser ce seuil");
      s += '<rect class="hit" data-k="' + k + '" x="' + (padL + i * step) + '" y="' + padT + '" width="' + step + '" height="' +
           (h - padT - 4) + '" fill="transparent" style="cursor:pointer" data-tip="' + esc(tip) + '"/>';
      if (k === 1 || k % 5 === 0) s += '<text x="' + cx + '" y="' + (h - padB + 15) + '" text-anchor="middle" class="ax">' + k + "</text>";
    });
    s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(0) + '" y2="' + y(0) + '" stroke="' + COL.ink2 + '"/>';
    s += '<text x="' + ((w + padL) / 2) + '" y="' + (h - 4) + '" text-anchor="middle" class="ax">' + t("count threshold (provinces)", "seuil (nombre de provinces)") + "</text>";
    s += "</svg>";
    el.innerHTML = s;
  }

  // ---------------- chart 3: national yield anomaly
  function renderYield(sum) {
    const el = $("chart-yield"), w = chartWidth(el), h = 230, padL = 44, padR = 14, padT = 14, padB = 30;
    const X = yearX(w, padL, padR), lim = 25;
    const y = function (v) { return padT + (h - padT - padB) * (lim - Math.max(-lim, Math.min(lim, v))) / (2 * lim); };
    const act = new Set(sum.years);
    const last = DATA.meta.years[DATA.meta.years.length - 1];
    const prodMode = ST.nat === "prod";
    let s = svgOpen(w, h, t("National millet and sorghum " + (prodMode ? "production" : "yield") + ", percentage from trend, by season",
                            (prodMode ? "Production" : "Rendement") + " national de mil et de sorgho, écart à la tendance en pourcentage, par saison"));
    [-20, -10, 0, 10, 20].forEach(function (v) {
      s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + (v === 0 ? COL.ink2 : COL.grid) + '"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end" class="ax">' + (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v) + "%</text>";
    });
    const bw = Math.min(22, X.step * 0.7);
    DATA.meta.years.forEach(function (yr) {
      const cx = X.x(yr), ny = nationalYield(yr);
      if (ny) {
        const v = prodMode ? ny.prodAnom : ny.anom;
        const y0 = y(0), y1 = y(v);
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
      const lab = (yr % 5 === 0 || yr === DATA.meta.years[0] || yr === last) ? String(yr) : "";
      if (lab) s += '<text x="' + cx + '" y="' + (h - padB + 16) + '" text-anchor="middle" class="ax">' + lab + "</text>";
    });
    s += "</svg>";
    el.innerHTML = s;
  }

  // ---------------- chart 4: provinces x seasons
  function renderGrid() {
    const el = $("chart-grid"), w = chartWidth(el), padL = 210, padR = 14, padT = 22, rowH = 13, gap = 6;
    const ys = DATA.meta.years, step = (w - padL - padR) / ys.length;
    const regions = [];
    DATA.provinces.forEach(function (p) {
      if (!regions.length || regions[regions.length - 1].name !== p.region) regions.push({ name: p.region, provs: [] });
      regions[regions.length - 1].provs.push(p);
    });
    const h = padT + DATA.provinces.length * rowH + (regions.length - 1) * gap + 8;
    let s = svgOpen(w, h, t("Provinces meeting the warning condition by season, with poor-yield provinces marked",
                            "Provinces en alerte par saison, avec les provinces à rendement faible marquées"));
    ys.forEach(function (yr, i) {
      if (yr % 5 === 0 || i === 0 || i === ys.length - 1) {
        s += '<text x="' + (padL + (i + 0.5) * step) + '" y="' + (padT - 8) + '" text-anchor="middle" class="ax">' + yr + "</text>";
      }
    });
    let top = padT;
    regions.forEach(function (rg) {
      s += '<text x="4" y="' + (top + 9) + '" class="rg">' + esc(rg.name) + "</text>";
      rg.provs.forEach(function (p, j) {
        const ry = top + j * rowH;
        s += '<text x="' + (padL - 6) + '" y="' + (ry + 10) + '" text-anchor="end" class="pv">' + esc(p.name) + "</text>";
        ROWS.forEach(function (r, i) {
          const x = padL + i * step;
          const n = r.dekadsMet[p.id], isMet = r.valid && n >= ST.minDek;
          const fill = !r.valid ? "#fff" : isMet ? COL.act : n > 0 ? COL.actSoft : COL.none;
          s += '<rect x="' + (x + 1) + '" y="' + (ry + 1) + '" width="' + (step - 2) + '" height="' + (rowH - 2) + '" fill="' + fill + '"' +
               (!r.valid ? ' stroke="' + COL.grid + '"' : "") + "/>";
          const yi = yieldIdx(r.year);
          const ya = yi >= 0 ? DATA.yield.province[p.id].anom[yi] : null;
          if (ya !== null && ya <= -ST.yt) {
            s += '<circle cx="' + (x + step / 2) + '" cy="' + (ry + rowH / 2) + '" r="2.6" fill="' + COL.ink + '" stroke="#fff" stroke-width="1"/>';
          }
          const nDk = ST.d1 - ST.d0 + 1;
          const tip = p.name + " (" + p.region + "), " + r.year + "\n" +
                      (!r.valid ? t("No ASAP data for the whole dekad range", "Pas de données ASAP pour toute la plage de décades") :
                       t("Condition met in " + n + " of " + nDk + " dekads", "En alerte pendant " + n + (n > 1 ? " décades" : " décade") + " sur " + nDk) +
                       (isMet ? "" : n > 0 ? t(" (below the minimum of " + ST.minDek + ")", " (sous le minimum de " + ST.minDek + ")") : "")) +
                      "\n" + levelSummary(p.id, r.year) +
                      (yi < 0 ? "" : ya === null ? t("\nNo complete millet and sorghum statistics", "\nPas de statistiques complètes pour le mil et le sorgho") :
                        t("\nMillet and sorghum yield ", "\nRendement mil et sorgho ") + DATA.yield.province[p.id].kg_ha[yi] + " kg/ha, " +
                        pct(ya) + t(" from trend", " par rapport à la tendance"));
          if (r.year === ST.year) {
            s += '<rect x="' + (x + 0.5) + '" y="' + (ry + 0.5) + '" width="' + (step - 1) + '" height="' + (rowH - 1) +
                 '" fill="none" stroke="' + COL.ink2 + '" stroke-width="0.8"/>';
          }
          s += '<rect class="hit" data-year="' + r.year + '" x="' + x + '" y="' + ry + '" width="' + step + '" height="' + rowH +
               '" fill="transparent" style="cursor:pointer" data-tip="' +
               esc(tip + t("\nClick to show this season on the map", "\nCliquez pour afficher cette saison sur la carte")) + '"/>';
        });
      });
      top += rg.provs.length * rowH + gap;
    });
    s += "</svg>";
    el.innerHTML = s;
  }

  // ---------------- map by season
  function lvl(code) { const v = CODE_LEVEL[code]; return v === undefined ? -1 : v; }
  // level shown for one dekad under the land-cover setting (or: higher of the two; and: lower of the two)
  function coverLevel(d, i) {
    const c = lvl(d.crop[i]), r = lvl(d.range[i]);
    if (ST.cover === "crop") return c;
    if (ST.cover === "range") return r;
    if (ST.cover === "and") return Math.min(c, r);
    return Math.max(c, r);
  }
  function levelSeq(arr, yi) {
    let out = [];
    for (let dk = ST.d0; dk <= ST.d1; dk++) { const v = lvl(arr[yi * 36 + dk - 1]); out.push(v < 0 ? "–" : String(v)); }
    return out.join(" ");
  }
  function renderMap() {
    const m = DATA.map, yi = DATA.meta.years.indexOf(ST.year), r = ROWS[yi];
    const coverName = { crop: t("cropland", "zones agricoles"), range: t("rangeland", "zones de pâturage"),
                        or: t("cropland or rangeland, higher of the two", "zones agricoles ou de pâturage, niveau le plus élevé des deux"),
                        and: t("cropland and rangeland, lower of the two", "zones agricoles et de pâturage, niveau le plus faible des deux") }[ST.cover];
    let s = '<svg viewBox="-4 -4 ' + (m.width + 8) + " " + (m.height + 8) + '" role="img" aria-label="' +
            esc(t("ASAP warnings by province, ", "Alertes ASAP par province, ") + ST.year) + '">';
    let outlines = "";
    DATA.provinces.forEach(function (p) {
      const d = DEC[p.id];
      let level = -1;
      if (ST.mapDk) level = coverLevel(d, yi * 36 + ST.mapDk - 1);
      else for (let dk = ST.d0; dk <= ST.d1; dk++) level = Math.max(level, coverLevel(d, yi * 36 + dk - 1));
      const n = r.dekadsMet[p.id], counts = r.valid && n >= ST.minDek, nDk = ST.d1 - ST.d0 + 1;
      const lvTxt = level > 0 ? t("level ", "niveau ") + level : level === 0 ? t("no warning", "pas d’alerte") : t("off season or not assessed", "hors saison ou non évalué");
      const tip = p.name + " (" + p.region + "), " + ST.year + (ST.year === DATA.meta.years[DATA.meta.years.length - 1] ? t(" (provisional)", " (provisoire)") : "") +
        "\n" + (ST.mapDk ? t("Dekad ", "Décade ") + ST.mapDk + " (" + dekadLabel(ST.mapDk) + ")" : t("Highest over dekads ", "Plus élevé sur les décades ") + ST.d0 + "–" + ST.d1) +
        " (" + coverName + ")" + t(": ", "\u00a0: ") + lvTxt +
        t("\nCropland by dekad ", "\nZones agricoles par décade ") + ST.d0 + "–" + ST.d1 + t(": ", "\u00a0: ") + levelSeq(d.crop, yi) +
        t("\nRangeland by dekad ", "\nZones de pâturage par décade ") + ST.d0 + "–" + ST.d1 + t(": ", "\u00a0: ") + levelSeq(d.range, yi) +
        (!r.valid ? t("\nNo ASAP data for the whole dekad range", "\nPas de données ASAP pour toute la plage de décades") :
         counts ? t("\nCounts toward the threshold (condition met in " + n + " of " + nDk + " dekads)",
                    "\nComptée pour le seuil (en alerte pendant " + n + (n > 1 ? " décades" : " décade") + " sur " + nDk + ")")
                : t("\nDoes not count (condition met in " + n + " of " + nDk + " dekads; minimum " + ST.minDek + ")",
                    "\nNon comptée (en alerte pendant " + n + (n > 1 ? " décades" : " décade") + " sur " + nDk + "\u00a0; minimum " + ST.minDek + ")"));
      s += '<path d="' + m.provinces[String(p.id)] + '" fill="' + LEVEL_FILL[level] + '" stroke="' + (level < 0 ? "#c9d3d3" : "#fff") +
           '" stroke-width="0.8" data-tip="' + esc(tip) + '"/>';
      if (counts) outlines += '<path d="' + m.provinces[String(p.id)] + '" fill="none" stroke="' + COL.ink + '" stroke-width="2.2" pointer-events="none"/>';
    });
    m.regions.forEach(function (dd) { s += '<path d="' + dd + '" fill="none" stroke="#7e8e8f" stroke-width="0.9" pointer-events="none"/>'; });
    $("map").innerHTML = s + outlines + "</svg>";
    document.querySelectorAll(".map-cover").forEach(function (el) { el.textContent = coverName; });

    // side panel: did the season reach the threshold?
    const sum = summarise(ROWS, ST.k), reached = sum.years.indexOf(ST.year) >= 0, ny = nationalYield(ST.year);
    const recs = impactRecords(ST.year), last = DATA.meta.years[DATA.meta.years.length - 1];
    const impTxt = !inImpactRecord(ST.year) ? '<span class="muted">' + t("not yet known", "pas encore connu") + "</span>" :
                   impactSeasons().indexOf(ST.year) >= 0 ? '<span class="tag imp">' + t("Yes", "Oui") + "</span>" : t("No", "Non");
    let info = '<div class="yr">' + ST.year + (ST.year === last ? '<span class="muted">*</span>' : "") + "</div>";
    info += '<div class="kv"><span>' + t("Provinces meeting the condition", "Provinces en alerte") + "</span><b>" + (r.valid ? r.count : "–") + "</b></div>";
    info += '<div class="kv"><span>' + t("Threshold", "Seuil") + " (" + nWord(ST.k, "province", "provinces", "province", "provinces") + ")</span><b>" +
            (!r.valid ? t("no data", "pas de données") : reached ? '<span class="tag on">' + t("reached", "atteint") + "</span> " +
             t("by ", "dès ") + dekadLabel(r.metAt[ST.k - 1]) : '<span class="tag off">' + t("not reached", "non atteint") + "</span>") + "</b></div>";
    info += '<div class="kv"><span>' + t("National yield vs trend", "Rendement national, écart à la tendance") + "</span><b>" + (ny ? pct(ny.anom) : "–") + "</b></div>";
    info += '<div class="kv"><span>' + t("National production vs trend", "Production nationale, écart à la tendance") + "</span><b>" + (ny ? pct(ny.prodAnom) : "–") + "</b></div>";
    info += '<div class="kv"><span>' + t("Impact season", "Saison avec impact") + "</span><b>" + impTxt + "</b></div>";
    if (recs.length) info += '<ul class="recs-list">' + recs.map(function (x) { return "<li>" + esc(recLabel(x)) + ' <span class="muted">(' + esc(recDate(x)) + ")</span></li>"; }).join("") + "</ul>";
    $("map-info").innerHTML = info;
    $("yprev").disabled = ST.year === DATA.meta.years[0];
    $("ynext").disabled = ST.year === last;
  }

  function levelSummary(pid, year) {
    const yi = DATA.meta.years.indexOf(year), d = DEC[pid];
    let hc = -1, hr = -1;
    for (let dk = ST.d0; dk <= ST.d1; dk++) {
      const i = yi * 36 + dk - 1;
      hc = Math.max(hc, CODE_LEVEL[d.crop[i]] === undefined ? -1 : CODE_LEVEL[d.crop[i]]);
      hr = Math.max(hr, CODE_LEVEL[d.range[i]] === undefined ? -1 : CODE_LEVEL[d.range[i]]);
    }
    const f = function (v) {
      return v > 0 ? t("level ", "niveau ") + v : v === 0 ? t("no warning", "pas d’alerte") : t("off season or not assessed", "hors saison ou non évalué");
    };
    return t("Highest ASAP warning in the range: cropland " + f(hc) + ", rangeland " + f(hr),
             "Alerte ASAP la plus élevée sur la plage\u00a0: zones agricoles " + f(hc) + ", zones de pâturage " + f(hr));
  }

  // ---------------- table
  function tableRows(sum) {
    const act = new Set(sum.years), imp = new Set(impactSeasons()), fw = new Set(DATA.meta.framework_years);
    const last = DATA.meta.years[DATA.meta.years.length - 1];
    return ROWS.slice().reverse().map(function (r) {
      const ny = nationalYield(r.year), poor = poorYieldProvinces(r.year), recs = impactRecords(r.year);
      return {
        year: r.year, provisional: r.year === last, valid: r.valid,
        count: r.valid ? r.count : null,
        reached: r.valid ? (act.has(r.year) ? "Yes" : "No") : "No data", // CSV values (English); shown via t()
        dekad: r.valid && act.has(r.year) ? r.metAt[ST.k - 1] : null,
        yieldKg: ny ? ny.kg : null, yieldAnom: ny ? ny.anom : null, prodAnom: ny ? ny.prodAnom : null,
        poor: poor ? poor.length : null, withYield: provincesWithYield(r.year),
        impact: inImpactRecord(r.year) ? (imp.has(r.year) ? "Yes" : "No") : "Not yet known",
        emdat: recs.filter(function (x) { return x.source === "EM-DAT"; }),
        cerf: recs.filter(function (x) { return x.source === "CERF"; }),
        framework: fw.has(r.year),
      };
    });
  }

  function renderTable(sum) {
    const rows = tableRows(sum);
    let s = "";
    const YES = t("Yes", "Oui"), NO = t("No", "Non");
    rows.forEach(function (row) {
      const cls = row.reached === "Yes" ? ' class="hit-row"' : "";
      const recs = row.emdat.concat(row.cerf);
      s += "<tr" + cls + "><td>" + row.year + (row.provisional ? "*" : "") + "</td>" +
           '<td class="num">' + (row.count === null ? "–" : row.count) + "</td>" +
           '<td class="nw">' + (row.reached === "Yes" ? '<span class="tag on">' + YES + "</span> " + dekadLabel(row.dekad) :
             row.reached === "No" ? '<span class="tag off">' + NO + "</span>" : t("No data", "Pas de données")) + "</td>" +
           '<td class="num">' + (row.yieldKg === null ? "–" : row.yieldKg) + "</td>" +
           '<td class="num">' + pct(row.yieldAnom) + "</td>" +
           '<td class="num">' + pct(row.prodAnom) + "</td>" +
           '<td class="num">' + (row.poor === null ? "–" : row.poor + (row.withYield < DATA.provinces.length ? t(" of ", " sur ") + row.withYield : "")) + "</td>" +
           '<td class="nw">' + (row.impact === "Yes" ? '<span class="tag imp">' + YES + "</span>" : row.impact === "No" ? NO :
             '<span class="muted">' + t("not yet known", "pas encore connu") + "</span>") + "</td>" +
           '<td class="recs">' + recs.map(function (x) {
             return '<span data-tip="' + esc(recLabel(x) + t("\nRecorded ", "\nDate\u00a0: ") + recDate(x) + " (" + x.source + " " + x.id + ")") + '">' +
                    esc(x.short) + "</span>";
           }).join("<br>") + "</td>" +
           "<td>" + (row.framework ? YES : "") + "</td></tr>";
    });
    $("tbody").innerHTML = s;
    $("th-poor").textContent = t("Provinces with yield ≥" + ST.yt + "% below trend", "Provinces avec un rendement ≥" + ST.yt + "% sous la tendance");
  }

  function downloadCsv() {
    const sum = summarise(ROWS, ST.k);
    const rows = tableRows(sum);
    const head = ["season", "provisional", "provinces_meeting_condition", "threshold_reached", "threshold_reached_dekad",
                  "national_millet_sorghum_yield_kg_ha", "national_yield_pct_from_trend", "national_production_pct_from_trend",
                  "provinces_yield_" + ST.yt + "pct_below_trend", "provinces_with_yield_data", "impact_season", "emdat_drought", "cerf_drought", "framework_target_year"];
    const q = function (v) { v = v === null || v === undefined ? "" : String(v); return /[",;\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const lines = [head.join(",")];
    rows.forEach(function (row) {
      const dk = row.dekad ? row.dekad + " (" + MONTHS[Math.floor((row.dekad - 1) / 3)] + " " + ((row.dekad - 1) % 3 + 1) + ")" : "";
      lines.push([row.year, row.provisional ? "yes" : "", row.count, row.reached, dk,
                  row.yieldKg, row.yieldAnom, row.prodAnom, row.poor, row.poor === null ? "" : row.withYield, row.impact,
                  row.emdat.map(function (x) { return x.label + " [" + x.id + ", " + x.recorded + "]"; }).join("; "),
                  row.cerf.map(function (x) { return x.label + " [" + x.id + ", " + x.recorded + "]"; }).join("; "),
                  row.framework ? "yes" : ""].map(q).join(","));
    });
    const settings = "# settings: warnings " + ST.codes.slice().sort(function (a, b) { return a - b; }).join("/") +
                     (ST.exceptional ? " incl. exceptional-conditions variants" : "") + "; land cover " + ST.cover +
                     "; dekads " + ST.d0 + "-" + ST.d1 + "; min dekads " + ST.minDek + "; threshold " + ST.k +
                     " provinces; impact dating " + ST.imp + "; " + location.href;
    const blob = new Blob([settings + "\n" + lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "bfa_asap_trigger_explorer.csv";
    document.body.appendChild(a); a.click(); a.remove();
  }

  // ---------------- tooltip
  function initTooltip() {
    const tip = $("tip");
    document.addEventListener("mouseover", function (e) {
      const t = e.target.closest && e.target.closest("[data-tip]");
      if (!t) { tip.hidden = true; return; }
      tip.textContent = (LANG === "fr" && t.getAttribute("data-tip-fr")) || t.getAttribute("data-tip");
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
    if (!ST.codes.length) {
      $("empty").hidden = false;
    } else {
      $("empty").hidden = true;
    }
    ST.minDek = Math.max(1, Math.min(Math.round(ST.minDek) || 1, ST.d1 - ST.d0 + 1));
    if (!kOnly) ROWS = evaluate(DATA, DEC, ST);
    if (ST.k === null) ST.k = suggestK(ROWS, DATA.provinces.length, 4);
    syncControls();
    writeState();
    const sum = summarise(ROWS, ST.k);
    renderSummary(sum);
    renderMap();
    renderCounts(sum);
    renderKStrip();
    renderYield(sum);
    renderGrid();
    renderTable(sum);
  }

  const TITLES = {
    en: "Burkina Faso drought — ASAP warning explorer for a national trigger",
    fr: "Sécheresse au Burkina Faso — explorateur des alertes ASAP pour un déclencheur national",
  };
  function staticDynamicText() {
    if (!DATA) return;
    const last = new Date(DATA.meta.asap_last_dekad + "T00:00:00Z");
    const lastDk = last.getUTCMonth() * 3 + Math.min(Math.floor((last.getUTCDate() - 1) / 10), 2) + 1;
    const lastTxt = dekadLong(lastDk) + " " + last.getUTCFullYear();
    const longMonth = LANG === "fr" ? MONTHS_FR_LONG[last.getUTCMonth()] : MONTHS[last.getUTCMonth()];
    $("vintage").textContent = t("ASAP archive to " + DATA.meta.asap_last_dekad + " (" + lastTxt + "); built " + DATA.meta.built + ".",
                                 "Archive ASAP jusqu’au " + DATA.meta.asap_last_dekad + " (" + lastTxt + ")\u00a0; générée le " + DATA.meta.built + ".");
    document.querySelectorAll(".last-dekad").forEach(function (el) {
      el.textContent = last.getUTCDate() + " " + longMonth + " " + last.getUTCFullYear() + " (" + lastTxt + ")";
    });
  }
  function setLang(l) {
    LANG = l === "fr" ? "fr" : "en";
    const html = document.documentElement;
    html.lang = LANG; html.setAttribute("data-lang", LANG);
    try { localStorage.setItem("aa-lang", LANG); } catch (e) { /* private mode */ }
    document.title = TITLES[LANG];
    document.querySelectorAll(".aa-lang button").forEach(function (b) { b.classList.toggle("on", b.dataset.l === LANG); });
    // <option> and aria-label can't hold spans: they carry data-fr (and remember their English)
    document.querySelectorAll("option[data-fr]").forEach(function (o) {
      if (!o.dataset.en) o.dataset.en = o.textContent;
      o.textContent = LANG === "fr" ? o.dataset.fr : o.dataset.en;
    });
    document.querySelectorAll("[data-aria-fr]").forEach(function (el) {
      if (!el.dataset.ariaEn) el.dataset.ariaEn = el.getAttribute("aria-label") || "";
      el.setAttribute("aria-label", LANG === "fr" ? el.dataset.ariaFr : el.dataset.ariaEn);
    });
    if (DATA) {
      buildDekadOptions();
      staticDynamicText();
      update(true);
    }
  }
  function initLang() {
    const q = new URLSearchParams(location.search).get("lang");
    let stored = null;
    try { stored = localStorage.getItem("aa-lang"); } catch (e) { /* private mode */ }
    document.querySelectorAll(".aa-lang button").forEach(function (b) {
      b.addEventListener("click", function () { setLang(b.dataset.l); });
    });
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
      $("kslider").max = data.provinces.length; $("k").max = data.provinces.length;
      $("app").hidden = false; $("loading").hidden = true;
      update();
      let timer;
      window.addEventListener("resize", function () { clearTimeout(timer); timer = setTimeout(function () { update(true); }, 150); });
    }).catch(function (err) {
      $("loading").textContent = t("Could not load the data (", "Impossible de charger les données (") + err + ").";
    });
  }
  root.ASAPExplorer = api;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})(this);
