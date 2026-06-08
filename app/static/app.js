"use strict";

const STATE = { station: null, years: [] };

const api = (p) => fetch(p).then((r) => {
  if (!r.ok) throw new Error(p + " -> " + r.status);
  return r.json();
});

// Aggiunge la stazione selezionata alla query string.
function apiUrl(path) {
  if (!STATE.station) return path;
  return path + (path.includes("?") ? "&" : "?") + "station=" + encodeURIComponent(STATE.station);
}
const apiS = (p) => api(apiUrl(p));

const charts = {};
const YEAR_COLORS = ["#38bdf8", "#f97316", "#a78bfa", "#34d399", "#f43f5e", "#fbbf24"];

// Plugin: linea verticale tratteggiata sull'istante della foto nei grafici di dettaglio
const photoMarker = {
  id: "photoMarker",
  afterDatasetsDraw(chart, _args, opts) {
    const idx = opts && opts.index;
    if (idx == null || idx < 0) return;
    const x = chart.scales.x.getPixelForValue(idx);
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = "#fbbf24";
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#fbbf24";
    ctx.font = "12px sans-serif";
    ctx.fillText("📷", x - 8, top + 12);
    ctx.restore();
  },
};

function makeChart(id, config) {
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id);
  config.options = Object.assign({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { labels: { color: "#e2e8f0" } } },
    scales: {
      x: { ticks: { color: "#94a3b8", maxTicksLimit: 14 }, grid: { color: "#1e293b" } },
      y: { ticks: { color: "#94a3b8" }, grid: { color: "#1e293b" } },
    },
  }, config.options || {});
  charts[id] = new Chart(ctx, config);
  return charts[id];
}

// ---------- Tabs ----------
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

const fmt = (v, u = "") => (v == null ? "–" : Math.round(v * 10) / 10 + u);

// --- Formattazione date in italiano (giorno/mese/anno) ---
// "2025-02-10" o "2025-02-10T12:15:00" -> "10/02/2025"
function dmy(iso) {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  return d ? `${d}/${m}/${y}` : String(iso);
}
// ISO -> "10/02" (giorno/mese, senza anno)
function dm(iso) {
  if (!iso) return "";
  const [, m, d] = String(iso).slice(0, 10).split("-");
  return d ? `${d}/${m}` : String(iso);
}
// chiave confronto "MM-DD" -> "10/02"
function mdToDm(md) {
  if (!md) return "";
  const [m, d] = String(md).split("-");
  return d ? `${d}/${m}` : md;
}
// "2026-06-05T12:15:00" -> "05/06/2026 12:15"
function dmyTime(iso) {
  if (!iso) return "";
  const s = String(iso).replace("T", " ");
  const [datePart, timePart = ""] = s.split(" ");
  return `${dmy(datePart)} ${timePart.slice(0, 5)}`.trim();
}
// "2026-06-05T12:15:00" -> "05/06 12:15"
function dmTime(iso) {
  if (!iso) return "";
  const s = String(iso).replace("T", " ");
  const [datePart, timePart = ""] = s.split(" ");
  return `${dm(datePart)} ${timePart.slice(0, 5)}`.trim();
}
const title = (text) => ({ display: true, text, color: "#e2e8f0", font: { size: 14 } });
function line(label, data, color) {
  return { label, data, borderColor: color, backgroundColor: color,
           borderWidth: 2, pointRadius: 0, tension: 0.25 };
}

// ---------- Header: stazione + condizioni attuali ----------
async function loadStation() {
  try {
    const s = await apiS("/api/station");
    const parts = [s.station_name || s.station_code, s.area, s.region_name].filter(Boolean);
    document.getElementById("station-info").textContent =
      parts.join(" · ") + (s.altitude != null ? ` · ${s.altitude} m s.l.m.` : "");
  } catch (e) { /* ignora */ }
}

