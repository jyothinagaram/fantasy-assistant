"""
The page for the in-season app (served by app.py).

One file of HTML, styling and JavaScript, like the draft page. It never
talks to ESPN -- it draws whatever app.py hands it. Built phone-first: tabs
sit at the bottom on a phone, where a thumb can reach them, and move to the
top on a wider screen.
"""

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0e1117">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Fantasy Assistant</title>
<style>
  :root {
    --bg:#0e1117; --panel:#161b26; --panel2:#1c2230; --line:#262d3c; --ink:#e8ecf3;
    --dim:#8b97ad; --good:#3ddc84; --warn:#ffb020; --bad:#ff6b61; --accent:#5b9dff;
    --tabs:62px;
  }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  html, body { margin:0; background:var(--bg); color:var(--ink); }
  body { font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
         padding-bottom:calc(var(--tabs) + env(safe-area-inset-bottom)); }
  header { position:sticky; top:0; z-index:20; background:var(--panel);
           border-bottom:1px solid var(--line); padding:10px 16px;
           padding-top:calc(10px + env(safe-area-inset-top)); }
  .bar { display:flex; gap:10px; align-items:center; max-width:1320px; margin:0 auto; }
  select, button, input { font:inherit; color:var(--ink); background:var(--panel2);
           border:1px solid var(--line); border-radius:9px; padding:8px 12px; }
  select { flex:1; min-width:0; font-weight:600; }
  button { cursor:pointer; white-space:nowrap; }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
  button:disabled { opacity:.5; cursor:default; }
  .freshness { max-width:1320px; margin:4px auto 0; font-size:12px; color:var(--dim); }
  .freshness.busy { color:var(--warn); }
  main { max-width:1320px; margin:0 auto; padding:14px 16px 24px; }
  /* Reading-width sections (start/sit, guide) stay narrow even on a wide page. */
  main.narrow-page { max-width:980px; }
  nav { position:fixed; left:0; right:0; bottom:0; z-index:30; display:flex;
        background:var(--panel); border-top:1px solid var(--line);
        padding-bottom:env(safe-area-inset-bottom); }
  nav button { flex:1; background:none; border:0; border-radius:0; padding:8px 4px 10px;
               color:var(--dim); font-size:12px; display:flex; flex-direction:column;
               align-items:center; gap:2px; height:var(--tabs); }
  nav button .icon { font-size:20px; line-height:1; }
  nav button.on { color:var(--accent); font-weight:600; }
  @media (min-width:760px) {
    body { padding-bottom:0; }
    nav { position:sticky; top:var(--header-h, 58px); bottom:auto; border-top:0;
          border-bottom:1px solid var(--line); justify-content:center; }
    nav button { flex:0 0 auto; flex-direction:row; gap:8px; height:auto; padding:12px 20px; font-size:14px; }
    nav button .icon { font-size:16px; }
  }
  h2 { font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--dim);
       margin:22px 0 10px; font-weight:650; }
  h2:first-child { margin-top:4px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:14px;
          padding:14px; margin-bottom:10px; }
  .card.flash { animation:flash 1.6s ease-out; }
  @keyframes flash { 0%,30% { border-color:var(--accent); box-shadow:0 0 0 2px var(--accent); } 100% { box-shadow:none; } }
  .row { display:flex; justify-content:space-between; gap:10px; align-items:baseline; }
  .muted { color:var(--dim); font-size:13px; }
  .small { font-size:12px; }
  .big { font-size:26px; font-weight:700; letter-spacing:-.02em; }
  .good { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); }
  .pill { display:inline-block; font-size:11px; font-weight:700; letter-spacing:.04em;
          padding:2px 7px; border-radius:99px; background:var(--panel2); color:var(--dim);
          border:1px solid var(--line); vertical-align:middle; }
  .pill.good { color:var(--good); border-color:#1f5b3a; background:#11261b; }
  .pill.bad { color:var(--bad); border-color:#5b2622; background:#2a1412; }
  .pill.warn { color:var(--warn); border-color:#5b4416; background:#2a2010; }
  .pill.accent { color:var(--accent); border-color:#25406b; background:#121d31; }
  .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; }
  .stat { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px 14px; }
  .stat .label { font-size:12px; color:var(--dim); }
  .stat .value { font-size:20px; font-weight:700; margin-top:2px; }
  .bars { display:grid; gap:9px; }
  .barrow { display:grid; grid-template-columns:48px 1fr 64px; gap:10px; align-items:center; font-size:14px; }
  .track { position:relative; height:10px; background:var(--panel2); border-radius:99px; }
  .track .mid { position:absolute; left:50%; top:-3px; bottom:-3px; width:1px; background:var(--dim); opacity:.5; }
  .track .fill { position:absolute; top:0; bottom:0; border-radius:99px; }
  .barrow .num { text-align:right; font-variant-numeric:tabular-nums; }
  .accent-note { color:var(--accent); }
  .aside { margin:6px 0 14px; }
  .aside summary { cursor:pointer; color:var(--dim); font-size:13px; padding:8px 0; }
  .aside[open] summary { color:var(--ink); }
  .reads { margin-top:10px; padding-top:10px; border-top:1px dashed var(--line); }
  .reads .pitch { margin-top:6px; font-size:13px; color:var(--ink); background:var(--panel2);
                  border:1px solid var(--line); border-radius:11px; padding:9px 11px; line-height:1.45; }
  .needrow { display:grid; grid-template-columns:52px 1fr auto; gap:10px; align-items:baseline;
             font-size:14px; padding:7px 0; border-bottom:1px solid var(--line); }
  .needrow:last-child { border-bottom:0; }
  .needrow .num { text-align:right; font-variant-numeric:tabular-nums; font-weight:700; }
  .fitrow { padding:10px 0; border-bottom:1px solid var(--line); }
  .fitrow:last-child { border-bottom:0; }
  .section-head { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
  .section-head .title { font-weight:700; font-size:16px; }
  .move { display:block; width:100%; text-align:left; background:var(--panel2); border:1px solid var(--line);
          border-radius:11px; padding:10px 12px; margin-top:8px; color:var(--ink); }
  .move:active { transform:scale(.99); }
  .move .title { font-weight:600; }
  .move .detail { color:var(--dim); font-size:13px; margin-top:2px; }
  .move .go { float:right; color:var(--accent); font-size:13px; margin-left:8px; }
  ul.reasons { margin:8px 0 0; padding-left:18px; color:var(--dim); font-size:13px; }
  ul.reasons li { margin:2px 0; }
  .quote { margin-top:8px; padding:8px 10px; border-left:3px solid var(--line); color:#c4cbd8;
           font-size:13px; font-style:italic; background:var(--panel2); border-radius:0 8px 8px 0; }
  .player { display:flex; justify-content:space-between; gap:10px; align-items:center;
            padding:9px 0; border-top:1px solid var(--line); }
  .player:first-child { border-top:0; }
  .player .slot { width:58px; flex:0 0 58px; font-size:12px; color:var(--dim); font-weight:600; }
  .player .who { flex:1; min-width:0; }
  .player .who .name { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .player .pts { font-weight:700; font-variant-numeric:tabular-nums; text-align:right; }
  .swap { display:grid; grid-template-columns:1fr auto 1fr; gap:8px; align-items:center; }
  .swap .arrow { color:var(--dim); }
  .empty { color:var(--dim); text-align:center; padding:26px 10px; }
  .checker label { display:flex; gap:10px; align-items:center; padding:8px 0; border-top:1px solid var(--line); }
  .checker label:first-of-type { border-top:0; }
  .checker input[type=checkbox] { width:20px; height:20px; accent-color:var(--accent); }
  .columns { display:grid; gap:12px; }
  @media (min-width:760px) { .columns { grid-template-columns:1fr 1fr; } }
  .loading { text-align:center; color:var(--dim); padding:60px 20px; }
  .spinner { width:26px; height:26px; border:3px solid var(--line); border-top-color:var(--accent);
             border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 12px; }
  @keyframes spin { to { transform:rotate(360deg); } }

  /* A deck: several cards on one line.
     Phone: one row you swipe sideways, the next card peeking in so it is
     obvious there is more. Tablet and up: a grid, as many per row as fit. */
  .deck { display:grid; grid-auto-flow:column; grid-auto-columns:86%; gap:10px;
          overflow-x:auto; scroll-snap-type:x mandatory; overscroll-behavior-x:contain;
          margin:0 -16px 10px; padding:2px 16px 8px; scroll-padding-inline:16px;
          -webkit-overflow-scrolling:touch; scrollbar-width:thin; }
  .deck > .card { margin:0; scroll-snap-align:start; min-width:0; }
  .deck-head { display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
  .deck-head h2 { margin-bottom:10px; }
  .deck-count { font-size:12px; color:var(--dim); white-space:nowrap; }
  .card { scroll-margin-top:calc(var(--header-h, 58px) + 16px); }
  @media (min-width:760px) {
    .deck { grid-auto-flow:row; grid-template-columns:repeat(auto-fill, minmax(330px, 1fr));
            grid-auto-columns:auto; overflow:visible; margin:0 0 10px; padding:0; align-items:start; }
    .deck .swipe-hint { display:none; }
    .card { scroll-margin-top:calc(var(--header-h, 58px) + 66px); }
  }
  @media (min-width:760px) { .deck-count .swipe { display:none; } }
  .team-link { background:none; border:0; padding:0; font:inherit; font-weight:700; color:var(--accent);
               cursor:pointer; text-decoration:underline; text-underline-offset:3px; }
  .team-link:focus-visible, .back:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .back { background:none; border:0; padding:6px 0; color:var(--accent); font-weight:600; }
  .roster-head { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; }
  .roster-head .name { font-size:22px; font-weight:700; }
  .pos-tag { display:inline-block; min-width:38px; font-size:11px; font-weight:700; color:var(--dim); }
  .score { display:grid; grid-template-columns:1fr auto 1fr; gap:10px; align-items:center; }
  .score .side { min-width:0; }
  .score .side.them { text-align:right; }
  .score .team { font-weight:600; font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .score .pts { font-size:34px; font-weight:750; letter-spacing:-.02em; font-variant-numeric:tabular-nums; line-height:1.1; }
  .score .vs { color:var(--dim); font-size:12px; font-weight:700; }
  .score .sub { font-size:12px; color:var(--dim); font-variant-numeric:tabular-nums; }
  .live-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:var(--bad); margin-right:5px; vertical-align:middle; }
  details.box { margin-top:12px; }
  details.box summary { cursor:pointer; color:var(--accent); font-weight:600; font-size:14px; list-style:none; }
  details.box summary::-webkit-details-marker { display:none; }
  .box-grid { display:grid; gap:12px; margin-top:10px; }
  @media (min-width:760px) { .box-grid { grid-template-columns:1fr 1fr; } }
  .box-row { display:grid; grid-template-columns:58px 1fr auto; gap:8px; align-items:center; padding:6px 0;
             border-top:1px solid var(--line); font-size:14px; }
  .box-row .slot { color:var(--dim); font-size:12px; font-weight:600; }
  .box-row .nm { min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .box-row .p { font-weight:700; font-variant-numeric:tabular-nums; text-align:right; }
  .box-row .p small { display:block; font-weight:400; color:var(--dim); font-size:11px; }
  .state-live { color:var(--bad); } .state-upcoming { color:var(--dim); } .state-final { color:var(--dim); }
  @media (prefers-reduced-motion: reduce) { .deck { scroll-behavior:auto; } .card.flash { animation:none; } }
  .guide h2 { margin-top:26px; }
  .guide .lede { color:var(--dim); margin:4px 0 0; }
  .guide dl { margin:0; display:grid; gap:12px; }
  .guide dt { font-weight:600; }
  .guide dd { margin:2px 0 0; color:var(--dim); font-size:14px; }
  .guide .job { font-weight:600; color:var(--accent); font-size:13px; margin-bottom:10px; }
  .guide table { width:100%; border-collapse:collapse; font-size:14px; }
  .guide td { padding:8px 0; border-top:1px solid var(--line); vertical-align:top; }
  .guide tr:first-child td { border-top:0; }
  .guide td:first-child { font-weight:600; width:38%; padding-right:10px; }
  .guide td:last-child { color:var(--dim); }
  .guide code { font:12.5px/1.4 ui-monospace,Menlo,monospace; background:var(--panel2); padding:2px 6px; border-radius:6px; overflow-wrap:anywhere; }
  .guide .cmd { display:grid; gap:2px; padding:8px 0; border-top:1px solid var(--line); }
  .guide .cmd:first-of-type { border-top:0; }
</style>
</head>
<body>
<header id="header">
  <div class="bar">
    <select id="league" aria-label="League"></select>
    <button id="refresh" title="Get fresh numbers from ESPN">↻ Refresh</button>
  </div>
  <div class="freshness" id="freshness"></div>
</header>
<nav id="tabs">
  <button data-tab="home" class="on"><span class="icon">◉</span>Team</button>
  <button data-tab="lineup"><span class="icon">☰</span>Start/Sit</button>
  <button data-tab="waivers"><span class="icon">＋</span>Waivers</button>
  <button data-tab="trades"><span class="icon">⇄</span>Trades</button>
  <button data-tab="guide"><span class="icon">?</span>Guide</button>
</nav>
<main id="main"><div class="loading"><div class="spinner"></div>Loading…</div></main>

<script>
const state = { leagues: [], leagueId: null, data: null, tab: "home", poll: null, rosterTeam: null, scoreboard: null, scoreboardFor: null, scoreboardAt: 0 };
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const signed = (n, d=1) => (n > 0 ? "+" : "") + Number(n).toFixed(d);
const matchupLine = (p) => p.matchup ? `<div class="small ${p.matchup_quality === "soft" ? "good" : p.matchup_quality === "tough" ? "bad" : "muted"}">${esc(p.matchup)}</div>` : "";
const deckHead = (title, count, noun) => `<div class="deck-head"><h2>${title}</h2>${count > 1 ? `<span class="deck-count">${count} ${noun}<span class="swipe"> · swipe →</span></span>` : ""}</div>`;
const ordinal = (n) => { if (n == null) return "?"; const s = ["th","st","nd","rd"], v = n % 100; return n + (s[(v-20)%10] || s[v] || s[0]); };

function remember(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
function recall(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

async function api(path, body) {
  const options = body ? { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) } : {};
  const response = await fetch(path, options);
  // The session ran out (or the password changed). Reloading lands on the
  // login form rather than leaving a page full of stale numbers that
  // quietly stop updating.
  if (response.status === 401) { location.reload(); return new Promise(() => {}); }
  return response.json();
}

function ago(seconds) {
  if (!seconds) return "never";
  const mins = Math.round((Date.now()/1000 - seconds) / 60);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  return hours < 24 ? `${hours} hr ago` : `${Math.round(hours/24)} days ago`;
}

// ---------------------------------------------------------------- loading

async function loadLeagues() {
  state.leagues = await api("/api/leagues");
  const select = $("#league");
  const chosen = state.leagueId || Number(recall("league")) || state.leagues[0]?.league_id;
  select.innerHTML = state.leagues.map(L => `<option value="${L.league_id}">${esc(L.name)}</option>`).join("");
  if (state.leagues.some(L => L.league_id === chosen)) select.value = chosen;
  state.leagueId = Number(select.value);
  showFreshness();
}

function showFreshness() {
  const L = state.leagues.find(x => x.league_id === state.leagueId);
  const el = $("#freshness");
  if (!L) { el.textContent = ""; return; }
  if (L.status && !L.status.startsWith("failed")) {
    el.className = "freshness busy";
    el.textContent = `Updating (${L.status})… showing ${L.updated ? "numbers from " + ago(L.updated) : "nothing yet"}`;
  } else if (L.status) {
    el.className = "freshness bad";
    el.textContent = `Last update ${L.status}. Showing numbers from ${ago(L.updated)}.`;
  } else {
    el.className = "freshness";
    el.textContent = `Updated ${ago(L.updated)}`;
  }
  $("#refresh").disabled = Boolean(L.status && !L.status.startsWith("failed"));
}

async function loadLeague() {
  loadScoreboard(true);
  const data = await api(`/api/league/${state.leagueId}`);
  state.data = data.loading ? null : data;
  render();
}

async function tick() {
  const before = state.leagues.find(x => x.league_id === state.leagueId)?.updated;
  state.leagues = await api("/api/leagues");
  const after = state.leagues.find(x => x.league_id === state.leagueId)?.updated;
  showFreshness();
  if (after !== before || !state.data) loadLeague();
  else if (state.tab === "home") loadScoreboard(false);
}

// ---------------------------------------------------------------- tabs & links

function setTab(tab, target) {
  if (tab !== state.tab) state.rosterTeam = null;
  state.tab = tab;
  remember("tab", tab);
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  render();
  if (target) {
    requestAnimationFrame(() => {
      const el = document.getElementById(target);
      if (!el) return;
      const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start", inline: "start" });
      el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
    });
  } else {
    scrollTo({ top: 0 });
  }
}

function moveButton(move) {
  const tab = move.kind === "trade" ? "trades" : "waivers";
  const target = `${move.kind}-${move.id}`;
  const label = move.kind === "trade" ? "Trades" : "Waivers";
  return `<button class="move" onclick="setTab('${tab}','${target}')">
    <span class="go">${label} ›</span>
    <div class="title">${esc(move.title)}</div>
    <div class="detail">${esc(move.detail)}</div></button>`;
}

// ---------------------------------------------------------------- home

function renderHome(d) {
  const h = d.home, s = h.season, latest = s.weeks[s.weeks.length - 1];
  const myTeam = (d.trades.teams || []).find(x => x.mine);
  let html = renderScoreboard();
  if (myTeam) html += `<button class="move" onclick="openRoster(${Number(myTeam.team_id)})"><span class="go">Roster ›</span>
    <div class="title">My roster</div><div class="detail">${esc(myTeam.name)} · ${myTeam.players.length} players · starters, bench and IR</div></button>`;
  html += `<h2>How you're doing</h2><div class="stats">`;
  if (d.start_sit && d.start_sit.matchup) {
    const m = d.start_sit.matchup, cls = m.situation === "favourite" ? "good" : m.situation === "underdog" ? "bad" : "warn";
    html += `<div class="stat" onclick="setTab('lineup')" style="cursor:pointer"><div class="label">Week ${d.start_sit.week} vs ${esc(m.opponent)}</div>
      <div class="value ${cls}">${m.chance}% <span class="muted small">${esc(m.situation)}</span></div>
      <div class="muted small">${m.mine.toFixed(1)} – ${m.theirs.toFixed(1)} projected</div></div>`;
  }
  if (latest) {
    const result = !latest.final ? "In progress"
      : latest.score > latest.opponent_score ? "Won" : latest.score < latest.opponent_score ? "Lost" : "Tied";
    const cls = !latest.final ? "warn" : result === "Won" ? "good" : result === "Lost" ? "bad" : "";
    html += `<div class="stat"><div class="label">Week ${latest.week} · <span class="${cls}">${result}</span></div>
      <div class="value">${latest.score.toFixed(1)} <span class="muted">– ${latest.opponent_score.toFixed(1)}</span></div>
      <div class="muted small">vs ${esc(latest.opponent)}</div></div>
      <div class="stat"><div class="label">Weekly score rank</div>
      <div class="value">${ordinal(latest.league_rank)} <span class="muted">of ${latest.team_count}</span></div>
      <div class="muted small">${latest.final ? (latest.left_on_bench >= 0.5 ? latest.left_on_bench.toFixed(1) + " pts left on bench" : "best lineup started") : "bench review after games finish"}</div></div>`;
  }
  const record = `${s.wins}-${s.losses}${s.ties ? "-" + s.ties : ""}`;
  html += `<div class="stat"><div class="label">Record · standing</div>
      <div class="value">${record} <span class="muted">· ${ordinal(s.standing)}</span></div>
      <div class="muted small">${s.playoff_spots} of ${s.team_count} make playoffs</div></div>
    <div class="stat"><div class="label">Playoff chance (ESPN)</div>
      <div class="value">${s.playoff_chance != null ? Math.round(s.playoff_chance) + "%" : "–"}</div>
      <div class="muted small">${s.points_for.toFixed(1)} pts scored</div></div></div>`;

  // Position bars: centre line is the league median.
  const widest = Math.max(4, ...h.positions.map(p => Math.abs(p.difference)));
  html += `<h2>Your starters vs the league</h2><div class="card"><div class="bars">`;
  for (const p of h.positions) {
    const pct = Math.min(50, Math.abs(p.difference) / widest * 50);
    const color = p.difference >= 1 ? "var(--good)" : p.difference <= -1 ? "var(--bad)" : "var(--dim)";
    const pos = p.difference >= 0 ? `left:50%;width:${pct}%` : `left:${50-pct}%;width:${pct}%`;
    html += `<div class="barrow"><b>${esc(p.group)}</b>
      <div class="track"><div class="mid"></div><div class="fill" style="${pos};background:${color}"></div></div>
      <div class="num"><span style="color:${color}">${signed(p.difference)}</span> <span class="muted small">${ordinal(p.rank)}</span></div></div>`;
  }
  html += `</div><div class="muted small" style="margin-top:10px">Points per normal week compared with the league's middle team. Rank out of ${h.positions[0]?.team_count || ""}.</div></div>`;

  html += deckHead("Biggest weaknesses", h.weaknesses.length, "positions");
  if (!h.weaknesses.length) html += `<div class="card muted">No position is clearly behind the league. 👍</div>`;
  html += `<div class="deck">`;
  for (const w of h.weaknesses) {
    const p = w.position;
    html += `<div class="card"><div class="section-head"><span class="pill bad">WEAKNESS</span>
      <span class="title">${esc(p.group)}</span><span class="muted">${signed(p.difference)} pts · ${ordinal(p.rank)} of ${p.team_count}</span></div>
      <div class="muted small">Starting: ${esc(p.starters.join(", ") || "nobody")}</div>
      ${w.moves.length ? w.moves.map(moveButton).join("") : `<div class="muted small" style="margin-top:8px">No pickup or trade fixes this yet — check back next week.</div>`}</div>`;
  }
  html += `</div>`;

  html += deckHead("Biggest strengths", h.strengths.length, "positions");
  if (!h.strengths.length) html += `<div class="card muted">No position is clearly ahead of the league yet.</div>`;
  html += `<div class="deck">`;
  for (const st of h.strengths) {
    const p = st.position;
    html += `<div class="card"><div class="section-head"><span class="pill good">STRENGTH</span>
      <span class="title">${esc(p.group)}</span><span class="muted">${signed(p.difference)} pts · ${ordinal(p.rank)} of ${p.team_count}</span></div>
      <div class="muted small">Starting: ${esc(p.starters.join(", "))}</div>
      ${st.moves.length ? `<div class="muted small" style="margin-top:8px">Trade from this depth to fix a weakness:</div>` + st.moves.map(moveButton).join("")
        : `<div class="muted small" style="margin-top:8px">No trade selling from here helps both teams yet.</div>`}</div>`;
  }
  html += `</div>`;

  if (d.start_sit && d.start_sit.worth_changing) {
    html += `<h2>This week's lineup</h2>
      <button class="move" onclick="setTab('lineup')"><span class="go">Start/Sit ›</span>
      <div class="title">${d.start_sit.changes.length} lineup change${d.start_sit.changes.length > 1 ? "s" : ""} worth ${signed(d.start_sit.gain)} pts</div>
      <div class="detail">${d.start_sit.changes.map(c => `Start ${esc(c.in.name)} over ${esc(c.out.name)}`).join(" · ")}</div></button>`;
  }
  return html;
}

// ---------------------------------------------------------------- start / sit

function playerRow(p, slotLabel) {
  const flag = p.injury ? ` <span class="pill ${/out|reserve|suspension|doubtful/i.test(p.injury) ? "bad" : "warn"}">${esc(p.injury)}</span>` : "";
  const lock = p.locked ? `<span class="pill">LOCKED</span>` : p.locks_in ? `<span class="muted small">${esc(p.locks_in)}</span>` : "";
  const experts = p.experts != null ? ` · experts ${p.experts.toFixed(1)}` : "";
  return `<div class="player">${slotLabel !== undefined ? `<div class="slot">${esc(slotLabel || "")}</div>` : ""}
    <div class="who"><div class="name">${esc(p.name)}${flag}</div>
    <div class="muted small">${esc(p.position)} · ${esc(p.team)}${p.opponent ? " vs " + esc(p.opponent) : ""} · ESPN ${p.espn?.toFixed(1) ?? "–"}${experts} ${lock}</div>
    ${p.usage ? `<div class="muted small">${esc(p.usage)}</div>` : ""}${matchupLine(p)}${p.consistency ? `<div class="muted small">${esc(p.consistency)}</div>` : ""}</div>
    <div class="pts">${p.this_week?.toFixed(1) ?? "–"}</div></div>`;
}

function renderLineup(d) {
  const s = d.start_sit;
  if (!s) return `<div class="empty">Start/sit is not available for this league right now.</div>`;
  let html = "";
  if (s.matchup) {
    const m = s.matchup, cls = m.situation === "favourite" ? "good" : m.situation === "underdog" ? "bad" : "warn";
    html += `<h2>This week's matchup</h2><div class="card"><div class="row"><div><div class="muted small">vs ${esc(m.opponent)}</div>
      <div class="big">${m.mine.toFixed(1)} <span class="muted">– ${m.theirs.toFixed(1)}</span></div></div>
      <div style="text-align:right"><div class="big ${cls}">${m.chance}%</div><div class="small ${cls}">${esc(m.situation)}</div></div></div>
      ${m.tiebreaks.length ? `<div class="muted small" style="margin-top:8px">Close calls worth leaning on:</div><ul class="reasons">${m.tiebreaks.map(t => `<li><b style="color:var(--ink)">${esc(t.start)}</b> over ${esc(t.over)} (${esc(t.slot)}) — ${esc(t.reason)}</li>`).join("")}</ul>`
        : `<div class="muted small" style="margin-top:8px">${m.situation === "toss-up" ? "It's close — just start the highest projections." : "No close calls where that changes anything."}</div>`}</div>`;
  }
  html += `<h2>Week ${s.week}</h2><div class="stats">
    <div class="stat"><div class="label">Best lineup</div><div class="value">${s.recommended_total.toFixed(1)}</div></div>
    <div class="stat"><div class="label">Your current lineup</div><div class="value">${s.current_total.toFixed(1)}</div></div></div>`;
  if (!s.experts_loaded) html += `<div class="muted small" style="margin-top:8px">Expert rankings for this week aren't out yet — using ESPN projections only.</div>`;

  html += `<h2>Changes to make</h2>`;
  if (!s.changes.length) html += `<div class="card good">Your lineup is already the best one.</div>`;
  else if (!s.worth_changing) html += `<div class="card muted">The best alternative is only ${signed(s.gain)} pts — inside the margin of error. No change needed.</div>`;
  else for (const c of s.changes) {
    html += `<div class="card"><div class="swap">
      <div><span class="pill bad">BENCH</span><div style="font-weight:600;margin-top:4px">${esc(c.out.name)}</div><div class="muted small">${c.out.this_week?.toFixed(1)} pts</div></div>
      <div class="arrow">→</div>
      <div><span class="pill good">START</span><div style="font-weight:600;margin-top:4px">${esc(c.in.name)}</div><div class="muted small">${c.in.this_week?.toFixed(1)} pts</div></div></div>
      ${[...c.in.reasons, ...c.out.reasons.map(r => c.out.name + ": " + r)].length ? `<ul class="reasons">${[...c.in.reasons, ...c.out.reasons.map(r => c.out.name + ": " + r)].map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}</div>`;
  }

  const watch = s.lineup.filter(p => p.injury || p.reasons.some(r => /questionable|practice|split|moved him down|ESPN higher|^weather/.test(r)));
  if (watch.length) {
    html += `<h2>Watch these starters</h2>`;
    for (const p of watch) html += `<div class="card"><div class="row"><b>${esc(p.name)}</b><span class="muted small">${esc(p.locks_in || "")}</span></div>
      <ul class="reasons">${p.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>${p.note ? `<div class="quote">“${esc(p.note)}”</div>` : ""}</div>`;
  }

  html += `<h2>Recommended lineup</h2><div class="card">${s.lineup.map(p => playerRow(p, p.slot)).join("")}</div>`;
  html += `<h2>Bench</h2><div class="card">${s.bench.map(p => playerRow(p, "BE")).join("")}</div>`;
  return html;
}

// ---------------------------------------------------------------- waivers

function claimBlock(c) {
  return `<div class="row" style="margin-top:10px;align-items:center">
      <div><span class="pill good">ADD</span> <b>${esc(c.add.name)}</b>
      ${c.drop ? `<div class="muted small" style="margin-top:4px"><span class="pill bad">DROP</span> ${esc(c.drop.name)} (${esc(c.drop.position)})</div>` : `<div class="muted small">no drop needed</div>`}</div>
      <div style="text-align:right"><div class="big">$${c.bid}</div><div class="good small">+${c.gain_per_week.toFixed(1)} pts/wk</div></div></div>`;
}

function renderWaivers(d) {
  const w = d.waivers;
  let html = `<div class="stats" style="margin-top:4px">
    <div class="stat"><div class="label">Your FAAB left</div><div class="value">$${w.budget_left}</div><div class="muted small">min bid $${w.minimum_bid}</div></div>
    <div class="stat"><div class="label">Most money elsewhere</div><div class="value">$${w.richest[0]?.budget_left ?? "–"}</div><div class="muted small">${esc(w.richest[0]?.team || "")}</div></div></div>
    <div class="muted small" style="margin-top:8px">${esc(w.schedule)}</div>
    <div class="muted small" style="margin-top:4px">${esc(w.market || "")}</div>
    ${w.big_spenders && w.big_spenders.length ? `<div class="muted small" style="margin-top:4px">Biggest spenders: ${w.big_spenders.map(m => `${esc(m.team)} $${m.spent} (${m.claims})`).join(" · ")}</div>` : ""}`;

  html += deckHead("Under the radar", w.gems.length, "players") + `<div class="muted small" style="margin:-4px 0 10px">Running backs, receivers and tight ends whose situation just changed, before their numbers catch up.</div>`;
  if (!w.gems.length) html += `<div class="card muted">Nobody available has enough evidence behind them this week.</div>`;
  html += `<div class="deck">`;
  for (const g of w.gems) {
    html += `<div class="card" id="gem-${g.id}"><div class="row">
      <div><b>${esc(g.name)}</b> <span class="muted">${esc(g.position)} · ${esc(g.team)}${g.opponent ? " vs " + esc(g.opponent) : ""}</span></div>
      <span class="pill accent">UPSIDE ${g.upside.toFixed(1)}</span></div>
      <div class="muted small">owned in ${g.owned}% of ESPN leagues${g.usage ? " · " + esc(g.usage) : ""}</div>${matchupLine(g)}
      <ul class="reasons">${g.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>
      ${g.note ? `<div class="quote">“${esc(g.note)}”${g.note_date ? `<div class="small" style="font-style:normal;margin-top:4px">— ${esc(g.note_date)}</div>` : ""}</div>` : ""}
      ${g.claim ? claimBlock(g.claim) : `<div class="muted small" style="margin-top:10px"><span class="pill">STASH</span> doesn't beat your players on today's numbers — a $${w.minimum_bid} bid if you have a spare bench spot.</div>`}</div>`;
  }
  html += `</div>`;

  html += deckHead("Best claims on today's numbers", w.claims.length, "claims");
  html += claimNotes(w);
  if (!w.claims.length) html += `<div class="card muted">No free agent adds at least half a point a week to your lineup.</div>`;
  html += `<div class="deck">`;
  for (const c of w.claims) {
    html += `<div class="card" id="waiver-${c.add.id}"><div class="row"><div><b>${esc(c.add.name)}</b>
      <span class="muted">${esc(c.add.position)} · ${esc(c.add.team)}</span>${c.add.injury ? ` <span class="pill warn">${esc(c.add.injury)}</span>` : ""}</div></div>
      ${claimBlock(c)}<ul class="reasons">${c.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul></div>`;
  }
  html += `</div>`;
  html += `<div class="muted small">Each claim assumes only that one move. After one goes through, refresh before relying on the next.</div>`;
  return html;
}

// ---------------------------------------------------------------- trades

function tradeCard(t, id) {
  const names = (list) => list.map(p => `<div style="font-weight:600">${esc(p.name)}${p.injury ? ` <span class="pill warn">${esc(p.injury)}</span>` : ""}</div>
    <div class="muted small">${esc(p.position)} · ${p.normal_week?.toFixed(1) ?? "–"} pts/wk</div>
    ${p.usage ? `<div class="muted small">${esc(p.usage)}</div>` : ""}
    ${p.situation ? `<div class="small accent-note">${esc(p.situation)} — those games no longer count toward his average</div>` : ""}
    ${p.playoffs ? `<div class="small ${p.playoff_bye ? "bad" : "muted"}">${esc(p.playoffs)}</div>` : ""}`).join("");
  const verdict = (n) => n >= 2 ? "good" : n >= 0.5 ? "good" : n > -0.5 ? "" : "bad";
  let lopsided = "";
  if (t.paper_get > 1.25 * t.paper_give) lopsided = `On paper you get ${t.paper_get} pts/wk of players for ${t.paper_give} — they may see it as lopsided, so explain why it helps them.`;
  else if (t.paper_give > 1.25 * t.paper_get) lopsided = `On paper you give ${t.paper_give} pts/wk of players for ${t.paper_get} — an easy yes for them; make sure it's worth it.`;
  const partner = t.partner_id != null
    ? `<button class="team-link" onclick="openRoster(${Number(t.partner_id)})" title="See ${esc(t.partner)}'s roster">${esc(t.partner)} ›</button>`
    : `<b style="color:var(--ink)">${esc(t.partner)}</b>`;
  return `<div class="card" ${id ? `id="${id}"` : ""}><div class="muted small">with ${partner}</div>
    <div class="swap" style="margin-top:8px"><div><span class="pill bad">GIVE</span>${names(t.give)}</div><div class="arrow">⇄</div><div><span class="pill good">GET</span>${names(t.get)}</div></div>
    <div class="row" style="margin-top:10px">
      <div><div class="muted small">You</div><div class="big ${verdict(t.my_gain_per_week)}">${signed(t.my_gain_per_week)}</div></div>
      <div style="text-align:right"><div class="muted small">Them</div><div class="big ${verdict(t.their_gain_per_week)}">${signed(t.their_gain_per_week)}</div></div></div>
    <div class="muted small">points per week to each best lineup</div>
    ${t.i_cut.length ? `<div class="muted small" style="margin-top:6px">You'd need to drop: ${esc(t.i_cut.join(", "))}</div>` : ""}
    ${t.they_cut.length ? `<div class="muted small" style="margin-top:6px">They'd need to drop: ${esc(t.they_cut.join(", "))}</div>` : ""}
    ${lopsided ? `<div class="warn small" style="margin-top:8px">${esc(lopsided)}</div>` : ""}
    ${readsBlock(t.perception)}</div>`;
}

// How the offer looks to the OTHER manager -- he compares points per game and
// knows his own holes, he does not run this program. Never part of the
// numbers above; it only decides whether the offer is worth sending.
function readsBlock(seen) {
  if (!seen) return "";
  const tone = seen.reads === "easy yes" ? "good" : seen.reads === "hard sell" ? "bad" : "warn";
  const fills = seen.fills.length
    ? seen.fills.map(f => `${esc(f.name)} fills their ${esc(f.position)} hole (${signed(f.need_per_week)}/wk)`).join(" · ")
    : "Fills no hole they can see.";
  return `<div class="reads">
    <div class="section-head" style="margin-bottom:6px"><span class="pill ${tone}">${esc(seen.reads.toUpperCase())}</span>
      <span class="muted small">how it reads to them</span></div>
    <div class="muted small">${fills}</div>
    <div class="pitch">“${esc(seen.pitch)}”</div></div>`;
}

function openRoster(teamId) {
  state.rosterTeam = teamId;
  render();
  scrollTo({ top: 0 });
}

function closeRoster(target) {
  state.rosterTeam = null;
  setTab(state.tab, target);
}

function tradeWith(teamId) {
  remember("partner", teamId);
  state.rosterTeam = null;
  setTab("trades", "checker");
}

// A player who costs nothing to lose reads better as "free" than as "-0.0".
const spareCost = (n) => n < 0.05 ? `<span class="good">free</span>` : `−${n.toFixed(1)}`;

const POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "D/ST"];

function renderRoster(d, team) {
  const inIdeas = new Map();
  d.trades.ideas.forEach((idea, n) => {
    if (idea.partner_id !== team.team_id) return;
    idea.get.forEach(p => inIdeas.set(p.id, n));
  });
  const byPosition = (list) => [...list].sort((a, b) =>
    (POSITION_ORDER.indexOf(a.position) - POSITION_ORDER.indexOf(b.position)) || ((b.normal_week || 0) - (a.normal_week || 0)));

  const row = (p) => {
    const idea = inIdeas.get(p.id);
    const flag = p.injury ? ` <span class="pill ${/out|reserve|suspension|doubtful/i.test(p.injury) ? "bad" : "warn"}">${esc(p.injury)}</span>` : "";
    return `<div class="player"><div class="who">
        <div class="name"><span class="pos-tag">${esc(p.position)}</span>${esc(p.name)}${flag}</div>
        <div class="muted small">${esc(p.team || "")}${p.ros_rank ? " · experts " + esc(p.ros_rank) : ""}${p.usage ? " · " + esc(p.usage) : ""}</div>
        ${p.situation ? `<div class="small accent-note">${esc(p.situation)}</div>` : ""}
        ${p.playoffs ? `<div class="small ${p.playoff_bye ? "bad" : "muted"}">${esc(p.playoffs)}</div>` : ""}
        ${idea !== undefined ? `<button class="team-link small" onclick="closeRoster('trade-${idea}')">In a trade idea ›</button>` : ""}
      </div><div class="pts">${p.normal_week?.toFixed(1) ?? "–"}<div class="muted small" style="font-weight:400">pts/wk</div></div></div>`;
  };
  const starters = byPosition(team.players.filter(p => p.starting));
  const bench = byPosition(team.players.filter(p => !p.starting && !p.on_ir));
  const ir = byPosition(team.players.filter(p => p.on_ir));

  return `<div class="narrow-inner" style="max-width:980px">
    <button class="back" onclick="closeRoster()">‹ Back</button>
    <div class="card"><div class="roster-head">
      <div><div class="name">${esc(team.name)}</div>
      <div class="muted small">${esc(team.record || "")}${team.standing ? ` · ${ordinal(team.standing)} place` : ""} · ${team.players.length} players</div></div>
      ${team.mine ? `<span class="pill accent">YOUR TEAM</span>` : `<button class="primary" onclick="tradeWith(${Number(team.team_id)})">Build a trade with them</button>`}</div></div>
    <h2>Starting lineup</h2><div class="card">${starters.length ? starters.map(row).join("") : `<div class="muted">No starters set.</div>`}</div>
    <h2>Bench</h2><div class="card">${bench.length ? bench.map(row).join("") : `<div class="muted">Empty bench.</div>`}</div>
    ${ir.length ? `<h2>Injured reserve</h2><div class="card">${ir.map(row).join("")}</div>` : ""}
    <div class="muted small">Points per week are what each player scores for their team in a normal week. Lineup is how they have it set on ESPN right now.</div>
  </div>`;
}

// Two things that are true of every claims list and easy to misread: the
// runners-up for a slot you can only fill once, and the fact that several
// claims spend the same roster spot.
function claimNotes(w) {
  const bits = [];
  if ((w.folded || []).length) {
    bits.push("More were close at " + w.folded.map(f =>
      `${esc(f.position)} (${f.count} more)`).join(", ")
      + " — claims at one position are alternatives for the same slot, not moves you can stack.");
  }
  (w.shared_drop || []).forEach(d => {
    bits.push(`${esc(d.name)} is the drop on ${d.count} of these — he can only be dropped once, so once a claim goes through, refresh before relying on the next.`);
  });
  return bits.length
    ? `<div class="muted small" style="margin:-4px 0 10px">${bits.join("<br>")}</div>`
    : "";
}

function renderTrades(d) {
  const t = d.trades;

  let html = `<div class="muted small" style="margin-top:4px">Trade deadline: ${esc(t.deadline || "none")} · Veto votes needed: ${esc(t.veto_votes ?? "–")}</div>`;
  html += renderNeeds(t.needs);
  html += deckHead("Trades that help both teams", t.ideas.length, "trades");
  if (!t.ideas.length) html += `<div class="card muted">No trade clearly helps both you and another team right now.</div>`;
  html += `<div class="deck">`;
  t.ideas.forEach((idea, n) => { html += tradeCard(idea, `trade-${n}`); });
  html += `</div>`;

  // Set aside rather than hidden: a trade whose whole gain sits at a spot the
  // waiver wire refills for free is a bad deal even when the maths likes it,
  // but you should still be able to see what was left out and why.
  const aside = t.set_aside || [];
  if (aside.length) {
    html += `<details class="aside"><summary>${aside.length} more that waivers can fix for free</summary>
      <div class="muted small" style="margin:8px 0">These improve both lineups, but everything you'd get plays a position you can refill off the wire for nothing — so you'd be paying a player for something a claim would buy.</div>
      <div class="deck">${aside.map((idea, n) => tradeCard(idea, `aside-${n}`)).join("")}</div></details>`;
  }

  const others = t.teams.filter(x => !x.mine), mine = t.teams.find(x => x.mine);
  const partner = Number(recall("partner")) || others[0]?.team_id;
  html += `<h2>Check a trade</h2><div class="card checker" id="checker">
    <select id="partner" style="width:100%;margin-bottom:12px">${others.map(x => `<option value="${x.team_id}" ${x.team_id === partner ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
    <div class="columns"><div><div class="muted small" style="margin-bottom:4px">You give</div>
      ${mine.players.map(p => `<label><input type="checkbox" name="give" value="${p.id}"><span class="who"><b>${esc(p.name)}</b> <span class="muted small">${esc(p.position)} · ${p.normal_week?.toFixed(1) ?? "–"}</span></span></label>`).join("")}</div>
    <div><div class="muted small" style="margin-bottom:4px">You get</div><div id="their-players"></div></div></div>
    <button class="primary" id="check" style="width:100%;margin-top:12px">Check this trade</button>
    <div id="check-result" style="margin-top:12px"></div></div>`;
  return html;
}

// The needs board: where my lineup leaks points, who I can spare for nothing,
// and which teams cross with mine in BOTH directions. This is the "where
// should I even be looking" half of the Trades tab; the decks below it are
// the answers.
function renderNeeds(n) {
  if (!n) return "";
  let html = "";

  html += `<h2>What I need</h2><div class="card">`;
  html += n.holes.length
    ? n.holes.map(h => `<div class="needrow"><b>${esc(h.position)}</b>
        <span class="muted small">an average ${esc(h.position)} here scores ${h.bar.toFixed(1)}${h.free_fix >= 0.1 && h.replacement ? ` · waivers already fix ${h.free_fix.toFixed(1)} of ${h.raw_need.toFixed(1)} — ${esc(h.replacement)} is free` : ""}</span>
        <span class="num bad">${signed(h.need_per_week)}</span></div>`).join("")
      + `<div class="muted small" style="margin-top:10px">Points a week a TRADE at each spot is worth — what an average starter would add, minus whatever the waiver wire already fixes for free. A hole the wire can fill is not worth paying a player for.${n.holes.some(h => h.position === "K" || h.position === "D/ST") ? " A kicker or defence hole is real, but it's a waiver fix, not a trade — nobody trades them." : ""}</div>`
    : `<div class="muted">Every spot is close to a league-average starter. Nothing worth trading for.</div>`;
  html += `</div>`;

  html += `<h2>What I can spare</h2><div class="card">`;
  html += n.spares.length
    ? n.spares.map(p => `<div class="needrow"><span class="pos-tag">${esc(p.position)}</span>
        <span><b>${esc(p.name)}</b> <span class="muted small">${p.normal_week?.toFixed(1) ?? "–"} pts/wk</span></span>
        <span class="num ${p.cost_per_week <= 0.5 ? "good" : ""}">${spareCost(p.cost_per_week)}</span></div>`).join("")
      + `<div class="muted small" style="margin-top:10px">What losing him would actually cost my lineup — the next man slides into his slot. Near zero means free to trade.</div>`
    : `<div class="muted">Nobody. Every player worth trading is holding a lineup spot.</div>`;
  html += `</div>`;

  html += deckHead("Offers built from what both sides can spare", n.ideas.length, "offers");
  html += n.ideas.length
    ? `<div class="deck">` + n.ideas.map((idea, i) => tradeCard(idea, `need-trade-${i}`)).join("") + `</div>`
    : `<div class="card muted">Nobody's spare depth lines up with anybody's hole right now.</div>`;
  if (n.partners.length) {
    html += deckHead("Who fits", n.partners.length, "teams");
    html += `<div class="deck">`;
    for (const p of n.partners) {
      const line = (list) => list.map(h => `${esc(h.position)} ${signed(h.need_per_week)}`).join(" · ");
      html += `<div class="card"><div class="section-head">
        <button class="team-link" onclick="openRoster(${Number(p.team_id)})">${esc(p.name)} ›</button>
        <span class="muted small">fit ${p.fit.toFixed(1)}</span></div>
        <div class="fitrow"><div class="muted small">They can fill for me</div><div>${line(p.they_fill)}</div></div>
        <div class="fitrow"><div class="muted small">I can fill for them</div><div>${line(p.i_fill)}</div></div>
        <div class="fitrow"><div class="muted small" style="margin-bottom:4px">They can spare</div>
          ${p.their_spares.map(sp => `<div class="needrow"><span class="pos-tag">${esc(sp.position)}</span>
            <span><b>${esc(sp.name)}</b> <span class="muted small">${sp.normal_week?.toFixed(1) ?? "–"} pts/wk</span></span>
            <span class="num ${sp.cost_per_week <= 0.5 ? "good" : ""}">${spareCost(sp.cost_per_week)}</span></div>`).join("")}</div>
        <button class="move" onclick="tradeWith(${Number(p.team_id)})">Build a trade with them ›</button></div>`;
    }
    html += `</div><div class="muted small" style="margin:-2px 0 10px">Only teams that cross with mine in both directions — they have depth at a spot I'm leaking points at, and I have depth at one of theirs. One direction alone is a request, not an offer.</div>`;
  }

  return html;
}

function wireTrades(d) {
  if (state.rosterTeam != null) return;
  const partnerSelect = $("#partner");
  if (!partnerSelect) return;
  const fill = () => {
    remember("partner", partnerSelect.value);
    const others = d.trades.teams.filter(x => !x.mine);
    const team = others.find(x => x.team_id === Number(partnerSelect.value)) || others[0];
    if (!team) return;
    $("#their-players").innerHTML = team.players.map(p =>
      `<label><input type="checkbox" name="get" value="${p.id}"><span class="who"><b>${esc(p.name)}</b> <span class="muted small">${esc(p.position)} · ${p.normal_week?.toFixed(1) ?? "–"}</span></span></label>`).join("");
    $("#check-result").innerHTML = "";
  };
  partnerSelect.onchange = fill;
  fill();
  $("#check").onclick = async () => {
    const picked = (name) => [...document.querySelectorAll(`input[name=${name}]:checked`)].map(x => Number(x.value));
    const button = $("#check");
    button.disabled = true; button.textContent = "Checking…";
    try {
      const result = await api("/api/trade-check", { league_id: state.leagueId, give: picked("give"), get: picked("get") });
      $("#check-result").innerHTML = result.error ? `<div class="bad">${esc(result.error)}</div>` : tradeCard(result);
    } finally { button.disabled = false; button.textContent = "Check this trade"; }
  };
}



// ---------------------------------------------------------------- scoreboard

async function loadScoreboard(force) {
  if (!state.leagueId) return;
  const fresh = state.scoreboardFor === state.leagueId && Date.now() - state.scoreboardAt < 55000;
  if (fresh && !force) return;
  try {
    const board = await api(`/api/scoreboard/${state.leagueId}`);
    state.scoreboard = board; state.scoreboardFor = state.leagueId; state.scoreboardAt = Date.now();
    if (state.tab === "home" && state.rosterTeam == null) {
      const slot = document.getElementById("scoreboard");
      if (slot) slot.outerHTML = renderScoreboard();
    }
  } catch (e) { /* the rest of the page does not depend on it */ }
}

function boxRows(side) {
  const label = { final: "final", live: "playing", upcoming: "to play", bye: "bye" };
  const row = (r) => `<div class="box-row"><span class="slot">${esc(r.starting ? r.slot : "BE")}</span>
    <span class="nm">${esc(r.name)}<span class="small state-${r.state}"> · ${r.state === "live" ? '<span class="live-dot"></span>' : ""}${label[r.state]}${r.opponent ? " vs " + esc(r.opponent) : ""}</span></span>
    <span class="p">${r.points.toFixed(1)}<small>proj ${r.projected.toFixed(1)}</small></span></div>`;
  const starters = side.players.filter(r => r.starting), bench = side.players.filter(r => !r.starting);
  return `<div><div style="font-weight:700;margin-bottom:4px">${esc(side.team)}</div>${starters.map(row).join("")}
    ${bench.length ? `<div class="muted small" style="margin-top:8px">Bench</div>${bench.map(row).join("")}` : ""}</div>`;
}

function renderScoreboard() {
  const b = state.scoreboardFor === state.leagueId ? state.scoreboard : null;
  if (!b || b.loading) return `<div id="scoreboard"><h2>This week's matchup</h2><div class="card muted">Loading the scoreboard…</div></div>`;
  if (b.error) return `<div id="scoreboard"><h2>This week's matchup</h2><div class="card muted">${esc(b.error)}</div></div>`;
  if (b.bye) return `<div id="scoreboard"><h2>Week ${b.week}</h2><div class="card muted">No matchup this week.</div></div>`;
  const me = b.me, them = b.them;
  const ahead = me.score > them.score ? "good" : me.score < them.score ? "bad" : "";
  const liveNow = me.playing + them.playing > 0;
  const status = b.finished ? "Final" : liveNow ? `<span class="live-dot"></span>Live` : "Not started";
  const stillToPlay = (v) => v.yet_to_play + v.playing ? `${v.yet_to_play + v.playing} left to play · ` : "";
  return `<div id="scoreboard"><div class="deck-head"><h2>Week ${b.week} scoreboard</h2><span class="deck-count">${status} · updated ${esc(b.checked_at)}</span></div>
    <div class="card">
      <div class="score">
        <div class="side"><div class="team">${esc(me.team)} <span class="muted small">(you)</span></div>
          <div class="pts ${ahead}">${me.score.toFixed(1)}</div>
          <div class="sub">${stillToPlay(me)}${b.finished ? "" : "on pace " + me.live_projection.toFixed(1)}</div></div>
        <div class="vs">VS</div>
        <div class="side them"><div class="team">${them.team_id != null ? `<button class="team-link" onclick="openRoster(${Number(them.team_id)})">${esc(them.team)}</button>` : esc(them.team)}</div>
          <div class="pts">${them.score.toFixed(1)}</div>
          <div class="sub">${stillToPlay(them)}${b.finished ? "" : "on pace " + them.live_projection.toFixed(1)}</div></div>
      </div>
      <details class="box"><summary>Player-by-player ›</summary><div class="box-grid">${boxRows(me)}${boxRows(them)}</div></details>
    </div></div>`;
}

// ---------------------------------------------------------------- guide

function renderGuide() {
  const section = (title, job, items) => `<h2>${title}</h2><div class="card"><div class="job">${job}</div>
    <dl>${items.map(([t, d]) => `<div><dt>${t}</dt><dd>${d}</dd></div>`).join("")}</dl></div>`;
  return `<div class="guide">
    <h2>How this works</h2>
    <div class="card"><div>This reads your three ESPN leagues and recommends moves. It can't change anything on ESPN — you always make the move in the ESPN app.</div>
      <div class="muted small" style="margin-top:8px">Open it on this network at <code>${esc(location.host)}</code>. Your Mac must be on and awake.</div></div>
    ${section("Team", "Where you stand, and what to fix first", [
      ["Live scoreboard", "This week's score against your opponent, who's still to play, where each team is on pace to finish, and a player-by-player view. Refreshes every minute."],
      ["My roster", "Your whole roster — starters, bench and injured reserve. Tap your opponent's name on the scoreboard to see theirs."],
      ["How you're doing", "Last week's score and how it ranked in the league, your record, standing, and ESPN's playoff odds."],
      ["This week's win chance", "Your projected score against your opponent's, and whether you're the favorite, underdog or it's a toss-up."],
      ["Strengths &amp; weaknesses", "A bar for each position showing if your starters are better or worse than the league's typical team."],
      ["What to do about it", "Under each weakness: pickups and trades that fix it. Under each strength: trades that turn extra depth into help where you're weak. Tap one to see the details."],
    ])}
    ${section("Start/Sit", "Who to play this week", [
      ["Best lineup", "Built from ESPN's and the experts' projections averaged, with flex spots handled correctly. Changes worth less than half a point aren't suggested."],
      ["Close calls", "If a bench player is within 1.5 points of a starter: as the underdog, lean to the player with bigger big weeks; as the favorite, lean to the steadier one."],
      ["“Questionable” players", "Reads practice reports — a full practice on Friday is very different from none all week."],
      ["Lock countdowns", "Each player locks when his own game kicks off, so Thursday players are decided first."],
    ])}
    ${section("Waivers", "Who to add, who to drop, and what to bid", [
      ["Under the radar", "Running backs, receivers and tight ends whose situation just changed before their stats caught up: a teammate newly hurt, snaps jumping, managers rushing to add him, lots of chances near the end zone."],
      ["Recommended claims", "For each free agent: the best player of yours to drop, and how many points a week the swap adds to your lineup for the rest of the season."],
      ["What to bid", "A suggested FAAB bid. Once your league has five claims above the minimum bid, it adjusts to what winning claims actually cost there."],
    ])}
    ${section("Trades", "Trades that help both sides — the ones that get accepted", [
      ["Why only one or two claims per position", "Claims at the same position are alternatives for one lineup slot, not moves you can stack — six quarterbacks in a row is one decision with five runners-up. The best one or two at each position are shown and the rest are counted under the list, so a running back who would actually change your season isn't buried under kickers."],
      ["Trade ideas", "One-for-one and two-for-one trades with every team that improve both lineups. A trade whose whole gain sits at a position you could refill off the waiver wire for free is set aside under \"waivers can fix for free\" — it's still shown, just not sold to you, because a claim costs nothing and a trade costs a player."],
      ["What I need", "Points a week your best lineup leaks at each spot — what one league-average starter there would add. Not \"you only have two running backs\": a hole is only a hole if it is costing you points."],
      ["What I can spare", "What losing a player would actually cost you, once the next man slides into his slot. A fourth receiver on a team that starts three is worth about nothing to you and possibly a lot to someone else."],
      ["Who fits", "Teams that cross with yours in both directions — they can spare someone at a spot you're leaking points at, and you can spare someone at one of theirs. One direction alone is a request, not an offer."],
      ["Games that no longer count", "A receiver's past games only count as evidence if the same quarterback was throwing. When his team is about to start someone else — an injured starter back, or a change under centre — those games stop counting toward his average and his value leans on the projections instead. You'll see the reason on the player (\"2 of 2 games thrown by C.Rush, not Michael Penix Jr.\") so you can check it. It cuts both ways: a hot start with the backup is discounted too. Running backs are left alone, because carries arrive whoever is under centre."],
      ["How it reads to them", "The other manager doesn't run this program: he compares points per game and knows his own holes. EASY YES, NEEDS A PITCH or HARD SELL is how the offer looks to him, plus the line to send. It never changes whether a trade is good for you — only whether it's worth sending."],
      ["Trade checker", "Tick players on each side to see points per week gained or lost, for you and for them."],
      ["Their roster", "Tap the other team's name on any trade to see their whole roster, and start a trade with them from there."],
      ["Looks lopsided?", "A warning when a fair trade will look unfair by name, so you know to explain why it helps them."],
      ["Playoff schedule", "Each player's opponents in weeks 15–17, with a warning for a bye during your playoffs."],
    ])}
    <h2>The information behind it</h2>
    <div class="card"><table><tbody>
      ${[["Projections", "ESPN and FantasyPros experts, averaged — this week and rest of season"],
         ["Snaps &amp; targets", "How much a player is really on the field and getting the ball"],
         ["Red-zone looks", "Who gets the ball inside the 20, where touchdowns happen"],
         ["Consistency", "Steady week to week, or boom-or-bust"],
         ["Defense matchup", "Points this week's opponent allows to that position (green = soft, red = tough)"],
         ["Betting lines", "How many points each NFL team is expected to score"],
         ["Weather", "Wind 15+ mph, likely rain, or bitter cold at outdoor games"],
         ["League bids", "What winning waiver claims cost in your league"],
         ["Practice reports", "Full, limited or no practice for injured players"]]
        .map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join("")}
    </tbody></table></div>
    <h2>Ground rules</h2>
    <div class="card"><dl>
      <div><dt>Numbers decide, opinions are shown</dt><dd>News and expert quotes appear word for word, but only hard facts change a recommendation.</dd></div>
      <div><dt>Nothing counts twice</dt><dd>Matchups and weather are already in the projections, so they're shown as extra context, not added again.</dd></div>
      <div><dt>It says when data is thin</dt><dd>Early in the season it waits for enough games before labeling a matchup or schedule.</dd></div>
    </dl></div>
    <h2>Running it yourself</h2>
    <div class="card"><div class="muted small" style="margin-bottom:6px">From the fantasy-assistant folder in Terminal — or ask Claude to run any of these.</div>
      ${[["app.py", "Start this app"], ["team_report.py", "Team check-up as a text report"],
         ["start_sit.py --lock", "Last-minute check before kickoff"], ["waiver_wire.py", "Waiver pickups, drops and bids"],
         ["trade_finder.py", "Trade ideas (add --give / --get to check one)"]]
        .map(([c, d]) => `<div class="cmd"><code>.venv/bin/python ${c}</code><span class="muted small">${d}</span></div>`).join("")}
      <div class="muted small" style="margin-top:10px">If it stops finding your leagues, your ESPN login values in .env have expired and need re-copying from your browser.</div>
    </div>
  </div>`;
}

// ---------------------------------------------------------------- render

function render() {
  const main = $("#main");
  if (state.tab === "guide") { main.innerHTML = renderGuide(); main.classList.add("narrow-page"); return; }
  if (!state.data) {
    main.innerHTML = `<div class="loading"><div class="spinner"></div>Working out this league for the first time.<br>This takes a minute or two.</div>`;
    return;
  }
  const d = state.data;
  const views = { home: renderHome, lineup: renderLineup, waivers: renderWaivers, trades: renderTrades };
  const rosterTeam = state.rosterTeam != null && d.trades.teams.find(x => x.team_id === state.rosterTeam);
  if (rosterTeam) { main.innerHTML = renderRoster(d, rosterTeam); main.classList.add("narrow-page"); return; }
  state.rosterTeam = null;
  main.innerHTML = views[state.tab](d);
  main.classList.toggle("narrow-page", state.tab === "lineup");
  if (state.tab === "trades") wireTrades(d);
}

document.querySelectorAll("nav button").forEach(b => b.onclick = () => { state.rosterTeam = null; setTab(b.dataset.tab); });
$("#league").onchange = () => { state.rosterTeam = null; state.leagueId = Number($("#league").value); remember("league", state.leagueId); state.data = null; showFreshness(); render(); loadLeague(); };
$("#refresh").onclick = async () => { state.leagues = await api("/api/refresh", { league_id: state.leagueId }); showFreshness(); };

(async () => {
  state.tab = recall("tab") || "home";
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.tab === state.tab));
  document.documentElement.style.setProperty("--header-h", $("#header").offsetHeight + "px");
  await loadLeagues();
  await loadLeague();
  state.poll = setInterval(tick, 5000);
})();
</script>
</body>
</html>
"""
