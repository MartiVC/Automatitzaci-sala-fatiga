/* ===========================================================================
   Dashboard de consulta remota — sala de fatiga
   App d'una sola pàgina amb pestanyes:
     · "Resum" — vista visual i senzilla per a cop d'ull (siluetes per bomba).
     · una pestanya per cada bomba — detall complet (KPIs, tendència, taules).
   Sense dependències (vanilla JS + SVG fet a mà). Només llegeix l'API REST
   del PC LAB; mai parla amb cap dispositiu de camp.
   =========================================================================== */
"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const SERIES_COLORS = ["#1f6feb", "#1f9d57", "#d97706", "#cc2f3a", "#7c3aed", "#0f8a8a", "#b8336a", "#4d5a6b"];

const $ = (id) => document.getElementById(id);

const els = {
  title: $("title"),
  connChips: $("conn-chips"),
  healthPill: $("health-pill"),
  healthDot: $("health-dot"),
  healthText: $("health-text"),
  autorefresh: $("autorefresh"),
  refreshBtn: $("refresh-btn"),
  tabs: $("tabs"),
  pageOverview: $("page-overview"),
  pageEquip: $("page-equip"),
  overviewTime: $("overview-time"),
  pumpGrid: $("pump-grid"),
  kpiStateCard: $("kpi-state-card"),
  kpiState: $("kpi-state"),
  kpiStateDetail: $("kpi-state-detail"),
  kpiFresh: $("kpi-fresh"),
  kpiFreshDetail: $("kpi-fresh-detail"),
  kpiEquips: $("kpi-equips"),
  kpiEquipsDetail: $("kpi-equips-detail"),
  kpiAlarms: $("kpi-alarms"),
  kpiAlarmsDetail: $("kpi-alarms-detail"),
  metricsEquip: $("metrics-equip"),
  metricsTime: $("metrics-time"),
  metricGrid: $("metric-grid"),
  rangeSeg: $("range-seg"),
  scaleSeg: $("scale-seg"),
  seriesPicker: $("series-picker"),
  chart: $("chart"),
  chartEmpty: $("chart-empty"),
  legend: $("legend"),
  eventsBody: $("events-body"),
  eventsCount: $("events-count"),
  latestBody: $("latest-body"),
  measurementsBody: $("measurements-body"),
  footText: $("foot-text"),
  tooltip: $("tooltip"),
};

const state = {
  catalog: new Map(),        // variable_id -> def
  chartVars: [],             // [variable_id, ...] (analògiques, per equip)
  health: null,
  latest: [],                // [{equip_id, variable_id, value, unit, quality, ts, raw, ...}]
  events: [],
  recentMeas: [],
  equips: [],                // ids d'equips coneguts
  selectedEquip: null,       // equip actiu a la pestanya d'equip
  activeTab: "overview",     // "overview" | "<equip_id>"
  rangeMin: 15,
  scaleMode: "real",         // "real" | "norm"
  selectedSeries: new Set(),
  seriesData: new Map(),     // variable_id -> {points: [[ts,val],...], unit, name, color}
  autoTimer: null,
};

// Configuració de les siluetes mostrades al resum. L'ordre marca la posició.
// `range` defineix com s'omple visualment la silueta. Per a tipus "alarm"/"comm"
// es mostra com a LED.
const OVERVIEW_TILES = [
  { var: "pressio",      type: "barometer", range: [0, 16],   icon: "Pressió" },
  { var: "freq_hz",      type: "tacho",     range: [0, 60],   icon: "Freqüència" },
  { var: "intensitat",   type: "current",   range: [0, 30],   icon: "Intensitat" },
  { var: "rpm_motor",    type: "tacho",     range: [0, 3000], icon: "Velocitat" },
  { var: "t_motor",      type: "thermo",    range: [0, 120],  icon: "Temp. motor" },
  { var: "t_rodament_de",type: "thermo",    range: [0, 100],  icon: "Temp. rod. DE" },
  { var: "t_rodament_nde",type:"thermo",    range: [0, 100],  icon: "Temp. rod. NDE" },
  { var: "t_fluid",      type: "thermo",    range: [0, 100],  icon: "Temp. fluid" },
  { var: "vib_de",       type: "bar",       range: [0, 10],   icon: "Vibració DE" },
  { var: "vib_nde",      type: "bar",       range: [0, 10],   icon: "Vibració NDE" },
  { var: "estat_alarma", type: "led-bad",   icon: "Alarma" },
  { var: "comm_485_nok", type: "led-warn",  icon: "RS-485" },
];

/* ── HTTP ──────────────────────────────────────────────────── */
async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

/* ── Format ────────────────────────────────────────────────── */
function fmtClock(ts) { return new Date(ts * 1000).toLocaleTimeString("ca-ES"); }
function fmtDateTime(ts) { return new Date(ts * 1000).toLocaleString("ca-ES"); }

function fmtAge(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 90) return `fa ${Math.round(seconds)} s`;
  if (seconds < 5400) return `fa ${Math.round(seconds / 60)} min`;
  if (seconds < 172800) return `fa ${Math.round(seconds / 3600)} h`;
  return `fa ${Math.round(seconds / 86400)} d`;
}

function fmtNumber(value, decimals = 2) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  const n = Number(value);
  const abs = Math.abs(n);
  const d = abs >= 1000 ? 0 : abs >= 100 ? 1 : decimals;
  return n.toLocaleString("ca-ES", { minimumFractionDigits: 0, maximumFractionDigits: d });
}

function fmtValue(def, value) {
  if (value === null || value === undefined) return "—";
  if (def && def.kind === "digital") return Number(value) ? "Sí" : "No";
  if (def && def.kind === "code") return String(Math.round(Number(value)));
  return fmtNumber(value);
}

/* ── Llindars ──────────────────────────────────────────────── */
function thresholdLevel(def, value) {
  if (!def || value === null || value === undefined || !Number.isFinite(Number(value))) return "ok";
  const v = Number(value);
  if (def.alarm_min !== null && v <= def.alarm_min) return "alarm";
  if (def.alarm_max !== null && v >= def.alarm_max) return "alarm";
  if (def.warn_min !== null && v <= def.warn_min) return "warn";
  if (def.warn_max !== null && v >= def.warn_max) return "warn";
  return "ok";
}