async function loadLatest() {
  try {
    const d = await apiS("/api/latest");
    const cards = [
      ["Temperatura", fmt(d.temperature, "°C")],
      ["Umidità", fmt(d.rh, "%")],
      ["Vento", fmt(d.wind_speed, " km/h")],
      ["Raffica", fmt(d.wind_gust, " km/h")],
      ["Pioggia oggi", fmt(d.daily_rain, " mm")],
      ["Pressione", fmt(d.smlp, " hPa")],
    ];
    document.getElementById("latest-cards").innerHTML = cards.map(([l, v]) =>
      `<div class="card"><div class="val">${v}</div><div class="lbl">${l}</div></div>`
    ).join("") +
      `<div class="card"><div class="val" style="font-size:.8rem">${dmyTime(d.observation_time_local)}</div><div class="lbl">Aggiornato</div></div>`;
  } catch (e) {
    document.getElementById("latest-cards").innerHTML =
      `<div class="card"><div class="lbl">Nessun dato realtime</div></div>`;
  }
}

// ---------- Andamento giornaliero ----------
async function loadOverview(year) {
  const rows = await apiS(`/api/daily?year=${year}`);
  const labels = rows.map((r) => dm(r.observation_date));
  makeChart("chart-temp", {
    type: "line",
    data: {
      labels,
      datasets: [
        line("T max", rows.map((r) => r.t_max), "#f97316"),
        line("T media", rows.map((r) => r.t_med), "#38bdf8"),
        line("T min", rows.map((r) => r.t_min), "#a78bfa"),
      ],
    },
    options: { plugins: { title: title(`Temperature ${year} (°C)`) } },
  });
  makeChart("chart-rain", {
    type: "bar",
    data: { labels, datasets: [{ label: "Pioggia (mm)", data: rows.map((r) => r.rain), backgroundColor: "#34d399" }] },
    options: { plugins: { title: title(`Pioggia ${year} (mm)`) } },
  });
}

// ---------- Confronto annate ----------
function buildCompareYears() {
  const box = document.getElementById("compare-years");
  box.innerHTML = STATE.years.map((y, i) =>
    `<label><input type="checkbox" value="${y}" ${i < 2 ? "checked" : ""}/> ${y}</label>`
  ).join("");
}

async function setupMetricSelect() {
  const metrics = await api("/api/metrics");
  const msel = document.getElementById("compare-metric");
  msel.innerHTML = metrics.map((m) => `<option value="${m.key}">${m.label} (${m.unit})</option>`).join("");
  msel.value = "t_med";
  msel.addEventListener("change", loadCompare);
  document.getElementById("compare-years").addEventListener("change", loadCompare);
}

function selectedYears() {
  return Array.from(document.querySelectorAll("#compare-years input:checked")).map((c) => c.value);
}

async function loadCompare() {
  const metric = document.getElementById("compare-metric").value;
  const years = selectedYears();
  if (!metric || !years.length) return;

  const res = await apiS(`/api/compare?metric=${metric}&years=${years.join(",")}`);
  const allMd = new Set();
  Object.values(res.series).forEach((arr) => arr.forEach((p) => allMd.add(p.md)));
  // Chiave interna "MM-DD" per ordinare cronologicamente; etichetta mostrata "DD/MM".
  const sortedMd = Array.from(allMd).sort();
  const datasets = Object.keys(res.series).map((y, i) => {
    const map = Object.fromEntries(res.series[y].map((p) => [p.md, p.value]));
    return line(y, sortedMd.map((md) => (md in map ? map[md] : null)), YEAR_COLORS[i % YEAR_COLORS.length]);
  });
  makeChart("chart-compare", {
    type: "line",
    data: { labels: sortedMd.map(mdToDm), datasets },
    options: { spanGaps: true, plugins: { title: title(`${res.label} per giorno dell'anno (${res.unit})`) } },
  });

  loadMonthly(metric);
}

const MONTHS = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

async function loadMonthly(metric) {
  const res = await apiS(`/api/monthly?metric=${metric}`);
  const yrs = Object.keys(res.data).sort();
  const datasets = yrs.map((y, i) => ({
    label: y,
    data: MONTHS.map((_, m) => (res.data[y][m + 1] != null ? res.data[y][m + 1] : null)),
    backgroundColor: YEAR_COLORS[i % YEAR_COLORS.length],
  }));
  const aggTxt = res.agg === "sum" ? "totale" : "media";
  makeChart("chart-monthly", {
    type: "bar",
    data: { labels: MONTHS, datasets },
    options: { plugins: { title: title(`${res.label} mensile (${aggTxt}, ${res.unit})`) } },
  });
}

