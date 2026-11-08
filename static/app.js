const $ = (s) => document.querySelector(s);
const api = (p, opt) => fetch(p, opt).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (ts) => ts ? new Date(ts * 1000).toISOString().slice(0, 10) : "";
const fmtDT = (ts) => ts ? new Date(ts * 1000).toISOString().slice(0, 16).replace("T", " ") + "Z" : "";
const daysAgo = (ts) => Math.round((Date.now() / 1000 - ts) / 86400);
const tick = (t) => t ? ` <span class="muted">(${esc(t)})</span>` : "";

let state = { signals: [], companies: [], threshold: 60 };

// ---------- tabs ----------
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === name));
  try { localStorage.setItem("jetdeal.tab", name); } catch (e) {}
  ({ flights: loadFlights, deals: loadDeals, companies: loadCompanies, sources: loadSources })[name]?.();
}

function badge(s) {
  if (s.alert) return `<span class="badge alert">ALERT</span>`;
  return `<span class="badge ${s.status}">${s.status}</span>`;
}

function table(el, cols, rows, onClick) {
  el.innerHTML = `<thead><tr>${cols.map((c) => `<th>${c[0]}</th>`).join("")}</tr></thead><tbody>${
    rows.length ? rows.map((r, i) => `<tr data-i="${i}" class="${onClick ? "clickable" : ""}">${
      cols.map((c) => `<td class="${c[2] || ""}">${c[1](r)}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${cols.length}" class="muted">No rows</td></tr>`}</tbody>`;
  if (onClick) el.querySelectorAll("tbody tr[data-i]").forEach((tr) => tr.addEventListener("click", (e) => onClick(rows[+tr.dataset.i], e)));
}

// ---------- signals ----------
async function loadSignals() {
  const [sig, st] = await Promise.all([api("/api/signals"), api("/api/status")]);
  state.signals = sig; state.threshold = st.alert_threshold;
  $("#sample-badge").hidden = !sig.some((s) => s.is_sample);
  const alerts = sig.filter((s) => s.alert);
  const confirmed = sig.filter((s) => s.status === "confirmed" && s.backtest);
  const leads = confirmed.map((s) => s.backtest.lead_days).filter((d) => d != null);
  $("#kpis").innerHTML = [
    [alerts.length, "Open alerts (score ≥ " + st.alert_threshold + ")"],
    [sig.length, "Company pairs with visits"],
    [confirmed.length, "Signals later confirmed by a deal"],
    [leads.length ? Math.round(leads.reduce((a, b) => a + b, 0) / leads.length) + " d" : "–", "Avg. warning before deal (backtest)"],
    [st.counts.flights, "Flights ingested"],
  ].map(([v, l]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

  $("#alerts").innerHTML = alerts.length ? alerts.map((s, i) => `
    <div class="card" data-i="${i}">
      <div class="pair">${esc(s.visitor)} → ${esc(s.host)}</div>
      <div class="meta">${s.visits_30d} landings in ${esc(s.host_city)} in 30 days · last ${daysAgo(s.last_visit)} d ago · ${esc(s.tails.join(", "))}</div>
      <div class="meta">${s.deal ? "Related: " + esc(s.deal.title) : "No deal announced between them"}</div>
      <div class="score-row"><div class="bar"><i style="width:${s.score}%"></i></div><span class="score">${s.score}</span></div>
    </div>`).join("") : `<div class="empty">No open alerts right now.</div>`;
  $("#alerts").querySelectorAll(".card").forEach((c) => c.addEventListener("click", () => openTimeline(alerts[+c.dataset.i])));
  renderSignalTable();
  fillPairSelect();
}

function renderSignalTable() {
  const st = $("#f-status").value, min = +$("#f-score").value || 0, watchOnly = $("#f-watch").checked;
  const watched = new Set(state.companies.filter((c) => c.watch).map((c) => c.id));
  const rows = state.signals.filter((s) => (!st || s.status === st) && (s.score >= min || s.status === "confirmed")
    && (!watchOnly || watched.has(s.visitor_id) || watched.has(s.host_id)));
  table($("#signals-table"), [
    ["Score", (s) => `<b>${s.score}</b>`, "num"],
    ["Status", badge],
    ["Visitor (jet owner)", (s) => esc(s.visitor) + tick(s.visitor_ticker)],
    ["Host (HQ city)", (s) => esc(s.host) + tick(s.host_ticker) + ` · ${esc(s.host_city)}`],
    ["30d visits", (s) => s.visits_30d, "num"],
    ["All visits", (s) => s.visits_total, "num"],
    ["Last visit", (s) => fmtDate(s.last_visit)],
    ["Backtest", (s) => s.backtest ? `peak ${s.backtest.peak_score}` + (s.backtest.lead_days ? `, alert ${s.backtest.lead_days} d before deal` : ", never crossed threshold") : ""],
    ["Deal / filing", (s) => s.deal ? `${esc(s.deal.kind)} · ${fmtDate(s.deal.ts)}` : ""],
  ], rows, openTimeline);
}
["#f-status", "#f-score", "#f-watch"].forEach((s) => $(s).addEventListener("input", renderSignalTable));

// ---------- timeline ----------
function pairKey(s) { return `${s.visitor_id}-${s.host_id}`; }
function fillPairSelect() {
  const sel = $("#tl-pair"), cur = sel.value;
  sel.innerHTML = state.signals.map((s) => `<option value="${pairKey(s)}">${esc(s.visitor)} → ${esc(s.host)} (${s.score}, ${s.status})</option>`).join("");
  if (cur) sel.value = cur;
}
$("#tl-pair").addEventListener("change", () => renderTimeline());
function openTimeline(s) { showTab("timeline"); $("#tl-pair").value = pairKey(s); renderTimeline(); }

async function renderTimeline() {
  const s = state.signals.find((x) => pairKey(x) === $("#tl-pair").value);
  if (!s) { $("#tl-summary").innerHTML = `<div class="empty">No signals yet.</div>`; return; }
  const t = await api(`/api/timeline?visitor=${s.visitor_id}&host=${s.host_id}`);
  const p = s.parts || {};
  $("#tl-summary").innerHTML = `
    <h2 style="margin-top:4px">${esc(s.visitor)} → ${esc(s.host)} ${badge(s)}</h2>
    <p class="hint">Score ${s.score}: frequency ${p.frequency ?? 0}, novelty ${p.novelty ?? 0}, recency ${p.recency ?? 0},
      day trips ${p.day_trips ?? 0}, watchlist ${p.watchlist ?? 0}${p.leisure_penalty ? ", leisure penalty ×0.3" : ""}.
      ${t.flights.length} of ${t.total_flights_visitor} ${esc(s.visitor)} flights landed in ${esc(s.host_city)}.
      ${s.backtest ? `Backtest: ${s.backtest.pre_deal_visits} visits in the 120 days before the deal, peak score ${s.backtest.peak_score}` +
        (s.backtest.lead_days ? `, first alert ${s.backtest.lead_days} days before announcement.` : ".") : ""}</p>`;
  drawChart(t);
  table($("#tl-table"), [
    ["Type", (r) => r._type === "deal" ? `<span class="badge open" style="color:var(--deal)">${esc(r.kind)}</span>` : "landing"],
    ["Date (UTC)", (r) => r._type === "deal" ? fmtDate(r.ts) : fmtDT(r.arr_ts)],
    ["Detail", (r) => r._type === "deal"
      ? (r.url && r.url.startsWith("http") ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title))
      : `${esc(r.tail)} ${esc(r.origin || "?")} → ${esc(r.dest)} (${esc(r.dest_name)})`, "wrap"],
  ], [...t.flights.map((f) => ({ ...f, _type: "flight", _ts: f.arr_ts })), ...t.deals.map((d) => ({ ...d, _type: "deal", _ts: d.ts }))]
    .sort((a, b) => b._ts - a._ts));
}

function drawChart(t) {
  const now = Date.now() / 1000;
  const tsAll = [...t.flights.map((f) => f.arr_ts), ...t.deals.map((d) => d.ts)];
  const start = Math.min(now - 120 * 86400, ...tsAll) - 7 * 86400, end = now + 5 * 86400;
  const W = 1000, H = 190, L = 20, R = 20, axisY = 150;
  const x = (ts) => L + ((ts - start) / (end - start)) * (W - L - R);
  const tails = [...new Set(t.flights.map((f) => f.tail))];
  const lane = (tail) => 40 + tails.indexOf(tail) * Math.min(30, 90 / Math.max(1, tails.length));
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Timeline of landings and deals">`;
  // month ticks
  const d = new Date(start * 1000); d.setUTCDate(1); d.setUTCHours(0, 0, 0, 0);
  for (d.setUTCMonth(d.getUTCMonth() + 1); d.getTime() / 1000 < end; d.setUTCMonth(d.getUTCMonth() + 1)) {
    const xx = x(d.getTime() / 1000);
    svg += `<line x1="${xx}" x2="${xx}" y1="20" y2="${axisY}" stroke="var(--line)"/><text x="${xx + 3}" y="${axisY + 16}">${d.toISOString().slice(0, 7)}</text>`;
  }
  svg += `<line x1="${L}" x2="${W - R}" y1="${axisY}" y2="${axisY}" stroke="var(--muted)"/>`;
  svg += `<line x1="${x(now)}" x2="${x(now)}" y1="14" y2="${axisY}" stroke="var(--muted)" stroke-dasharray="3 3"/><text x="${x(now) - 22}" y="12">today</text>`;
  t.deals.forEach((dl) => {
    const xx = x(dl.ts);
    svg += `<line x1="${xx}" x2="${xx}" y1="20" y2="${axisY}" stroke="var(--deal)" stroke-width="2"><title>${esc(dl.title)}</title></line>`;
    svg += `<path d="M${xx - 5},${axisY + 2} L${xx + 5},${axisY + 2} L${xx},${axisY - 6} Z" fill="var(--deal)"/>`;
    svg += `<text x="${xx + 4}" y="30" style="fill:var(--deal)">${esc(dl.kind)}</text>`;
  });
  tails.forEach((tl) => { svg += `<text x="${L}" y="${lane(tl) - 8}">${esc(tl)}</text>`; });
  t.flights.forEach((f) => {
    svg += `<circle cx="${x(f.arr_ts)}" cy="${lane(f.tail)}" r="5" fill="var(--flight)" fill-opacity=".85"><title>${esc(f.tail)} landed ${esc(f.dest)} ${fmtDT(f.arr_ts)}</title></circle>`;
  });
  svg += `</svg><div class="hint" style="margin:6px 0 0">● landing in host city &nbsp; <span style="color:var(--deal)">▲ deal / filing / rumor</span></div>`;
  $("#tl-chart").innerHTML = svg;
}

// ---------- companies / aircraft ----------
async function loadCompanies() {
  const [cs, ac] = await Promise.all([api("/api/companies"), api("/api/aircraft")]);
  state.companies = cs;
  table($("#companies-table"), [
    ["", (c) => `<button class="star ${c.watch ? "on" : ""}" data-id="${c.id}" aria-label="watch">${c.watch ? "★" : "☆"}</button>`],
    ["Company", (c) => esc(c.name) + (c.is_sample ? ` <span class="badge sample">sample</span>` : "")],
    ["Ticker", (c) => esc(c.ticker)], ["Sector", (c) => esc(c.sector)], ["HQ", (c) => esc(c.hq_city)],
    ["HQ airports", (c) => esc(c.hq_airports)], ["Aircraft", (c) => c.aircraft, "num"], ["Deals", (c) => c.deals, "num"],
    ["CIK", (c) => esc(c.cik)],
  ], cs);
  $("#companies-table").querySelectorAll(".star").forEach((b) => b.addEventListener("click", async () => {
    const on = !b.classList.contains("on");
    await api(`/api/companies/${b.dataset.id}/watch`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ watch: on }) });
    await loadCompanies(); loadSignals();
  }));
  table($("#aircraft-table"), [
    ["Tail", (a) => esc(a.tail)], ["ICAO24", (a) => esc(a.icao24)], ["Model", (a) => esc(a.model)],
    ["Registered to", (a) => esc(a.registrant)], ["Type", (a) => esc(a.registrant_type)], ["Company", (a) => esc(a.company)],
  ], ac);
}