// Nivell "efectiu": llindars del catàleg + estats coneguts del variador.
function effectiveLevel(def, value) {
  if (!def || value === null || value === undefined) return "ok";
  const v = Number(value);
  if (def.id === "alarma_codi" && v > 0) return "alarm";
  if (def.id === "estat_alarma" && v >= 1) return "alarm";
  if (def.id === "comm_485_nok" && v >= 1) return "warn";
  return thresholdLevel(def, value);
}

/* ── Boot ──────────────────────────────────────────────────── */
async function boot() {
  bindControls();
  try {
    const cat = await api("/api/variables");
    state.catalog = new Map(cat.map((d) => [d.id, d]));
    state.chartVars = cat.filter((d) => d.kind === "analog" && d.per_equip).map((d) => d.id);
    // selecció inicial: les 3 variables de procés del variador (si hi són)
    const wanted = ["pressio", "freq_hz", "intensitat"];
    state.selectedSeries = new Set(wanted.filter((id) => state.catalog.has(id)) || []);
    if (state.selectedSeries.size === 0) state.chartVars.slice(0, 3).forEach((id) => state.selectedSeries.add(id));
    buildSeriesPicker();
  } catch (err) {
    setHealth("bad", `No s'ha pogut llegir el catàleg: ${err.message}`);
    return;
  }
  await refreshAll();
  scheduleAuto();
  window.addEventListener("resize", () => drawChart());
}

function bindControls() {
  els.refreshBtn.addEventListener("click", () => refreshAll());
  els.autorefresh.addEventListener("change", scheduleAuto);
  els.rangeSeg.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-min]");
    if (!btn) return;
    state.rangeMin = Number(btn.dataset.min);
    setSegActive(els.rangeSeg, btn);
    refreshChart();
  });
  els.scaleSeg.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-scale]");
    if (!btn) return;
    state.scaleMode = btn.dataset.scale;
    setSegActive(els.scaleSeg, btn);
    drawChart();
  });
}

function setSegActive(seg, btn) {
  seg.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
}

function scheduleAuto() {
  if (state.autoTimer) { clearInterval(state.autoTimer); state.autoTimer = null; }
  if (els.autorefresh.checked) state.autoTimer = setInterval(refreshAll, 5000);
}

/* ── Pestanyes ─────────────────────────────────────────────── */
function buildTabs() {
  els.tabs.innerHTML = "";
  // pestanya Resum sempre la primera
  els.tabs.append(makeTab("overview", "Resum"));
  // una pestanya per cada equip
  for (const id of state.equips) {
    const cfg = (state.health?.equips || []).find((e) => e.id === id);
    const label = cfg && cfg.descripcio ? `${id} · ${cfg.descripcio}` : id;
    els.tabs.append(makeTab(id, label));
  }
  applyActiveTab();
}

function makeTab(id, label) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "tab";
  btn.dataset.tab = id;
  btn.role = "tab";
  btn.textContent = label;
  btn.addEventListener("click", () => setActiveTab(id));
  return btn;
}

function setActiveTab(id) {
  // si demanen una pestanya d'equip que ja no existeix, caiem al resum
  if (id !== "overview" && !state.equips.includes(id)) id = "overview";
  state.activeTab = id;
  if (id !== "overview") state.selectedEquip = id;
  applyActiveTab();
  renderActivePage();
}

function applyActiveTab() {
  els.tabs.querySelectorAll(".tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === state.activeTab);
  });
  const isOverview = state.activeTab === "overview";
  els.pageOverview.hidden = !isOverview;
  els.pageEquip.hidden = isOverview;
}

function renderActivePage() {
  if (state.activeTab === "overview") {
    renderOverview();
  } else {
    renderMetrics();
    renderEvents();
    renderRawTables();
    refreshChart();
  }
}

/* ── Refresc global ────────────────────────────────────────── */
async function refreshAll() {
  let health, latest, events, recent;
  try {
    const since24h = Math.floor(Date.now() / 1000) - 86400;
    [health, latest, events, recent] = await Promise.all([
      api("/api/health"),
      api("/api/latest"),
      api(`/api/events?ts_from=${since24h}&limit=500&newest_first=true`),
      api("/api/measurements?limit=120&newest_first=true"),
    ]);
  } catch (err) {
    setHealth("bad", `Sense connexió amb el servidor: ${err.message}`);
    return;
  }

  state.health = health;
  state.latest = latest;
  state.events = events;
  state.recentMeas = recent;
  els.title.textContent = health.installation || "Sala de fatiga";
  els.footText.textContent = `PC LAB · ${health.installation || "sala de fatiga"} · històric: ${health.db_path || "?"}`;

  rebuildEquipList();
  buildTabs();
  renderConnChips();
  renderKpis();
  renderActivePage();
  setHealth("ok", `Connectat · dades ${fmtDateTime(health.ts)}`);
}

function setHealth(kind, text) {
  els.healthPill.className = `health-pill ${kind}`;
  els.healthText.textContent = text;
}

/* ── Llista d'equips ───────────────────────────────────────── */
function rebuildEquipList() {
  const fromCfg = (state.health?.equips || []).map((e) => e.id);
  const fromData = [...new Set(state.latest.filter((r) => r.equip_id !== "SISTEMA").map((r) => r.equip_id))];
  const ids = [...new Set([...fromCfg, ...fromData])];
  state.equips = ids;
  if (!state.selectedEquip || !ids.includes(state.selectedEquip)) state.selectedEquip = ids[0] || null;
  // si la pestanya activa apunta a un equip que ja no hi és, tornem al resum
  if (state.activeTab !== "overview" && !ids.includes(state.activeTab)) {
    state.activeTab = "overview";
  }
}