// ---------- Tempo reale ----------
async function loadRealtime() {
  const start = document.getElementById("rt-start").value;
  const end = document.getElementById("rt-end").value;

  let path, rangeTxt;
  if (start || end) {
    const s = start || end;          // se ne manca una, uso l'altra (singolo giorno)
    const e = end || start;
    path = "/api/realtime?limit=5000"
      + "&start=" + encodeURIComponent(s + " 00:00:00")
      + "&end=" + encodeURIComponent(e + " 23:59:59");
    rangeTxt = s === e ? `del ${dmy(s)}` : `dal ${dmy(s)} al ${dmy(e)}`;
  } else {
    path = "/api/realtime?limit=500";
    rangeTxt = "recenti";
  }

  const rows = await apiS(path);
  document.getElementById("rt-info").textContent =
    rows.length ? `${rows.length} rilevazioni ${rangeTxt}` : `Nessun dato ${rangeTxt}`;
  const labels = rows.map((r) => dmTime(r.observation_time_local));
  makeChart("chart-rt-temp", {
    type: "line",
    data: {
      labels,
      datasets: [
        line("Temperatura", rows.map((r) => r.temperature), "#f97316"),
        line("Punto di rugiada", rows.map((r) => r.dew_point), "#38bdf8"),
        { ...line("Umidità %", rows.map((r) => r.rh), "#34d399"), yAxisID: "y1" },
      ],
    },
    options: {
      plugins: { title: title(`Temperatura / umidità (${rangeTxt})`) },
      scales: {
        x: { ticks: { color: "#94a3b8", maxTicksLimit: 12 }, grid: { color: "#1e293b" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "#1e293b" } },
        y1: { position: "right", ticks: { color: "#34d399" }, grid: { drawOnChartArea: false }, min: 0, max: 100 },
      },
    },
  });
  makeChart("chart-rt-wind", {
    type: "line",
    data: {
      labels,
      datasets: [
        line("Vento", rows.map((r) => r.wind_speed), "#38bdf8"),
        line("Raffica", rows.map((r) => r.wind_gust), "#f43f5e"),
      ],
    },
    options: { plugins: { title: title(`Vento ${rangeTxt} (km/h)`) } },
  });
}

// ---------- Tabella ----------
const TABLE_COLS = [
  ["observation_date", "Data"], ["t_min", "T min"], ["t_med", "T med"], ["t_max", "T max"],
  ["rh_med", "UR med %"], ["slpres", "Press. hPa"], ["w_med", "Vento med"], ["w_max", "Raffica max"],
  ["w_dir", "Dir."], ["rain", "Pioggia mm"],
];

async function loadTable(year) {
  const rows = await apiS(`/api/daily?year=${year}`);
  const thead = "<thead><tr>" + TABLE_COLS.map(([, l]) => `<th>${l}</th>`).join("") + "</tr></thead>";
  const tbody = "<tbody>" + rows.slice().reverse().map((r) =>
    "<tr>" + TABLE_COLS.map(([k]) => {
      if (k === "observation_date") return `<td>${dmy(r[k])}</td>`;
      return `<td>${r[k] == null ? "–" : r[k]}</td>`;
    }).join("") + "</tr>"
  ).join("") + "</tbody>";
  document.getElementById("daily-table").innerHTML = thead + tbody;
  document.getElementById("table-count").textContent = `${rows.length} giorni`;
}

