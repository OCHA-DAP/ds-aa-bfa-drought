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
    { code: 2, level: 1, label: "Water balance (WSI)" },
    { code: 3, level: 1, label: "Rainfall (SPI-3)" },
    { code: 4, level: 1, label: "Water balance and rainfall" },
    { code: 5, level: 2, label: "Biomass (zNDVIc)" },
    { code: 6, level: 3, label: "Biomass and water balance" },
    { code: 7, level: 3, label: "Biomass and rainfall" },
    { code: 8, level: 3, label: "Biomass, water balance and rainfall" },
    { code: 9, level: 4, label: "End-of-season biomass" },
  ];
  const LEVEL_NAMES = {
    1: "Level 1: rainfall or water-balance deficit",
    2: "Level 2: poor biomass",
    3: "Level 3: poor biomass with rainfall or water-balance deficit",
    4: "Level 4: poor biomass at the end of the season",
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
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const PART = ["1st", "2nd", "3rd"];
  function dekadLabel(dk) { return MONTHS[Math.floor((dk - 1) / 3)] + " " + ((dk - 1) % 3 + 1); }
  function dekadLong(dk) { return PART[(dk - 1) % 3] + " dekad of " + MONTHS[Math.floor((dk - 1) / 3)]; }

  const COL = {
    act: "#9d372b", actSoft: "#f2d9d6", base: "#b9c4c5", none: "#eef1f1", ink: "#1f2324",
    ink2: "#5e6a6b", grid: "#e2e8e8", band: "#e9f5f1", brand: "#1e795f",
  };
  const DEFAULTS = { codes: [6, 7, 8, 9], exceptional: true, cover: "or", d0: 21, d1: 26, minDek: 1, k: null,
                     imp: "main", yt: 20, nat: "yield" };
  const PRESETS = [
    { id: "ge1", label: "Level 1 or above", codes: [2, 3, 4, 5, 6, 7, 8, 9] },
    { id: "ge2", label: "Level 2 or above", codes: [5, 6, 7, 8, 9] },
    { id: "ge3", label: "Level 3 or above", codes: [6, 7, 8, 9] },
    { id: "eq4", label: "Level 4 only", codes: [9] },
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
  function fmtRp(rp) { return rp ? "1 in " + rp.toFixed(1) + " years" : "never"; }

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
    return st;
  }
  function writeState() {
    const q = new URLSearchParams();
    q.set("w", ST.codes.slice().sort(function (a, b) { return a - b; }).join(","));
    q.set("x", ST.exceptional ? "1" : "0");
    q.set("lc", ST.cover); q.set("d0", ST.d0); q.set("d1", ST.d1); q.set("md", ST.minDek);
    q.set("k", ST.k); q.set("imp", ST.imp); q.set("yt", ST.yt); q.set("nat", ST.nat);
    history.replaceState(null, "", "?" + q.toString());
  }

  // ---------------- controls
  function buildControls() {
    const lv = $("levels");
    let html = "";
    [1, 2, 3, 4].forEach(function (L) {
      html += '<fieldset class="lvl"><legend>' + esc(LEVEL_NAMES[L]) + "</legend>";
      WARNING_TYPES.filter(function (t) { return t.level === L; }).forEach(function (t) {
        html += '<label><input type="checkbox" data-code="' + t.code + '"> ' + esc(t.label) + "</label>";
      });
      html += "</fieldset>";
    });
    lv.innerHTML = html;
    $("presets").innerHTML = PRESETS.map(function (p) {
      return '<button type="button" class="preset" data-preset="' + p.id + '">' + esc(p.label) + "</button>";
    }).join("");

    const opts = [];
    for (let dk = 1; dk <= 36; dk++) opts.push('<option value="' + dk + '">' + dk + " · " + dekadLabel(dk) + "</option>");
    $("d0").innerHTML = opts.join(""); $("d1").innerHTML = opts.join("");

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
    document.querySelectorAll('input[name="cover"]').forEach(function (el) {
      el.addEventListener("change", function (e) { ST.cover = e.target.value; update(); });
    });
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
  }

  function syncControls() {
    document.querySelectorAll("#levels input[data-code]").forEach(function (el) {
      el.checked = ST.codes.indexOf(+el.dataset.code) >= 0;
    });
    const key = ST.codes.slice().sort().join(",");
    document.querySelectorAll(".preset").forEach(function (b) {
      const p = PRESETS.find(function (x) { return x.id === b.dataset.preset; });
      b.classList.toggle("on", p.codes.slice().sort().join(",") === key);
    });
    $("exc").checked = ST.exceptional;
    document.querySelectorAll('input[name="cover"]').forEach(function (el) { el.checked = el.value === ST.cover; });
    $("d0").value = ST.d0; $("d1").value = ST.d1;
    $("mindek").max = ST.d1 - ST.d0 + 1;
    $("mindek").value = ST.minDek;
    $("k").value = ST.k; $("kslider").value = ST.k;
    document.querySelectorAll('input[name="nat"]').forEach(function (el) { el.checked = el.value === ST.nat; });
    $("imp").value = ST.imp; $("yt").value = ST.yt;
    $("ytlabel").textContent = ST.yt;
    $("klabel").textContent = ST.k;
    $("range-note").textContent = dekadLong(ST.d0) + " to " + dekadLong(ST.d1) + " (" + (ST.d1 - ST.d0 + 1) + " dekads)";
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

    const tiles = [
      { v: sum.k + " of " + sum.n, l: "seasons reach the threshold" },
      { v: fmtRp(sum.rp), l: "return period" },
      { v: hits.length + " of " + (hits.length + misses.length), l: "impact seasons reached" },
      { v: String(fa.length), l: "seasons reached without a recorded impact" },
    ];
    $("tiles").innerHTML = tiles.map(function (t) {
      return '<div class="tile"><div class="tv">' + esc(t.v) + '</div><div class="tl">' + esc(t.l) + "</div></div>";
    }).join("");

    const list = function (a) { return a.length ? a.join(", ") : "none"; };
    const prov = ROWS.find(function (r) { return r.year === DATA.meta.years[DATA.meta.years.length - 1]; });
    let s = "<p>Seasons that reach the threshold: <strong>" + list(sum.years) + "</strong>";
    if (prov && prov.valid && act.has(prov.year)) s += " (" + prov.year + " provisional)";
    s += ". Return period from " + sum.n + " seasons with data for the whole dekad range.</p>";
    s += "<p>Impact seasons (" + (ST.imp === "alt" ? "framework labelling" : "dated to the growing season") + "): reached " +
         list(hits) + "; not reached " + list(misses) + ". Seasons reached with no recorded drought impact (" +
         impactRecordYears().join("–") + "): " + list(fa) + ".</p>";
    const mA = mean(yA), mN = mean(yN);
    s += "<p>National millet and sorghum " + (ST.nat === "prod" ? "production" : "yield") + ", " + DATA.yield.years[0] + "–" + DATA.yield.years[DATA.yield.years.length - 1] +
         ": " + pct(mA) + " from trend on average in seasons that reach the threshold (" + yA.length + "), " + pct(mN) +
         " in the others (" + yN.length + ").";
    if (met && notMet) {
      s += " By province: when a province met the warning condition, its yield was at least " + ST.yt +
           "% below trend in " + Math.round(100 * metPoor / met) + "% of cases (" + metPoor + " of " + met +
           "), against " + Math.round(100 * notPoor / notMet) + "% when it did not.";
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
    let s = svgOpen(w, h, "Number of provinces meeting the warning condition in each season");
    [0, 10, 20, 30, 40].forEach(function (v) {
      s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + COL.grid + '"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end" class="ax">' + v + "</text>";
    });
    const bw = Math.min(22, X.step * 0.7);
    ROWS.forEach(function (r) {
      const cx = X.x(r.year);
      if (!r.valid) {
        s += '<text x="' + cx + '" y="' + (y(0) - 5) + '" text-anchor="middle" class="ax na">n/a</text>';
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
      s += '<rect class="hit" x="' + (cx - X.step / 2) + '" y="' + padT + '" width="' + X.step + '" height="' + (h - padT - 8) +
           '" fill="transparent" data-tip="' + esc(tip) + '"/>';
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
    const lines = [String(r.year) + (r.year === DATA.meta.years[DATA.meta.years.length - 1] ? " (provisional)" : "")];
    if (!r.valid) {
      lines.push("No ASAP data for the whole dekad range");
    } else {
      lines.push(r.count + " provinces met the condition" + (on ? " (threshold reached by " + dekadLabel(r.metAt[ST.k - 1]) + ")" : ""));
      const names = DATA.provinces.filter(function (p) { return r.dekadsMet[p.id] >= ST.minDek; }).map(function (p) { return p.name; });
      if (names.length && names.length <= 14) lines.push(names.join(", "));
    }
    const ny = nationalYield(r.year);
    if (ny) lines.push("National millet and sorghum yield " + pct(ny.anom) + " from trend");
    impactRecords(r.year).forEach(function (rec) { lines.push(rec.label); });
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
    let s = svgOpen(w, h, "Number of seasons reaching the threshold, for each count threshold");
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
      const tip = "Threshold " + k + " provinces: " + st.k + " of " + st.n + " seasons, " + fmtRp(st.rp) +
                  (st.years.length && st.years.length <= 12 ? "\n" + st.years.join(", ") : "") + "\nClick to use this threshold";
      s += '<rect class="hit" data-k="' + k + '" x="' + (padL + i * step) + '" y="' + padT + '" width="' + step + '" height="' +
           (h - padT - 4) + '" fill="transparent" style="cursor:pointer" data-tip="' + esc(tip) + '"/>';
      if (k === 1 || k % 5 === 0) s += '<text x="' + cx + '" y="' + (h - padB + 15) + '" text-anchor="middle" class="ax">' + k + "</text>";
    });
    s += '<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + y(0) + '" y2="' + y(0) + '" stroke="' + COL.ink2 + '"/>';
    s += '<text x="' + ((w + padL) / 2) + '" y="' + (h - 4) + '" text-anchor="middle" class="ax">count threshold (provinces)</text>';
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
    let s = svgOpen(w, h, "National millet and sorghum " + (prodMode ? "production" : "yield") + ", percentage from trend, by season");
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
        const tip = yr + "\nYield " + ny.kg + " kg/ha, " + pct(ny.anom) + " from trend\nProduction " + ny.prod + " thousand t, " +
                    pct(ny.prodAnom) + " from trend" + (act.has(yr) ? "\nThreshold reached" : "");
        s += '<rect class="hit" x="' + (cx - X.step / 2) + '" y="' + padT + '" width="' + X.step + '" height="' + (h - padT - padB) +
             '" fill="transparent" data-tip="' + esc(tip) + '"/>';
      } else {
        s += '<text x="' + cx + '" y="' + (y(0) - 5) + '" text-anchor="middle" class="ax na">n/a</text>';
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
    let s = svgOpen(w, h, "Provinces meeting the warning condition by season, with poor-yield provinces marked");
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
          const tip = p.name + " (" + p.region + "), " + r.year + "\n" + (!r.valid ? "No ASAP data for the whole dekad range" :
                      "Condition met in " + n + " of " + (ST.d1 - ST.d0 + 1) + " dekads" + (isMet ? "" : n > 0 ? " (below the minimum of " + ST.minDek + ")" : "")) +
                      "\n" + levelSummary(p.id, r.year) +
                      (yi < 0 ? "" : ya === null ? "\nNo complete millet and sorghum statistics" :
                        "\nMillet and sorghum yield " + DATA.yield.province[p.id].kg_ha[yi] + " kg/ha, " + pct(ya) + " from trend");
          s += '<rect class="hit" x="' + x + '" y="' + ry + '" width="' + step + '" height="' + rowH + '" fill="transparent" data-tip="' + esc(tip) + '"/>';
        });
      });
      top += rg.provs.length * rowH + gap;
    });
    s += "</svg>";
    el.innerHTML = s;
  }

  function levelSummary(pid, year) {
    const yi = DATA.meta.years.indexOf(year), d = DEC[pid];
    let hc = -1, hr = -1;
    for (let dk = ST.d0; dk <= ST.d1; dk++) {
      const i = yi * 36 + dk - 1;
      hc = Math.max(hc, CODE_LEVEL[d.crop[i]] === undefined ? -1 : CODE_LEVEL[d.crop[i]]);
      hr = Math.max(hr, CODE_LEVEL[d.range[i]] === undefined ? -1 : CODE_LEVEL[d.range[i]]);
    }
    const f = function (v) { return v > 0 ? "level " + v : v === 0 ? "no warning" : "off season or not assessed"; };
    return "Highest warning in the range: cropland " + f(hc) + ", rangeland " + f(hr);
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
        reached: r.valid ? (act.has(r.year) ? "Yes" : "No") : "No data",
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
    rows.forEach(function (t) {
      const cls = t.reached === "Yes" ? ' class="hit-row"' : "";
      const recs = t.emdat.concat(t.cerf);
      s += "<tr" + cls + "><td>" + t.year + (t.provisional ? "*" : "") + "</td>" +
           '<td class="num">' + (t.count === null ? "–" : t.count) + "</td>" +
           '<td class="nw">' + (t.reached === "Yes" ? '<span class="tag on">Yes</span> ' + dekadLabel(t.dekad) : t.reached === "No" ? '<span class="tag off">No</span>' : "No data") + "</td>" +
           '<td class="num">' + (t.yieldKg === null ? "–" : t.yieldKg) + "</td>" +
           '<td class="num">' + pct(t.yieldAnom) + "</td>" +
           '<td class="num">' + pct(t.prodAnom) + "</td>" +
           '<td class="num">' + (t.poor === null ? "–" : t.poor + (t.withYield < DATA.provinces.length ? " of " + t.withYield : "")) + "</td>" +
           '<td class="nw">' + (t.impact === "Yes" ? '<span class="tag imp">Yes</span>' : t.impact === "No" ? "No" : '<span class="muted">not yet known</span>') + "</td>" +
           '<td class="recs">' + recs.map(function (x) { return '<span data-tip="' + esc(x.label + "\nRecorded " + x.recorded + " (" + x.source + " " + x.id + ")") + '">' + esc(x.short) + "</span>"; }).join("<br>") + "</td>" +
           "<td>" + (t.framework ? "Yes" : "") + "</td></tr>";
    });
    $("tbody").innerHTML = s;
    $("th-poor").textContent = "Provinces with yield " + ST.yt + "%+ below trend";
  }

  function downloadCsv() {
    const sum = summarise(ROWS, ST.k);
    const rows = tableRows(sum);
    const head = ["season", "provisional", "provinces_meeting_condition", "threshold_reached", "threshold_reached_dekad",
                  "national_millet_sorghum_yield_kg_ha", "national_yield_pct_from_trend", "national_production_pct_from_trend",
                  "provinces_yield_" + ST.yt + "pct_below_trend", "provinces_with_yield_data", "impact_season", "emdat_drought", "cerf_drought", "framework_target_year"];
    const q = function (v) { v = v === null || v === undefined ? "" : String(v); return /[",;\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const lines = [head.join(",")];
    rows.forEach(function (t) {
      lines.push([t.year, t.provisional ? "yes" : "", t.count, t.reached, t.dekad ? t.dekad + " (" + dekadLabel(t.dekad) + ")" : "",
                  t.yieldKg, t.yieldAnom, t.prodAnom, t.poor, t.poor === null ? "" : t.withYield, t.impact,
                  t.emdat.map(function (x) { return x.label + " [" + x.id + ", " + x.recorded + "]"; }).join("; "),
                  t.cerf.map(function (x) { return x.label + " [" + x.id + ", " + x.recorded + "]"; }).join("; "),
                  t.framework ? "yes" : ""].map(q).join(","));
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
      tip.textContent = t.getAttribute("data-tip");
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
    renderCounts(sum);
    renderKStrip();
    renderYield(sum);
    renderGrid();
    renderTable(sum);
  }

  function init() {
    fetch("data.json").then(function (r) { return r.json(); }).then(function (data) {
      DATA = data;
      DEC = decode(data);
      ST = readState();
      buildControls();
      initTooltip();
      const last = new Date(data.meta.asap_last_dekad + "T00:00:00Z");
      const lastDk = last.getUTCMonth() * 3 + Math.min(Math.floor((last.getUTCDate() - 1) / 10), 2) + 1;
      const lastTxt = dekadLong(lastDk) + " " + last.getUTCFullYear();
      $("vintage").textContent = "ASAP archive to " + data.meta.asap_last_dekad + " (" + lastTxt + "); built " + data.meta.built + ".";
      $("last-dekad").textContent = last.getUTCDate() + " " + MONTHS[last.getUTCMonth()] + " " + last.getUTCFullYear() +
                                    " (" + lastTxt + ")";
      $("kslider").max = data.provinces.length; $("k").max = data.provinces.length;
      $("app").hidden = false; $("loading").hidden = true;
      update();
      let t;
      window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(function () { update(true); }, 150); });
    }).catch(function (err) {
      $("loading").textContent = "Could not load the data (" + err + ").";
    });
  }
  root.ASAPExplorer = api;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})(this);