/* ── Chips de connexió (variables de sistema + mode d'històric) ─ */
function renderConnChips() {
  els.connChips.innerHTML = "";
  const defs = [
    ["comm_variador", "Variador"],
    ["comm_plc", "PLC"],
  ];
  for (const [varId, label] of defs) {
    const row = state.latest.find((r) => r.equip_id === "SISTEMA" && r.variable_id === varId);
    const chip = document.createElement("span");
    chip.className = "chip";
    let cls = "", title = "sense dada";
    if (row) {
      const fresh = (Date.now() / 1000 - row.ts) < 30;
      cls = !fresh ? "" : Number(row.value) ? "ok" : "bad";
      title = `${fresh ? "" : "(antic) "}${fmtAge(Date.now() / 1000 - row.ts)}`;
    }
    if (cls) chip.classList.add(cls);
    chip.title = title;
    chip.innerHTML = `<span class="dot"></span>${label}`;
    els.connChips.append(chip);
  }

  // Chip del mode d'històric (Oracle / SQLite local)
  const mode = state.health?.storage_mode;
  if (mode) {
    const chip = document.createElement("span");
    chip.className = "chip";
    let label = "Oracle", title = "";
    if (mode === "remote") {
      chip.classList.add("ok");
      title = "Llegint d'Oracle corporatiu";
    } else if (mode === "degraded") {
      chip.classList.add("warn");
      label = "Oracle (fallback)";
      title = state.health.storage_error
        ? `Oracle ha fallat: ${state.health.storage_error}. Servint del SQLite local.`
        : "Oracle no respon. Servint del SQLite local.";
    } else {
      // "local" — Oracle desactivat o no configurat
      label = "SQLite local";
      title = "Oracle desactivat. Servint només del buffer SQLite local.";
    }
    chip.title = title;
    chip.innerHTML = `<span class="dot"></span>${escapeHtml(label)}`;
    els.connChips.append(chip);
  }
}

/* ── KPIs ──────────────────────────────────────────────────── */
function renderKpis() {
  const now = state.health ? state.health.ts : Date.now() / 1000;
  const fieldRows = state.latest.filter((r) => r.equip_id !== "SISTEMA");

  // Estat global a partir de l'estat actual de les variables
  let worst = "ok";
  let detailBits = [];
  let badQ = 0, staleQ = 0, warnT = 0, alarmT = 0;
  for (const r of fieldRows) {
    if (r.quality === "bad") badQ++;
    else if (r.quality === "stale") staleQ++;
    const def = state.catalog.get(r.variable_id);
    const lvl = effectiveLevel(def, r.value);
    if (lvl === "alarm") alarmT++;
    else if (lvl === "warn") warnT++;
  }
  const newestField = fieldRows.reduce((m, r) => Math.max(m, r.ts), 0);
  const age = newestField ? now - newestField : Infinity;

  if (alarmT > 0 || badQ > 0) { worst = "bad"; }
  else if (warnT > 0 || staleQ > 0 || !newestField || age > 30) { worst = "warn"; }

  els.kpiStateCard.className = "kpi " + (worst === "bad" ? "is-bad" : worst === "warn" ? "is-warn" : "is-ok");
  els.kpiState.textContent = worst === "bad" ? "ALARMA" : worst === "warn" ? "REVISAR" : "OK";
  if (alarmT) detailBits.push(`${alarmT} var. en alarma`);
  if (warnT) detailBits.push(`${warnT} en avís`);
  if (badQ) detailBits.push(`${badQ} dolentes`);
  if (staleQ) detailBits.push(`${staleQ} antigues`);
  els.kpiStateDetail.textContent = detailBits.length ? detailBits.join(" · ") : (newestField ? "Tot dins de rang" : "Sense lectures");

  els.kpiFresh.textContent = newestField ? fmtAge(age) : "—";
  els.kpiFreshDetail.textContent = newestField ? `Última lectura ${fmtClock(newestField)}` : "Cap dada a l'històric";

  const withData = new Set(fieldRows.map((r) => r.equip_id)).size;
  const total = (state.health?.equips || []).length;
  els.kpiEquips.textContent = total ? `${withData} / ${total}` : `${withData}`;
  els.kpiEquipsDetail.textContent = total ? `${total} equip(s) configurat(s)` : "Equips detectats a les dades";

  const since24h = now - 86400;
  const alarms = state.events.filter((e) => e.ts >= since24h && e.type === "alarm_set");
  const warns = state.events.filter((e) => e.ts >= since24h && e.type === "warning_set");
  els.kpiAlarms.textContent = `${alarms.length}`;
  els.kpiAlarmsDetail.textContent = `${warns.length} avisos · ${state.events.length} esdev. en 24 h`;
}

/* ── Vista RESUM — graella de bombes amb siluetes ─────────── */
function renderOverview() {
  els.pumpGrid.innerHTML = "";
  let newestAll = 0;
  if (!state.equips.length) {
    els.pumpGrid.innerHTML = `<div class="pump-card empty">Sense equips configurats.</div>`;
    els.overviewTime.textContent = "";
    return;
  }
  for (const equipId of state.equips) {
    const card = buildPumpCard(equipId);
    if (card.newest > newestAll) newestAll = card.newest;
    els.pumpGrid.append(card.node);
  }
  els.overviewTime.textContent = newestAll ? `actualitzat ${fmtClock(newestAll)}` : "sense dades recents";
}