// ---------- Foto ----------
async function loadPhotos() {
  const g = document.getElementById("photos-gallery");
  let data;
  try {
    data = await apiS("/api/photos");
  } catch (e) {
    g.innerHTML = `<div class="photos-empty">Errore nel caricamento delle foto.</div>`;
    return;
  }
  if (!data.count) {
    g.innerHTML = `<div class="photos-empty">Nessuna foto trovata. Aggiungi immagini nella cartella <code>photos/</code> del progetto (anche in sottocartelle).</div>`;
    return;
  }
  let uid = 0;
  g.innerHTML = data.groups.map((group) => {
    const header = group.folder
      ? `<h3 class="photo-folder-title">📁 ${escapeHtml(group.folder)}</h3>`
      : "";
    const events = group.events.map((ev) => renderPhotoEvent(ev, uid++)).join("");
    return `<div class="photo-folder">${header}${events}</div>`;
  }).join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderPhotoEvent(ev, uid) {
  const hh = ev.hour.slice(11, 13);
  const hourLabel = `${dmy(ev.hour)} · ${hh}:00–${hh}:59`;
  const thumbs = ev.photos.map((p) =>
    `<a href="${p.url}" target="_blank" title="${escapeHtml(p.file)} — ${dmyTime(p.taken_at)}">` +
    `<img loading="lazy" src="${p.url}" alt=""></a>`
  ).join("");
  const count = ev.photos.length;
  const hasDetail = ev.weather && ev.weather.source === "realtime";
  const detailUI = hasDetail
    ? `<button class="btn btn-ghost detail-toggle" data-hour="${ev.hour}" data-uid="${uid}" data-target="pd-${uid}">📈 Dettaglio meteo 48h</button>
       <div class="photo-detail" id="pd-${uid}" hidden></div>`
    : "";
  return `<div class="photo-event">
    <div class="photo-event-head">
      <span class="photo-event-hour">📅 ${hourLabel}</span>
      <span class="photo-event-weather">${weatherSummary(ev.weather)}</span>
      <span class="hint">${count} foto</span>
    </div>
    <div class="photo-thumbs">${thumbs}</div>
    ${detailUI}
  </div>`;
}

function weatherSummary(w) {
  if (!w) return '<span class="src">dati meteo non disponibili per questo orario</span>';
  if (w.source === "realtime") {
    const parts = [
      `🌡 ${fmt(w.temperature, "°C")}`,
      `💧 ${fmt(w.rh, "%")}`,
      `💨 ${fmt(w.wind_speed, " km/h")}${w.wind_direction ? " " + w.wind_direction : ""}`,
    ];
    if (w.rain_rate != null && w.rain_rate > 0) parts.push(`🌧 ${fmt(w.rain_rate, " mm/h")}`);
    return parts.join(" · ") +
      ` <span class="src">(rilevazione ${dmTime(w.observation_time_local)})</span>`;
  }
  // riepilogo giornaliero (nessuna rilevazione realtime vicina)
  return `🌡 min ${fmt(w.t_min)} / med ${fmt(w.t_med)} / max ${fmt(w.t_max)} °C` +
    ` · 🌧 ${fmt(w.rain, " mm")} <span class="src">(dato giornaliero)</span>`;
}

// "2025-03-15T14:00:00" + ore -> "2025-03-15 12:00:00" (orario locale, formato API)
function shiftHour(iso, deltaHours) {
  const d = new Date(iso);
  d.setHours(d.getHours() + deltaHours);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
         `${p(d.getHours())}:${p(d.getMinutes())}:00`;
}

// Grafico di dettaglio con linea-marker sull'istante della foto
function detailChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), {
    type: cfg.type,
    data: cfg.data,
    plugins: [photoMarker],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#e2e8f0" } },
        title: title(cfg.title),
        photoMarker: { index: cfg.markerIndex },
      },
      scales: Object.assign({
        x: { ticks: { color: "#94a3b8", maxTicksLimit: 10 }, grid: { color: "#1e293b" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "#1e293b" } },
      }, cfg.extraScales || {}),
    },
  });
}