async function loadFlights() {
  table($("#flights-table"), [
    ["Departed (UTC)", (f) => fmtDT(f.dep_ts)], ["Tail", (f) => esc(f.tail)], ["Company", (f) => esc(f.company)],
    ["From", (f) => `${esc(f.origin || "?")} <span class="muted">${esc(f.origin_city || "")}</span>`],
    ["To", (f) => `${esc(f.dest || "?")} <span class="muted">${esc(f.dest_city || "")}</span>`],
    ["Duration", (f) => f.arr_ts && f.dep_ts ? Math.round((f.arr_ts - f.dep_ts) / 60) + " min" : "", "num"],
    ["Source", (f) => esc(f.source)],
  ], await api("/api/flights"));
}

async function loadDeals() {
  table($("#deals-table"), [
    ["Date", (d) => fmtDate(d.ts)], ["Kind", (d) => esc(d.kind)], ["Acquirer / filer", (d) => esc(d.acquirer || "–")],
    ["Target / subject", (d) => esc(d.target || "–")],
    ["Title", (d) => d.url && d.url.startsWith("http") ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a>` : esc(d.title), "wrap"],
    ["Source", (d) => esc(d.source)],
  ], await api("/api/deals"));
}

// ---------- sources ----------
async function loadSources() {
  const st = await api("/api/status");
  const runs = Object.fromEntries(st.runs.map((r) => [r.source, r]));
  const info = {
    opensky: ["OpenSky Network (flights)", "Set OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET in .env"],
    faa: ["FAA aircraft registry (owners)", "Download ReleasableAircraft.zip, unzip, set FAA_REGISTRY_DIR"],
    edgar: ["SEC EDGAR (M&A filings)", "Set SEC_USER_AGENT (app name + contact email) and add CIKs in companies.csv"],
  };
  $("#source-status").innerHTML = Object.entries(info).map(([k, [name, howto]]) => {
    const r = runs[k], conf = st.sources[k].configured;
    return `<div class="card" style="cursor:default"><div class="pair">${name}
      <span class="badge ${conf ? "live" : "sample"}">${conf ? "configured" : "using sample data"}</span></div>
      <div class="meta">${r ? `Last run ${fmtDT(r.ts)} · ${r.mode} · ${r.rows} rows` : "Never run"}</div>
      ${r && r.note ? `<div class="meta" style="color:var(--warn)">${esc(r.note)}</div>` : ""}
      ${conf ? "" : `<div class="meta">${howto}</div>`}</div>`;
  }).join("");
}
async function runIngest(body) {
  const btns = [$("#btn-ingest"), $("#btn-sample")]; btns.forEach((b) => (b.disabled = true));
  $("#ingest-msg").textContent = "Running… (live OpenSky pulls can take a few minutes)";
  try {
    const r = await api("/api/ingest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("#ingest-msg").textContent = `Done. Aircraft kept ${r.faa.kept} (dropped ${r.faa.dropped_individual} individual, ${r.faa.dropped_blocked} blocked), flights +${r.opensky.inserted}, deals +${r.edgar.inserted}.`;
    await Promise.all([loadSources(), loadCompanies(), loadSignals()]);
  } catch (e) { $("#ingest-msg").textContent = "Failed: " + e.message; }
  btns.forEach((b) => (b.disabled = false));
}
$("#btn-ingest").addEventListener("click", () => runIngest({ sample: false }));
$("#btn-sample").addEventListener("click", () => runIngest({ sample: true, reset: true }));

// ---------- boot ----------
(async () => {
  await loadCompanies();
  await loadSignals();
  let tab = "signals";
  try { tab = localStorage.getItem("jetdeal.tab") || "signals"; } catch (e) {}
  showTab(tab);
  if (tab === "timeline") renderTimeline();
})();