function buildPumpCard(equipId) {
  const byVar = new Map(state.latest.filter((r) => r.equip_id === equipId).map((r) => [r.variable_id, r]));
  let newest = 0;
  let worst = "ok";
  for (const r of byVar.values()) {
    if (r.ts > newest) newest = r.ts;
    if (r.quality === "bad") { if (worst !== "alarm") worst = "warn"; }
    const def = state.catalog.get(r.variable_id);
    const lvl = effectiveLevel(def, r.value);
    if (lvl === "alarm") worst = "alarm";
    else if (lvl === "warn" && worst === "ok") worst = "warn";
  }

  const card = document.createElement("article");
  card.className = `pump-card lvl-${worst}`;
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-label", `Veure detall de ${equipId}`);

  const cfg = (state.health?.equips || []).find((e) => e.id === equipId);
  const subtitle = cfg && cfg.descripcio ? cfg.descripcio : "bomba";
  const stateLabel = worst === "alarm" ? "ALARMA" : worst === "warn" ? "REVISAR" : "OK";

  const tilesHtml = OVERVIEW_TILES
    .map((t) => buildTileHtml(t, byVar.get(t.var)))
    .filter(Boolean)
    .join("");

  card.innerHTML = `
    <header class="pump-head">
      <div>
        <h3 class="pump-name">${escapeHtml(equipId)}</h3>
        <span class="pump-sub">${escapeHtml(subtitle)}</span>
      </div>
      <span class="pump-state">${stateLabel}</span>
    </header>
    <div class="tile-grid">${tilesHtml}</div>
    <footer class="pump-foot">${newest ? `Actualitzat ${fmtClock(newest)}` : "sense lectures"}</footer>`;

  const go = () => setActiveTab(equipId);
  card.addEventListener("click", go);
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
  });
  return { node: card, newest };
}

function buildTileHtml(tile, reading) {
  const def = state.catalog.get(tile.var);
  if (!def) return "";
  const value = reading ? Number(reading.value) : null;
  const hasValue = reading && reading.value !== null && Number.isFinite(value);
  const lvl = effectiveLevel(def, reading?.value);
  const qBad = reading && (reading.quality === "bad" || reading.quality === "stale");

  let svg = "";
  let valueTxt = "—";

  if (tile.type === "thermo") {
    const fill = hasValue ? clamp01((value - tile.range[0]) / (tile.range[1] - tile.range[0])) : 0;
    svg = thermoSVG(fill, lvl, hasValue);
    valueTxt = hasValue ? `${fmtNumber(value)} ${def.unit || ""}` : "—";
  } else if (tile.type === "barometer") {
    const fill = hasValue ? clamp01((value - tile.range[0]) / (tile.range[1] - tile.range[0])) : 0;
    svg = gaugeSVG(fill, lvl, hasValue);
    valueTxt = hasValue ? `${fmtNumber(value)} ${def.unit || ""}` : "—";
  } else if (tile.type === "tacho") {
    const fill = hasValue ? clamp01((value - tile.range[0]) / (tile.range[1] - tile.range[0])) : 0;
    svg = gaugeSVG(fill, lvl, hasValue);
    valueTxt = hasValue ? `${fmtNumber(value)} ${def.unit || ""}` : "—";
  } else if (tile.type === "current") {
    const fill = hasValue ? clamp01((value - tile.range[0]) / (tile.range[1] - tile.range[0])) : 0;
    svg = boltSVG(fill, lvl, hasValue);
    valueTxt = hasValue ? `${fmtNumber(value)} ${def.unit || ""}` : "—";
  } else if (tile.type === "bar") {
    const fill = hasValue ? clamp01((value - tile.range[0]) / (tile.range[1] - tile.range[0])) : 0;
    svg = barSVG(fill, lvl, hasValue);
    valueTxt = hasValue ? `${fmtNumber(value)} ${def.unit || ""}` : "—";
  } else if (tile.type === "led-bad" || tile.type === "led-warn") {
    const on = hasValue && value >= 1;
    const ledColor = on ? (tile.type === "led-bad" ? "alarm" : "warn") : "ok";
    svg = ledSVG(on, ledColor, hasValue);
    valueTxt = !hasValue ? "—" : on ? (tile.type === "led-bad" ? "Alarma" : "Sense bus") : "OK";
  }

  const cls = `tile lvl-${qBad ? "stale" : lvl}` + (hasValue ? "" : " empty");
  return `
    <div class="${cls}" title="${escapeHtml(def.name)}">
      <div class="tile-icon">${svg}</div>
      <div class="tile-name">${escapeHtml(tile.icon)}</div>
      <div class="tile-value">${escapeHtml(valueTxt)}</div>
    </div>`;
}

function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }

/* ── Siluetes SVG ──────────────────────────────────────────── */
// Termòmetre clàssic: tub + bulb. La columna de líquid s'omple de baix a dalt
// en funció de "fill" (0..1). Colorit segons el nivell (ok/warn/alarm).
function thermoSVG(fill, lvl, hasValue) {
  const colors = lvlColor(lvl);
  const top = 12;
  const bottom = 56;
  const colHeight = bottom - top;
  const liquidH = colHeight * fill;
  const liquidY = bottom - liquidH;
  const lvlClass = hasValue ? `s-${lvl}` : "s-empty";
  return `
  <svg viewBox="0 0 50 80" xmlns="http://www.w3.org/2000/svg" class="silhouette ${lvlClass}">
    <defs><clipPath id="thClip"><rect x="22" y="${top}" width="6" height="${colHeight}" rx="3"/></clipPath></defs>
    <rect x="22" y="${top}" width="6" height="${colHeight}" rx="3" fill="#e8ecf3" stroke="${colors.line}" stroke-width="1.2"/>
    <rect x="22" y="${liquidY}" width="6" height="${liquidH}" fill="${colors.fill}" clip-path="url(#thClip)"/>
    <circle cx="25" cy="62" r="9" fill="${colors.fill}" stroke="${colors.line}" stroke-width="1.5"/>
    <circle cx="25" cy="62" r="4" fill="${colors.deep}" />
    <line x1="20" y1="20" x2="22" y2="20" stroke="${colors.line}" stroke-width="1"/>
    <line x1="20" y1="32" x2="22" y2="32" stroke="${colors.line}" stroke-width="1"/>
    <line x1="20" y1="44" x2="22" y2="44" stroke="${colors.line}" stroke-width="1"/>
  </svg>`;
}