async function loadPhotoDetail(hour, sid, container) {
  const start = shiftHour(hour, -48);   // 48 ore prima
  const end = shiftHour(hour, 6);       // qualche ora dopo
  let rows;
  try {
    rows = await apiS(`/api/realtime?limit=1000` +
      `&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
  } catch (e) {
    container.innerHTML = `<div class="photos-empty">Errore nel caricamento del dettaglio.</div>`;
    return;
  }
  if (!rows.length) {
    container.innerHTML = `<div class="photos-empty">Dettaglio meteo non disponibile per questo periodo.</div>`;
    return;
  }

  container.innerHTML =
    `<div class="chart-box detail-box"><canvas id="pdt-${sid}"></canvas></div>` +
    `<div class="chart-box detail-box"><canvas id="pdr-${sid}"></canvas></div>` +
    `<div class="chart-box detail-box"><canvas id="pdw-${sid}"></canvas></div>`;

  const labels = rows.map((r) => dmTime(r.observation_time_local));
  // indice della rilevazione più vicina all'ora della foto (per il marker)
  const hourTime = new Date(hour).getTime();
  let idx = 0, best = Infinity;
  rows.forEach((r, i) => {
    const d = Math.abs(new Date(r.observation_time_local).getTime() - hourTime);
    if (d < best) { best = d; idx = i; }
  });

  detailChart(`pdt-${sid}`, {
    type: "line",
    title: "Temperatura / umidità (48h prima → dopo)",
    markerIndex: idx,
    data: { labels, datasets: [
      line("Temperatura", rows.map((r) => r.temperature), "#f97316"),
      line("Punto di rugiada", rows.map((r) => r.dew_point), "#38bdf8"),
      { ...line("Umidità %", rows.map((r) => r.rh), "#34d399"), yAxisID: "y1" },
    ] },
    extraScales: { y1: { position: "right", min: 0, max: 100,
      ticks: { color: "#34d399" }, grid: { drawOnChartArea: false } } },
  });
  detailChart(`pdr-${sid}`, {
    type: "bar",
    title: "Precipitazioni (mm/h)",
    markerIndex: idx,
    data: { labels, datasets: [
      { label: "Precipitazioni (mm/h)", data: rows.map((r) => r.rain_rate), backgroundColor: "#34d399" },
    ] },
  });
  detailChart(`pdw-${sid}`, {
    type: "line",
    title: "Vento (km/h)",
    markerIndex: idx,
    data: { labels, datasets: [
      line("Vento", rows.map((r) => r.wind_speed), "#38bdf8"),
      line("Raffica", rows.map((r) => r.wind_gust), "#f43f5e"),
    ] },
  });
}

// ---------- Ricarica tutto per la stazione selezionata ----------
async function reloadStation() {
  const ovSel = document.getElementById("overview-year");
  const tbSel = document.getElementById("table-year");

  await Promise.all([loadStation(), loadLatest(), loadRealtime(), loadPhotos()]);

  STATE.years = await apiS("/api/years");
  const opts = STATE.years.map((y) => `<option value="${y}">${y}</option>`).join("");
  ovSel.innerHTML = opts;
  tbSel.innerHTML = opts;
  buildCompareYears();

  if (STATE.years.length) {
    await loadOverview(STATE.years[0]);
    await loadCompare();
    await loadTable(STATE.years[0]);
  } else {
    ["chart-temp", "chart-rain", "chart-compare", "chart-monthly"].forEach((id) => {
      if (charts[id]) charts[id].destroy();
    });
    document.getElementById("daily-table").innerHTML = "";
    document.getElementById("table-count").textContent = "nessun dato giornaliero per questa stazione";
  }
}

// ---------- Bootstrap ----------
async function main() {
  // Selettore stazione
  const list = await api("/api/stations");
  const sel = document.getElementById("station-select");
  sel.innerHTML = list.map((s) => `<option value="${s.station_code}">${s.name}</option>`).join("");
  STATE.station = list.length ? list[0].station_code : null;
  sel.value = STATE.station || "";
  sel.addEventListener("change", () => { STATE.station = sel.value; reloadStation(); });

  // Listener fissi (registrati una sola volta)
  document.getElementById("overview-year").addEventListener("change", (e) => loadOverview(e.target.value));
  document.getElementById("table-year").addEventListener("change", (e) => loadTable(e.target.value));

  // Tempo reale: mostra intervallo scelto, oppure torna alle rilevazioni recenti
  document.getElementById("rt-show").addEventListener("click", loadRealtime);
  document.getElementById("rt-recent").addEventListener("click", () => {
    document.getElementById("rt-start").value = "";
    document.getElementById("rt-end").value = "";
    loadRealtime();
  });

  // Foto: apertura/chiusura del dettaglio meteo 48h (caricato alla prima apertura)
  document.getElementById("photos-gallery").addEventListener("click", (e) => {
    const btn = e.target.closest(".detail-toggle");
    if (!btn) return;
    const container = document.getElementById(btn.dataset.target);
    if (container.hidden) {
      container.hidden = false;
      btn.textContent = "📉 Nascondi dettaglio";
      if (!container.dataset.loaded) {
        container.dataset.loaded = "1";
        container.innerHTML = `<div class="photos-empty">Caricamento…</div>`;
        loadPhotoDetail(btn.dataset.hour, btn.dataset.uid, container);
      }
    } else {
      container.hidden = true;
      btn.textContent = "📈 Dettaglio meteo 48h";
    }
  });

  await setupMetricSelect();

  await reloadStation();

  // Aggiorna le condizioni attuali ogni 5 minuti
  setInterval(loadLatest, 5 * 60 * 1000);
}

main();