// Indicador analògic semicircular ("baròmetre" / "tacòmetre"): arc gris al
// fons, arc acolorit segons llindar, agulla apuntant a l'angle proporcional.
function gaugeSVG(fill, lvl, hasValue) {
  const colors = lvlColor(lvl);
  const cx = 40, cy = 44, r = 28;
  const startA = Math.PI;        // 180°
  const endA = 2 * Math.PI;      // 360°
  const pointerA = startA + (endA - startA) * fill;
  const px = cx + r * 0.78 * Math.cos(pointerA);
  const py = cy + r * 0.78 * Math.sin(pointerA);
  const bgArc = arcPath(cx, cy, r, startA, endA);
  const fgArc = arcPath(cx, cy, r, startA, pointerA);
  const lvlClass = hasValue ? `s-${lvl}` : "s-empty";
  return `
  <svg viewBox="0 0 80 60" xmlns="http://www.w3.org/2000/svg" class="silhouette ${lvlClass}">
    <path d="${bgArc}" stroke="#dde2ea" stroke-width="6" fill="none" stroke-linecap="round"/>
    ${hasValue ? `<path d="${fgArc}" stroke="${colors.fill}" stroke-width="6" fill="none" stroke-linecap="round"/>` : ""}
    <line x1="${cx}" y1="${cy}" x2="${px.toFixed(2)}" y2="${py.toFixed(2)}" stroke="${colors.deep}" stroke-width="2.2" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="3.2" fill="${colors.deep}"/>
  </svg>`;
}

// Llamp d'intensitat: silueta clàssica de "bolt" que es plena des de baix.
function boltSVG(fill, lvl, hasValue) {
  const colors = lvlColor(lvl);
  const lvlClass = hasValue ? `s-${lvl}` : "s-empty";
  // bbox del llamp aprox: y 8..72
  const y0 = 8, y1 = 72;
  const splitY = y1 - (y1 - y0) * fill;
  return `
  <svg viewBox="0 0 50 80" xmlns="http://www.w3.org/2000/svg" class="silhouette ${lvlClass}">
    <defs>
      <clipPath id="boltClip"><path d="M28 8 L12 44 L22 44 L18 72 L40 36 L30 36 Z"/></clipPath>
    </defs>
    <path d="M28 8 L12 44 L22 44 L18 72 L40 36 L30 36 Z" fill="#e8ecf3" stroke="${colors.line}" stroke-width="1.4" stroke-linejoin="round"/>
    <rect x="0" y="${splitY}" width="50" height="${y1 - splitY}" fill="${colors.fill}" clip-path="url(#boltClip)"/>
  </svg>`;
}

// Barra vertical (vibració): tub que s'omple amb el valor i marca el llindar.
function barSVG(fill, lvl, hasValue) {
  const colors = lvlColor(lvl);
  const lvlClass = hasValue ? `s-${lvl}` : "s-empty";
  const x = 18, w = 14, top = 10, bot = 70;
  const h = bot - top;
  const fy = bot - h * fill;
  return `
  <svg viewBox="0 0 50 80" xmlns="http://www.w3.org/2000/svg" class="silhouette ${lvlClass}">
    <rect x="${x}" y="${top}" width="${w}" height="${h}" rx="3" fill="#e8ecf3" stroke="${colors.line}" stroke-width="1.2"/>
    ${hasValue ? `<rect x="${x}" y="${fy}" width="${w}" height="${bot - fy}" rx="3" fill="${colors.fill}"/>` : ""}
    <line x1="${x - 3}" y1="${top + h * 0.3}" x2="${x}" y2="${top + h * 0.3}" stroke="#c77700" stroke-width="1.4"/>
    <line x1="${x - 3}" y1="${top + h * 0.15}" x2="${x}" y2="${top + h * 0.15}" stroke="#cc2f3a" stroke-width="1.4"/>
  </svg>`;
}

// LED rodó: estat ON/OFF amb halo segons severitat.
function ledSVG(on, color, hasValue) {
  const palette = lvlColor(color);
  const fill = on ? palette.fill : "#e8ecf3";
  const halo = on ? palette.fill : "#cdd3dc";
  const lvlClass = hasValue ? `s-${color}` : "s-empty";
  return `
  <svg viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg" class="silhouette ${lvlClass}">
    ${on ? `<circle cx="30" cy="30" r="22" fill="${halo}" opacity="0.18"/>` : ""}
    <circle cx="30" cy="30" r="14" fill="${fill}" stroke="${palette.line}" stroke-width="1.4"/>
    <circle cx="26" cy="26" r="3.5" fill="#fff" opacity="${on ? 0.6 : 0.3}"/>
  </svg>`;
}

function lvlColor(lvl) {
  switch (lvl) {
    case "alarm": return { fill: "#cc2f3a", deep: "#7a1e25", line: "#cc2f3a" };
    case "warn":  return { fill: "#d97706", deep: "#7a4302", line: "#d97706" };
    case "stale": return { fill: "#8a93a3", deep: "#4d5a6b", line: "#8a93a3" };
    case "ok":
    default:      return { fill: "#1f9d57", deep: "#0e5a30", line: "#1f9d57" };
  }
}

function arcPath(cx, cy, r, a0, a1) {
  const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
  const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
  const large = Math.abs(a1 - a0) > Math.PI ? 1 : 0;
  const sweep = a1 > a0 ? 1 : 0;
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} ${sweep} ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/* ── Targetes de variable de l'equip seleccionat ───────────── */
function renderMetrics() {
  const equip = state.selectedEquip;
  els.metricsEquip.textContent = equip || "—";
  els.metricGrid.innerHTML = "";
  if (!equip) {
    els.metricsTime.textContent = "";
    const empty = document.createElement("div");
    empty.className = "metric empty";
    empty.innerHTML = `<div class="metric-name">Sense equip</div><div class="metric-value">—</div>`;
    els.metricGrid.append(empty);
    return;
  }

  const byVar = new Map(state.latest.filter((r) => r.equip_id === equip).map((r) => [r.variable_id, r]));
  let newest = 0;
  for (const def of state.catalog.values()) {
    if (!def.per_equip) continue;
    const r = byVar.get(def.id);
    if (r && r.ts > newest) newest = r.ts;
    els.metricGrid.append(metricCard(def, r));
  }
  els.metricsTime.textContent = newest ? `actualitzat ${fmtClock(newest)}` : "sense dades recents";
}

function metricCard(def, r) {
  const card = document.createElement("article");
  card.className = "metric";
  const value = r ? r.value : null;
  const quality = r ? r.quality : null;
  const lvl = effectiveLevel(def, value);

  if (!r) card.classList.add("empty");
  if (quality === "bad") card.classList.add("q-bad");
  else if (quality === "stale") card.classList.add("q-stale");
  else if (lvl === "alarm") card.classList.add("lvl-alarm");
  else if (lvl === "warn" || quality === "uncertain") card.classList.add("lvl-warn");
  else if (quality === "good") card.classList.add("q-good");

  let tag = "";
  if (lvl === "alarm") tag = `<span class="metric-tag alarm">alarma</span>`;
  else if (lvl === "warn") tag = `<span class="metric-tag warn">avís</span>`;
  else if (quality === "stale") tag = `<span class="metric-tag stale">antiga</span>`;
  else if (quality === "bad") tag = `<span class="metric-tag alarm">dolenta</span>`;
  else if (quality === "uncertain") tag = `<span class="metric-tag warn">incerta</span>`;

  const unit = def.unit && def.kind === "analog" ? `<span class="unit">${escapeHtml(def.unit)}</span>` : "";
  let foot = "";
  if (r) {
    if (def.kind === "code" && r.note) foot = escapeHtml(r.note);
    else if (def.id === "estat_alarma" && lvl === "alarm") foot = "equip en alarma";
    else if (def.id === "comm_485_nok" && lvl === "warn") foot = "sense RS-485 intern";
    else if (lvl !== "ok") foot = limitsText(def);
    else foot = fmtAge(Date.now() / 1000 - r.ts);
  } else foot = "sense lectura";

  card.innerHTML = `
    <div class="metric-name"><span>${escapeHtml(def.name)}</span>${tag}</div>
    <div class="metric-value">${escapeHtml(fmtValue(def, value))}${unit}</div>
    <div class="metric-foot">${foot}</div>`;
  return card;
}

function limitsText(def) {
  const parts = [];
  if (def.alarm_min !== null) parts.push(`mín ${fmtNumber(def.alarm_min)}`);
  if (def.warn_max !== null && def.alarm_max !== null) parts.push(`avís ${fmtNumber(def.warn_max)} · alarma ${fmtNumber(def.alarm_max)}`);
  else if (def.alarm_max !== null) parts.push(`alarma ${fmtNumber(def.alarm_max)}`);
  else if (def.warn_max !== null) parts.push(`avís ${fmtNumber(def.warn_max)}`);
  return parts.join(" · ") || "fora de rang";
}

/* ── Selector de sèries del gràfic ─────────────────────────── */
function buildSeriesPicker() {
  els.seriesPicker.innerHTML = "";
  const groups = new Map(); // origin -> [ids]
  state.chartVars.forEach((id) => {
    const def = state.catalog.get(id);
    const g = def.origin || "altres";
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(id);
  });
  const labels = { variador: "Variador", plc: "PLC / sensors", sistema: "Sistema", altres: "Altres" };
  for (const [g, ids] of groups) {
    const lab = document.createElement("span");
    lab.className = "group-label";
    lab.textContent = labels[g] || g;
    els.seriesPicker.append(lab);
    for (const id of ids) {
      const def = state.catalog.get(id);
      const color = colorFor(id);
      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "pill" + (state.selectedSeries.has(id) ? " on" : "");
      pill.style.setProperty("--swatch", color);
      pill.dataset.var = id;
      pill.innerHTML = `<span class="swatch"></span>${escapeHtml(def.name)}`;
      pill.addEventListener("click", () => {
        if (state.selectedSeries.has(id)) state.selectedSeries.delete(id);
        else state.selectedSeries.add(id);
        pill.classList.toggle("on");
        refreshChart();
      });
      els.seriesPicker.append(pill);
    }
  }
}

function colorFor(variableId) {
  const idx = state.chartVars.indexOf(variableId);
  return SERIES_COLORS[(idx < 0 ? 0 : idx) % SERIES_COLORS.length];
}

/* ── Dades del gràfic ──────────────────────────────────────── */
async function refreshChart() {
  const equip = state.selectedEquip;
  state.seriesData = new Map();
  if (equip && state.selectedSeries.size) {
    const tsFrom = Math.floor(Date.now() / 1000) - state.rangeMin * 60;
    const ids = [...state.selectedSeries];
    const results = await Promise.allSettled(
      ids.map((id) =>
        api(`/api/measurements?equip_id=${encodeURIComponent(equip)}&variable_id=${encodeURIComponent(id)}&ts_from=${tsFrom}&newest_first=true&limit=5000`)
      )
    );
    results.forEach((res, i) => {
      if (res.status !== "fulfilled") return;
      const id = ids[i];
      const def = state.catalog.get(id);
      const points = res.value
        .filter((row) => row.value !== null && Number.isFinite(Number(row.value)))
        .map((row) => [row.ts, Number(row.value)])
        .sort((a, b) => a[0] - b[0]);
      state.seriesData.set(id, { points, unit: def.unit || "", name: def.name, color: colorFor(id) });
    });
  }
  drawChart();
}

/* ── Dibuix del gràfic SVG ─────────────────────────────────── */
function niceScale(min, max, count = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 1, ticks: [0, 1] };
  if (min === max) { min -= 1; max += 1; }
  const range = max - min;
  const rawStep = range / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const niceMin = Math.floor(min / step) * step;
  const niceMax = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = niceMin; v <= niceMax + step * 1e-9; v += step) ticks.push(Number(v.toFixed(10)));
  return { min: niceMin, max: niceMax, ticks };
}

function el(name, attrs, children) {
  const node = document.createElementNS(SVG_NS, name);
  if (attrs) for (const k in attrs) node.setAttribute(k, attrs[k]);
  if (children) for (const c of children) node.append(c);
  return node;
}

function drawChart() {
  const host = els.chart;
  host.innerHTML = "";
  els.legend.innerHTML = "";

  const series = [...state.seriesData.entries()]
    .filter(([, s]) => s.points.length > 0)
    .map(([id, s]) => ({ id, ...s }));

  const W = Math.max(320, host.clientWidth || 600);
  const H = Math.max(220, host.clientHeight || 320);
  const m = { l: 52, r: 16, t: 14, b: 26 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;

  const hasData = series.length > 0;
  els.chartEmpty.hidden = hasData;
  if (!hasData) { renderLegend(series, null); return; }

  const now = Date.now() / 1000;
  const t0 = now - state.rangeMin * 60;
  const t1 = now;

  // domini Y
  const norm = state.scaleMode === "norm";
  let yScale;
  let perSeriesRange = new Map();
  if (norm) {
    yScale = { min: 0, max: 1, ticks: [0, 0.25, 0.5, 0.75, 1] };
    for (const s of series) {
      const vals = s.points.map((p) => p[1]);
      const lo = Math.min(...vals), hi = Math.max(...vals);
      perSeriesRange.set(s.id, [lo, hi === lo ? lo + 1 : hi]);
    }
  } else {
    const vals = series.flatMap((s) => s.points.map((p) => p[1]));
    yScale = niceScale(Math.min(...vals), Math.max(...vals), 5);
  }

  const x = (ts) => m.l + ((ts - t0) / (t1 - t0)) * pw;
  const yReal = (v) => m.t + (1 - (v - yScale.min) / (yScale.max - yScale.min)) * ph;
  const yNorm = (v, id) => { const [lo, hi] = perSeriesRange.get(id); return m.t + (1 - (v - lo) / (hi - lo)) * ph; };
  const yOf = (v, id) => (norm ? yNorm(v, id) : yReal(v));

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });

  // graella horitzontal + etiquetes Y
  for (const tick of yScale.ticks) {
    const yy = yReal(tick);
    svg.append(el("line", { class: "grid-line" + (tick === 0 && !norm ? " zero" : ""), x1: m.l, x2: W - m.r, y1: yy, y2: yy }));
    const label = norm ? `${Math.round(tick * 100)}%` : fmtNumber(tick);
    svg.append(el("text", { class: "tick-label", x: m.l - 8, y: yy + 3.5, "text-anchor": "end" }, [document.createTextNode(label)]));
  }
  // eixos
  svg.append(el("line", { class: "axis-line", x1: m.l, x2: m.l, y1: m.t, y2: m.t + ph }));
  svg.append(el("line", { class: "axis-line", x1: m.l, x2: W - m.r, y1: m.t + ph, y2: m.t + ph }));

  // etiquetes X (temps)
  const xticks = 5;
  const spanH = (t1 - t0) / 3600;
  for (let i = 0; i <= xticks; i++) {
    const ts = t0 + (i / xticks) * (t1 - t0);
    const xx = x(ts);
    if (i > 0 && i < xticks) svg.append(el("line", { class: "grid-line", x1: xx, x2: xx, y1: m.t, y2: m.t + ph }));
    const d = new Date(ts * 1000);
    const txt = spanH > 12
      ? d.toLocaleString("ca-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
      : d.toLocaleTimeString("ca-ES", { hour: "2-digit", minute: "2-digit", second: spanH <= 0.5 ? "2-digit" : undefined });
    const anchor = i === 0 ? "start" : i === xticks ? "end" : "middle";
    svg.append(el("text", { class: "tick-label", x: xx, y: m.t + ph + 16, "text-anchor": anchor }, [document.createTextNode(txt)]));
  }

  // camins de sèrie
  for (const s of series) {
    let dpath = "";
    s.points.forEach((p, i) => {
      const px = x(p[0]).toFixed(1);
      const py = yOf(p[1], s.id).toFixed(1);
      dpath += (i === 0 ? "M" : "L") + px + " " + py + " ";
    });
    svg.append(el("path", { class: "series-path", d: dpath.trim(), stroke: s.color }));
  }

  // capa d'interacció (hover)
  const hoverLine = el("line", { class: "hover-line", y1: m.t, y2: m.t + ph, x1: 0, x2: 0, visibility: "hidden" });
  const hoverDots = el("g", { visibility: "hidden" });
  svg.append(hoverLine, hoverDots);
  const overlay = el("rect", { class: "chart-overlay-rect", x: m.l, y: m.t, width: pw, height: ph });
  svg.append(overlay);

  overlay.addEventListener("mousemove", (ev) => {
    const rect = host.getBoundingClientRect();
    const px = (ev.clientX - rect.left) / rect.width * W;
    const tsHover = t0 + ((px - m.l) / pw) * (t1 - t0);
    hoverLine.setAttribute("x1", px);
    hoverLine.setAttribute("x2", px);
    hoverLine.setAttribute("visibility", "visible");
    hoverDots.replaceChildren();
    const ttRows = [];
    let lastTs = null;
    for (const s of series) {
      const pt = nearestPoint(s.points, tsHover);
      if (!pt) continue;
      lastTs = lastTs === null ? pt[0] : (Math.abs(pt[0] - tsHover) < Math.abs(lastTs - tsHover) ? pt[0] : lastTs);
      const cy = yOf(pt[1], s.id);
      hoverDots.append(el("circle", { class: "hover-dot", cx: x(pt[0]), cy, r: 4, fill: s.color }));
      ttRows.push({ color: s.color, name: s.name, text: `${fmtNumber(pt[1])} ${s.unit}`.trim() });
    }
    hoverDots.setAttribute("visibility", "visible");
    showTooltip(ev.clientX, ev.clientY, lastTs ?? tsHover, ttRows);
  });
  overlay.addEventListener("mouseleave", () => {
    hoverLine.setAttribute("visibility", "hidden");
    hoverDots.setAttribute("visibility", "hidden");
    hideTooltip();
  });

  host.append(svg);
  renderLegend(series, perSeriesRange.size ? perSeriesRange : null);
}

function nearestPoint(points, ts) {
  if (!points.length) return null;
  // cerca binària
  let lo = 0, hi = points.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid][0] < ts) lo = mid + 1; else hi = mid;
  }
  const a = points[Math.max(0, lo - 1)];
  const b = points[lo];
  return Math.abs(a[0] - ts) <= Math.abs(b[0] - ts) ? a : b;
}

function renderLegend(series, ranges) {
  els.legend.innerHTML = "";
  if (!series.length) {
    const span = document.createElement("span");
    span.className = "muted";
    span.textContent = state.selectedSeries.size ? "Cap mostra de les sèries seleccionades en aquest interval." : "Selecciona alguna variable per veure la tendència.";
    els.legend.append(span);
    return;
  }
  for (const s of series) {
    const last = s.points[s.points.length - 1];
    const item = document.createElement("span");
    item.className = "legend-item";
    let rangeTxt = "";
    if (ranges && ranges.has(s.id)) { const [lo, hi] = ranges.get(s.id); rangeTxt = ` <span class="lg-range">[${fmtNumber(lo)}…${fmtNumber(hi)} ${escapeHtml(s.unit)}]</span>`; }
    item.innerHTML = `<span class="swatch" style="background:${s.color}"></span>` +
      `<span class="lg-name">${escapeHtml(s.name)}</span>` +
      `<span class="lg-val">${fmtNumber(last[1])} ${escapeHtml(s.unit)}</span>${rangeTxt}`;
    els.legend.append(item);
  }
}

/* ── Tooltip ───────────────────────────────────────────────── */
function showTooltip(clientX, clientY, ts, rows) {
  if (!rows.length) { hideTooltip(); return; }
  const html = `<div class="tt-time">${fmtDateTime(ts)}</div>` +
    rows.map((r) => `<div class="tt-row"><span class="swatch" style="background:${r.color}"></span>${escapeHtml(r.name)}<span class="tt-val">${escapeHtml(r.text)}</span></div>`).join("");
  els.tooltip.innerHTML = html;
  els.tooltip.hidden = false;
  const pad = 14;
  const rect = els.tooltip.getBoundingClientRect();
  let left = clientX + pad;
  let top = clientY + pad;
  if (left + rect.width > window.innerWidth - 8) left = clientX - rect.width - pad;
  if (top + rect.height > window.innerHeight - 8) top = clientY - rect.height - pad;
  els.tooltip.style.left = `${Math.max(8, left)}px`;
  els.tooltip.style.top = `${Math.max(8, top)}px`;
}
function hideTooltip() { els.tooltip.hidden = true; }

/* ── Taula d'esdeveniments ─────────────────────────────────── */
function renderEvents() {
  // a la pestanya d'equip, filtrem només esdeveniments d'aquell equip (o de SISTEMA)
  const equip = state.selectedEquip;
  const filtered = equip
    ? state.events.filter((e) => e.equip_id === equip || e.equip_id === "SISTEMA")
    : state.events;
  const rows = filtered.slice(0, 50);
  els.eventsCount.textContent = `${filtered.length} en les últimes 24 h`;
  els.eventsBody.innerHTML = "";
  if (!rows.length) {
    els.eventsBody.innerHTML = `<tr class="empty-row"><td colspan="6">Cap esdeveniment registrat en les últimes 24 h.</td></tr>`;
    return;
  }
  for (const e of rows) {
    const tr = document.createElement("tr");
    const sev = (e.severity_name || "").toLowerCase();
    tr.innerHTML = `
      <td>${escapeHtml(fmtDateTime(e.ts))}</td>
      <td>${escapeHtml(e.equip_id)}</td>
      <td><span class="tag ${sev}">${escapeHtml(e.severity_name || "—")}</span></td>
      <td>${escapeHtml(e.type)}</td>
      <td>${escapeHtml(e.code)}</td>
      <td class="msg">${escapeHtml(e.message)}</td>`;
    els.eventsBody.append(tr);
  }
}

/* ── Taules de detall ──────────────────────────────────────── */
function renderRawTables() {
  // últimes lectures de l'equip seleccionat
  els.latestBody.innerHTML = "";
  const equip = state.selectedEquip;
  const rows = state.latest.filter((r) => r.equip_id === equip).sort(byCatalog);
  if (!rows.length) {
    els.latestBody.innerHTML = `<tr class="empty-row"><td colspan="7">Sense lectures per a l'equip seleccionat.</td></tr>`;
  } else {
    for (const r of rows) {
      const def = state.catalog.get(r.variable_id);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(def ? def.name : r.variable_id)}</td>
        <td>${escapeHtml(r.origin)}</td>
        <td class="num">${escapeHtml(fmtValue(def, r.value))} ${escapeHtml(r.unit || "")}</td>
        <td><span class="tag ${escapeHtml(r.quality)}">${escapeHtml(r.quality)}</span></td>
        <td class="num">${r.raw ?? ""}</td>
        <td>${escapeHtml(fmtClock(r.ts))}</td>
        <td class="msg">${escapeHtml(r.note || "")}</td>`;
      els.latestBody.append(tr);
    }
  }

  // històric recent (mesclat) — a la pestanya d'equip, filtrem només aquell equip
  els.measurementsBody.innerHTML = "";
  const recent = equip
    ? state.recentMeas.filter((r) => r.equip_id === equip || r.equip_id === "SISTEMA")
    : state.recentMeas;
  if (!recent.length) {
    els.measurementsBody.innerHTML = `<tr class="empty-row"><td colspan="6">Sense mesures recents a l'històric.</td></tr>`;
    return;
  }
  for (const r of recent) {
    const def = state.catalog.get(r.variable_id);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(fmtDateTime(r.ts))}</td>
      <td>${escapeHtml(r.equip_id)}</td>
      <td>${escapeHtml(def ? def.name : r.variable_id)}</td>
      <td>${escapeHtml(r.origin)}</td>
      <td class="num">${escapeHtml(fmtValue(def, r.value))} ${escapeHtml(r.unit || "")}</td>
      <td><span class="tag ${escapeHtml(r.quality)}">${escapeHtml(r.quality)}</span></td>`;
    els.measurementsBody.append(tr);
  }
}

function byCatalog(a, b) {
  const order = [...state.catalog.keys()];
  return order.indexOf(a.variable_id) - order.indexOf(b.variable_id);
}

/* ── Utils ─────────────────────────────────────────────────── */
function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

boot();
